"""Explicit provisioning only; never replaces an existing journal or contacts 1C."""
import hashlib
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import Settings
from app.firstbit import FirstBitSettings
from app.operations import OperationJournal


def main():
    settings = Settings.from_env()
    if settings.mode != 'firstbit_write' or settings.operation_db is None:
        raise ValueError('Explicit firstbit_write settings required')
    provider = FirstBitSettings.from_env(writable=True)
    if settings.operation_db.exists():
        raise ValueError('Existing state must be opened and reconciled, never reinitialized')
    namespace = 'invoice:v1:firstbit_write:' + hashlib.sha256(provider.base_url.encode()).hexdigest()
    OperationJournal(settings.operation_db, namespace=namespace, create=True)
    print('EMPTY_JOURNAL_PROVISIONED: zero external requests, preserve this state')


if __name__ == '__main__':
    try:
        main()
    except Exception:
        print('JOURNAL_PROVISIONING_FAILED: configuration, existing state or permissions')
        raise SystemExit(1) from None
