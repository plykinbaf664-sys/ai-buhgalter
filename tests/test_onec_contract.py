"""Reusable behavioral contract. Running this suite never connects to real 1C."""
import asyncio

import pytest

from app.domain import (Invoice, OperationState, PreparedInvoice, ResolvedClient,
                        ResolvedInvoiceCommand, StaleBasis, WorkflowFailure)
from app.fake_onec import FakeOneC
from app.parser import parse_command
from app.service import InvoiceService


def test_existing_draft_is_resumed_and_already_posted_is_reused():
    async def scenario():
        backend = FakeOneC()
        command = parse_command("Создай счёт для ООО Ромашка за сентябрь 2026")
        service = InvoiceService(backend)
        prepared = await service.prepare(command, "tg-1", 123)
        basis = prepared.basis
        existing = await backend.ensure_draft(basis, "external-existing-operation")
        result = await service.execute(prepared, "tg-1", 123)
        repeated = await service.execute(prepared, "tg-2", 456)
        assert result.invoice.document_id == existing.document_id
        assert result == repeated and result.invoice.posted
        assert len(backend.documents) == 1
    asyncio.run(scenario())


def test_semantic_duplicate_normalizes_company_and_retains_period():
    async def scenario():
        backend = FakeOneC()
        service = InvoiceService(backend)
        results = []
        for text in [
            "Создай счёт для ООО Ромашка за сентябрь 2026",
            'Сделай счет для ООО "Ромашка" за сентябрь 2026',
            "Сформируй счёт для ООО Ромашка за октябрь 2026",
        ]:
            prepared = await service.prepare(parse_command(text), "tg-1", 123)
            results.append(await service.execute(prepared, "tg-1", 123))
        assert results[0].invoice.document_id == results[1].invoice.document_id
        assert results[2].invoice.document_id != results[0].invoice.document_id
        assert len(backend.documents) == 2
    asyncio.run(scenario())


def test_fake_pdf_cannot_be_requested_for_nonexistent_document():
    with pytest.raises(ValueError):
        asyncio.run(FakeOneC().get_pdf(Invoice(document_id="invented", posted=True,
                                               client_id="client-001", basis_key="none", revision="1")))


def test_name_is_only_used_for_resolution_and_execution_uses_stable_id():
    async def scenario():
        backend = FakeOneC()
        service = InvoiceService(backend)
        prepared = await service.prepare(parse_command("Сделай счёт для Ромашке за сентябрь 2026"), "tg-1", 1)
        assert prepared.request.client_id == "client-001"

        async def must_not_search(query):
            raise AssertionError("execution must not search by display name")

        backend.resolve_client = must_not_search
        result = await service.execute(prepared, "tg-2", 1)
        assert result.invoice.client_id == "client-001"
    asyncio.run(scenario())


def test_revision_change_blocks_write():
    async def scenario():
        backend = FakeOneC()
        service = InvoiceService(backend)
        prepared = await service.prepare(parse_command("Создай счёт для ООО Ромашка за сентябрь 2026"), "tg-1", 1)
        backend.billing_revisions["client-001"] = "v2"
        with pytest.raises(WorkflowFailure) as error:
            await service.execute(prepared, "tg-2", 1)
        assert error.value.stage == "stale"
        assert not backend.documents
    asyncio.run(scenario())


def test_unknown_operation_state_never_calls_mutation():
    class Unknown(FakeOneC):
        async def read_operation(self, basis, operation_id):
            return OperationState(operation_id=operation_id, status="unknown")

        async def ensure_draft(self, basis, operation_id):
            raise AssertionError("unknown state must stop before create")

    async def scenario():
        backend = Unknown()
        service = InvoiceService(backend)
        prepared = await service.prepare(parse_command("Создай счёт для ООО Ромашка за сентябрь 2026"), "tg-1", 1)
        with pytest.raises(WorkflowFailure) as error:
            await service.execute(prepared, "tg-2", 1)
        assert error.value.state == "unknown"
        assert not backend.documents
    asyncio.run(scenario())


@pytest.mark.parametrize("permission", [False, True])
def test_real_write_requires_explicit_flag_and_durable_store(permission):
    class RealShape(FakeOneC):
        is_fake = False
        writes = 0

        async def ensure_draft(self, basis, operation_id):
            self.writes += 1
            return await super().ensure_draft(basis, operation_id)

    async def scenario():
        backend = RealShape()
        service = InvoiceService(backend, allow_real_writes=permission)
        prepared = await service.prepare(parse_command("Создай счёт для ООО Ромашка за сентябрь 2026"), "tg-1", 1)
        with pytest.raises(WorkflowFailure) as error:
            await service.execute(prepared, "tg-2", 1)
        assert error.value.stage == "write_disabled"
        assert backend.writes == 0
    asyncio.run(scenario())


def test_native_adapter_pdf_is_passed_through_without_mock_renderer(monkeypatch, tmp_path):
    from app.domain import PdfDocument
    from app.operations import OperationJournal
    native = PdfDocument(content=b"%PDF-1.7\nnative-test-document\n%%EOF")
    class NativeTestAdapter(FakeOneC):
        is_fake = False

        async def get_pdf(self, invoice):
            assert invoice.posted
            return native

    def forbidden(*args):
        raise AssertionError("Native adapter must not use mock PDF")
    monkeypatch.setattr("app.fake_onec.render_mock_pdf", forbidden)
    async def scenario():
        backend = NativeTestAdapter()
        service = InvoiceService(backend, allow_real_writes=True, journal=OperationJournal(
            tmp_path / "state" / "native.sqlite", namespace="synthetic-native-test", create=True))
        prepared = await service.prepare(parse_command("Создай счёт для ООО Ромашка за сентябрь 2026"), "native", 123)
        result = await service.execute(prepared, "native", 123)
        assert result.pdf == native and len(backend.documents) == 1
    asyncio.run(scenario())


def test_pdf_request_rejects_forged_document_metadata():
    async def scenario():
        backend = FakeOneC()
        service = InvoiceService(backend)
        prepared = await service.prepare(parse_command("Создай счёт для ООО Ромашка за сентябрь 2026"), "pdf", 123)
        result = await service.execute(prepared, "pdf", 123)
        for changed in ({"revision": "forged"}, {"client_id": "other"}, {"preview_digest": "0" * 64}):
            with pytest.raises(ValueError):
                await backend.get_pdf(Invoice.model_validate({**result.invoice.model_dump(), **changed}))
    asyncio.run(scenario())
