"""Start a real HTTP server locally; no requests to Telegram or 1C."""
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def main():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = {
        **os.environ, "APP_MODE": "mock", "AI_MODE": "disabled",
        "TELEGRAM_BOT_TOKEN": "123:" + secrets.token_urlsafe(32),
        "TELEGRAM_WEBHOOK_SECRET": secrets.token_urlsafe(32),
        "TELEGRAM_ALLOWED_USER_IDS": "123",
    }
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:create_app", "--factory",
         "--host", "127.0.0.1", "--port", str(port), "--no-access-log"],
        cwd=Path(__file__).resolve().parents[1], env=env,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            if process.poll() is not None:
                raise RuntimeError("Server failed to start")
            try:
                with urlopen(base + "/healthz", timeout=0.3) as response:
                    assert response.status == 200
                    break
            except URLError:
                time.sleep(0.1)
        else:
            raise RuntimeError("Server startup timed out")
        for headers, body, expected in [
            ({}, b"{}", 403),
            ({"X-Telegram-Bot-Api-Secret-Token": env["TELEGRAM_WEBHOOK_SECRET"]}, b"{", 400),
        ]:
            try:
                urlopen(Request(base + "/telegram/webhook", data=body, headers=headers), timeout=2)
            except HTTPError as exc:
                assert exc.code == expected
            else:
                raise AssertionError("Invalid webhook was accepted")
        print("SMOKE OK: real HTTP startup, health, webhook authentication, malformed input")
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


if __name__ == "__main__":
    main()
