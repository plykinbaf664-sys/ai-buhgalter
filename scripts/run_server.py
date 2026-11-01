"""Single-worker Linux FirstBit runtime; secrets arrive through the service ENV."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import Settings
from app.firstbit import FirstBitSettings
from app.http import disable_wire_logs


def check_config() -> Settings:
    settings = Settings.from_env()
    if settings.mode == 'firstbit_write':
        FirstBitSettings.from_env(writable=True)
    else:
        FirstBitSettings.from_env()
    if (settings.mode not in ('firstbit_readonly', 'firstbit_write') or settings.ai_mode != "openai"
            or settings.mode == 'firstbit_readonly' and settings.onec_write_enabled
            or settings.fake_onec_fault != "disabled"):
        raise ValueError("Server requires readonly FirstBit, OpenAI and disabled writes/faults")
    return settings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--port", type=int, default=8107)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        raise ValueError("Expected unprivileged port")
    disable_wire_logs()
    check_config()
    if args.check:
        print("FIRSTBIT_SERVER_CONFIG=OK mode=" + check_config().mode)
        return
    import uvicorn
    uvicorn.run("app.main:create_app", factory=True, host="127.0.0.1", port=args.port,
                workers=1, access_log=False, log_level="warning", proxy_headers=False)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("FIRSTBIT_SERVER_FAILED: " + type(exc).__name__, file=sys.stderr)
        raise SystemExit(1)
