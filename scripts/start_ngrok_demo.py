"""Start the readonly demo on ngrok; keep the app/draft alive during a tunnel switch."""
import argparse
import asyncio
import os
from pathlib import Path
import re
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import httpx
from pydantic import Field, SecretStr
from app.config import Settings
from app.domain import ExternalModel
from app.validation import validate_json
from scripts import start_readonly_demo as demo
from scripts.register_demo_webhook import register_webhook, validate_public_url
from scripts.run_local import load_local_env

NGROK = demo.ROOT / '.local/tools/ngrok.exe'
CONFIG = demo.RUNTIME / 'ngrok-safe.yml'
CANDIDATE = demo.RUNTIME / 'ngrok-candidate.json'


class EndpointConfig(ExternalModel):
    addr: str
    inspect: bool


class Endpoint(ExternalModel):
    public_url: str
    proto: str
    config: EndpointConfig


class Endpoints(ExternalModel):
    tunnels: tuple[Endpoint, ...] = Field(max_length=20)


def authtoken() -> SecretStr:
    value = os.environ.get('NGROK_AUTHTOKEN', '')
    if not value:
        # Existing user-owned ngrok config is read only; token is passed in ENV,
        # never copied to project config, command arguments or logs.
        path = Path(os.environ.get('LOCALAPPDATA', '')) / 'ngrok/ngrok.yml'
        text = path.read_text(encoding='utf-8-sig') if path.exists() else ''
        match = re.search(r'''(?m)^\s*authtoken:\s*["']?([A-Za-z0-9_-]{10,})["']?\s*$''', text)
        value = match[1] if match else ''
    if not re.fullmatch(r'[A-Za-z0-9_-]{10,}', value):
        raise ValueError('Configure NGROK_AUTHTOKEN privately')
    return SecretStr(value)


def endpoint() -> str | None:
    try:
        with httpx.Client(timeout=1, trust_env=False, follow_redirects=False) as client:
            response = client.get('http://127.0.0.1:4047/api/tunnels')
            response.raise_for_status()
            result = validate_json(Endpoints, response.content)
        matches = [t for t in result.tunnels if t.proto == 'https'
            and t.config.addr == 'http://127.0.0.1:8000' and t.config.inspect is False]
        return validate_public_url(matches[0].public_url) if len(matches) == 1 else None
    except (ValueError, httpx.HTTPError):
        return None


def owned_agent(state: demo.State) -> bool:
    if state.tunnel_provider != 'ngrok' or state.tunnel_pid is None:
        return False
    rows = demo.process_query(f'ProcessId={state.tunnel_pid}')
    if not rows:
        return False
    command = (rows[0].CommandLine or '').casefold()
    if rows[0].Name != 'ngrok.exe' or str(NGROK).casefold().replace('/', '\\') not in command:
        raise ValueError('Refusing an unrelated ngrok PID')
    return True


def start(*, restart=False):
    load_local_env()
    settings = Settings.from_env()
    if settings.mode != 'firstbit_readonly' or settings.onec_write_enabled or settings.ai_mode != 'openai':
        raise ValueError('Read-only OpenAI demo required')
    token = authtoken()
    if not NGROK.is_file():
        raise ValueError('Official ngrok agent missing under .local/tools/')
    old = validate_json(demo.State, demo.STATE.read_text(encoding='utf-8-sig')) if demo.STATE.exists() else None
    if old is not None and Path(old.workspace).resolve() != demo.ROOT:
        raise ValueError('Unexpected workspace')
    if restart and old is not None:
        demo.stop_owned(old)
        time.sleep(.5)
    ready = demo.health()
    if ready is not None and (ready.mode != 'firstbit_readonly' or old is None):
        raise ValueError('Untracked server on port 8000')
    app_pid = old.app_pid if ready is not None else None
    if app_pid is None:
        subprocess.run([str(demo.PYTHON), 'scripts/run_local.py', '--check'], cwd=demo.ROOT, check=True)
        demo.archive_logs()
        app_pid = demo.launch('app')
        # Track the owned process even if creating the replacement endpoint fails.
        if restart or old is None:
            demo.STATE.write_text(demo.State(workspace=str(demo.ROOT), app_pid=app_pid,
                tunnel_provider='ngrok').model_dump_json(), encoding='utf-8')
        for _ in range(40):
            health = demo.health()
            if health is not None and health.mode == 'firstbit_readonly':
                break
            time.sleep(.5)
        else:
            raise RuntimeError('App is not healthy')
    candidate = None
    for path in (demo.STATE, CANDIDATE):
        if path.exists() and not restart:
            state = validate_json(demo.State, path.read_text(encoding='utf-8-sig'))
            if Path(state.workspace).resolve() == demo.ROOT and state.app_pid == app_pid and owned_agent(state):
                candidate = state
                break
    if candidate is None:
        CONFIG.parent.mkdir(parents=True, exist_ok=True)
        CONFIG.write_text('version: "2"\nweb_addr: 127.0.0.1:4047\nupdate_check: false\n', encoding='utf-8')
        process = subprocess.Popen([str(NGROK), 'http', 'http://127.0.0.1:8000', '--config', str(CONFIG),
            '--inspect=false', '--log=false', '--name', 'ai-buhgalter-readonly'], cwd=demo.ROOT,
            env={**os.environ, 'NGROK_AUTHTOKEN': token.get_secret_value()}, stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
        candidate = demo.State(workspace=str(demo.ROOT), app_pid=app_pid,
            tunnel_pid=process.pid, tunnel_provider='ngrok')
        CANDIDATE.write_text(candidate.model_dump_json(), encoding='utf-8')
    public = None
    for _ in range(40):
        public = endpoint()
        if public:
            break
        time.sleep(.5)
    if public is None:
        raise RuntimeError('Ngrok endpoint is not ready; existing webhook retained')
    # Registration validates HTTPS public health before changing Telegram, and
    # verifies the resulting URL. Old app/tunnel stay until the switch succeeds.
    asyncio.run(register_webhook(public, settings))
    candidate = demo.State(**{**candidate.model_dump(), 'public_url': public})
    if old is not None:
        (demo.RUNTIME / 'previous-demo-processes.json').write_text(old.model_dump_json(), encoding='utf-8')
    demo.STATE.write_text(candidate.model_dump_json(), encoding='utf-8')
    CANDIDATE.write_text(candidate.model_dump_json(), encoding='utf-8')
    if old is not None and old.tunnel_provider == 'cloudflare' and not restart:
        demo.stop_owned(old, roles=('tunnel',))
    print('NGROK_DEMO_READY; inspection disabled; writes disabled')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--restart', action='store_true')
    args = parser.parse_args()
    try:
        start(restart=args.restart)
    except Exception as exc:
        print('NGROK_DEMO_FAILED: ' + type(exc).__name__)
        raise SystemExit(1)
