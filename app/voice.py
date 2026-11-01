import os
import tempfile
from typing import Literal

import httpx
from pydantic import Field, SecretStr, field_validator

from app.domain import ExternalModel, StrictModel, UserProblem
from app.http import ExternalFailure, bounded_request, disable_wire_logs
from app.model_selection import OpenAIModelSelector
from app.validation import validate_json

MAX_VOICE_BYTES = 4_000_000
MAX_VOICE_SECONDS = 120
STT_MODELS = {"gpt-4o-transcribe", "gpt-4o-mini-transcribe", "gpt-4o-mini-transcribe-2025-12-15"}


class AudioFile(StrictModel):
    content: bytes = Field(min_length=32, max_length=MAX_VOICE_BYTES, repr=False)

    @field_validator("content")
    @classmethod
    def ogg_opus_header(cls, value: bytes) -> bytes:
        if not value.startswith(b"OggS") or b"OpusHead" not in value[:256]:
            raise ValueError("Expected OGG/Opus")
        return value


class TokenConfidence(ExternalModel):
    token: str
    logprob: float = Field(le=0, allow_inf_nan=False)


class Transcript(ExternalModel):
    text: str = Field(min_length=1, max_length=1000)
    logprobs: list[TokenConfidence] = Field(min_length=1, max_length=4096)

    @field_validator("text")
    @classmethod
    def nonempty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Empty transcript")
        return value.strip()


class TranscriptionRequest(StrictModel):
    model: str
    language: Literal["ru"] = "ru"
    response_format: Literal["json"] = "json"
    include: list[Literal["logprobs"]] = Field(default_factory=lambda: ["logprobs"], serialization_alias="include[]")


class UncertainTranscript(UserProblem):
    """Untrusted speech text: only a readonly, explicit-choice flow may use it."""
    def __init__(self, transcript: Transcript, message: str):
        self.transcript = Transcript.model_validate(transcript)
        super().__init__(message)


class SpeechToText:
    def __init__(self, client: httpx.AsyncClient | None, api_key: SecretStr, model: str,
                 sdk_client: object | None = None,
                 model_selector: OpenAIModelSelector | None = None):
        self.client, self.api_key, self.model, self.sdk_client = client, api_key, model, sdk_client
        self.model_selector = model_selector
        disable_wire_logs()

    async def _transcribe_sdk(self, audio: AudioFile) -> Transcript:
        model = await self.model_selector.stt() if self.model_selector is not None else self.model
        temporary_path: str | None = None
        try:
            # On Windows the SDK reopens the file, so delete-on-close prevents upload.
            with tempfile.NamedTemporaryFile(prefix="telegram-voice-", suffix=".ogg", delete=False) as temporary:
                temporary.write(audio.content)
                temporary_path = temporary.name
            with open(temporary_path, "rb") as handle:
                response = await self.sdk_client.audio.transcriptions.create(
                    file=handle,
                    model=model,
                    language="ru",
                    response_format="json",
                    include=["logprobs"],
                )
        except Exception as exc:
            name = type(exc).__name__.lower()
            code = "openai_timeout" if "timeout" in name or isinstance(exc, TimeoutError) else "openai_api_error"
            raise ExternalFailure(code) from None
        finally:
            if temporary_path is not None:
                try:
                    os.unlink(temporary_path)
                except FileNotFoundError:
                    pass
                except OSError:
                    raise ExternalFailure("audio_cleanup_failed") from None
        try:
            text = getattr(response, "text", None)
            provider_logprobs = getattr(response, "logprobs", None)
            logprobs = [
                {"token": getattr(item, "token", None), "logprob": getattr(item, "logprob", None)}
                for item in (provider_logprobs or [])
            ]
            transcript = Transcript.model_validate({"text": text, "logprobs": logprobs})
        except (ValueError, TypeError, RecursionError):
            raise ExternalFailure("invalid_transcript") from None
        self._check_confidence(transcript)
        return transcript

    @staticmethod
    def _check_confidence(transcript: Transcript) -> None:
        scores = [entry.logprob for entry in transcript.logprobs]
        # A conservative heuristic, not a calibrated confidence guarantee.
        if sum(scores) / len(scores) < -1.0 or min(scores) < -3.0:
            raise UncertainTranscript(transcript, "Голос распознан неуверенно. Я услышал:\n«" + " ".join(transcript.text.split())
                              + "»\nИсправьте название или дату и пришлите запрос текстом, либо запишите голосовое ещё раз.")

    async def transcribe(self, audio: AudioFile) -> Transcript:
        audio = AudioFile.model_validate(audio)
        if self.sdk_client is not None:
            return await self._transcribe_sdk(audio)
        if self.client is None:
            raise ExternalFailure("openai_not_configured")
        content = await bounded_request(
            self.client, "POST", "https://api.openai.com/v1/audio/transcriptions", deadline=45,
            headers={"Authorization": "Bearer " + self.api_key.get_secret_value()},
            data=TranscriptionRequest(model=self.model).model_dump(by_alias=True),
            files={"file": ("voice.ogg", audio.content, "audio/ogg")},
        )
        try:
            transcript = validate_json(Transcript, content)
        except (ValueError, RecursionError):
            raise ExternalFailure("invalid_transcript") from None
        self._check_confidence(transcript)
        return transcript
