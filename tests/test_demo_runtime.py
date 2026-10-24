import pytest

from scripts import start_readonly_demo as demo


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
