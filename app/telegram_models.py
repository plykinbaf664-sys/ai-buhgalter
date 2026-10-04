from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain import StrictModel


class TelegramModel(BaseModel):
    # Telegram adds unrelated fields. Validate all used fields; discard the rest.
    model_config = ConfigDict(strict=True, extra="ignore", frozen=True,
                              hide_input_in_errors=True, revalidate_instances="always",
                              validate_by_name=True)


class Sender(TelegramModel):
    id: int = Field(gt=0, lt=2**52)
    is_bot: bool


class Chat(TelegramModel):
    id: int
    type: str


class Voice(TelegramModel):
    file_id: str = Field(min_length=1, max_length=256)
    file_unique_id: str = Field(min_length=1, max_length=256)
    duration: int = Field(ge=0)
    mime_type: str | None = None
    file_size: int | None = Field(default=None, ge=0)


class Message(TelegramModel):
    message_id: int = Field(gt=0)
    sender: Sender = Field(alias="from")
    chat: Chat
    text: str | None = None
    voice: Voice | None = None
    # Presence rejects these messages; their content is never used.
    sender_chat: TelegramModel | None = None
    forward_origin: TelegramModel | None = None


class CallbackMessage(TelegramModel):
    message_id: int = Field(gt=0)
    chat: Chat


class CallbackQuery(TelegramModel):
    id: str = Field(min_length=1, max_length=256)
    sender: Sender = Field(alias="from")
    message: CallbackMessage | None = None
    data: str = Field(min_length=1, max_length=64)


class Update(TelegramModel):
    update_id: int = Field(ge=0)
    message: Message | None = None
    callback_query: CallbackQuery | None = None

    @model_validator(mode="after")
    def one_supported_event(self):
        if self.message is not None and self.callback_query is not None:
            raise ValueError("Update has multiple event types")
        return self


class SentChat(TelegramModel):
    id: int


class SentMessage(TelegramModel):
    message_id: int = Field(gt=0)
    chat: SentChat


class SuccessResponse(TelegramModel):
    ok: bool

    @field_validator("ok")
    @classmethod
    def success_only(cls, value: bool) -> bool:
        if value is not True:
            raise ValueError("Telegram rejected request")
        return value


class SendResponse(SuccessResponse):
    result: SentMessage


class FileRequest(StrictModel):
    file_id: str


class TelegramFile(TelegramModel):
    file_id: str
    file_unique_id: str
    file_size: int | None = Field(default=None, gt=0)
    file_path: str = Field(min_length=1, max_length=512)


class FileResponse(SuccessResponse):
    result: TelegramFile


class TextRequest(StrictModel):
    chat_id: int
    text: str = Field(min_length=1, max_length=4096)
    reply_markup: "InlineKeyboardMarkup | None" = None


class InlineButton(StrictModel):
    text: str = Field(min_length=1, max_length=64)
    callback_data: str = Field(min_length=1, max_length=64)


class InlineKeyboardMarkup(StrictModel):
    inline_keyboard: list[list[InlineButton]] = Field(min_length=1)


class CallbackAnswerRequest(StrictModel):
    callback_query_id: str = Field(min_length=1, max_length=256)


class CallbackAnswerResponse(SuccessResponse):
    result: Literal[True]


class DocumentRequest(StrictModel):
    chat_id: str
    caption: str


class WebhookAck(StrictModel):
    ok: Literal[True] = True


class Health(StrictModel):
    status: Literal["ok"] = "ok"
    mode: Literal["mock"] = "mock"
