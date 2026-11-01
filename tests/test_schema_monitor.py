import asyncio,json
from app.schema_monitor import check_schema,monitor_schema

class Backend:
    schema_sha256='a'*64
    def __init__(self):self.calls=0
    async def _schema(self):
        self.calls+=1
        raise ValueError('PRIVATE schema response must never be copied')

def test_schema_failure_stores_only_safe_health_and_approved_fingerprint(tmp_path):
    path=tmp_path/'health.json'
    assert asyncio.run(check_schema(Backend(),status_path=path)) is False
    record=json.loads(path.read_text())
    assert record['healthy'] is False and record['reviewed_sha256']=='a'*64
    assert 'PRIVATE' not in path.read_text()
    assert path.stat().st_mode & 0o777 == 0o600

def test_schema_schedule_is_twelve_hours_and_alert_is_not_repeated(tmp_path,monkeypatch):
    import app.schema_monitor as module
    backend=Backend();alerts=[];waits=[]
    async def alert():alerts.append('blocked')
    async def pause(seconds):
        waits.append(seconds)
        if len(waits)==2:raise asyncio.CancelledError
    monkeypatch.setattr(module.asyncio,'sleep',pause)
    async def scenario():
        try:await monitor_schema(backend,status_path=tmp_path/'health.json',alert=alert)
        except asyncio.CancelledError:pass
    asyncio.run(scenario())
    assert backend.calls==2 and alerts==['blocked'] and waits==[43200,43200]

def test_native_ui_cannot_enable_writes_in_readonly_configuration():
    import pytest
    from pydantic import ValidationError
    from app.config import Settings
    with pytest.raises(ValidationError):
        Settings(token='123:'+'x'*30,webhook_secret='x'*32,allowed_users=frozenset({123}),
            mode='firstbit_readonly',firstbit_native_ui_enabled=True)
