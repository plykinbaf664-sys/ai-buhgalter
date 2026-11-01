"""Fresh GET-only discovery of the prospective write schema, never a write test.

Load private ENV explicitly. A matching schema pin does NOT approve accounting
defaults, native printing, runtime writer admission or a production operation.
"""
import argparse
import asyncio
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.firstbit import FirstBit, FirstBitSettings
from app.firstbit_write_schema import inspect_write_schema
from app.service import safe_backend_error


async def preflight(expected: str | None, save: bool, execution: bool = False):
    backend = FirstBit(FirstBitSettings.from_env(writable=os.environ.get('APP_MODE') == 'firstbit_write'))
    try:
        await backend.check_metadata()
        raw = await backend._get("$metadata", metadata=True)
        if execution:
            from app.firstbit_write import execution_schema
            schema = execution_schema(raw)
        else:
            schema = inspect_write_schema(raw)
        if expected is not None:
            schema.require_approved(expected)
        result = {"result": "SCHEMA_PIN_MATCH" if expected is not None else "DISCOVERY_ONLY",
                  "schema": schema.model_dump(), "write_admitted": False, "production_GET_only": True,
                  "mutations": 0, "production_E2E": "not attempted",
                  "schema_scope": 'controlled_create' if execution else 'core_prospective',
                  "unproven": ["current new-document defaults and supplier admission",
                               "native PDF contract outside this metadata surface",
                               "real create/read-back/reconciliation behavior"]}
        if save:
            target = Path(__file__).resolve().parents[1] / ".local/firstbit/production-operation"
            target.mkdir(parents=True, exist_ok=True)
            prefix = 'controlled-create-schema' if execution else 'write-schema'
            (target / (prefix + '.xml')).write_bytes(raw)
            (target / (prefix + '-preflight.json')).write_text(json.dumps(result, indent=2), encoding="utf-8")
        return result
    finally:
        await backend.aclose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-schema-sha256")
    parser.add_argument("--save-private", action="store_true")
    parser.add_argument('--execution-schema', action='store_true')
    args = parser.parse_args()
    try:
        print(json.dumps(asyncio.run(preflight(args.expected_schema_sha256, args.save_private, args.execution_schema))))
    except Exception as exc:
        code = ("firstbit_write_schema_mismatch" if exc.args == ("firstbit_write_schema_mismatch",)
                else safe_backend_error(exc))
        print(json.dumps({"result": "BLOCKED", "error_type": code, "mutations": 0}))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
