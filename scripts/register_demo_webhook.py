"""Register the local demo's HTTPS webhook; never print token-bearing API URLs."""
import asyncio
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit
from typing import Literal

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import httpx
from pydantic import Field

from app.config import Settings
from app.domain import ExternalModel
from app.http import bounded_request, disable_wire_logs
from app.telegram_models import Health, SuccessResponse
from app.validation import validate_json
from scripts.run_local import load_local_env


class DemoState(ExternalModel):
    app_pid: int = Field(gt=0)
    workspace: str = Field(min_length=1, max_length=1000)
    public_url: str = Field(min_length=1, max_length=2048)


class WebhookInfo(ExternalModel):
    url: str = Field(max_length=2048)
    pending_update_count: int = Field(ge=0)


class WebhookInfoResponse(SuccessResponse):
    result: WebhookInfo


class WebhookSetResponse(SuccessResponse):
    result: Literal[True]


def validate_public_url(public: str) -> str:
    parsed = urlsplit(public)
    if (parsed.scheme != "https" or not parsed.hostname
            or not re.fullmatch(r"(?!api\.|www\.)[a-z0-9-]+\.(?:trycloudflare\.com|ngrok-free\.app|ngrok-free\.dev|ngrok\.app|ngrok\.io)", parsed.hostname)
            or parsed.username or parsed.password or parsed.path not in ("", "/")
            or parsed.port or parsed.query or parsed.fragment):
        raise ValueError("Expected the demo's HTTPS tunnel root")
    return public.rstrip('/')


async def register_webhook(public: str, settings: Settings):
    disable_wire_logs()
    if settings.mode != "firstbit_readonly" or settings.onec_write_enabled:
        raise ValueError("Read-only mode required")
    public = validate_public_url(public)
    async with httpx.AsyncClient(timeout=20, follow_redirects=False, trust_env=False) as client:
        health = validate_json(Health, await bounded_request(client, "GET", public + "/healthz",
            headers={"ngrok-skip-browser-warning": "1"}))
        if health.mode != "firstbit_readonly":
            raise ValueError("Unexpected public app health")
        base = "https://api.telegram.org/bot" + settings.token.get_secret_value() + "/"
        before = await bounded_request(client, "GET", base + "getWebhookInfo")
        validate_json(WebhookInfoResponse, before)
        (ROOT / ".local/runtime/previous-webhook-info.json").write_bytes(before)
        validate_json(WebhookSetResponse, await bounded_request(client, "POST", base + "setWebhook", json={
            "url": public + "/telegram/webhook", "secret_token": settings.webhook_secret.get_secret_value(),
            "allowed_updates": ["message", "callback_query"], "max_connections": 1,
        }))
        info = validate_json(WebhookInfoResponse, await bounded_request(client, "GET", base + "getWebhookInfo"))
        if info.result.url != public + "/telegram/webhook":
            raise ValueError("Webhook registration did not persist")
        print(json.dumps({"webhook": "READY", "app_mode": settings.mode,
                          "pending_updates_dropped": False, "writes_enabled": False}))


async def main():
    load_local_env()
    state = validate_json(DemoState, (ROOT / '.local/runtime/demo-processes.json').read_text(encoding='utf-8-sig'))
    await register_webhook(state.public_url, Settings.from_env())


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:
        print("DEMO_WEBHOOK_FAILED: " + type(exc).__name__, file=sys.stderr)
        raise SystemExit(1)
