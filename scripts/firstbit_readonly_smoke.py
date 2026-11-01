"""Application smoke. Default: offline. --live: FirstBit GET only, no Telegram/OpenAI."""
import argparse
import asyncio
import json
import os
from datetime import date
from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx
from fastapi.testclient import TestClient

from app.config import Settings
from app.domain import InvoiceCommand
from app.firstbit import FirstBit, FirstBitSettings
from app.main import create_app
from app.service import InvoiceService
from scripts.firstbit_fixture import FirstBitFixture


def offline_smoke():
    fixture = FirstBitFixture()
    replies, ai_calls = [], []
    audio = b"OggS" + b"\x00" * 24 + b"OpusHead" + b"\x00" * 32

    def telegram(request):
        if request.url.path.endswith("getFile"):
            return httpx.Response(200, json={"ok": True, "result": {
                "file_id": "synthetic", "file_unique_id": "synthetic", "file_size": len(audio), "file_path": "voice/smoke.oga"}})
        if "/file/bot" in request.url.path:
            return httpx.Response(200, content=audio)
        if request.url.path.endswith("answerCallbackQuery"):
            return httpx.Response(200, json={"ok": True, "result": True})
        assert request.url.path.endswith("sendMessage"), "PDF/mutation delivery attempted"
        replies.append(json.loads(request.content))
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 1, "chat": {"id": 123}}})

    def ai(request):
        ai_calls.append(request)
        if request.url.path.endswith("transcriptions"):
            return httpx.Response(200, json={"text": "Выстави, пожалуйста, счёт ООО Синтетика за сентябрь 2026",
                "logprobs": [{"token": "synthetic", "logprob": -.01}]})
        payload = json.loads(request.content)
        source = payload["input"][-1]["content"]
        if "цена" in source:
            context = payload["input"][1]["content"]
            assert "Bookkeeping synthetic row" not in context and "TEST-TRN" not in context
            assert '"services":[]' in context
            result = {"action": "edit", "client_change": None, "date_change": None, "period_change": None,
                "line_changes": [], "tax_change": None, "previous_hint_request": None, "clarification": None,
                "preview_changes": [
                    {"kind": "price", "line_number": 1, "amount_span": {"first_word": 5, "last_word": 5}},
                    {"kind": "tax", "line_number": 1, "source_span": {"first_word": 6, "last_word": 7},
                        "mode": "rate", "rate_span": {"first_word": 7, "last_word": 7}, "profile_span": None},
                    {"kind": "description", "line_number": 1, "description_span": {"first_word": 9, "last_word": 10}}]}
        elif "количество" in source:
            # Production-derived rows, quantities, TRN and invoice refs must never reach AI.
            context = payload["input"][1]["content"]
            assert "Bookkeeping synthetic row" not in context
            assert "Синтетика" not in context and "TEST-TRN" not in context
            assert '"services":[]' in context
            result = {"action": "edit", "client_change": None, "date_change": None, "period_change": None,
                "line_changes": [{"kind": "quantity", "line_number": 2,
                    "quantity": {"source_span": {"first_word": 6, "last_word": 6}, "value": 3}}],
                "tax_change": None, "previous_hint_request": None, "clarification": None}
        else:
            result = {"action": "create_invoice", "client": "ООО Синтетика", "year": 2026, "month": 9}
        return httpx.Response(200, json={"status": "completed", "output": [{"type": "message", "role": "assistant",
            "status": "completed", "content": [{"type": "output_text", "text": json.dumps(result)}]}]})

    settings = Settings(token="123:" + "x" * 32, webhook_secret="x" * 32, allowed_users=frozenset({123}),
        mode="firstbit_readonly", ai_mode="openai", openai_api_key="synthetic-only",
        llm_model="offline-fixture", stt_model="gpt-4o-mini-transcribe")
    with patch.dict(os.environ, fixture.env()):
        app = create_app(settings, telegram_transport=httpx.MockTransport(telegram),
            ai_transport=httpx.MockTransport(ai), firstbit_transport=httpx.MockTransport(fixture.respond))
    with TestClient(app) as client:
        client.headers["X-Telegram-Bot-Api-Secret-Token"] = "x" * 32
        assert client.get("/healthz").json()["mode"] == "firstbit_readonly"

        def send(n, text=None, voice=None):
            message = {"message_id": n, "from": {"id": 123, "is_bot": False}, "chat": {"id": 123, "type": "private"}}
            message.update({"text": text} if text is not None else {"voice": voice})
            assert client.post("/telegram/webhook", json={"update_id": n, "message": message}).status_code == 200

        def press(n, data):
            assert client.post("/telegram/webhook", json={"update_id": n, "callback_query": {"id": str(n),
                "from": {"id": 123, "is_bot": False}, "message": {"message_id": 1,
                    "chat": {"id": 123, "type": "private"}}, "data": data}}).status_code == 200

        def token():
            return app.state.bot.pending[123].token

        send(1, text="Сформируй счёт для ООО Синтетика за сентябрь 2026")
        original = app.state.bot.pending[123].prepared
        assert len(original.preview.lines) == 2
        assert original.preview.total == 3150
        assert "READ-ONLY" in replies[-1]["text"]
        assert "Цены проверены заново" not in replies[-1]["text"]
        old = token()
        send(2, text="Во второй строке поставь количество три")
        assert token() != old
        assert app.state.bot.pending[123].prepared.preview.total == 4200
        press(3, "invoice:confirm:" + old)
        assert "устарело" in replies[-1]["text"]
        valid = token()
        source = fixture.records["Document_InventoryExpense"][0]
        source["Inventory"][1] = fixture.line(2, "2", "1200")
        source["DocumentAmount"] = "3570.00"
        press(4, "invoice:confirm:" + valid)
        assert "Данные 1С изменились" in replies[-1]["text"]
        assert app.state.bot.pending[123].prepared.preview.total == 4830
        press(5, "invoice:confirm:" + token())
        assert "Preview повторно проверен" in replies[-1]["text"]
        assert not app.state.bot.recoveries
        send(6, voice={"file_id": "synthetic", "file_unique_id": "synthetic", "duration": 10,
            "mime_type": "audio/ogg", "file_size": len(audio)})
        assert 123 in app.state.bot.pending
        fixture.status = 503
        press(7, "invoice:confirm:" + token())
        assert "Создание документа не запускалось" in replies[-1]["text"]
        assert not app.state.bot.pending and not app.state.bot.recoveries
        fixture.status = None
        send(8, text="Сформируй счёт для ООО Синтетика за сентябрь 2026")
        press(9, "invoice:cancel:" + token())
        assert not app.state.bot.pending and not app.state.bot.contexts
        count = len(fixture.calls)
        send(6, voice={"file_id": "synthetic", "file_unique_id": "synthetic", "duration": 10,
            "mime_type": "audio/ogg", "file_size": len(audio)})
        assert len(fixture.calls) == count
        send(10, text="Сформируй счёт для ООО Синтетика за сентябрь 2026")
        before = app.state.bot.pending[123].prepared
        send(11, text="В первой строке цена 1500, НДС 5%, название Новое обслуживание")
        edited = app.state.bot.pending[123].prepared
        assert edited.preview.lines[0].price == 1500 and edited.preview.lines[0].tax.rate == 5
        assert edited.preview.lines[0].description == "Новое обслуживание"
        assert edited.preview.lines[0].service_id == before.preview.lines[0].service_id
        assert edited.preview.lines[1] == before.preview.lines[1]
        assert edited.operation_id == before.operation_id and edited.preview.digest != before.preview.digest
        assert "Изменено пользователем" in replies[-1]["text"]
        press(12, "invoice:confirm:" + token())
        assert "документ не создавался" in replies[-1]["text"]
    assert all(r.method == "GET" for r in fixture.calls)
    return {"result": "PASS", "FirstBit": "synthetic GET only", "firstbit_gets": len(fixture.calls),
        "ai_calls": len(ai_calls), "production_contact": False, "mutations": 0, "pdf_deliveries": 0,
        "verified": "text/voice -> STT/LLM -> FirstBit -> preview; quantity/price/VAT/description edits, stale token, refresh, verify, cancel, dedupe"}


async def live_smoke(*, save_preview: bool = False):
    if os.environ.get("ONEC_WRITE_ENABLED", "false") != "false":
        raise ValueError("ONEC_WRITE_ENABLED must be false")
    # Do not print client names, records, amounts, IDs, endpoint, credentials or preview.
    client = os.environ.get("FIRSTBIT_SMOKE_CLIENT", "")
    day = os.environ.get("FIRSTBIT_SMOKE_INVOICE_DATE", "")
    if not client or not day:
        raise ValueError("Set FIRSTBIT_SMOKE_CLIENT and FIRSTBIT_SMOKE_INVOICE_DATE (YYYY-MM-DD)")
    backend = FirstBit(FirstBitSettings.from_env())
    try:
        service = InvoiceService(backend, timeout=60)
        prepared = await service.prepare(InvoiceCommand(client=client, invoice_date=date.fromisoformat(day)), "readonly-smoke", 1)
        refreshed = await service.refresh(prepared, "readonly-smoke-refresh", 1)
        if refreshed != prepared:
            raise ValueError("Source changed during smoke; review and rerun")
        if save_preview:
            from app.presentation import preview_text
            output = Path('.local/firstbit/readonly-preview.txt')
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text("READ-ONLY: document not created.\n\n" + preview_text(prepared.preview), encoding="utf-8")
        return {"result": "PASS", "FirstBit": "live GET only", "production_contact": True,
            "lines": len(prepared.preview.lines), "mutations": 0, "pdf_deliveries": 0,
            "Telegram": "not contacted", "OpenAI": "not contacted"}
    finally:
        await backend.aclose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="GET-only real FirstBit service prepare/refresh using ENV")
    parser.add_argument("--save-preview", action="store_true", help="With --live, save private review text under ignored .local/firstbit/")
    args = parser.parse_args()
    if args.save_preview and not args.live:
        parser.error("--save-preview requires --live")
    try:
        result = asyncio.run(live_smoke(save_preview=args.save_preview)) if args.live else offline_smoke()
    except Exception as exc:
        # Never print raw provider/config exception text or tracebacks.
        print(json.dumps({"result": "BLOCKED", "error_type": type(exc).__name__,
            "guidance": "See docs/firstbit/READONLY_PIPELINE.md; no mutation path exists."}))
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
