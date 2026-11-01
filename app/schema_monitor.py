"""Periodic live schema health, with fresh fail-closed guards still preceding every write."""
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path

async def check_schema(backend, *, status_path: Path):
    try:
        await backend._schema()
        healthy=True
    except Exception:
        healthy=False
    record={'checked_at':datetime.now(timezone.utc).isoformat(),
            'healthy':healthy,'reviewed_sha256':backend.schema_sha256}
    temporary=status_path.with_suffix('.tmp')
    temporary.write_text(json.dumps(record))
    temporary.chmod(0o600)
    temporary.replace(status_path)
    return healthy

async def monitor_schema(backend, *, status_path: Path, alert, interval=12*60*60):
    previous=None
    while True:
        healthy=await check_schema(backend,status_path=status_path)
        if not healthy and previous is not False:
            await alert()
        previous=healthy
        await asyncio.sleep(interval)
