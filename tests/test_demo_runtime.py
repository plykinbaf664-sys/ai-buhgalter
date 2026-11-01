import pytest

from scripts import start_readonly_demo as demo
from scripts.register_demo_webhook import validate_public_url


@pytest.mark.parametrize('url', ['https://synthetic.ngrok-free.dev','https://synthetic.ngrok-free.app',
    'https://synthetic.ngrok.app','https://synthetic.trycloudflare.com'])
def test_supported_https_tunnel_roots(url):
    assert validate_public_url(url) == url


@pytest.mark.parametrize('url', ['http://synthetic.ngrok.app','https://ngrok.app.evil.invalid',
    'https://user:secret@synthetic.ngrok.app','https://synthetic.ngrok.app/path',
    'https://synthetic.ngrok.app?secret=x','https://api.trycloudflare.com'])
def test_invalid_tunnel_roots_rejected(url):
    with pytest.raises(ValueError):
        validate_public_url(url)


def test_ngrok_switch_stops_only_owned_old_tunnel_not_app(monkeypatch):
    tunnel = demo.Process(ProcessId=123, Name='cloudflared.exe', CommandLine=str(demo.TUNNEL))
    queried, stopped = [], []
    monkeypatch.setattr(demo, 'process_query', lambda q: queried.append(q) or (tunnel,))
    monkeypatch.setattr(demo, 'shell', lambda code: stopped.append(code) or '')
    demo.stop_owned(demo.State(workspace=str(demo.ROOT), app_pid=100, tunnel_pid=123), roles=('tunnel',))
    assert queried == ['ProcessId=123'] and len(stopped) == 1


def test_tunnel_uses_tcp_http2_instead_of_unstable_udp(monkeypatch):
    captured = []
    monkeypatch.setattr(demo, "shell", lambda code: captured.append(code) or "123")
    assert demo.launch("tunnel") == 123
    assert "'--protocol','http2'" in captured[0]
    assert "-WindowStyle Hidden" in captured[0]


def test_failed_tunnel_api_url_is_not_registered_as_a_public_webhook():
    log = 'failed to request quick Tunnel: Post "https://api.trycloudflare.com/tunnel": lookup api.trycloudflare.com: no such host'
    assert demo.quick_tunnel_url(log) is None


def test_only_created_tunnel_announcement_supplies_public_url():
    log = ('Requesting new quick Tunnel on trycloudflare.com...\n'
           'Your quick Tunnel has been created! Visit it at:\n'
           '| https://synthetic-demo-host.trycloudflare.com |\n')
    assert demo.quick_tunnel_url(log) == 'https://synthetic-demo-host.trycloudflare.com'
    assert demo.quick_tunnel_url('Your quick Tunnel has been created https://api.trycloudflare.com') is None


def test_restart_refuses_other_workspace_without_querying_processes(monkeypatch, tmp_path):
    def unexpected(_):
        raise AssertionError("Foreign workspace must be rejected before process access")
    monkeypatch.setattr(demo, "process_query", unexpected)
    with pytest.raises(ValueError, match="workspace"):
        demo.stop_owned(demo.State(workspace=str(tmp_path), app_pid=123))


def test_restart_refuses_reused_pid_of_unrelated_python(monkeypatch):
    process = demo.Process(ProcessId=123, Name="python.exe",
        CommandLine='"C:\\unrelated\\python.exe" scripts/run_local.py')
    monkeypatch.setattr(demo, "process_query", lambda _: (process,))
    def no_stop(_):
        raise AssertionError("Unrelated process must never be stopped")
    monkeypatch.setattr(demo, "shell", no_stop)
    with pytest.raises(ValueError, match="unrelated"):
        demo.stop_owned(demo.State(workspace=str(demo.ROOT), app_pid=123))


def test_restart_ignores_recorded_process_that_already_exited(monkeypatch):
    monkeypatch.setattr(demo, "process_query", lambda _: ())
    def no_stop(_):
        raise AssertionError("Missing process requires no stop command")
    monkeypatch.setattr(demo, "shell", no_stop)
    demo.stop_owned(demo.State(workspace=str(demo.ROOT), app_pid=123))


def test_restart_preserves_existing_audit_logs_without_touching_other_files(monkeypatch, tmp_path):
    monkeypatch.setattr(demo, "RUNTIME", tmp_path)
    (tmp_path / "app.stderr.log").write_text('safe-stage-audit', encoding="utf-8")
    (tmp_path / "unrelated.txt").write_text('untouched', encoding="utf-8")
    demo.archive_logs()
    archives = list((tmp_path / "archive").iterdir())
    assert len(archives) == 1 and archives[0].read_text(encoding="utf-8") == 'safe-stage-audit'
    assert not (tmp_path / "app.stderr.log").exists()
    assert (tmp_path / "unrelated.txt").read_text(encoding="utf-8") == 'untouched'
    demo.archive_logs()
    assert list((tmp_path / "archive").iterdir()) == archives
