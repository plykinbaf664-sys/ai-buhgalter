"""Offline voice/text E2E over a real loopback socket; all outbound HTTP is fake."""
from pathlib import Path
import secrets
import socket
import sys
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx
from pydantic import BaseModel, ConfigDict, Field
import uvicorn

from app.ai import Extraction, ModelResponse, OutputMessage, OutputText
from app.config import Settings
from app.fake_onec import FakeOneC
from app.main import create_app
from app.telegram_models import (CallbackAnswerResponse, CallbackMessage, CallbackQuery,
                                 Chat, FileResponse, Message, Sender, SendResponse,
                                 SentChat, SentMessage, TelegramFile, TextRequest, Update, Voice)
from app.validation import validate_json
from app.voice import TokenConfidence, Transcript

AUDIO = b"OggS" + b"\x00" * 24 + b"OpusHead" + b"\x00" * 32


class Evidence(BaseModel):
    model_config = ConfigDict(validate_assignment=True)
    replies: list[str] = Field(default_factory=list)
    confirmation_data: str | None = None
    callback_acks: int = 0
    pdf_deliveries: int = 0
    stt_calls: int = 0
    llm_calls: int = 0


def main():
    evidence, backend = Evidence(), FakeOneC()
    settings = Settings(token="123:" + secrets.token_urlsafe(32),
                        webhook_secret=secrets.token_urlsafe(32), allowed_users=frozenset({123}),
                        ai_mode="openai", openai_api_key=secrets.token_urlsafe(32),
                        llm_model="offline-fixture", stt_model="gpt-4o-mini-transcribe")

    def telegram(request):
        if request.url.path.endswith("getFile"):
            return httpx.Response(200, json=FileResponse(ok=True, result=TelegramFile(
                file_id="file1", file_unique_id="unique1", file_size=len(AUDIO), file_path="voice/demo.oga",
            )).model_dump())
        if "/file/bot" in request.url.path:
            return httpx.Response(200, content=AUDIO)
        if request.url.path.endswith("sendMessage"):
            reply = validate_json(TextRequest, request.content)
            evidence.replies.append(reply.text)
            if reply.reply_markup is not None:
                evidence.confirmation_data = reply.reply_markup.inline_keyboard[0][0].callback_data
        elif request.url.path.endswith("answerCallbackQuery"):
            evidence.callback_acks += 1
            return httpx.Response(200, json=CallbackAnswerResponse(ok=True, result=True).model_dump())
        elif request.url.path.endswith("sendDocument"):
            assert b"%PDF-" in request.content and b"test-invoice.pdf" in request.content
            evidence.pdf_deliveries += 1
        else:
            raise AssertionError("Unexpected Telegram method")
        return httpx.Response(200, json=SendResponse(ok=True, result=SentMessage(
            message_id=1, chat=SentChat(id=123),
        )).model_dump())

    def ai(request):
        if request.url.path.endswith("transcriptions"):
            evidence.stt_calls += 1
            return httpx.Response(200, json=Transcript(
                text="Выстави, пожалуйста, счёт ООО Ромашка за сентябрь 2026",
                logprobs=[TokenConfidence(token="fixture", logprob=-0.1)],
            ).model_dump())
        assert request.url.path.endswith("responses")
        evidence.llm_calls += 1
        extraction = Extraction(action="create_invoice", client="ООО Ромашка", year=2026, month=9)
        return httpx.Response(200, json=ModelResponse(status="completed", output=[OutputMessage(
            type="message", role="assistant", status="completed",
            content=[OutputText(type="output_text", text=extraction.model_dump_json())],
        )]).model_dump())

    app = create_app(settings, backend=backend, telegram_transport=httpx.MockTransport(telegram),
                     ai_transport=httpx.MockTransport(ai))
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(app, access_log=False, log_level="warning",
                                              timeout_graceful_shutdown=3))
        thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
        thread.start()
        try:
            for _ in range(100):
                if server.started:
                    break
                if not thread.is_alive():
                    raise RuntimeError("Demo server failed to start")
                time.sleep(0.05)
            else:
                raise RuntimeError("Demo server startup timeout")
            with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=5, trust_env=False,
                              headers={"X-Telegram-Bot-Api-Secret-Token": settings.webhook_secret.get_secret_value()}) as client:
                def send(update_id, *, text=None, voice=None):
                    update = Update(update_id=update_id, message=Message(
                        message_id=update_id, sender=Sender(id=123, is_bot=False),
                        chat=Chat(id=123, type="private"), text=text, voice=voice,
                    ))
                    response = client.post("/telegram/webhook", json=update.model_dump(by_alias=True))
                    assert response.status_code == 200

                def press(update_id, data):
                    update = Update(update_id=update_id, callback_query=CallbackQuery(
                        id=f"callback-{update_id}", sender=Sender(id=123, is_bot=False),
                        message=CallbackMessage(message_id=1, chat=Chat(id=123, type="private")),
                        data=data,
                    ))
                    response = client.post("/telegram/webhook", json=update.model_dump(by_alias=True))
                    assert response.status_code == 200

                voice = Voice(file_id="file1", file_unique_id="unique1", duration=10,
                              mime_type="audio/ogg", file_size=len(AUDIO))
                send(1, voice=voice)
                send(1, voice=voice)
                assert not backend.documents
                assert evidence.confirmation_data is not None
                assert "/confirm" not in evidence.replies[-1]
                press(2, evidence.confirmation_data)
                press(2, evidence.confirmation_data)
                send(3, text="Сформируй счёт для ООО Ромашка за сентябрь 2026")
                press(4, evidence.confirmation_data)
                assert len(backend.documents) == 1
                assert evidence.stt_calls == evidence.llm_calls == 1
                assert evidence.pdf_deliveries == 1
                assert evidence.callback_acks == 2
                assert next(iter(backend.documents.values())).posted
            print("OFFLINE E2E OK: voice -> STT -> LLM -> confirmation button -> fake 1C -> PDF")
            print("Repeated update: no new AI call or delivery. Repeated command: no second PDF.")
            print("Documents: 1. PDF deliveries: 1. No live Telegram/OpenAI/1C calls.")
        finally:
            server.should_exit = True
            thread.join(timeout=5)
            if thread.is_alive():
                raise RuntimeError("Demo server did not stop")


if __name__ == "__main__":
    main()
