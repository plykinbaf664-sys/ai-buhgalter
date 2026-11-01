import asyncio
import hmac
from decimal import Decimal
import re
import secrets
import time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.ai import CommandInterpreter
from app.domain import (ClientCandidate, ClientCandidates, ClientChoiceRequired, InvoiceCommand, PreparedInvoice, ResolvedClient,
                        ServiceCandidates, ServiceChoiceRequired,
                        InitialQuantityRequired,
                        Label, ServiceProblem, ServiceSelection, StrictModel, UserProblem, WorkflowFailure)
from app.http import ExternalFailure
from app.service import InvoiceService, event, safe_backend_error
from app.telegram import DeliveryFailure, Telegram
from app.telegram_models import CallbackQuery, InlineButton, InlineKeyboardMarkup, Message
from app.voice import SpeechToText, UncertainTranscript
from app.intent import InvoiceDraft, InvoiceIntent, IntentPreviewChange, merge_intent
from app.domain import PreviewTaxRequest
from app.numbers import explicit_decimal, explicit_tax_rate
from app.language import explicit_line_target, normalize_request_text, company_search_phrase, service_refinement_phrase
from app.presentation import message_chunks, preview_text
from app.parser import HELP


class Receipt(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", validate_assignment=True)
    attempts: int = 0
    done: bool = False
    fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    prepared: PreparedInvoice | None = None
    response_text: str | None = None
    response_markup: InlineKeyboardMarkup | None = None
    response_sent: int = 0


class Pending(StrictModel):
    token: str = Field(pattern=r"^[a-f0-9]{32}$")
    prepared: PreparedInvoice
    expires_at: float


class PendingClientChoice(StrictModel):
    token: str = Field(pattern=r"^[a-f0-9]{32}$")
    command: InvoiceCommand | None = None
    draft: InvoiceDraft | None = None
    choices: ClientCandidates
    expires_at: float

    @model_validator(mode="after")
    def one_request(self):
        if (self.command is None) == (self.draft is None):
            raise ValueError("Choice requires exactly one command or discovery draft")
        if self.draft is not None and self.draft.client is None:
            raise ValueError("Discovery requires a literal name query")
        return self


class PendingServiceChoice(StrictModel):
    token: str = Field(pattern=r"^[a-f0-9]{32}$")
    command: InvoiceCommand
    line_number: int = Field(ge=1, le=20)
    choices: ServiceCandidates
    expires_at: float


class PendingInitialQuantity(StrictModel):
    token: str = Field(pattern=r"^[a-f0-9]{32}$")
    command: InvoiceCommand
    line_number: int = Field(ge=1, le=20)
    expires_at: float


class CallbackAction(StrictModel):
    action: Literal["confirm", "edit", "cancel"]
    token: str = Field(pattern=r"^[a-f0-9]{32}$")


class ConfirmationPrompt(StrictModel):
    text: str
    reply_markup: InlineKeyboardMarkup


class SupplierReviewScope(StrictModel):
    client_id: Label
    contract_id: Label
    source_entity_id: Label
    contract_entity_id: Label

    @classmethod
    def from_prepared(cls, prepared: PreparedInvoice):
        source = prepared.preview.historical_proposal
        if source is None or source.contract_entity_id is None:
            return None
        return cls(client_id=prepared.request.client_id, contract_id=source.contract_id,
                   source_entity_id=source.entity_id, contract_entity_id=source.contract_entity_id)


class DraftContext(StrictModel):
    draft: InvoiceDraft
    command: InvoiceCommand | None = None
    prepared: PreparedInvoice | None = None
    selected_client_id: str | None = Field(default=None, min_length=1, max_length=200)
    supplier_review: SupplierReviewScope | None = None
    require_client_choice: bool = False
    selected_service_ids: dict[int, str] = Field(default_factory=dict)


class DeliveredInvoice(StrictModel):
    telegram_user_id: int = Field(gt=0)
    operation_id: str = Field(pattern=r"^[a-f0-9]{64}$")


def failure_text(exc: WorkflowFailure) -> str:
    if exc.stage.startswith('tax_'):
        return (f'Исходный Invoice {exc.document_id} уже записан. '
                'Связанный Tax Invoice или его PDF пока не подтверждены. '
                '/retry сверит ту же операцию с 1С; повторное создание вслепую запрещено.')
    if exc.stage == "resolve":
        return "Не удалось получить данные 1С. Создание документа не запускалось. Повторите чтение командой /retry — наговаривать запрос заново не нужно."
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
        # Unconfirmed conversations remain process-local. An optional private
        # journal restores only already-confirmed operations and PDF delivery.
        self.pending: dict[int, Pending] = {}
        self.client_choices: dict[int, PendingClientChoice] = {}
        self.service_choices: dict[int, PendingServiceChoice] = {}
        self.initial_quantities: dict[int, PendingInitialQuantity] = {}
        self.supplier_reviews: dict[int, Pending] = {}
        self.contexts: dict[int, DraftContext] = {}
        self.last_contexts: dict[int, DraftContext] = {}
        self.recoveries: dict[int, PreparedInvoice] = (
            service.journal.recoveries() if service.journal is not None else {})
        # The webhook receipt limit also bounds this set within one process.
        self.delivered: dict[DeliveredInvoice, PreparedInvoice] = {}
        self.delivery_attempted: set[DeliveredInvoice] = set()

    def show_preview(self, uid: int, prepared: PreparedInvoice, command: InvoiceCommand,
                     notice: str = "") -> ConfirmationPrompt:
        previous_context = self.contexts.get(uid)
        selected_id = (previous_context.selected_client_id if previous_context is not None
                       and previous_context.draft.client == command.client else None)
        supplier_review = (previous_context.supplier_review if previous_context is not None
                           and previous_context.draft.client == command.client else None)
        command = InvoiceCommand.model_validate({**command.model_dump(),
            "initial_overrides": (),
            "preview_overrides": prepared.preview.user_overrides,
            "invoice_date": prepared.preview.invoice_date, "legacy_period": prepared.request.legacy_period,
            "service_period": prepared.request.service_period,
            "year": prepared.request.year, "month": prepared.request.month,
            "services": tuple(ServiceSelection(query=line.description, quantity=line.quantity)
                              for line in prepared.preview.lines)})
        self.contexts[uid] = DraftContext(draft=InvoiceDraft.from_command(command), command=command,
                                         prepared=prepared, selected_client_id=selected_id,
                                         supplier_review=supplier_review)
        scope = SupplierReviewScope.from_prepared(prepared)
        if scope is not None and scope != supplier_review:
            self.pending.pop(uid, None)
            pending_review = Pending(token=secrets.token_hex(16), prepared=prepared, expires_at=time.monotonic() + 300)
            self.supplier_reviews[uid] = pending_review
            source = prepared.preview.historical_proposal
            return ConfirmationPrompt(text=notice + (
                f"Компания: {prepared.preview.recipient.name}\n"
                f"Нашёл счёт №{source.source_number} от {source.source_date:%d.%m.%Y}.\n\n"
                f"Поставщик в этом счёте: {prepared.preview.issuer.name}\n"
                f"В текущем договоре: {source.contract_entity_name}\n\n"
                "Организации различаются. Показать образец по историческому счёту? "
                + ("Это не выбирает организацию для записи нового документа."
                   if self.service.readonly_preview(prepared) else
                   "В новом счёте будет поставщик из исторического образца. "
                   "Проверьте его в preview перед окончательным подтверждением.")),
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                    InlineButton(text="Показать образец из истории", callback_data=f"supplier:{pending_review.token}:accept"),
                    InlineButton(text="Отмена", callback_data=f"supplier:{pending_review.token}:cancel")]]))
        self.supplier_reviews.pop(uid, None)
        pending = Pending(token=secrets.token_hex(16), prepared=prepared, expires_at=time.monotonic() + 300)
        self.pending[uid] = pending
        readonly = self.service.readonly_preview(prepared)
        mode = ("\nREAD-ONLY: документ не создан. Запись, проведение и PDF отключены."
                if readonly else "\nTEST / MOCK: реальные счета в 1С не создаются." if self.service.onec.is_fake is True else "")
        if not readonly and getattr(self.service.onec, 'requires_tax_invoice', False) is True:
            mode += '\nПодтверждение: Invoice → связанный Tax Invoice → штатный Tax Invoice (EN, landscape) PDF.'
        return ConfirmationPrompt(text=notice + preview_text(prepared.preview) + mode,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineButton(text="Проверить preview" if readonly else "Создать черновик в 1С"
                    if getattr(self.service.onec, "posting_enabled", True) is False else "Подтвердить", callback_data=f"invoice:confirm:{pending.token}"),
                InlineButton(text="Изменить", callback_data=f"invoice:edit:{pending.token}"),
                InlineButton(text="Отмена", callback_data=f"invoice:cancel:{pending.token}"),
            ]]))

    async def review_supplier(self, callback: CallbackQuery, request_id: str):
        uid = callback.sender.id
        if uid in self.recoveries:
            raise UserProblem("Сначала восстановите операцию командой /retry.")
        match = re.fullmatch(r"supplier:([a-f0-9]{32}):(accept|cancel)", callback.data)
        pending = self.supplier_reviews.get(uid)
        if (not match or pending is None or time.monotonic() > pending.expires_at
                or not hmac.compare_digest(match[1], pending.token)):
            raise UserProblem("Выбор образца устарел. Пришлите запрос заново.")
        self.supplier_reviews.pop(uid)
        if match[2] == "cancel":
            self.contexts.pop(uid, None)
            return "Запрос отменён. Документ не создавался."
        refreshed = await self.service.refresh(pending.prepared, request_id, uid)
        context = self.contexts[uid]
        if refreshed != pending.prepared:
            return self.show_preview(uid, refreshed, context.command, "Данные 1С изменились. Проверьте обновлённый источник.\n\n")
        scope = SupplierReviewScope.from_prepared(refreshed)
        self.contexts[uid] = DraftContext(**{**context.model_dump(), "supplier_review": scope})
        event(request_id=request_id, user_id=uid, stage="supplier_review", status="accepted")
        return self.show_preview(uid, refreshed, context.command)

    def show_client_choices(self, uid: int, command: InvoiceCommand | None, choices: ClientCandidates,
                            *, draft: InvoiceDraft | None = None) -> ConfirmationPrompt:
        pending = PendingClientChoice(token=secrets.token_hex(16), command=command,
                                      draft=draft, choices=choices, expires_at=time.monotonic() + 300)
        self.client_choices[uid] = pending
        self.pending.pop(uid, None)
        text = ["Выберите компанию из найденных вариантов:"]
        buttons = []
        for index, candidate in enumerate(choices.candidates, 1):
            text.append(f"{index}. {candidate.full_name} · {candidate.client_id[-8:]}"
                        + (f"\nTRN: {candidate.tax_number}" if candidate.tax_number else "\nTRN не заполнен"))
            buttons.append([InlineButton(text=f"{index}. {candidate.display_name[:40]} · {candidate.client_id[-8:]}",
                                          callback_data=f"client:{pending.token}:{index}")])
        text.append("Остальные параметры запроса сохранены. Состав и цена будут проверены после выбора. "
                    "Если нужной записи нет, напишите или наговорите другую часть названия.")
        buttons.append([InlineButton(text="Отмена", callback_data=f"client:{pending.token}:cancel")])
        return ConfirmationPrompt(text="\n\n".join(text), reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

    async def choose_client(self, callback: CallbackQuery, request_id: str):
        uid = callback.sender.id
        if uid in self.recoveries:
            raise UserProblem("Сначала восстановите операцию командой /retry.")
        match = re.fullmatch(r"client:([a-f0-9]{32}):([1-9]|1[0-9]|cancel)", callback.data)
        pending = self.client_choices.get(uid)
        if (not match or pending is None or time.monotonic() > pending.expires_at
                or not hmac.compare_digest(match[1], pending.token)):
            raise UserProblem("Выбор компании устарел или недействителен. Пришлите запрос заново.")
        if match[2] == "cancel":
            self.client_choices.pop(uid)
            self.contexts.pop(uid, None)
            return "Выбор компании отменён. Документ не создавался."
        index = int(match[2]) - 1
        return await self.select_client(uid, pending, index, request_id)

    async def select_client(self, uid: int, pending: PendingClientChoice, index: int, request_id: str):
        if (self.client_choices.get(uid) != pending or time.monotonic() > pending.expires_at
                or uid in self.recoveries):
            raise UserProblem("Выбор компании устарел. Повторите поиск.")
        if index < 0:
            raise UserProblem("Кнопка выбора компании недействительна.")
        if index >= len(pending.choices.candidates):
            raise UserProblem("Кнопка выбора компании недействительна.")
        candidate = pending.choices.candidates[index]
        self.client_choices.pop(uid)
        draft = InvoiceDraft.from_command(pending.command) if pending.command is not None else pending.draft
        self.contexts[uid] = DraftContext(draft=draft,
                                         selected_client_id=candidate.client_id)
        event(request_id=request_id, user_id=uid, stage="client_choice", status="selected")
        try:
            if pending.command is None:
                try:
                    fresh = ResolvedClient.model_validate(await asyncio.wait_for(
                        self.service.onec.resolve_client(draft.client, selected_id=candidate.client_id), self.service.timeout))
                    if fresh.client_id != candidate.client_id:
                        raise ValueError("Selected identity changed")
                except UserProblem:
                    self.contexts.pop(uid, None)
                    raise
                except Exception as exc:
                    self.contexts.pop(uid, None)
                    event(request_id=request_id, user_id=uid, stage="company_search", status="error", error=safe_backend_error(exc))
                    raise WorkflowFailure("resolve", None) from None
                if draft.invoice_date is None and draft.service_period is None:
                    return f"Компания выбрана: {fresh.display_name}. Укажите дату счёта или период услуг."
                try:
                    command = draft.command()
                except UserProblem:
                    return f"Компания выбрана: {fresh.display_name}. Укажите дату счёта или период услуг."
                return await self.prepare_command(uid, command, request_id)
            return await self.prepare_command(uid, pending.command, request_id)
        except UserProblem as exc:
            raise UserProblem("Компания выбрана. " + str(exc)) from None

    def show_service_choices(self, uid: int, command: InvoiceCommand, exc: ServiceChoiceRequired):
        pending = PendingServiceChoice(token=secrets.token_hex(16), command=command, line_number=exc.line_number,
            choices=exc.choices, expires_at=time.monotonic() + 300)
        self.service_choices[uid] = pending
        context = self.contexts[uid]
        draft = InvoiceDraft(**{**context.draft.model_dump(), "unresolved_line": exc.line_number})
        self.contexts[uid] = DraftContext(**{**context.model_dump(), "draft": draft})
        self.pending.pop(uid, None)
        buttons = [[InlineButton(text=(f"{i}. {item.display_name[:45]}" + (f" · {item.code}" if item.code else ""))[:64],
            callback_data=f"service:{pending.token}:{i}")] for i, item in enumerate(exc.choices.candidates, 1)]
        buttons.append([InlineButton(text="Отмена", callback_data=f"service:{pending.token}:cancel")])
        return ConfirmationPrompt(text=f"Выберите услугу для строки {exc.line_number}:\n" + "\n".join(
            f"{i}. {item.display_name}" + (f" · код {item.code}" if item.code else f" · запись {item.service_id}")
            for i, item in enumerate(exc.choices.candidates, 1))
            + "\nСуммы и остальные параметры сохранены.", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

    async def choose_service(self, callback: CallbackQuery, request_id: str):
        uid = callback.sender.id
        match = re.fullmatch(r"service:([a-f0-9]{32}):([1-5]|cancel)", callback.data)
        pending = self.service_choices.get(uid)
        if (match is None or pending is None or uid in self.recoveries
                or time.monotonic() > pending.expires_at or not hmac.compare_digest(match[1], pending.token)):
            raise UserProblem("Выбор услуги устарел или недействителен. Повторите запрос.")
        if match[2] == "cancel":
            self.service_choices.pop(uid)
            self.contexts.pop(uid, None)
            return "Выбор услуги отменён. Документ не создавался."
        index = int(match[2]) - 1
        return await self.select_service(uid, pending, index, request_id)

    async def select_service(self, uid: int, pending: PendingServiceChoice, index: int, request_id: str):
        if (self.service_choices.get(uid) != pending or uid in self.recoveries
                or time.monotonic() > pending.expires_at):
            raise UserProblem("Выбор услуги устарел. Повторите запрос.")
        if index < 0 or index >= len(pending.choices.candidates):
            raise UserProblem("Недействительный номер услуги.")
        self.service_choices.pop(uid)
        context = self.contexts[uid]
        selected = {**context.selected_service_ids, pending.line_number: pending.choices.candidates[index].service_id}
        self.contexts[uid] = DraftContext(**{**context.model_dump(), "selected_service_ids": selected})
        event(request_id=request_id, user_id=uid, stage="service_choice", status="selected")
        return await self.prepare_command(uid, pending.command, request_id)

    async def search_company(self, uid: int, draft: InvoiceDraft, request_id: str):
        """Directory discovery before requiring a complete financial command."""
        self.pending.pop(uid, None)
        self.contexts[uid] = DraftContext(draft=draft)
        try:
            client = ResolvedClient.model_validate(await asyncio.wait_for(
                self.service.onec.resolve_client(draft.client), self.service.timeout))
            choices = ClientCandidates(candidates=(ClientCandidate(client_id=client.client_id,
                display_name=client.display_name, full_name=client.display_name),))
        except ClientChoiceRequired as exc:
            choices = exc.choices
        except UserProblem:
            raise
        except Exception as exc:
            event(request_id=request_id, user_id=uid, stage="company_search", status="error", error=safe_backend_error(exc))
            raise WorkflowFailure("resolve", None) from None
        event(request_id=request_id, user_id=uid, stage="company_search", status="candidates")
        return self.show_client_choices(uid, None, choices, draft=draft)

    async def confirm(self, uid: int, pending: Pending, request_id: str):
        if uid in self.recoveries:
            raise UserProblem("Сначала восстановите операцию командой /retry.")
        try:
            refreshed = await self.service.refresh(pending.prepared, request_id, uid)
        except UserProblem:
            self.pending.pop(uid, None)
            raise
        except WorkflowFailure as exc:
            if self.service.readonly_preview(pending.prepared):
                self.pending.pop(uid, None)
            elif exc.state == "unknown":
                self.pending.pop(uid, None)
                self.recoveries[uid] = pending.prepared
            raise
        if refreshed != pending.prepared:
            context = self.contexts[uid]
            return self.show_preview(uid, refreshed, context.command,
                                     "Данные 1С изменились. Проверьте обновлённый счёт и подтвердите заново.\n\n")
        self.pending.pop(uid, None)
        if self.service.readonly_preview(pending.prepared):
            return "Preview повторно проверен по данным FirstBit. Режим READ-ONLY: документ не создавался. Можно изменить запрос или отменить."
        return pending.prepared

    async def prepare_callback(self, callback: CallbackQuery, request_id: str):
        if callback.data.startswith("initialqty:"):
            uid = callback.sender.id
            match = re.fullmatch(r"initialqty:([a-f0-9]{32}):(one|edit|cancel)", callback.data)
            pending = self.initial_quantities.get(uid)
            if (not match or pending is None or uid in self.recoveries or time.monotonic() > pending.expires_at
                    or not hmac.compare_digest(match[1], pending.token)):
                raise UserProblem("Выбор количества устарел. Повторите запрос.")
            self.initial_quantities.pop(uid)
            if match[2] == "cancel":
                self.contexts.pop(uid, None)
                return "Запрос отменён. Документ не создавался."
            if match[2] == "edit":
                return f"Укажите количество для строки {pending.line_number}, например «Во второй строке количество 1». Остальные параметры сохранены."
            services = list(pending.command.services)
            selection = services[pending.line_number - 1]
            services[pending.line_number - 1] = ServiceSelection(query=selection.query, quantity=Decimal('1'))
            command = InvoiceCommand(**{**pending.command.model_dump(), "services": tuple(services)})
            context = self.contexts[uid]
            self.contexts[uid] = DraftContext(**{**context.model_dump(), "draft": InvoiceDraft.from_command(command)})
            return await self.prepare_command(uid, command, request_id)
        if callback.data.startswith("service:"):
            return await self.choose_service(callback, request_id)
        if callback.data.startswith("supplier:"):
            return await self.review_supplier(callback, request_id)
        if callback.data.startswith("client:"):
            return await self.choose_client(callback, request_id)
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
        if action.action == "cancel":
            self.pending.pop(uid)
            self.contexts.pop(uid, None)
            return "Команда отменена. Документ не создавался."
        if action.action == "edit":
            self.pending.pop(uid)
            return "Напишите или наговорите, что изменить: дату, цену без НДС, налог, название услуги или количество. Для нескольких строк укажите номер. Остальные параметры сохранены."
        return await self.confirm(uid, pending, request_id)

    async def prepare(self, message: Message | CallbackQuery,
                      request_id: str) -> PreparedInvoice | ConfirmationPrompt | str:
        if isinstance(message, CallbackQuery):
            return await self.prepare_callback(message, request_id)
        uid = message.sender.id
        # A new message revokes selection buttons before parsing/downloading.
        previous_choice = self.client_choices.pop(uid, None)
        previous_service = self.service_choices.pop(uid, None)
        self.initial_quantities.pop(uid, None)
        self.supplier_reviews.pop(uid, None)
        pending = self.pending.get(uid)
        if pending is not None and time.monotonic() > pending.expires_at:
            self.pending.pop(uid)
        is_voice = message.voice is not None
        uncertain_voice = None
        if is_voice:
            if uid in self.recoveries:
                raise UserProblem("Сначала восстановите предыдущую операцию командой /retry. Новый счёт пока не создаём.")
            self.pending.pop(uid, None)
            if self.speech is None:
                raise UserProblem("Сейчас доступен только текст. Пришлите компанию и дату счёта.")
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
            except UncertainTranscript as exc:
                if getattr(self.service.onec, "preview_only", False) is not True:
                    event(request_id=request_id, user_id=uid, stage="voice", status="clarification")
                    raise
                uncertain_voice = exc
                transcript = exc.transcript
                event(request_id=request_id, user_id=uid, stage="voice", status="uncertain")
            except UserProblem:
                event(request_id=request_id, user_id=uid, stage="voice", status="clarification")
                raise
            text = transcript.text
        elif message.text is not None:
            text = message.text
        else:
            raise UserProblem("Пришлите текст или голосовое сообщение с командой создания счёта.")
        if len(text) <= 1000 and not any(ord(char) < 32 and not char.isspace() for char in text):
            text = normalize_request_text(text)
        if previous_choice is not None and not is_voice and re.fullmatch(r"[1-9]|1[0-9]", text):
            # The numeric reply is scoped to this user's current expiring prompt.
            self.client_choices[uid] = previous_choice
            return await self.select_client(uid, previous_choice, int(text) - 1, request_id)
        if previous_service is not None and not is_voice and re.fullmatch(r"[1-5]", text):
            self.service_choices[uid] = previous_service
            return await self.select_service(uid, previous_service, int(text) - 1, request_id)
        if not is_voice and text in ("/start", "/help"):
            return ("Подготовка счёта по данным 1С.\n"
                    "Например: Сформируй счёт Ромашке на 1 октября за бухгалтерское обслуживание с НДС.\n"
                    "Сначала покажем полный preview. До подтверждения документы не создаются.\n"
                    "Правки можно писать или наговаривать коротко: остальные поля сохраняются.\n"
                    "После preview: «Цена 1500», «НДС 5%», «Без НДС», «Назови услугу Бухгалтерское обслуживание». "
                    "Цена — за единицу без НДС в валюте preview. Для нескольких строк укажите номер.\n"
                    "Если год/месяц даты не указан, используем текущий или дату из контекста — проверьте preview.\n"
                    + ("Сейчас TEST / MOCK: вымышленные данные и тестовый PDF, реальные счета не создаются."
                       if self.service.onec.is_fake is True else
                       "Сейчас READ-ONLY: только историческое предложение и проверка preview; запись и PDF отключены."
                       if getattr(self.service.onec, "preview_only", False) is True else
                       "После подтверждения используется штатная печатная форма 1С."))
        if not is_voice and text == "/cancel":
            self.pending.pop(uid, None)
            self.contexts.pop(uid, None)
            return "Ожидающая подтверждения команда отменена."
        if not is_voice and text == "/retry":
            if uid not in self.recoveries:
                context = self.contexts.get(uid)
                if getattr(self.service.onec, "preview_only", False) is True and context is not None:
                    self.pending.pop(uid, None)
                    if (context.draft.client is not None and context.draft.invoice_date is None
                            and context.draft.service_period is None):
                        return await self.search_company(uid, context.draft, request_id)
                    return await self.prepare_command(uid, context.draft.command(), request_id, context)
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
            return await self.confirm(uid, pending, request_id)
        event(request_id=request_id, user_id=uid, stage="interpret", status="started")
        context = self.contexts.get(uid)
        # Any attempted edit revokes the old confirmation before parsing/resolution.
        self.pending.pop(uid, None)
        if getattr(self.service.onec, "preview_only", False) is True:
            query = service_refinement_phrase(text) if previous_service is not None else company_search_phrase(text)
            if query is not None:
                if previous_service is not None:
                    services = list(previous_service.command.services)
                    original = services[previous_service.line_number - 1]
                    services[previous_service.line_number - 1] = ServiceSelection(query=query, quantity=original.quantity)
                    command = InvoiceCommand(**{**previous_service.command.model_dump(), "services": tuple(services)})
                    saved = self.contexts[uid]
                    selected = {number: key for number, key in saved.selected_service_ids.items()
                        if number != previous_service.line_number}
                    self.contexts[uid] = DraftContext(draft=InvoiceDraft.from_command(command),
                        selected_client_id=saved.selected_client_id, selected_service_ids=selected)
                    return await self.prepare_command(uid, command, request_id)
                if previous_choice is not None and previous_choice.command is not None:
                    command = InvoiceCommand.model_validate({**previous_choice.command.model_dump(), "client": query})
                    self.contexts[uid] = DraftContext(draft=InvoiceDraft.from_command(command))
                    return await self.prepare_command(uid, command, request_id)
                base = previous_choice.draft if previous_choice is not None and previous_choice.draft is not None else InvoiceDraft()
                return await self.search_company(uid, InvoiceDraft.model_validate({**base.model_dump(), "client": query}), request_id)
        language_context = context or self.last_contexts.get(uid)
        try:
            interpretation = await self.interpreter.interpret(text, language_context.draft if language_context else None)
        except ExternalFailure as exc:
            if is_voice and exc.code in ("openai_timeout", "openai_api_error"):
                event(request_id=request_id, user_id=uid, stage="interpret", status="error", error=exc.code)
                raise UserProblem("Голос распознан:\n«" + text + "»\n\n"
                    "Сервис разбора команды не ответил. Документ не создавался. "
                    "Этот текст можно отправить повторно, не записывая голос заново.") from None
            raise
        event(request_id=request_id, user_id=uid, stage="interpret", status="parsed")
        if uncertain_voice is not None:
            intent = interpretation.intent
            # Never apply uncertain speech as an edit or financial override. A new
            # readonly proposal must first pass an explicit company selection.
            if interpretation.command is None and (intent is None or intent.action != "create"
                    or intent.client is None or intent.preview_changes
                    or any(e.price is not None or e.amount is not None or e.tax is not None for e in intent.initial_overrides)):
                raise uncertain_voice
            if interpretation.command is not None and interpretation.command.preview_overrides:
                raise uncertain_voice
        if interpretation.command is not None:
            command = interpretation.command
            context = None
        else:
            intent = interpretation.intent
            if intent.action == "cancel":
                self.contexts.pop(uid, None)
                return "Команда отменена. Документ не создавался."
            if intent.action == "reject":
                raise UserProblem("Укажите запрос на счёт или изменение его полей. В готовом preview можно явно изменить цену, НДС или название услуги.")
            if context is None and intent.client is None:
                context = self.last_contexts.get(uid)
            if (intent.tax is not None and intent.tax.mode != "default" and context is not None
                    and (context.prepared is not None or context.draft.initial_overrides)
                    and getattr(self.service.onec, "preview_only", False) is True):
                tax = intent.tax
                request = PreviewTaxRequest(mode=tax.mode, query=tax.query)
                rate_evidence = None
                literal_rate = explicit_tax_rate(tax.evidence) if not re.search(r"профил", tax.evidence, re.I) else None
                if literal_rate is not None:
                    rate, rate_evidence = literal_rate
                    request = PreviewTaxRequest(mode="rate", rate=rate)
                elif tax.mode == "without_tax" and not re.search(r"\bбез\s+(?:ндс|налог\w*)|\bno\s+vat\b", tax.evidence, re.I):
                    raise UserProblem("Укажите явно «Без НДС» или точную ставку, например «НДС 0%».")
                elif tax.mode == "profile" and tax.query is not None:
                    match = re.fullmatch(r"(?:НДС\s*)?([0-9]+(?:[.,][0-9]+)?)\s*%", tax.query, re.I)
                    if match:
                        rate_evidence = match[1]
                        request = PreviewTaxRequest(mode="rate", rate=explicit_decimal(rate_evidence, places=3))
                intent = InvoiceIntent.model_validate({**intent.model_dump(), "tax": None,
                    "preview_changes": intent.preview_changes + (IntentPreviewChange(tax=request,
                        line_number=explicit_line_target(text, text.casefold().index(tax.evidence.casefold())),
                        tax_evidence=tax.evidence, rate_evidence=rate_evidence),)})
            if intent.preview_changes:
                # The model may label an explicit field patch as "create" even with a
                # prepared local draft. Repair only the action, never values or scope.
                new_scope = re.search(r"\b(?:нов\w*|друг\w*)\s+сч[её]т\b|"
                    r"\b(?:сформир\w*|созд\w*|выстав\w*|подготов\w*|сдела\w*)\b.*\bсч[её]т\b|"
                    r"\b(?:для|компани\w*|клиент\w*|контрагент\w*)\b", text, re.I)
                if (intent.action == "create" and intent.client is None and context is not None
                        and (context.prepared is not None or context.draft.initial_overrides) and not new_scope):
                    intent = InvoiceIntent.model_validate({**intent.model_dump(), "action": "edit"})
                if (context is None or context.prepared is None and not context.draft.initial_overrides or intent.action == "create"
                        or intent.client is not None and intent.client.casefold() != context.draft.client.casefold()):
                    raise UserProblem("Сначала подготовьте preview для нужной компании, затем измените его цену, НДС или название.")
                for change in intent.preview_changes:
                    if context.prepared is not None and change.currency is not None and change.currency != context.prepared.preview.currency:
                        raise UserProblem(f"В preview валюта {context.prepared.preview.currency}. Укажите цену в этой валюте; конвертация не выполняется.")
            base = context.draft if context else InvoiceDraft()
            if intent.action == "create" and intent.client is not None:
                base, context = InvoiceDraft(), None
            draft = merge_intent(base, intent)
            self.contexts[uid] = DraftContext(draft=draft, command=context.command if context else None,
                                            prepared=context.prepared if context else None,
                                            selected_client_id=context.selected_client_id if context
                                                and draft.client == context.draft.client else None,
                                            supplier_review=context.supplier_review if context
                                                and draft.client == context.draft.client else None,
                                            selected_service_ids=context.selected_service_ids if context
                                                and draft.client == context.draft.client and draft.services == context.draft.services else {})
            if intent.action == "clarify":
                messages = {"client": "Уточните компанию.", "date": "Уточните дату счёта.",
                            "service": "Уточните название услуги.", "tax": "Уточните налоговый режим.",
                            "unsupported": "Уточните запрос на счёт."}
                known_locally = {"client": draft.client is not None,
                                 "date": draft.invoice_date is not None and draft.incomplete_date is None,
                                 "service": bool(draft.services)}
                if not known_locally.get(intent.clarification, False):
                    if (getattr(self.service.onec, "preview_only", False) is True and draft.client is not None
                            and self.contexts[uid].selected_client_id is None and intent.clarification == "date"):
                        return await self.search_company(uid, draft, request_id)
                    raise UserProblem(messages.get(intent.clarification, "Уточните недостающий параметр.") + " Остальные данные сохранены.")
            try:
                command = draft.command()
            except UserProblem:
                if (getattr(self.service.onec, "preview_only", False) is True and draft.client is not None
                        and draft.invoice_date is None and draft.service_period is None
                        and self.contexts[uid].selected_client_id is None and not draft.preview_overrides):
                    return await self.search_company(uid, draft, request_id)
                raise
        if context is None:
            self.contexts[uid] = DraftContext(draft=InvoiceDraft.from_command(command))
        if uncertain_voice is not None:
            self.contexts[uid] = DraftContext.model_validate({**self.contexts[uid].model_dump(),
                "require_client_choice": True})
        result = await self.prepare_command(uid, command, request_id, context)
        if uncertain_voice is not None and isinstance(result, ConfirmationPrompt):
            result = ConfirmationPrompt(text=("Я услышал неуверенно: «" + text + "»\n"
                "Выберите компанию ниже. Затем проверьте дату, количество и налог в preview.\n\n" + result.text),
                reply_markup=result.reply_markup)
        return result

    async def prepare_command(self, uid: int, command: InvoiceCommand, request_id: str,
                              context: DraftContext | None = None) -> ConfirmationPrompt:
        try:
            prepared = await self.service.prepare(command, request_id, uid,
                existing=context.prepared if context else None, old_command=context.command if context else None,
                selected_client_id=self.contexts[uid].selected_client_id,
                require_client_choice=self.contexts[uid].require_client_choice,
                selected_service_ids=self.contexts[uid].selected_service_ids)
        except ClientChoiceRequired as exc:
            event(request_id=request_id, user_id=uid, stage="client_choice", status="required")
            return self.show_client_choices(uid, command, exc.choices)
        except ServiceChoiceRequired as exc:
            event(request_id=request_id, user_id=uid, stage="service_choice", status="required")
            return self.show_service_choices(uid, command, exc)
        except InitialQuantityRequired as exc:
            pending = PendingInitialQuantity(token=secrets.token_hex(16), command=command,
                line_number=exc.line_number, expires_at=time.monotonic() + 300)
            self.initial_quantities[uid] = pending
            return ConfirmationPrompt(text=(f"Строка {exc.line_number}: указана сумма без НДС {exc.amount}. "
                f"В образце количество {exc.quantity} {exc.uom}; с ним цена до копейки не даёт точную сумму. "
                "Использовать количество 1? Сумма и налоговый запрос сохранятся."),
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineButton(text="Количество 1", callback_data=f"initialqty:{pending.token}:one")],
                    [InlineButton(text="Уточнить текстом", callback_data=f"initialqty:{pending.token}:edit")],
                    [InlineButton(text="Отмена", callback_data=f"initialqty:{pending.token}:cancel")]]))
        except ServiceProblem as exc:
            saved = self.contexts[uid]
            draft = InvoiceDraft.model_validate({**saved.draft.model_dump(), "unresolved_line": exc.line_number})
            self.contexts[uid] = DraftContext(draft=draft, command=saved.command, prepared=saved.prepared,
                                             selected_client_id=saved.selected_client_id, supplier_review=saved.supplier_review)
            raise
        event(request_id=request_id, user_id=uid, stage="interpret", status="success")
        return self.show_preview(uid, prepared, command)

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
                    journal = self.service.journal
                    durable_status = journal.delivery_status(delivery.operation_id, uid) if journal is not None else None
                    if delivery in self.delivered or durable_status == "delivered":
                        event(request_id=request_id, user_id=uid, stage="delivery", status="duplicate",
                              operation_id=delivery.operation_id)
                        old = self.delivered.get(delivery)
                        if old is None:
                            old = journal.get(delivery.operation_id).prepared
                        same = old.preview.digest == receipt.prepared.preview.digest
                        receipt.prepared = None
                        receipt.response_text = ("Этот счёт уже отправлен вам. Второй PDF не отправляем." if same else
                            "На это основание уже создан и отправлен счёт с другими данными. Новую версию не создаём. Обратитесь к оператору.")
                    elif delivery in self.delivery_attempted or durable_status == "sending":
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
                        if result.pdf is None:
                            if result.invoice.posted:
                                if journal is not None:
                                    journal.finalized_without_pdf(delivery.operation_id, uid)
                                self.recoveries.pop(uid, None)
                                receipt.response_text = (f"Счёт №{result.invoice.number or result.invoice.document_id} проведён в 1С и проверен чтением. "
                                    f"ID: {result.invoice.document_id}. Штатный PDF пока недоступен.")
                            else:
                                self.recoveries[uid] = receipt.prepared
                                receipt.response_text = (f"Черновик счёта №{result.invoice.number or result.invoice.document_id} создан в 1С и проверен чтением. "
                                    f"ID: {result.invoice.document_id}. Проведение заблокировано: нужна атомарная проверка в 1С. "
                                    "Повторная операция не создаст новый счёт. /retry проверит этот же документ.")
                            receipt.prepared = None
                            await self.telegram.send_text(uid, receipt.response_text)
                            receipt.response_sent = len(message_chunks(receipt.response_text))
                            return
                        stage = "delivery"
                        if journal is not None and not journal.claim_delivery(delivery.operation_id, uid):
                            raise UserProblem("Доставка уже начата или выполнена. Автоматически повторять PDF нельзя; проверьте чат.")
                        # Telegram has no idempotency key for sendDocument. A lost response
                        # leaves delivery unknown, so a retry must not send another PDF.
                        self.delivery_attempted.add(delivery)
                        await self.telegram.send_pdf(uid, result.pdf.content, is_mock=self.service.onec.is_fake is True)
                        if journal is not None:
                            journal.delivered(delivery.operation_id, uid)
                        self.delivered[delivery] = receipt.prepared
                        self.recoveries.pop(uid, None)
                        context = self.contexts.pop(uid, None)
                        if context is not None:
                            self.last_contexts[uid] = context
                        event(request_id=request_id, user_id=uid, stage=stage, status="success",
                              document_id=result.invoice.document_id)
                        return
        except UserProblem as exc:
            unparsed = str(exc) == HELP
            event(request_id=request_id, user_id=uid, stage=stage, status="clarification",
                  error="request_not_understood" if unparsed else None)
            receipt.response_text = ("Не удалось разобрать запрос целиком. Напишите или произнесите название компании отдельно — "
                "я найду варианты. Дату и услуги можно уточнить после выбора."
                if unparsed and getattr(self.service.onec, "preview_only", False) is True else str(exc))
        except WorkflowFailure as exc:
            if exc.stage == "stale" and exc.state == "not_started" and receipt.prepared is not None:
                try:
                    refreshed = await self.service.refresh(receipt.prepared, request_id, uid)
                    context = self.contexts[uid]
                    prompt = self.show_preview(uid, refreshed, context.command,
                        "Данные изменились перед записью. Проверьте новый preview и подтвердите заново.\n\n")
                    receipt.prepared = None
                    receipt.response_text, receipt.response_markup = prompt.text, prompt.reply_markup
                except UserProblem as problem:
                    receipt.prepared = None
                    receipt.response_text = str(problem)
                except WorkflowFailure as failure:
                    self.recoveries[uid] = receipt.prepared
                    receipt.response_text = failure_text(failure)
            else:
                if receipt.prepared is not None:
                    self.recoveries[uid] = receipt.prepared
                receipt.response_text = failure_text(exc)
        except DeliveryFailure:
            if receipt.prepared is not None:
                self.recoveries[uid] = receipt.prepared
            raise
        except ExternalFailure as exc:
            event(request_id=request_id, user_id=uid, stage=stage, status="error", error=exc.code)
            receipt.response_text = ("Не удалось безопасно распознать запрос. Документ не создавался. Повторите запрос позже."
                + (" Данные незавершённого счёта сохранены." if uid in self.contexts else ""))
        if receipt.response_text is not None:
            chunks = message_chunks(receipt.response_text)
            for index in range(receipt.response_sent, len(chunks)):
                await self.telegram.send_text(uid, chunks[index], receipt.response_markup if index == len(chunks) - 1 else None)
                receipt.response_sent = index + 1
