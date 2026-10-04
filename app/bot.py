import hmac
import re
import secrets
import time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.ai import CommandInterpreter
from app.domain import PreparedInvoice, StrictModel, UserProblem, WorkflowFailure
from app.http import ExternalFailure
from app.service import InvoiceService, event
from app.telegram import DeliveryFailure, Telegram
from app.telegram_models import CallbackQuery, InlineButton, InlineKeyboardMarkup, Message
from app.voice import SpeechToText


class Receipt(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", validate_assignment=True)
    attempts: int = 0
    done: bool = False
    fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    prepared: PreparedInvoice | None = None
    response_text: str | None = None
    response_markup: InlineKeyboardMarkup | None = None


class Pending(StrictModel):
    token: str = Field(pattern=r"^[a-f0-9]{32}$")
    prepared: PreparedInvoice
    expires_at: float


class CallbackAction(StrictModel):
    action: Literal["confirm", "cancel"]
    token: str = Field(pattern=r"^[a-f0-9]{32}$")


class ConfirmationPrompt(StrictModel):
    text: str
    reply_markup: InlineKeyboardMarkup


class DeliveredInvoice(StrictModel):
    telegram_user_id: int = Field(gt=0)
    operation_id: str = Field(pattern=r"^[a-f0-9]{64}$")


def failure_text(exc: WorkflowFailure) -> str:
    if exc.stage == "resolve":
        return "Не удалось получить данные 1С. Создание документа не запускалось. Повторите позже."
    if exc.stage == "write_disabled":
        return "Запись в настоящую 1С отключена. Обратитесь к оператору."
    if exc.stage == "stale":
        return "Данные 1С изменились. Запись остановлена; нужен разбор оператором. /retry проверит прежнюю операцию без нового поиска компании."
    if exc.state == "posted":
        return f"Документ {exc.document_id} проведён, но PDF не получен или не доставлен. Отправьте /retry."
    if exc.state == "draft":
        return f"Документ {exc.document_id} создан; проведение не завершено. Отправьте /retry для восстановления."
    if exc.state == "not_started":
        return "1С подтвердила, что операция не началась. /retry сначала проверит её состояние заново."
    return "Результат операции неизвестен: документ мог быть создан. Новую запись не выполняем. /retry проверит фактическое состояние прежней операции."


class Bot:
    def __init__(self, service: InvoiceService, telegram: Telegram, interpreter: CommandInterpreter,
                 speech: SpeechToText | None = None):
        self.service, self.telegram, self.interpreter = service, telegram, interpreter
        self.speech = speech
        # One pending command per authorized user; no transcripts, audio or PDF stored.
        self.pending: dict[int, Pending] = {}
        self.recoveries: dict[int, PreparedInvoice] = {}
        # The webhook receipt limit also bounds this set within one process.
        self.delivered: set[DeliveredInvoice] = set()
        self.delivery_attempted: set[DeliveredInvoice] = set()

    def prepare_callback(self, callback: CallbackQuery) -> PreparedInvoice | str:
        uid = callback.sender.id
        parts = callback.data.split(":")
        try:
            if len(parts) != 3 or parts[0] != "invoice":
                raise ValueError("Unexpected callback")
            action = CallbackAction(action=parts[1], token=parts[2])
        except (ValueError, ValidationError):
            raise UserProblem("Кнопка недействительна. Пришлите команду заново.") from None
        pending = self.pending.get(uid)
        if (pending is None or time.monotonic() > pending.expires_at
                or not hmac.compare_digest(action.token, pending.token)):
            raise UserProblem("Подтверждение устарело. Пришлите команду заново.")
        self.pending.pop(uid)
        if action.action == "cancel":
            return "Команда отменена. Документ не создавался."
        return pending.prepared

    async def prepare(self, message: Message | CallbackQuery,
                      request_id: str) -> PreparedInvoice | ConfirmationPrompt | str:
        if isinstance(message, CallbackQuery):
            return self.prepare_callback(message)
        uid = message.sender.id
        pending = self.pending.get(uid)
        if pending is not None and time.monotonic() > pending.expires_at:
            self.pending.pop(uid)
        is_voice = message.voice is not None
        if is_voice:
            if self.speech is None:
                raise UserProblem("Сейчас доступен только текст. Пришлите команду с месяцем и годом.")
            if message.text is not None:
                raise UserProblem("Пришлите отдельно текст или голосовое сообщение.")
            try:
                event(request_id=request_id, user_id=uid, stage="download", status="started")
                audio = await self.telegram.download_voice(message.voice)
                event(request_id=request_id, user_id=uid, stage="stt", status="started")
                transcript = await self.speech.transcribe(audio)
                event(request_id=request_id, user_id=uid, stage="stt", status="success")
            except ExternalFailure as exc:
                event(request_id=request_id, user_id=uid, stage="voice", status="error", error=exc.code)
                raise
            text = transcript.text
        elif message.text is not None:
            text = message.text
        else:
            raise UserProblem("Пришлите текст или голосовое сообщение с командой создания счёта.")
        if not is_voice and text in ("/start", "/help"):
            return ("Создание стандартного счёта по данным 1С.\n"
                    "Пример: Сформируй счёт для ООО Ромашка за сентябрь 2026\n"
                    "Укажите клиента, месяц и год. Голос и свободные формулировки требуют подтверждения.\n"
                    "Подтверждение и отмена доступны кнопками под запросом.\n"
                    "Сейчас тестовый режим: отправляем демонстрационный PDF, реальные счета не создаём.")
        if not is_voice and text == "/cancel":
            self.pending.pop(uid, None)
            return "Ожидающая подтверждения команда отменена."
        if not is_voice and text == "/retry":
            if uid not in self.recoveries:
                return "Нет незавершённой операции для восстановления."
            return self.recoveries[uid]
        if uid in self.recoveries:
            raise UserProblem("Сначала восстановите предыдущую операцию командой /retry. Новый счёт пока не создаём.")
        if not is_voice and text.startswith("/confirm"):
            match = re.fullmatch(r"/confirm ([a-f0-9]{32})", text)
            pending = self.pending.get(uid)
            if (not match or pending is None or time.monotonic() > pending.expires_at
                    or not hmac.compare_digest(match[1], pending.token)):
                raise UserProblem("Подтверждение недействительно или истекло. Пришлите команду заново.")
            self.pending.pop(uid)
            return pending.prepared
        event(request_id=request_id, user_id=uid, stage="interpret", status="started")
        interpretation = await self.interpreter.interpret(text)
        prepared = await self.service.prepare(interpretation.command, request_id, uid)
        event(request_id=request_id, user_id=uid, stage="interpret", status="success")
        if not interpretation.needs_confirmation and not is_voice:
            self.pending.pop(uid, None)
            return prepared
        pending = Pending(token=secrets.token_hex(16), prepared=prepared, expires_at=time.monotonic() + 300)
        self.pending[uid] = pending
        return ConfirmationPrompt(
            text=(f"Проверьте распознанную команду:\nКлиент из 1С: {prepared.display_name}\n"
                  f"Период: {prepared.request.month:02d}.{prepared.request.year}\n"
                  "Создать и провести стандартный счёт по данным 1С?\n"
                  "Выберите действие в течение 5 минут. Сейчас включён тестовый режим 1С."),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineButton(text="Подтвердить", callback_data=f"invoice:confirm:{pending.token}"),
                InlineButton(text="Отмена", callback_data=f"invoice:cancel:{pending.token}"),
            ]]),
        )

    async def handle(self, message: Message | CallbackQuery, receipt: Receipt, request_id: str) -> None:
        uid = message.sender.id
        stage = "interpret"
        try:
            if receipt.response_text is None:
                if receipt.prepared is None:
                    prepared = await self.prepare(message, request_id)
                    if isinstance(prepared, ConfirmationPrompt):
                        receipt.response_text = prepared.text
                        receipt.response_markup = prepared.reply_markup
                    elif isinstance(prepared, str):
                        receipt.response_text = prepared
                    else:
                        # Freeze interpretation BEFORE any financial operation. A Telegram
                        # redelivery never runs STT/LLM again or selects a different command.
                        receipt.prepared = PreparedInvoice.model_validate(prepared)
                if receipt.prepared is not None:
                    delivery = DeliveredInvoice(telegram_user_id=uid,
                                                operation_id=receipt.prepared.operation_id)
                    if delivery in self.delivered:
                        event(request_id=request_id, user_id=uid, stage="delivery", status="duplicate",
                              operation_id=delivery.operation_id)
                        receipt.prepared = None
                        receipt.response_text = "Этот счёт уже отправлен вам. Второй PDF не отправляем."
                    elif delivery in self.delivery_attempted:
                        event(request_id=request_id, user_id=uid, stage="delivery", status="unconfirmed",
                              operation_id=delivery.operation_id)
                        receipt.prepared = None
                        receipt.response_text = (
                            "Не удалось подтвердить доставку PDF: файл мог быть отправлен. "
                            "Второй раз автоматически не отправляем. Проверьте чат и обратитесь к оператору."
                        )
                    else:
                        stage = "invoice"
                        result = await self.service.execute(receipt.prepared, request_id, uid)
                        stage = "delivery"
                        # Telegram has no idempotency key for sendDocument. A lost response
                        # leaves delivery unknown, so a retry must not send another PDF.
                        self.delivery_attempted.add(delivery)
                        await self.telegram.send_pdf(uid, result.pdf.content)
                        self.delivered.add(delivery)
                        self.recoveries.pop(uid, None)
                        event(request_id=request_id, user_id=uid, stage=stage, status="success",
                              document_id=result.invoice.document_id)
                        return
        except UserProblem as exc:
            event(request_id=request_id, user_id=uid, stage=stage, status="clarification")
            receipt.response_text = str(exc)
        except WorkflowFailure as exc:
            if receipt.prepared is not None:
                self.recoveries[uid] = receipt.prepared
            receipt.response_text = failure_text(exc)
        except DeliveryFailure:
            if receipt.prepared is not None:
                self.recoveries[uid] = receipt.prepared
            raise
        except ExternalFailure as exc:
            event(request_id=request_id, user_id=uid, stage=stage, status="error", error=exc.code)
            receipt.response_text = "Не удалось безопасно распознать команду. Документ не создавался. Пришлите текст с клиентом, месяцем и годом."
        if receipt.response_text is not None:
            await self.telegram.send_text(uid, receipt.response_text, receipt.response_markup)
