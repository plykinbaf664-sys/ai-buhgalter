"""Local single-process read-only demo; load private ENV without shell evaluation."""
import os
import argparse
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import Settings
from app.firstbit import FirstBitSettings
from app.http import disable_wire_logs


def load_local_env():
    for line in (ROOT / ".env.local").read_text(encoding="utf-8-sig").splitlines():
        if re.match(r"^[A-Z][A-Z0-9_]*=", line):
            key, value = line.split("=", 1)
            os.environ[key] = value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Validate private ENV without starting a server")
    args = parser.parse_args()
    load_local_env()
    disable_wire_logs()
    settings = Settings.from_env()
    FirstBitSettings.from_env()
    if settings.mode != "firstbit_readonly" or settings.ai_mode != "openai" or settings.onec_write_enabled:
        raise ValueError("Local demo requires firstbit_readonly, openai and disabled writes")
    if args.check:
        print("READONLY_DEMO_CONFIG=OK")
        return
    import uvicorn
    uvicorn.run("app.main:create_app", factory=True, host="127.0.0.1", port=8000,
                workers=1, access_log=False, log_level="warning")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Never surface raw config/provider exception text in background logs.
        print("READONLY_DEMO_START_FAILED: " + type(exc).__name__, file=sys.stderr)
        raise SystemExit(1)
