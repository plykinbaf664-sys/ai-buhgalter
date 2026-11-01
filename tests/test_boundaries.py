import asyncio
import secrets

import pytest
from pydantic import ValidationError

from app.config import Settings
from app.domain import Invoice, WorkflowFailure
from app.fake_onec import FakeOneC
from app.parser import parse_command
from app.service import InvoiceService
from app.telegram_models import SendResponse, Update


@pytest.mark.parametrize("payload", [
    {"ok": 1, "result": {"message_id": 1, "chat": {"id": 123}}},
    {"ok": True, "result": {"message_id": "1", "chat": {"id": 123}}},
    {"ok": False, "result": {"message_id": 1, "chat": {"id": 123}}},
    {"ok": True, "result": {"message_id": 1, "chat": {"id": True}}},
    {"ok": True, "result": {}},
])
def test_telegram_responses_are_untrusted(payload):
    with pytest.raises(ValidationError):
        SendResponse.model_validate(payload)


@pytest.mark.parametrize("response", [
    {"document_id": "safe", "posted": "true"},
    {"document_id": "safe", "posted": True, "amount": 100},
    Invoice.model_construct(document_id="safe", posted="true"),
])
def test_backend_cannot_bypass_runtime_validation(response):
    class Broken(FakeOneC):
        async def ensure_draft(self, basis, operation_id):
            return response

    async def scenario():
        service = InvoiceService(Broken())
        prepared = await service.prepare(parse_command("Создай счёт для ООО Ромашка за сентябрь 2026"), "tg-1", 123)
        return await service.execute(prepared, "tg-1", 123)
    with pytest.raises(WorkflowFailure) as error:
        asyncio.run(scenario())
    assert error.value.stage == "create"


def test_config_invalid_secret_not_in_printed_error():
    secret = secrets.token_urlsafe(12)
    with pytest.raises(ValidationError) as error:
        Settings(token=secret, webhook_secret=secret, allowed_users=frozenset({123}))
    assert secret not in str(error.value)


def test_voice_metadata_requires_real_types():
    with pytest.raises(ValidationError):
        Update.model_validate({"update_id": 1, "message": {
            "message_id": 1, "from": {"id": 123, "is_bot": False},
            "chat": {"id": 123, "type": "private"},
            "voice": {"file_id": "f", "file_unique_id": "u", "duration": "60"},
        }})
