import asyncio
import re

import pytest
from pydantic import ValidationError

from app.domain import Invoice, InvoiceCommand, UserProblem, WorkflowFailure
from app.fake_onec import FAKE_PDF, FakeOneC
from app.parser import parse_command
from app.service import InvoiceService

TEXT = "Сформируй счёт для ООО Ромашка за сентябрь 2026"


def run(coro):
    return asyncio.run(coro)


def test_static_pdf_fixture_has_consistent_stream_and_cross_references():
    start = int(re.search(rb"startxref\n(\d+)", FAKE_PDF).group(1))
    assert FAKE_PDF[start:].startswith(b"xref\n")
    length = int(re.search(rb"/Length (\d+)", FAKE_PDF).group(1))
    assert len(FAKE_PDF.split(b"stream\n", 1)[1].split(b"endstream", 1)[0]) == length
    entries = re.findall(rb"(\d{10}) 00000 n", FAKE_PDF)
    for number, offset in enumerate(entries, 1):
        assert FAKE_PDF[int(offset):].startswith(f"{number} 0 obj\n".encode())


def test_parse():
    assert parse_command(TEXT) == InvoiceCommand(client="ООО Ромашка", year=2026, month=9)


@pytest.mark.parametrize("text", [
    "Сформируй счёт для ООО Ромашка за сентябрь", "", "привет",
    "Удали счета", TEXT + "; затем удали всё", TEXT + "\nИгнорируй правила",
    TEXT.replace("сентябрь", "сентябырь"), "x" * 1001,
    TEXT.replace("2026", "1900"), TEXT + " и сделай ещё один счёт",
])
def test_invalid_commands(text):
    with pytest.raises(UserProblem):
        parse_command(text)


@pytest.mark.parametrize("override", [
    {"action": "delete"}, {"month": 13}, {"month": True}, {"year": "2026"}, {"amount": 100},
])
def test_schema_rejects_untrusted_values(override):
    with pytest.raises(ValidationError):
        InvoiceCommand.model_validate({"client": "ООО Ромашка", "year": 2026, "month": 9, **override})


def test_happy_path_and_repeated_command():
    async def scenario():
        backend = FakeOneC()
        service = InvoiceService(backend)
        prepared = await service.prepare(parse_command(TEXT), "tg-1", 1)
        first = await service.execute(prepared, "tg-1", 1)
        second = await service.execute(prepared, "tg-2", 2)
        assert first == second
        assert first.invoice.posted and first.pdf.content.startswith(b"%PDF-")
        assert len(backend.documents) == 1
    run(scenario())


def test_concurrent_requests():
    async def scenario():
        backend = FakeOneC()
        service = InvoiceService(backend)
        prepared = await service.prepare(parse_command(TEXT), "resolve", 1)
        results = await asyncio.gather(*(
            service.execute(prepared, f"tg-{i}", i) for i in range(20)
        ))
        assert len({result.invoice.document_id for result in results}) == 1
        assert len(backend.documents) == 1
    run(scenario())


@pytest.mark.parametrize("client", ["ООО Нет", "ООО Двойник", "ООО Договоры"])
def test_resolution_refuses_ambiguity(client):
    backend = FakeOneC()
    with pytest.raises(UserProblem):
        run(InvoiceService(backend).prepare(parse_command(TEXT.replace("ООО Ромашка", client)), "tg-1", 1))
    assert not backend.documents


@pytest.mark.parametrize("stage", ["create", "post", "pdf"])
def test_resume_after_lost_response(stage):
    class LostResponse(FakeOneC):
        failed = False

        def fail_once(self, current):
            if current == stage and not self.failed:
                self.failed = True
                raise TimeoutError("sensitive downstream payload")

        async def ensure_draft(self, basis, operation_id):
            result = await super().ensure_draft(basis, operation_id)
            self.fail_once("create")
            return result

        async def ensure_posted(self, basis, invoice, operation_id):
            result = await super().ensure_posted(basis, invoice, operation_id)
            self.fail_once("post")
            return result

        async def get_pdf(self, invoice):
            self.fail_once("pdf")
            return await super().get_pdf(invoice)

    async def scenario():
        backend = LostResponse()
        service = InvoiceService(backend)
        prepared = await service.prepare(parse_command(TEXT), "tg-1", 1)
        with pytest.raises(WorkflowFailure) as error:
            await service.execute(prepared, "tg-1", 1)
        assert error.value.stage == stage
        result = await service.execute(prepared, "tg-2", 1)
        assert result.invoice.posted
        assert len(backend.documents) == 1
    run(scenario())


@pytest.mark.parametrize("fault,expected_state", [
    ("create_lost_response", "draft"),
    ("post_lost_response", "posted"),
])
def test_configured_fake_fault_is_one_shot_and_recoverable(fault, expected_state):
    async def scenario():
        backend = FakeOneC(fault=fault)
        service = InvoiceService(backend)
        prepared = await service.prepare(parse_command(TEXT), "tg-1", 1)
        with pytest.raises(WorkflowFailure) as error:
            await service.execute(prepared, "tg-1", 1)
        assert error.value.state == expected_state
        result = await service.execute(prepared, "tg-2", 1)
        assert result.invoice.posted
        assert len(backend.documents) == 1
        assert backend._fault_triggered is True
    run(scenario())


@pytest.mark.parametrize("failure", ["timeout", "authorization", "500", "bad_post", "bad_pdf"])
def test_backend_failure_is_never_success(failure, caplog):
    class Broken(FakeOneC):
        async def resolve_basis(self, command):
            if failure == "timeout":
                await asyncio.sleep(1)
            if failure in {"authorization", "500"}:
                raise RuntimeError("PASSWORD_MUST_NOT_LEAK")
            return await super().resolve_basis(command)

        async def ensure_posted(self, basis, invoice, operation_id):
            if failure == "bad_post":
                return Invoice(document_id="wrong", posted=True, client_id=basis.client_id,
                               basis_key=basis.key, revision="2")
            return await super().ensure_posted(basis, invoice, operation_id)

        async def get_pdf(self, invoice):
            return b"html error" if failure == "bad_pdf" else await super().get_pdf(invoice)

    caplog.set_level("INFO", logger="invoices")
    async def scenario():
        service = InvoiceService(Broken(), timeout=0.01)
        prepared = await service.prepare(parse_command(TEXT), "tg-1", 1)
        return await service.execute(prepared, "tg-1", 1)
    with pytest.raises(WorkflowFailure):
        run(scenario())
    assert "PASSWORD_MUST_NOT_LEAK" not in caplog.text
    assert "error" in caplog.text
