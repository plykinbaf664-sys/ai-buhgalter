"""Start/restart the Windows read-only demo with its secure Telegram webhook."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import tempfile
from typing import Literal

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import httpx
from pydantic import Field

from app.domain import ExternalModel
from app.telegram_models import Health
from app.validation import validate_json

RUNTIME = ROOT / ".local/runtime"
STATE = RUNTIME / "demo-processes.json"
PYTHON = ROOT / ".venv/Scripts/python.exe"
TUNNEL = ROOT / ".local/tools/cloudflared.exe"
POWERSHELL = str(Path(os.environ.get("SystemRoot", "C:/Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe")


class State(ExternalModel):
    workspace: str
    app_pid: int = Field(gt=0)
    tunnel_pid: int | None = Field(default=None, gt=0)
    public_url: str | None = None
    tunnel_provider: Literal['cloudflare', 'ngrok'] = 'cloudflare'


class Process(ExternalModel):
    ProcessId: int = Field(gt=0)
    Name: str
    CommandLine: str | None


def shell(code: str) -> str:
    # No script execution-policy changes, credentials or user text in command code.
    # File handles avoid waiting for EOF on a pipe inherited by a background app.
    with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
        result = subprocess.run([POWERSHELL, "-NoProfile", "-Command", code], cwd=ROOT,
            env={**os.environ, "DEMO_WORKSPACE": str(ROOT)}, stdout=output, stderr=errors,
            timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode:
            raise RuntimeError("Demo process management failed")
        output.seek(0)
        return output.read().decode("utf-8", errors="replace").strip()


def process_query(filter: str) -> tuple[Process, ...]:
    raw = shell("$OutputEncoding=[Text.UTF8Encoding]::new($false); "
        "[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false); "
        f"$items=@(Get-CimInstance Win32_Process -Filter '{filter}' | "
        "Select-Object ProcessId,Name,CommandLine); ConvertTo-Json -InputObject $items -Compress")
    return tuple(Process.model_validate(row) for row in json.loads(raw or "[]"))


def stop_owned(state: State, *, roles=('app', 'tunnel')):
    if Path(state.workspace).resolve() != ROOT:
        raise ValueError("Unexpected demo workspace")
    for role, pid in (("app", state.app_pid), ("tunnel", state.tunnel_pid)):
        if pid is None or role not in roles:
            continue
        rows = process_query(f"ProcessId={pid}")
        if not rows:
            continue
        process = rows[0]
        cmd = (process.CommandLine or "").casefold().replace('/', '\\')
        tunnel_binary = ROOT / '.local/tools/ngrok.exe' if state.tunnel_provider == 'ngrok' else TUNNEL
        tunnel_name = 'ngrok.exe' if state.tunnel_provider == 'ngrok' else 'cloudflared.exe'
        owned = (str(ROOT).casefold().replace('/', '\\') in cmd and
                 (role == "app" and process.Name == "python.exe" and str(PYTHON).casefold().replace('/', '\\') in cmd and "run_local.py" in cmd or
                  role == "tunnel" and process.Name == tunnel_name and str(tunnel_binary).casefold().replace('/', '\\') in cmd))
        if not owned:
            raise ValueError("Refusing to stop an unrelated process")
        if role == "app":
            for child in process_query(f"ParentProcessId={pid}"):
                if child.Name == "python.exe" and "run_local.py" in (child.CommandLine or ""):
                    shell(f"Stop-Process -Id {child.ProcessId} -ErrorAction SilentlyContinue; exit 0")
        shell(f"Stop-Process -Id {pid} -ErrorAction SilentlyContinue; exit 0")


def launch(role: str) -> int:
    if role == "app":
        code = "$file=Join-Path $env:DEMO_WORKSPACE '.venv\\Scripts\\python.exe'; $argsList=@('-u','scripts/run_local.py'); "
    else:
        code = "$file=Join-Path $env:DEMO_WORKSPACE '.local\\tools\\cloudflared.exe'; $argsList=@('tunnel','--protocol','http2','--url','http://127.0.0.1:8000','--no-autoupdate'); "
    code += ("$logs=Join-Path $env:DEMO_WORKSPACE '.local\\runtime'; "
        f"$process=Start-Process -FilePath $file -ArgumentList $argsList -WorkingDirectory $env:DEMO_WORKSPACE -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logs '{role}.stdout.log') -RedirectStandardError (Join-Path $logs '{role}.stderr.log') -PassThru; $process.Id")
    return int(shell(code))


def archive_logs():
    # Start-Process truncates redirected files; preserve safe audits across restart.
    for name in ("app.stderr.log", "app.stdout.log", "tunnel.stderr.log", "tunnel.stdout.log"):
        source = RUNTIME / name
        if source.is_file():
            archive = RUNTIME / "archive"
            archive.mkdir(exist_ok=True)
            source.replace(archive / f"{time.time_ns()}-{name}")


def health() -> Health | None:
    try:
        with httpx.Client(timeout=2, trust_env=False) as client:
            response = client.get("http://127.0.0.1:8000/healthz")
            response.raise_for_status()
            return validate_json(Health, response.content)
    except (ValueError, httpx.HTTPError):
        return None


def quick_tunnel_url(log: str) -> str | None:
    # An API failure also contains https://api.trycloudflare.com, not a public tunnel.
    marker = "Your quick Tunnel has been created"
    if marker not in log:
        return None
    matches = re.findall(r"https://(?!api\.|www\.)[a-z0-9-]+\.trycloudflare\.com\b", log.split(marker, 1)[1])
    return matches[-1] if matches else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--restart", action="store_true", help="Restart only this workspace's recorded app/tunnel")
    args = parser.parse_args()
    if os.name != "nt":
        raise ValueError("This launcher is for Windows")
    subprocess.run([str(PYTHON), "scripts/run_local.py", "--check"], cwd=ROOT, check=True)
    RUNTIME.mkdir(parents=True, exist_ok=True)
    state = validate_json(State, STATE.read_text(encoding="utf-8-sig")) if STATE.exists() else None
    if state is not None and state.tunnel_provider == 'ngrok':
        from scripts.start_ngrok_demo import start
        start(restart=args.restart)
        return
    if not TUNNEL.is_file():
        raise ValueError("Official cloudflared binary missing; see docs/firstbit/LIVE_DEMO.md")
    if state is not None and args.restart:
        stop_owned(state)
        time.sleep(.5)
    existing = health()
    if existing is not None:
        if existing.mode != "firstbit_readonly" or state is None or args.restart:
            raise ValueError("Port 8000 is occupied by an untracked app")
        print("READONLY_DEMO_ALREADY_RUNNING; use --restart after changing ENV")
        return
    archive_logs()
    state = State(workspace=str(ROOT), app_pid=launch("app"))
    STATE.write_text(state.model_dump_json(), encoding="utf-8")
    for _ in range(40):
        ready = health()
        if ready is not None and ready.mode == "firstbit_readonly":
            break
        time.sleep(.5)
    else:
        raise RuntimeError("Read-only app did not become healthy")
    state = State(**{**state.model_dump(), "tunnel_pid": launch("tunnel")})
    STATE.write_text(state.model_dump_json(), encoding="utf-8")
    public = None
    for _ in range(60):
        log_path = RUNTIME / "tunnel.stderr.log"
        log = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""
        public = quick_tunnel_url(log)
        if public:
            break
        if "failed to request quick Tunnel" in log:
            raise RuntimeError("Cloudflare tunnel creation failed; check network/DNS")
        time.sleep(.5)
    if public is None:
        raise RuntimeError("Tunnel URL unavailable")
    state = State(**{**state.model_dump(), "public_url": public})
    STATE.write_text(state.model_dump_json(), encoding="utf-8")
    for _ in range(5):
        check = subprocess.run([str(PYTHON), "scripts/register_demo_webhook.py"], cwd=ROOT)
        if check.returncode == 0:
            print("READONLY_DEMO_READY; logs and PIDs under .local/runtime")
            return
        time.sleep(2)
    raise RuntimeError("Webhook registration failed; app remains read-only")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("READONLY_DEMO_FAILED: " + type(exc).__name__, file=sys.stderr)
        raise SystemExit(1)
