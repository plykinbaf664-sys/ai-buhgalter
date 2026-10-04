import asyncio
import hashlib
import hmac
import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException, Request
from openai import AsyncOpenAI

from app.ai import CommandInterpreter
from app.bot import Bot, Receipt
from app.config import Settings
from app.domain import OneC
from app.fake_onec import FakeOneC
from app.model_selection import OpenAIModelSelector
from app.service import InvoiceService, event
from app.telegram import DeliveryFailure, Telegram
from app.telegram_models import Health, Update, WebhookAck
from app.voice import SpeechToText
from app.validation import validate_json

MAX_RECEIPTS = 10_000

def create_app(settings: Settings | None = None, *, backend: OneC | None = None,
               telegram_transport: httpx.AsyncBaseTransport | None = None,
               ai_transport: httpx.AsyncBaseTransport | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    service = InvoiceService(backend if backend is not None else FakeOneC(settings.fake_onec_fault),
                             allow_real_writes=settings.onec_write_enabled)
    # Stage-1 mock only, bounded and never evicted during process lifetime.
    # Refuse overflow rather than silently forgetting deduplication records.
    receipts: dict[int, Receipt] = {}
    gate = asyncio.Lock()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logging.basicConfig(level=logging.INFO, format="%(message)s")
        logging.getLogger("invoices").setLevel(logging.INFO)
        async with httpx.AsyncClient(
            transport=telegram_transport, timeout=httpx.Timeout(10, connect=3),
            follow_redirects=False, trust_env=False,
        ) as client, httpx.AsyncClient(
            transport=ai_transport, timeout=httpx.Timeout(20, connect=3),
            follow_redirects=False, trust_env=False,
        ) as ai_client:
            telegram = Telegram(settings.token.get_secret_value(), client)
            openai_client = None
            try:
                # Injected transports are the deterministic offline seam used by
                # tests; the real process uses the official SDK path.
                use_openai_sdk = settings.ai_mode == "openai" and ai_transport is None
                if use_openai_sdk:
                    openai_client = AsyncOpenAI(
                        api_key=settings.openai_api_key.get_secret_value(),
                        base_url="https://api.openai.com/v1",
                        timeout=20,
                        max_retries=0,
                    )
                model_selector = OpenAIModelSelector(openai_client) if openai_client is not None else None
                interpreter = (CommandInterpreter(
                    ai_client, settings.openai_api_key, settings.llm_model, sdk_client=openai_client,
                    model_selector=model_selector if settings.llm_model == "auto" else None,
                ) if settings.ai_mode == "openai" else CommandInterpreter())
                speech = (SpeechToText(
                    ai_client, settings.openai_api_key, settings.stt_model, sdk_client=openai_client,
                    model_selector=model_selector if settings.stt_model == "auto" else None,
                ) if settings.ai_mode == "openai" else None)
                app.state.bot = Bot(service, telegram, interpreter, speech)
                yield
            finally:
                if openai_client is not None:
                    await openai_client.close()

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    @app.get("/healthz")
    async def health():
        return Health()

    @app.post("/telegram/webhook")
    async def webhook(request: Request):
        supplied = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if not hmac.compare_digest(supplied.encode(), settings.webhook_secret.get_secret_value().encode()):
            raise HTTPException(403, "Forbidden")
        async def read_body():
            body = bytearray()
            async for chunk in request.stream():
                if len(body) + len(chunk) > 32_768:
                    raise HTTPException(413, "Update too large")
                body.extend(chunk)
            return body
        try:
            body = await asyncio.wait_for(read_body(), timeout=5)
        except asyncio.TimeoutError:
            raise HTTPException(408, "Request body timeout") from None
        try:
            update = validate_json(Update, body)
        except (ValueError, RecursionError):
            # Never echo validation errors, which may contain private input.
            raise HTTPException(400, "Invalid update") from None
        message = update.message
        callback = update.callback_query
        actor = message if message is not None else callback
        if actor is None:
            return WebhookAck()
        uid = actor.sender.id
        request_id = f"tg-{update.update_id}"
        chat = message.chat if message is not None else callback.message.chat if callback.message else None
        if (uid not in settings.allowed_users or actor.sender.is_bot or chat is None
                or chat.type != "private" or chat.id != uid
                or (message is not None and (message.sender_chat is not None
                                             or message.forward_origin is not None))):
            event(request_id=request_id, user_id=uid, stage="authorize", status="denied")
            return WebhookAck()
        try:
            await asyncio.wait_for(gate.acquire(), timeout=0.1)
        except asyncio.TimeoutError:
            raise HTTPException(503, "Busy") from None
        try:
            fingerprint = hashlib.sha256(update.model_dump_json(by_alias=True).encode()).hexdigest()
            receipt = receipts.get(update.update_id)
            if receipt is None:
                if len(receipts) >= MAX_RECEIPTS:
                    raise HTTPException(503, "Mock capacity reached")
                receipt = receipts[update.update_id] = Receipt(fingerprint=fingerprint)
            elif not hmac.compare_digest(receipt.fingerprint, fingerprint):
                event(request_id=request_id, user_id=uid, stage="deduplicate", status="conflict")
                raise HTTPException(409, "Update identity conflict")
            if receipt.done:
                event(request_id=request_id, user_id=uid, stage="deduplicate", status="duplicate")
                return WebhookAck()
            if receipt.attempts >= 3:
                # Do not acknowledge an undelivered result as success.
                event(request_id=request_id, user_id=uid, stage="delivery", status="exhausted")
                raise HTTPException(503, "Delivery attempts exhausted; operator action required")
            receipt.attempts += 1
            try:
                if callback is not None and not await request.app.state.bot.telegram.answer_callback(callback.id):
                    event(request_id=request_id, user_id=uid, stage="callback_ack", status="error")
                await request.app.state.bot.handle(actor, receipt, request_id)
            except DeliveryFailure:
                event(request_id=request_id, user_id=uid, stage="delivery", status="error",
                      error="DeliveryFailure")
                raise HTTPException(503, "Delivery not confirmed") from None
            except Exception as exc:
                # Final boundary: framework tracebacks must not leak external values.
                event(request_id=request_id, user_id=uid, stage="internal", status="error",
                      error=type(exc).__name__)
                raise HTTPException(500, "Operation not confirmed; contact operator") from None
            receipt.done = True
            receipt.prepared = None
            receipt.response_text = None
            receipt.response_markup = None
            event(request_id=request_id, user_id=uid, stage="update", status="handled")
            return WebhookAck()
        finally:
            gate.release()

    return app
