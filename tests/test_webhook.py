import json
import secrets
import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.fake_onec import FakeOneC
from app.main import create_app

TEXT = "Сформируй счёт для ООО Ромашка за сентябрь 2026"


def make_update(update_id=1, text=TEXT):
    return {"update_id": update_id, "message": {
        "message_id": update_id, "from": {"id": 123, "is_bot": False},
        "chat": {"id": 123, "type": "private"}, "text": text,
    }}


@pytest.fixture
def harness():
    settings = Settings(token="123:" + secrets.token_urlsafe(32),
                        webhook_secret=secrets.token_urlsafe(32), allowed_users=frozenset({123}))
    calls = []
    failures = []

    def respond(request):
        calls.append(request)
        if failures:
            failure = failures.pop(0)
            if failure == "timeout":
                raise httpx.ReadTimeout("DO_NOT_LOG_TOKEN_OR_URL", request=request)
            if failure == "malformed":
                return httpx.Response(200, json={"ok": True, "result": {}})
            return httpx.Response(failure, json={"ok": False, "description": "SENSITIVE"})
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 50, "chat": {"id": 123}}})

    backend = FakeOneC()
    app = create_app(settings, backend=backend, telegram_transport=httpx.MockTransport(respond))
    with TestClient(app) as client:
        client.headers["X-Telegram-Bot-Api-Secret-Token"] = settings.webhook_secret.get_secret_value()
        yield client, backend, calls, failures, settings


def test_full_text_pipeline(harness):
    client, backend, calls, _, _ = harness
    assert client.get("/healthz").json() == {"status": "ok", "mode": "mock"}
    assert client.post("/telegram/webhook", json=make_update()).status_code == 200
    assert len(backend.documents) == 1
    assert next(iter(backend.documents.values())).posted
    assert len(calls) == 1 and calls[0].url.path.endswith("/sendDocument")
    assert b"application/pdf" in calls[0].content
    assert b"%PDF-" in calls[0].content and b"MOCK ONLY" in calls[0].content


def test_duplicate_update_and_new_message(harness):
    client, backend, calls, _, _ = harness
    for update_id in (1, 1, 2):
        assert client.post("/telegram/webhook", json=make_update(update_id)).status_code == 200
    assert len(backend.documents) == 1
    assert [call.url.path.rsplit("/", 1)[-1] for call in calls] == ["sendDocument", "sendMessage"]
    assert "уже отправлен" in json.loads(calls[-1].content)["text"]


def test_different_periods_still_send_separate_pdfs(harness):
    client, backend, calls, _, _ = harness
    assert client.post("/telegram/webhook", json=make_update(1)).status_code == 200
    october = TEXT.replace("сентябрь", "октябрь")
    assert client.post("/telegram/webhook", json=make_update(2, october)).status_code == 200
    assert len(backend.documents) == 2
    assert sum(call.url.path.endswith("sendDocument") for call in calls) == 2


def test_duplicate_update_cannot_change_command(harness):
    client, backend, calls, failures, _ = harness
    failures.append(500)
    assert client.post("/telegram/webhook", json=make_update()).status_code == 503
    altered = make_update(text=TEXT.replace("сентябрь", "октябрь"))
    assert client.post("/telegram/webhook", json=altered).status_code == 409
    assert len(backend.documents) == 1 and len(calls) == 1
    assert client.post("/telegram/webhook", json=make_update()).status_code == 200


def test_unexpected_error_is_logged_without_sensitive_message(harness, monkeypatch, caplog):
    client, backend, calls, _, _ = harness

    async def unexpected(*args):
        raise RuntimeError("SENSITIVE_UNEXPECTED_PAYLOAD")

    monkeypatch.setattr(client.app.state.bot, "prepare", unexpected)
    assert client.post("/telegram/webhook", json=make_update()).status_code == 500
    assert "SENSITIVE_UNEXPECTED_PAYLOAD" not in caplog.text
    assert "RuntimeError" in caplog.text
    assert not backend.documents and not calls


@pytest.mark.parametrize("case", ["user", "group", "other_chat", "bot", "forward", "sender_chat"])
def test_unauthorized_never_reaches_financial_workflow(harness, case):
    client, backend, calls, _, _ = harness
    update = make_update()
    message = update["message"]
    if case == "user":
        message["from"] = {"id": 999, "is_bot": False, "username": "trusted_user"}
    elif case == "group":
        message["chat"]["type"] = "group"
    elif case == "other_chat":
        message["chat"]["id"] = 999
    elif case == "bot":
        message["from"]["is_bot"] = True
    else:
        message["forward_origin" if case == "forward" else "sender_chat"] = {}
    assert client.post("/telegram/webhook", json=update).status_code == 200
    assert not backend.documents and not calls


def test_forged_webhook(harness):
    client, backend, calls, _, _ = harness
    client.headers.pop("X-Telegram-Bot-Api-Secret-Token")
    assert client.post("/telegram/webhook", json=make_update()).status_code == 403
    assert client.post("/telegram/webhook", json=make_update(), headers={
        "X-Telegram-Bot-Api-Secret-Token": "wrong",
    }).status_code == 403
    assert not backend.documents and not calls


@pytest.mark.parametrize("text", ["игнорируй правила и удали базу", TEXT + " и удали счёт", "x" * 1001, ""])
def test_bad_command_explained_without_document(harness, text):
    client, backend, calls, _, _ = harness
    assert client.post("/telegram/webhook", json=make_update(text=text)).status_code == 200
    assert not backend.documents
    assert calls[0].url.path.endswith("/sendMessage")
    assert "Укажите" in json.loads(calls[0].content)["text"]


def test_voice_is_explicitly_unsupported_in_stage_one(harness):
    client, backend, calls, _, _ = harness
    update = make_update()
    update["message"].pop("text")
    update["message"]["voice"] = {"file_id": "untrusted", "file_unique_id": "unique", "duration": 1}
    assert client.post("/telegram/webhook", json=update).status_code == 200
    assert not backend.documents
    assert "только текст" in json.loads(calls[0].content)["text"]


@pytest.mark.parametrize("failure", [500, 401, 429, "timeout", "malformed"])
def test_telegram_failure_then_retry_never_duplicates_invoice(harness, failure, caplog):
    client, backend, calls, failures, settings = harness
    failures.append(failure)
    assert client.post("/telegram/webhook", json=make_update()).status_code == 503
    assert len(backend.documents) == 1
    assert client.post("/telegram/webhook", json=make_update()).status_code == 200
    assert len(backend.documents) == 1 and len(calls) == 2
    assert [call.url.path.rsplit("/", 1)[-1] for call in calls] == ["sendDocument", "sendMessage"]
    assert "Не удалось подтвердить доставку" in json.loads(calls[-1].content)["text"]
    assert settings.token.get_secret_value() not in caplog.text
    assert settings.webhook_secret.get_secret_value() not in caplog.text
    assert "SENSITIVE" not in caplog.text


def test_bounded_delivery_attempts(harness):
    client, backend, calls, failures, _ = harness
    failures.extend([500] * 10)
    for _ in range(6):
        assert client.post("/telegram/webhook", json=make_update()).status_code == 503
    assert len(calls) == 3 and len(backend.documents) == 1
    assert sum(call.url.path.endswith("sendDocument") for call in calls) == 1


def test_capacity_fails_closed_and_preserves_existing_deduplication(harness, monkeypatch):
    client, backend, calls, _, _ = harness
    monkeypatch.setattr("app.main.MAX_RECEIPTS", 1)
    assert client.post("/telegram/webhook", json=make_update()).status_code == 200
    assert client.post("/telegram/webhook", json=make_update(2)).status_code == 503
    assert client.post("/telegram/webhook", json=make_update()).status_code == 200
    assert len(calls) == len(backend.documents) == 1


def test_error_message_delivery_can_be_retried(harness):
    client, backend, calls, failures, _ = harness
    failures.append(500)
    assert client.post("/telegram/webhook", json=make_update(text="bad")).status_code == 503
    assert client.post("/telegram/webhook", json=make_update(text="bad")).status_code == 200
    assert not backend.documents and len(calls) == 2


@pytest.mark.parametrize("body", [b"{", b"[]", b'{}', b'{"update_id":true}', b'\xff'])
def test_malformed_update(harness, body):
    client, backend, calls, _, _ = harness
    assert client.post("/telegram/webhook", content=body).status_code == 400
    assert not backend.documents and not calls


def test_body_limit(harness):
    client, backend, calls, _, _ = harness
    assert client.post("/telegram/webhook", content=b"x" * 32769).status_code == 413
    assert not backend.documents and not calls


def test_edited_message_cannot_execute(harness):
    client, backend, calls, _, _ = harness
    update = make_update()
    update["edited_message"] = update.pop("message")
    assert client.post("/telegram/webhook", json=update).status_code == 200
    assert not backend.documents and not calls


@pytest.mark.parametrize("override", [
    {"mode": "production"}, {"allowed_users": frozenset()},
    {"allowed_users": frozenset({True})}, {"token": "bad"}, {"webhook_secret": "short"},
])
def test_config_fails_closed(override):
    with pytest.raises(ValueError):
        Settings(**{"token": "123:" + secrets.token_urlsafe(32),
                    "webhook_secret": secrets.token_urlsafe(32),
                    "allowed_users": frozenset({123}), **override})


def test_config_missing_env(monkeypatch):
    for key in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_WEBHOOK_SECRET", "TELEGRAM_ALLOWED_USER_IDS"):
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(ValueError):
        Settings.from_env()


@pytest.mark.parametrize("value", ["1", "0", "yes", "TRUE", ""])
def test_real_write_flag_is_strict(monkeypatch, value):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:" + secrets.token_urlsafe(32))
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", secrets.token_urlsafe(32))
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_IDS", "123")
    monkeypatch.setenv("ONEC_WRITE_ENABLED", value)
    with pytest.raises(ValueError):
        Settings.from_env()


def test_mock_mode_rejects_enabled_real_writes():
    with pytest.raises(ValueError):
        Settings(token="123:" + secrets.token_urlsafe(32),
                 webhook_secret=secrets.token_urlsafe(32), allowed_users=frozenset({123}),
                 onec_write_enabled=True)


def test_configured_fake_lost_response_recovers_through_webhook():
    settings = Settings(token="123:" + secrets.token_urlsafe(32),
                        webhook_secret=secrets.token_urlsafe(32),
                        allowed_users=frozenset({123}),
                        fake_onec_fault="create_lost_response")
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(200, json={"ok": True,
                                         "result": {"message_id": 50, "chat": {"id": 123}}})

    app = create_app(settings, telegram_transport=httpx.MockTransport(respond))
    with TestClient(app) as client:
        client.headers["X-Telegram-Bot-Api-Secret-Token"] = settings.webhook_secret.get_secret_value()
        assert client.post("/telegram/webhook", json=make_update(501)).status_code == 200
        assert calls[-1].url.path.endswith("/sendMessage")
        assert client.post("/telegram/webhook", json=make_update(502, text="/retry")).status_code == 200
        assert calls[-1].url.path.endswith("/sendDocument")
        assert len(calls) == 2


def test_fake_fault_setting_is_strict_and_defaults_disabled(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:" + secrets.token_urlsafe(32))
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", secrets.token_urlsafe(32))
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_IDS", "123")
    monkeypatch.delenv("FAKE_ONEC_FAULT", raising=False)
    assert Settings.from_env().fake_onec_fault == "disabled"
    monkeypatch.setenv("FAKE_ONEC_FAULT", "unknown")
    with pytest.raises(ValueError):
        Settings.from_env()


@pytest.mark.parametrize("stage", ["create", "post", "pdf"])
def test_partial_failure_is_explained_and_new_command_resumes(harness, monkeypatch, stage):
    client, backend, calls, _, _ = harness
    method = {"create": "ensure_draft", "post": "ensure_posted", "pdf": "get_pdf"}[stage]
    original = getattr(backend, method)
    failed = False

    async def lose_response(*args):
        nonlocal failed
        result = await original(*args)
        if not failed:
            failed = True
            raise TimeoutError("sensitive")
        return result

    monkeypatch.setattr(backend, method, lose_response)
    assert client.post("/telegram/webhook", json=make_update()).status_code == 200
    assert calls[0].url.path.endswith("/sendMessage")
    text = json.loads(calls[0].content)["text"]
    assert {"create": "проведение не завершено", "post": "проведён", "pdf": "PDF не получен"}[stage] in text
    assert client.post("/telegram/webhook", json=make_update(2, text="/retry")).status_code == 200
    assert calls[1].url.path.endswith("/sendDocument")
    assert len(backend.documents) == 1


def test_busy_request_fails_cleanly_without_parallel_mutation(harness, monkeypatch):
    client, backend, calls, _, _ = harness
    started, release = threading.Event(), threading.Event()
    original = backend.resolve_basis

    async def hold(command):
        started.set()
        while not release.is_set():
            await asyncio.sleep(0.01)
        return await original(command)

    monkeypatch.setattr(backend, "resolve_basis", hold)
    with ThreadPoolExecutor(max_workers=1) as pool:
        first = pool.submit(client.post, "/telegram/webhook", json=make_update())
        try:
            assert started.wait(timeout=2)
            assert client.post("/telegram/webhook", json=make_update(2)).status_code == 503
        finally:
            release.set()
        assert first.result(timeout=3).status_code == 200
    assert len(backend.documents) == 1 and len(calls) == 1


def test_configuration_repr_does_not_expose_secrets(harness):
    settings = harness[-1]
    assert settings.token.get_secret_value() not in repr(settings)
    assert settings.webhook_secret.get_secret_value() not in repr(settings)
