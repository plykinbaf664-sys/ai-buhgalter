from argparse import Namespace
import json

import httpx
import pytest

from scripts import run_server, server_control


@pytest.mark.parametrize("value", [
    "http://example.test", "https://user:secret@example.test",
    "https://example.test/?secret=1", "https://example.test/#fragment",
    "https://example.test:8443", "https://example.test/another-project",
    "https://example.test/ai-buhgalteria/../private", "https://example.test\n",
])
def test_project_public_url_rejects_unsafe_targets(value):
    with pytest.raises(ValueError):
        server_control.public_url(value)


def test_rollback_backup_is_private_and_never_overwritten(tmp_path):
    path = tmp_path / "private" / "previous.json"
    server_control.save_private(path, b'{"old":"webhook"}')
    with pytest.raises(FileExistsError):
        server_control.save_private(path, b'{"new":"webhook"}')
    assert json.loads(path.read_bytes()) == {"old": "webhook"}


def test_server_rejects_mock_mode(monkeypatch):
    monkeypatch.setattr(run_server.Settings, "from_env", lambda: Namespace(
        mode="mock", ai_mode="openai", onec_write_enabled=False, fake_onec_fault="disabled"))
    monkeypatch.setattr(run_server.FirstBitSettings, "from_env", lambda: None)
    with pytest.raises(ValueError):
        run_server.check_config()


def test_register_does_not_switch_when_public_admission_is_unsafe(monkeypatch, tmp_path):
    import asyncio
    from pydantic import SecretStr

    methods = []
    def respond(request):
        methods.append((request.method, request.url.path))
        if request.url.path.endswith("healthz"):
            return httpx.Response(200, json={"status": "ok", "mode": "firstbit_readonly"})
        return httpx.Response(200, json={})  # unsigned webhook incorrectly accepted

    original_client = httpx.AsyncClient
    monkeypatch.setattr(server_control, "check_config", lambda: Namespace(
        token=SecretStr("123:" + "x" * 32)))
    monkeypatch.setattr(server_control.httpx, "AsyncClient", lambda **kw:
        original_client(transport=httpx.MockTransport(respond), **kw))
    args = Namespace(action="register", public_url="https://example.test/ai-buhgalteria",
                     deep=False, backup=tmp_path / "before.json")
    with pytest.raises(ValueError, match="Unsigned"):
        asyncio.run(server_control.run(args))
    assert not any(path.endswith("setWebhook") for _, path in methods)
    assert not args.backup.exists()
