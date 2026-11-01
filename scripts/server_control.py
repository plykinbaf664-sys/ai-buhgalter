"""Readonly server readiness and explicit Telegram webhook cutover/rollback.

Run with the project's protected environment. Never prints provider data or URLs
containing tokens. FirstBit traffic is GET-only; register/restore mutate Telegram
configuration, not accounting data. No Telegram updates are discarded.
"""
import argparse
import asyncio
from datetime import date
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx
from openai import AsyncOpenAI

from app.ai import CommandInterpreter
from app.firstbit import FirstBit, FirstBitSettings
from app.http import bounded_request, disable_wire_logs
from app.intent import InvoiceDraft, merge_intent
from app.model_selection import OpenAIModelSelector
from app.telegram_models import Health
from app.validation import validate_json
from scripts.register_demo_webhook import WebhookInfoResponse, WebhookSetResponse
from scripts.run_server import check_config


def public_url(value: str) -> str:
    p = urlsplit(value)
    if (p.scheme != "https" or not p.hostname or p.username or p.password
            or p.port is not None or p.query or p.fragment
            or p.path not in ("", "/", "/ai-buhgalteria", "/ai-buhgalteria/")
            or not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", p.hostname)
            or "." not in p.hostname or any(c.isspace() for c in value)):
        raise ValueError("Expected HTTPS project base URL without credentials/query")
    return value.rstrip("/")


def save_private(path: Path, raw: bytes) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    # Never overwrite the original rollback evidence on repeated registration.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(raw)


async def run(args):
    disable_wire_logs()
    settings = check_config()
    public = public_url(args.public_url)
    base = "https://api.telegram.org/bot" + settings.token.get_secret_value() + "/"
    async with httpx.AsyncClient(timeout=25, follow_redirects=False, trust_env=False) as client:
        async def info():
            return validate_json(WebhookInfoResponse,
                await bounded_request(client, "GET", base + "getWebhookInfo"))

        async def health(target):
            result = validate_json(Health, await bounded_request(client, "GET", target + "/healthz"))
            if result.mode != getattr(settings, 'mode', 'firstbit_readonly'):
                raise ValueError("Configured FirstBit mode health required")

        if args.action == "restore":
            previous = validate_json(WebhookInfoResponse, args.backup.read_bytes())
            if not previous.result.url:
                raise ValueError("No previous webhook; manual rollback required")
            # Previous registration used the same unchanged secret and one connection.
            destination = previous.result.url
            if not destination.endswith("/telegram/webhook"):
                raise ValueError("Unexpected previous webhook")
            await health(public_url(destination.removesuffix("/telegram/webhook")))
            validate_json(WebhookSetResponse, await bounded_request(client, "POST", base + "setWebhook", json={
                "url": destination, "secret_token": settings.webhook_secret.get_secret_value(),
                "allowed_updates": ["message", "callback_query"], "max_connections": 1,
                "drop_pending_updates": False,
            }))
            if (await info()).result.url != destination:
                raise ValueError("Rollback not confirmed")
            return {"result": "RESTORED", "discarded_updates": False, "writes": False}

        await health("http://127.0.0.1:8107")
        await health(public)
        unsigned = await client.post(public + "/telegram/webhook", json={})
        if unsigned.status_code != 403:
            raise ValueError("Unsigned webhook must be denied")
        status = await info()
        if args.action == "register":
            if status.result.url != public + "/telegram/webhook":
                save_private(args.backup, status.model_dump_json().encode())
            validate_json(WebhookSetResponse, await bounded_request(client, "POST", base + "setWebhook", json={
                "url": public + "/telegram/webhook", "secret_token": settings.webhook_secret.get_secret_value(),
                "allowed_updates": ["message", "callback_query"], "max_connections": 1,
                "drop_pending_updates": False,
            }))
            status = await info()
            if status.result.url != public + "/telegram/webhook":
                raise ValueError("Webhook registration not confirmed")
        if args.deep:
            backend = FirstBit(FirstBitSettings.from_env(writable=getattr(settings, 'mode', 'firstbit_readonly') == 'firstbit_write'))
            try:
                await backend.check_metadata()
            finally:
                await backend.aclose()
            async with AsyncOpenAI(api_key=settings.openai_api_key.get_secret_value(),
                                   timeout=25, max_retries=0) as sdk:
                interpreter = CommandInterpreter(sdk_client=sdk, model=settings.llm_model,
                    model_selector=OpenAIModelSelector(sdk) if settings.llm_model == "auto" else None,
                    send_draft_context=False)
                parsed = await interpreter.interpret("Поменяй дату на 15 ноября 2026 года", InvoiceDraft())
                if parsed.intent is None or merge_intent(InvoiceDraft(), parsed.intent).invoice_date != date(2026, 11, 15):
                    raise ValueError("AI grounded date check failed")
        return {"result": "READY", "public_health": True, "unsigned_webhook_denied": True,
                "webhook_matches": status.result.url == public + "/telegram/webhook",
                "pending_updates": status.result.pending_update_count,
                "production_metadata_GET_and_real_AI": bool(args.deep), "writes": False}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=("check", "register", "restore"))
    p.add_argument("--public-url", required=True)
    p.add_argument("--backup", type=Path, default=Path("/srv/ai-buhgalteria/state/previous-webhook.json"))
    p.add_argument("--deep", action="store_true")
    args = p.parse_args()
    try:
        print(json.dumps(asyncio.run(run(args))))
    except Exception as exc:
        print(json.dumps({"result": "BLOCKED", "error_type": type(exc).__name__, "writes": False}))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
