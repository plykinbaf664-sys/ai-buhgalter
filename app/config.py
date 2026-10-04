import os
import re
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator, model_validator

from app.domain import StrictModel
from app.voice import STT_MODELS

UserId = Annotated[int, Field(gt=0, lt=2**52)]


def _strict_bool(value: str) -> bool:
    if value == "true":
        return True
    if value == "false":
        return False
    raise ValueError("ONEC_WRITE_ENABLED must be exactly true or false")


class Settings(StrictModel):
    token: SecretStr
    webhook_secret: SecretStr
    allowed_users: frozenset[UserId] = Field(min_length=1)
    mode: Literal["mock"] = "mock"
    onec_write_enabled: bool = False
    # One-shot failures for manual recovery checks. Safe only for the in-memory fake.
    fake_onec_fault: Literal["disabled", "create_lost_response", "post_lost_response"] = "disabled"
    ai_mode: Literal["disabled", "openai"] = "disabled"
    openai_api_key: SecretStr | None = None
    llm_model: str = Field(default="auto", max_length=100)
    stt_model: str = Field(default="auto", max_length=100)

    @field_validator("token")
    @classmethod
    def token_format(cls, value: SecretStr) -> SecretStr:
        if not re.fullmatch(r"[0-9]+:[A-Za-z0-9_-]{20,}", value.get_secret_value()):
            raise ValueError("Invalid TELEGRAM_BOT_TOKEN")
        return value

    @field_validator("webhook_secret")
    @classmethod
    def webhook_format(cls, value: SecretStr) -> SecretStr:
        if not re.fullmatch(r"[A-Za-z0-9_-]{32,256}", value.get_secret_value()):
            raise ValueError("Invalid TELEGRAM_WEBHOOK_SECRET")
        return value

    @model_validator(mode="after")
    def ai_configuration(self):
        if self.mode == "mock" and self.onec_write_enabled:
            raise ValueError("ONEC_WRITE_ENABLED cannot be true while APP_MODE=mock")
        if self.ai_mode == "openai":
            if (self.openai_api_key is None or not self.openai_api_key.get_secret_value().strip()
                    or not self.llm_model.strip() or not self.stt_model.strip()):
                raise ValueError("OpenAI requires OPENAI_API_KEY, OPENAI_LLM_MODEL and OPENAI_STT_MODEL")
            if self.stt_model != "auto" and self.stt_model not in STT_MODELS:
                raise ValueError("OPENAI_STT_MODEL must support JSON transcription with logprobs")
        return self

    @classmethod
    def from_env(cls):
        raw = os.environ.get("TELEGRAM_ALLOWED_USER_IDS", "")
        if not re.fullmatch(r"[0-9]+(?:\s*,\s*[0-9]+)*", raw):
            raise ValueError("Invalid TELEGRAM_ALLOWED_USER_IDS")
        return cls(
            token=os.environ.get("TELEGRAM_BOT_TOKEN", ""),
            webhook_secret=os.environ.get("TELEGRAM_WEBHOOK_SECRET", ""),
            allowed_users=frozenset(int(part.strip()) for part in raw.split(",")),
            mode=os.environ.get("APP_MODE", "mock"),
            onec_write_enabled=_strict_bool(os.environ.get("ONEC_WRITE_ENABLED", "false")),
            fake_onec_fault=os.environ.get("FAKE_ONEC_FAULT", "disabled"),
            ai_mode=os.environ.get("AI_MODE", "disabled"),
            openai_api_key=os.environ.get("OPENAI_API_KEY") or None,
            llm_model=os.environ.get("OPENAI_LLM_MODEL", "auto"),
            stt_model=os.environ.get("OPENAI_STT_MODEL", "auto"),
        )
