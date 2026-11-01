"""Synthetic native-provider contract proofs. No captured/prod records or sessions."""
import asyncio
from pathlib import Path
import sqlite3
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.domain import (Invoice, InvoiceConflict, TaxInvoicePdf, TaxPdfProvenance,
                        TaxInvoice, TaxInvoiceReference, TaxOperationState, WorkflowFailure, WritesDisabled)
from app.fake_onec import FakeOneC
from app.operations import OperationJournal, MutationUncertain, JournalUnavailable
from app.parser import parse_command
from app.service import InvoiceService

TEXT = 'Сформируй счет для ООО Ромашка за сентябрь 2026 года'
PDF = b'%PDF-1.7\nSYNTHETIC NATIVE PRINT CONTRACT TEST ONLY\n%%EOF'


class SyntheticTaxProvider(FakeOneC):
    # Deliberately real-shaped contract seam; no actual native API/network exists here.
    is_fake = False
    write_capable = True
    requires_tax_invoice = True

    def __init__(self, journal, *, generated_posted=True):
        super().__init__()
        self.journal = journal
        self.generated_posted = generated_posted
        self.tax_documents = {}
        self.creates = self.source_posts = self.generates = self.tax_posts = self.prints = 0
        self.tax_fault = None
        self.schema_ok = True
        self.hidden_tax = False
        self.bad_parent = False
        self.bad_pdf = False
        self.version_drift_at_print = False
        self.trace = []

    async def ensure_draft(self, basis, operation_id):
        if not self.schema_ok:
            raise WritesDisabled()
        self.journal.claim_provider_request(operation_id, 'create')
        self.creates += 1
        self.trace.append('source_create')
        return await super().ensure_draft(basis, operation_id)

    async def ensure_posted(self, basis, invoice, operation_id):
        if not self.schema_ok:
            raise WritesDisabled()
        self.journal.claim_provider_request(operation_id, 'post')
        self.source_posts += 1
        self.trace.append('source_post')
        return await super().ensure_posted(basis, invoice, operation_id)

    async def read_tax_operation(self, basis, invoice, operation_id):
        self.trace.append('tax_readback')
        if self.hidden_tax:
            return TaxOperationState(operation_id=operation_id, source_document_id=invoice.document_id, status='unknown')
        tax = self.tax_documents.get(operation_id)
        if tax is not None and self.bad_parent:
            tax = TaxInvoice(**{**tax.model_dump(), 'source_document_id': 'synthetic-foreign-parent'})
        return TaxOperationState(operation_id=operation_id, source_document_id=invoice.document_id,
                                 status=('posted' if tax.posted else 'draft') if tax else 'not_started', invoice=tax)

    async def ensure_tax_invoice(self, basis, invoice, operation_id):
        if not self.schema_ok:
            raise WritesDisabled()
        self.journal.claim_provider_request(operation_id, 'generate_tax')
        self.generates += 1
        self.trace.append('generate_tax')
        if self.tax_fault == 'generate_before_commit':
            raise TimeoutError('Synthetic lost response before commit')
        tax = TaxInvoice(document_id='synthetic-tax-' + operation_id[:12], source_document_id=invoice.document_id,
            number='SYN-TAX-001', posted=self.generated_posted, client_id=basis.client_id, basis_key=basis.key,
            revision='tax-v1', preview_digest=basis.preview.digest)
        self.tax_documents[operation_id] = tax
        if self.tax_fault == 'generate_after_commit':
            raise TimeoutError('Synthetic lost response after commit')
        if self.tax_fault == 'hidden_after_return':
            self.hidden_tax = True
        return TaxInvoiceReference(document_id=tax.document_id, source_document_id=invoice.document_id)

    async def ensure_tax_posted(self, basis, invoice, operation_id):
        if not self.schema_ok:
            raise WritesDisabled()
        self.journal.claim_provider_request(operation_id, 'post_tax')
        self.tax_posts += 1
        self.trace.append('tax_post')
        if self.tax_fault == 'post_before_commit':
            raise TimeoutError('Synthetic posting outcome unknown')
        posted = TaxInvoice(**{**invoice.model_dump(), 'posted': True, 'revision': 'tax-v2'})
        self.tax_documents[operation_id] = posted
        if self.tax_fault == 'post_after_commit':
            raise TimeoutError('Synthetic posting response lost')
        return TaxInvoiceReference(document_id=posted.document_id, source_document_id=posted.source_document_id)

    async def get_pdf(self, invoice):
        raise AssertionError('Source Invoice PDF is not the requested Tax Invoice form')

    async def get_tax_invoice_pdf(self, invoice):
        self.prints += 1
        self.trace.append('tax_pdf')
        if self.tax_fault == 'pdf_timeout':
            raise TimeoutError('Synthetic native PDF timeout')
        provenance = TaxPdfProvenance(document_id='synthetic-wrong-tax' if self.bad_pdf else invoice.document_id,
            source_document_id=invoice.source_document_id, document_revision=invoice.revision,
            print_manager='Document.TaxInvoice', template='TaxInvoiceLandscapeEN')
        if self.version_drift_at_print:
            for key, stored in self.tax_documents.items():
                if stored.document_id == invoice.document_id:
                    self.tax_documents[key] = TaxInvoice(**{**stored.model_dump(), 'revision': 'changed-during-print'})
        return TaxInvoicePdf(content=PDF, provenance=provenance)


def store(path, *, create=True):
    return OperationJournal(path, namespace='synthetic-tax-provider', create=create)


def service(backend):
    return InvoiceService(backend, journal=backend.journal, allow_real_writes=True)


async def prepare(backend):
    return await service(backend).prepare(parse_command(TEXT), 'synthetic-prepare', 123)


@pytest.mark.parametrize('generated_posted', [True, False])
def test_native_chain_reads_actual_state_and_never_reposts_already_posted_tax(generated_posted, tmp_path):
    backend = SyntheticTaxProvider(store(tmp_path / 'private/operations.sqlite'), generated_posted=generated_posted)
    async def scenario():
        prepared = await prepare(backend)
        result = await service(backend).execute(prepared, 'confirm', 123)
        assert result.invoice.posted and result.tax_invoice.posted
        assert result.tax_invoice.source_document_id == result.invoice.document_id
        assert result.pdf.provenance.document_id == result.tax_invoice.document_id
        assert result.pdf.provenance.template == 'TaxInvoiceLandscapeEN'
        assert (backend.creates, backend.source_posts, backend.generates) == (1, 1, 1)
        assert backend.tax_posts == (0 if generated_posted else 1)
        assert backend.trace.index('source_post') < backend.trace.index('generate_tax') < backend.trace.index('tax_pdf')
        cached = backend.journal.get(prepared.operation_id)
        assert cached.tax.invoice == result.tax_invoice and cached.tax.print_provenance == result.pdf.provenance
        backend.journal = store(backend.journal.path, create=False)
        repeated = await service(backend).execute(prepared, 'restart-repeat', 123)
        assert repeated == result and backend.generates == backend.prints == 1
    asyncio.run(scenario())


@pytest.mark.parametrize('fault', ['generate_before_commit', 'generate_after_commit'])
def test_generation_lost_response_restart_reconciles_without_duplicate(fault, tmp_path):
    backend = SyntheticTaxProvider(store(tmp_path / 'private/operations.sqlite'))
    backend.tax_fault = fault
    async def scenario():
        prepared = await prepare(backend)
        with pytest.raises(WorkflowFailure):
            await service(backend).execute(prepared, 'confirm', 123)
        assert backend.generates == 1 and backend.journal.get(prepared.operation_id).tax is not None
        backend.journal = store(backend.journal.path, create=False)
        backend.tax_fault = None
        if fault == 'generate_after_commit':
            result = await service(backend).execute(prepared, 'restart-retry', 123)
            assert result.tax_invoice.posted
        else:
            with pytest.raises(WorkflowFailure):
                await service(backend).execute(prepared, 'restart-retry', 123)
        assert backend.creates == backend.generates == 1
    asyncio.run(scenario())


def test_returned_reference_survives_restart_before_tax_readback(tmp_path):
    backend = SyntheticTaxProvider(store(tmp_path / 'private/operations.sqlite'))
    backend.tax_fault = 'hidden_after_return'
    async def scenario():
        prepared = await prepare(backend)
        with pytest.raises(WorkflowFailure):
            await service(backend).execute(prepared, 'confirm', 123)
        saved = store(backend.journal.path, create=False).get(prepared.operation_id).tax
        assert saved.phase == 'generation_started' and saved.invoice is None
        assert saved.returned_reference.document_id == backend.tax_documents[prepared.operation_id].document_id
        backend.hidden_tax = False
        backend.tax_fault = None
        backend.journal = store(backend.journal.path, create=False)
        assert (await service(backend).execute(prepared, 'retry', 123)).tax_invoice.posted
        assert backend.generates == 1
    asyncio.run(scenario())


@pytest.mark.parametrize('fault', ['post_before_commit', 'post_after_commit'])
def test_unknown_tax_posting_is_not_replayed(fault, tmp_path):
    backend = SyntheticTaxProvider(store(tmp_path / 'private/operations.sqlite'), generated_posted=False)
    backend.tax_fault = fault
    async def scenario():
        prepared = await prepare(backend)
        with pytest.raises(WorkflowFailure):
            await service(backend).execute(prepared, 'confirm', 123)
        backend.tax_fault = None
        backend.journal = store(backend.journal.path, create=False)
        if fault == 'post_after_commit':
            assert (await service(backend).execute(prepared, 'retry', 123)).tax_invoice.posted
        else:
            with pytest.raises(WorkflowFailure):
                await service(backend).execute(prepared, 'retry', 123)
        assert backend.generates == backend.tax_posts == 1
    asyncio.run(scenario())


@pytest.mark.parametrize('failure', ['pdf_timeout', 'wrong_pdf', 'revision_drift', 'foreign_parent'])
def test_pdf_and_source_mismatch_never_deliver_or_regenerate_tax(failure, tmp_path):
    backend = SyntheticTaxProvider(store(tmp_path / 'private/operations.sqlite'))
    backend.tax_fault = 'pdf_timeout' if failure == 'pdf_timeout' else None
    backend.bad_pdf = failure == 'wrong_pdf'
    backend.version_drift_at_print = failure == 'revision_drift'
    async def scenario():
        prepared = await prepare(backend)
        if failure == 'foreign_parent':
            # Generate once with a failed PDF, then make a later relation read inconsistent.
            backend.tax_fault = 'pdf_timeout'
            with pytest.raises(WorkflowFailure):
                await service(backend).execute(prepared, 'first', 123)
            backend.bad_parent = True
        with pytest.raises(WorkflowFailure):
            await service(backend).execute(prepared, 'confirm', 123)
        assert backend.journal.get(prepared.operation_id).pdf is None
        backend.tax_fault, backend.bad_pdf, backend.bad_parent, backend.version_drift_at_print = None, False, False, False
        await service(backend).execute(prepared, 'safe-retry', 123)
        assert backend.generates == 1 and backend.creates == 1
    asyncio.run(scenario())


def test_cached_tax_pdf_cannot_survive_document_version_change(tmp_path):
    backend = SyntheticTaxProvider(store(tmp_path / 'private/operations.sqlite'))
    async def scenario():
        prepared = await prepare(backend)
        await service(backend).execute(prepared, 'confirm', 123)
        current = backend.tax_documents[prepared.operation_id]
        backend.tax_documents[prepared.operation_id] = TaxInvoice(**{**current.model_dump(), 'revision': 'later-change'})
        with pytest.raises(WorkflowFailure):
            await service(backend).execute(prepared, 'repeat', 123)
        assert backend.prints == backend.generates == 1
    asyncio.run(scenario())


def test_v2_journal_migration_keeps_existing_source_intents(tmp_path):
    backend = SyntheticTaxProvider(store(tmp_path / 'private/operations.sqlite'))
    prepared = asyncio.run(prepare(backend))
    backend.journal.reserve(prepared, 123)
    backend.journal.claim_mutation(prepared.operation_id, 'create')
    backend.journal.claim_provider_request(prepared.operation_id, 'create')
    with sqlite3.connect(backend.journal.path) as db:
        db.execute('DROP TABLE tax_operations')
        db.execute('PRAGMA user_version=2')
    reopened = store(backend.journal.path, create=False)
    assert reopened.get(prepared.operation_id).phase == 'create_started'
    with pytest.raises(MutationUncertain):
        reopened.claim_provider_request(prepared.operation_id, 'create')


def test_tax_provider_requires_journal_before_source_mutation():
    backend = SyntheticTaxProvider(None)
    prepared = asyncio.run(prepare(backend))
    with pytest.raises(WorkflowFailure):
        asyncio.run(InvoiceService(backend, allow_real_writes=True).execute(prepared, 'confirm', 123))
    assert backend.creates == backend.generates == 0


@pytest.mark.parametrize('capability', ['posting_enabled', 'native_pdf_available', 'ensure_tax_invoice'])
def test_incomplete_native_capability_blocks_before_source_creation(tmp_path, capability):
    backend = SyntheticTaxProvider(store(tmp_path / 'private/operations.sqlite'))
    setattr(backend, capability, False)
    prepared = asyncio.run(prepare(backend))
    with pytest.raises(WorkflowFailure):
        asyncio.run(service(backend).execute(prepared, 'confirm', 123))
    assert backend.creates == backend.generates == 0


@pytest.mark.parametrize('lose_acknowledgement', [False, True])
def test_telegram_tax_pdf_restart_redelivery_and_unknown_delivery(tmp_path, lose_acknowledgement):
    path = tmp_path / 'private/operations.sqlite'
    backend = SyntheticTaxProvider(store(path))
    settings = Settings(token='123:' + 'x' * 32, webhook_secret='s' * 32,
        allowed_users=frozenset({123}), mode='firstbit_write', onec_write_enabled=True,
        operation_db=path, firstbit_write_schema_sha256='a' * 64)
    sent = []

    def respond(request):
        method = request.url.path.rsplit('/', 1)[-1]
        sent.append(method)
        if method == 'sendDocument':
            assert PDF in request.content
            if lose_acknowledgement:
                raise httpx.ReadTimeout('Synthetic lost delivery acknowledgement', request=request)
        return httpx.Response(200, json={'ok': True, 'result': {'message_id': 1, 'chat': {'id': 123}}})

    def application():
        backend.journal = store(path, create=False)
        return create_app(settings, backend=backend, telegram_transport=httpx.MockTransport(respond))

    def update(number, text):
        return {'update_id': number, 'message': {'message_id': number,
            'from': {'id': 123, 'is_bot': False}, 'chat': {'id': 123, 'type': 'private'}, 'text': text}}

    with TestClient(application()) as client:
        client.headers['X-Telegram-Bot-Api-Secret-Token'] = 's' * 32
        assert client.post('/telegram/webhook', json=update(1, TEXT)).status_code == 200
        token = client.app.state.bot.pending[123].token
        confirm = update(2, '/confirm ' + token)
        assert client.post('/telegram/webhook', json=confirm).status_code == (503 if lose_acknowledgement else 200)
        assert client.post('/telegram/webhook', json=confirm).status_code == 200
    with TestClient(application()) as client:
        client.headers['X-Telegram-Bot-Api-Secret-Token'] = 's' * 32
        assert client.post('/telegram/webhook', json=confirm).status_code == 200
        assert client.post('/telegram/webhook', json=update(3, '/retry')).status_code == 200
    assert backend.creates == backend.generates == backend.prints == sent.count('sendDocument') == 1
    operation_id = asyncio.run(prepare(backend)).operation_id
    assert backend.journal.delivery_status(operation_id, 123) == ('sending' if lose_acknowledgement else 'delivered')


def test_tax_generation_claim_is_atomic_across_independent_connections(tmp_path):
    path = tmp_path / 'private/operations.sqlite'
    backend = SyntheticTaxProvider(store(path))
    backend.tax_fault = 'generate_before_commit'
    prepared = asyncio.run(prepare(backend))
    with pytest.raises(WorkflowFailure):
        asyncio.run(service(backend).execute(prepared, 'first', 123))
    # Reconstruct the state immediately before any generation request was sent.
    with sqlite3.connect(path) as db:
        db.execute("DELETE FROM provider_requests WHERE stage='generate_tax'")
        db.execute('DELETE FROM tax_operations')

    def claim(_):
        try:
            store(path, create=False).claim_tax_generation(prepared.operation_id)
            return 'claimed'
        except MutationUncertain:
            return 'uncertain'

    with ThreadPoolExecutor(max_workers=4) as workers:
        results = list(workers.map(claim, range(8)))
    assert results.count('claimed') == 1 and results.count('uncertain') == 7


@pytest.mark.parametrize('corruption', ['tax_identity', 'pdf_template', 'pdf_version'])
def test_tax_journal_corruption_fails_closed(tmp_path, corruption):
    import json
    backend = SyntheticTaxProvider(store(tmp_path / 'private/operations.sqlite'))
    prepared = asyncio.run(prepare(backend))
    asyncio.run(service(backend).execute(prepared, 'confirm', 123))
    with sqlite3.connect(backend.journal.path) as db:
        if corruption == 'tax_identity':
            db.execute("UPDATE tax_operations SET tax_document_id='different-synthetic-tax'")
        else:
            meta = json.loads(db.execute('SELECT pdf_meta FROM tax_operations').fetchone()[0])
            meta['template' if corruption == 'pdf_template' else 'document_revision'] = 'unexpected'
            db.execute('UPDATE tax_operations SET pdf_meta=?', (json.dumps(meta),))
    with pytest.raises(JournalUnavailable):
        store(backend.journal.path, create=False).get(prepared.operation_id)
