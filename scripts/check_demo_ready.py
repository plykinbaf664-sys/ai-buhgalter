"""Private pre-demo connectivity check; FirstBit GET only. --deep checks one AI patch."""
import argparse
import asyncio
import json
from pathlib import Path
import re
import sys
from datetime import date

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import httpx
from openai import AsyncOpenAI
from app.ai import CommandInterpreter
from app.config import Settings
from app.domain import StrictModel
from app.firstbit import FirstBit, FirstBitSettings
from app.http import bounded_request, disable_wire_logs
from app.intent import InvoiceDraft
from app.telegram_models import Health
from app.validation import validate_json
from scripts.register_demo_webhook import DemoState, WebhookInfoResponse, validate_public_url
from scripts.run_local import ROOT, load_local_env
from app.model_selection import OpenAIModelSelector


class Check(StrictModel):
    service: str
    ok: bool
    error: str | None = None


async def check_ready(deep: bool):
    load_local_env()
    disable_wire_logs()
    settings = Settings.from_env()
    if settings.mode != "firstbit_readonly" or settings.onec_write_enabled or settings.ai_mode != 'openai':
        raise ValueError("Read-only runtime required")
    state = validate_json(DemoState, (ROOT / '.local/runtime/demo-processes.json').read_text(encoding='utf-8-sig'))
    validate_public_url(state.public_url)
    backend = FirstBit(FirstBitSettings.from_env())
    async with httpx.AsyncClient(timeout=8, trust_env=False, follow_redirects=False) as client, AsyncOpenAI(
            api_key=settings.openai_api_key.get_secret_value(), base_url='https://api.openai.com/v1',
            timeout=10, max_retries=0) as sdk:
        async def health(url):
            result = validate_json(Health, await bounded_request(client, 'GET', url, deadline=10,
                headers={'ngrok-skip-browser-warning': '1'}))
            if result.mode != 'firstbit_readonly':
                raise ValueError('Unexpected mode')
        async def webhook():
            raw = await bounded_request(client, 'GET', 'https://api.telegram.org/bot' + settings.token.get_secret_value() + '/getWebhookInfo', deadline=10)
            result = validate_json(WebhookInfoResponse, raw).result
            if result.url != state.public_url + '/telegram/webhook' or result.pending_update_count:
                raise ValueError('Webhook mismatch or undelivered queue')
        async def ai():
            selector = OpenAIModelSelector(sdk)
            model = await selector.llm() if settings.llm_model == 'auto' else settings.llm_model
            if settings.stt_model == 'auto':
                await selector.stt()
            if deep:
                result = await CommandInterpreter(api_key=settings.openai_api_key, model=model,
                    sdk_client=sdk, send_draft_context=False).interpret('Поставь дату на 5 ноября 2026',
                        InvoiceDraft(client='Synthetic demo context', invoice_date=date.today()))
                if result.intent is None or result.intent.invoice_date is None or result.intent.invoice_date.day != 5:
                    raise ValueError('Unexpected grounded patch')
        async def run(name, action):
            try:
                await action()
                return Check(service=name, ok=True)
            except Exception as exc:
                return Check(service=name, ok=False, error=getattr(exc, 'code', type(exc).__name__))
        try:
            results = await asyncio.gather(
                run('local', lambda: health('http://127.0.0.1:8000/healthz')),
                run('public', lambda: health(state.public_url + '/healthz')),
                run('telegram_webhook_queue', webhook), run('firstbit_metadata_GET', backend.check_metadata),
                run('openai_grounded_patch' if deep else 'openai_catalog', ai))
        finally:
            await backend.aclose()
    ok = all(item.ok for item in results)
    print(json.dumps({'result': 'READY' if ok else 'BLOCKED', 'checks': [r.model_dump() for r in results], 'writes_enabled': False}))
    return 0 if ok else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--deep', action='store_true', help='Also make one paid AI parsing request; no FirstBit mutation')
    args = parser.parse_args()
    try:
        raise SystemExit(asyncio.run(check_ready(args.deep)))
    except Exception as exc:
        print(json.dumps({'result': 'BLOCKED', 'error': type(exc).__name__}))
        raise SystemExit(1)
