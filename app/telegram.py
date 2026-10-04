import re

import httpx

from app.domain import UserProblem
from app.http import ExternalFailure, bounded_request, disable_wire_logs
from app.telegram_models import (CallbackAnswerRequest, CallbackAnswerResponse, DocumentRequest,
                                 FileRequest, FileResponse, InlineKeyboardMarkup, SendResponse,
                                 TextRequest, Voice)
from app.voice import AudioFile, MAX_VOICE_BYTES, MAX_VOICE_SECONDS
from app.validation import validate_json


class DeliveryFailure(Exception):
    pass


class Telegram:
    def __init__(self, token: str, client: httpx.AsyncClient):
        self._base = f"https://api.telegram.org/bot{token}"
        self._files = f"https://api.telegram.org/file/bot{token}/"
        self._client = client
        disable_wire_logs()

    async def _send(self, method: str, chat_id: int, **kwargs) -> None:
        try:
            content = await bounded_request(self._client, "POST", self._base + "/" + method, **kwargs)
            body = validate_json(SendResponse, content)
            if body.result.chat.id != chat_id:
                raise ValueError("Invalid Telegram acknowledgment")
        except (ExternalFailure, ValueError, TypeError, AttributeError, RecursionError):
            raise DeliveryFailure("Telegram delivery not confirmed") from None

    async def send_text(self, chat_id: int, text: str,
                        reply_markup: InlineKeyboardMarkup | None = None) -> None:
        payload = TextRequest(chat_id=chat_id, text=text, reply_markup=reply_markup)
        await self._send("sendMessage", chat_id, json=payload.model_dump(exclude_none=True))

    async def answer_callback(self, callback_id: str) -> bool:
        # UI acknowledgment is best effort and must never cause a financial retry.
        try:
            content = await bounded_request(
                self._client, "POST", self._base + "/answerCallbackQuery",
                json=CallbackAnswerRequest(callback_query_id=callback_id).model_dump(),
            )
            return validate_json(CallbackAnswerResponse, content).result
        except (ExternalFailure, ValueError, TypeError, AttributeError, RecursionError):
            return False

    async def send_pdf(self, chat_id: int, pdf: bytes) -> None:
        await self._send(
            "sendDocument", chat_id,
            data=DocumentRequest(chat_id=str(chat_id), caption="ТЕСТОВЫЙ РЕЖИМ: это mock-файл, не счёт из 1С.").model_dump(),
            files={"document": ("mock-not-an-invoice.pdf", pdf, "application/pdf")},
        )

    async def download_voice(self, voice: Voice) -> AudioFile:
        voice = Voice.model_validate(voice)
        if not 0 < voice.duration <= MAX_VOICE_SECONDS:
            raise UserProblem("Пришлите голосовое сообщение длительностью от 1 до 120 секунд.")
        if voice.file_size is not None and not 0 < voice.file_size <= MAX_VOICE_BYTES:
            raise UserProblem("Голосовой файл слишком большой. Максимум 4 МБ.")
        if voice.mime_type not in (None, "audio/ogg", "audio/opus"):
            raise UserProblem("Поддерживаются голосовые сообщения Telegram в формате OGG/Opus.")
        response = await bounded_request(self._client, "POST", self._base + "/getFile",
                                         json=FileRequest(file_id=voice.file_id).model_dump())
        try:
            file = validate_json(FileResponse, response).result
            if file.file_id != voice.file_id or file.file_unique_id != voice.file_unique_id:
                raise ValueError("File identity mismatch")
            # Never accept a URL, absolute path, traversal or encoded path from an API.
            if not re.fullmatch(r"[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*\.(?:oga|ogg|opus)", file.file_path):
                raise ValueError("Unsafe file path")
            if file.file_size is not None and file.file_size > MAX_VOICE_BYTES:
                raise UserProblem("Голосовой файл слишком большой. Максимум 4 МБ.")
            content = await bounded_request(self._client, "GET", self._files + file.file_path,
                                             limit=MAX_VOICE_BYTES, deadline=20)
            if file.file_size is not None and len(content) != file.file_size:
                raise ValueError("File size mismatch")
            return AudioFile(content=content)
        except (ValueError, RecursionError):
            raise ExternalFailure("invalid_audio_file") from None
