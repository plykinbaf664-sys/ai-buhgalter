"""Synthetic native-provider contract proofs. No captured/prod records or sessions."""
import asyncio
from datetime import date
from decimal import Decimal
from pathlib import Path
import sqlite3
import time
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.bot import Bot
from app.main import create_app
from app.domain import (Invoice, InvoiceConflict, TaxInvoicePdf, TaxPdfProvenance,
                        TaxInvoice, TaxInvoiceReference, TaxOperationState, WorkflowFailure, WritesDisabled,
                        InvoiceCommand, UserProblem, OperationState, SourceMarkedForDeletion, ReadbackMismatch)
from app.fake_onec import FakeOneC
from app.operations import OperationJournal, MutationUncertain, JournalUnavailable
from app.parser import parse_command
from app.service import InvoiceService
from app.telegram_models import CallbackQuery

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
        if self.tax_fault == 'pdf_timeout' or self.tax_fault == 'pdf_once' and self.prints == 1:
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


def test_posted_invoice_can_gain_tax_invoice_on_later_retry_after_restart(tmp_path):
    class LaterTaxProvider(SyntheticTaxProvider):
        tax_read_available = False

        async def read_tax_operation(self, basis, invoice, operation_id):
            if not self.tax_read_available:
                raise TimeoutError('Synthetic tax lookup temporarily unavailable')
            return await super().read_tax_operation(basis, invoice, operation_id)

    backend = LaterTaxProvider(store(tmp_path / 'private/operations.sqlite'))

    async def scenario():
        prepared = await prepare(backend)
        with pytest.raises(WorkflowFailure):
            await service(backend).execute(prepared, 'first', 123)
        saved = backend.journal.get(prepared.operation_id)
        assert saved.phase == 'posted' and saved.invoice.posted and saved.tax is None
        assert backend.creates == backend.source_posts == 1 and backend.generates == 0
        backend.journal = store(backend.journal.path, create=False)
        backend.tax_read_available = True
        result = await service(backend).execute(prepared, 'later', 123)
        assert result.tax_invoice.posted and result.pdf.provenance.template == 'TaxInvoiceLandscapeEN'
        assert backend.creates == backend.source_posts == backend.generates == backend.prints == 1
        assert (await service(backend).execute(prepared, 'repeat', 123)) == result
        assert backend.generates == 1

    asyncio.run(scenario())


def test_repeated_request_offers_original_invoice_tax_continuation(tmp_path):
    class TemporarilyUnavailableTax(SyntheticTaxProvider):
        tax_read_available = False

        async def read_tax_operation(self, basis, invoice, operation_id):
            if not self.tax_read_available:
                raise TimeoutError('Synthetic lookup unavailable')
            return await super().read_tax_operation(basis, invoice, operation_id)

    backend = TemporarilyUnavailableTax(store(tmp_path / 'private/operations.sqlite'))

    async def scenario():
        original = await prepare(backend)
        with pytest.raises(WorkflowFailure):
            await service(backend).execute(original, 'first-confirm', 123)
        assert backend.creates == backend.source_posts == 1 and backend.generates == 0
        old_service = backend.services['service-accounting']
        backend.services['service-accounting'] = old_service.model_copy(update={'price': Decimal('1300')})
        backend.journal = store(backend.journal.path, create=False)
        backend.tax_read_available = True
        bot = Bot(service(backend), None, None)
        repeated = await prepare(backend)
        assert repeated.operation_id == original.operation_id
        assert repeated.preview.digest != original.preview.digest
        prompt = bot.show_preview(123, repeated, parse_command(TEXT))
        assert 'Tax Invoice' in prompt.text and 'Новый Invoice не создаётся' in prompt.text
        assert 'Создать Tax Invoice' in prompt.reply_markup.inline_keyboard[0][0].text
        assert 'Ранее подтверждённые данные' in prompt.text
        assert 123 not in bot.pending
        callback_data = prompt.reply_markup.inline_keyboard[0][0].callback_data
        callback = lambda uid: CallbackQuery.model_validate({'id': 'synthetic-callback',
            'from': {'id': uid, 'is_bot': False},
            'message': {'message_id': 1, 'chat': {'id': uid, 'type': 'private'}},
            'data': callback_data})
        with pytest.raises(UserProblem):
            await bot.prepare_callback(callback(456), 'foreign')
        selected = await bot.prepare_callback(callback(123), 'continue')
        assert selected == original
        result = await bot.service.execute(selected, 'continue', 123)
        assert result.tax_invoice.posted and result.pdf is not None
        assert backend.creates == backend.source_posts == backend.generates == 1
        backend.journal.claim_delivery(original.operation_id, 123)
        backend.journal.delivered(original.operation_id, 123)
        finished = bot.show_preview(123, repeated, parse_command(TEXT))
        assert finished.reply_markup is None and 'PDF уже был доставлен' in finished.text
        other = await bot.service.prepare(
            InvoiceCommand(client='ООО Ромашка', invoice_date=date(2026, 12, 1)), 'other', 123)
        fresh = bot.show_preview(123, other, InvoiceCommand(client='ООО Ромашка', invoice_date=date(2026, 12, 1)))
        assert any(button.callback_data.startswith('invoice:confirm:')
                   for row in fresh.reply_markup.inline_keyboard for button in row)

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
            assert b'filename="Tax Invoice.pdf"' in request.content
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
        repeated_button = {'update_id': 20, 'callback_query': {'id': 'repeat-confirm',
            'from': {'id': 123, 'is_bot': False}, 'message': {'message_id': 1,
            'chat': {'id': 123, 'type': 'private'}}, 'data': 'invoice:confirm:' + token}}
        assert client.post('/telegram/webhook', json=repeated_button).status_code == 200
        assert sent.count('sendDocument') == 1
        assert sent.count('editMessageReplyMarkup') == 1
    with TestClient(application()) as client:
        client.headers['X-Telegram-Bot-Api-Secret-Token'] = 's' * 32
        assert client.post('/telegram/webhook', json=confirm).status_code == 200
        assert client.post('/telegram/webhook', json=update(3, '/retry')).status_code == 200
    assert backend.creates == backend.generates == backend.prints == sent.count('sendDocument') == 1
    operation_id = asyncio.run(prepare(backend)).operation_id
    assert backend.journal.delivery_status(operation_id, 123) == ('sending' if lose_acknowledgement else 'delivered')


@pytest.mark.parametrize('fault,expected_prints', [('pdf_once', 2), ('generate_after_commit', 1)])
def test_deferred_confirmation_recovers_pdf_without_recreating_documents(tmp_path, fault, expected_prints):
    path = tmp_path / 'private/operations.sqlite'
    backend = SyntheticTaxProvider(store(path))
    backend.tax_fault = fault
    settings = Settings(token='123:' + 'x' * 32, webhook_secret='s' * 32,
        allowed_users=frozenset({123}), mode='firstbit_write', onec_write_enabled=True,
        operation_db=path, firstbit_write_schema_sha256='a' * 64)
    sent = []

    def respond(request):
        sent.append(request.url.path.rsplit('/', 1)[-1])
        return httpx.Response(200, json={'ok': True, 'result': {'message_id': 1, 'chat': {'id': 123}}})

    def update(number, text):
        return {'update_id': number, 'message': {'message_id': number,
            'from': {'id': 123, 'is_bot': False}, 'chat': {'id': 123, 'type': 'private'}, 'text': text}}

    with TestClient(create_app(settings, backend=backend, telegram_transport=httpx.MockTransport(respond))) as client:
        client.headers['X-Telegram-Bot-Api-Secret-Token'] = 's' * 32
        bot = client.app.state.bot
        bot.defer_financial = True
        bot._completion_retry_delay = 0
        assert client.post('/telegram/webhook', json=update(1, TEXT)).status_code == 200
        token = bot.pending[123].token
        confirm = update(2, '/confirm ' + token)
        assert client.post('/telegram/webhook', json=confirm).status_code == 200
        operation_id = next(iter(bot._completion_tasks))
        for _ in range(200):
            if backend.journal.delivery_status(operation_id, 123) == 'delivered':
                break
            time.sleep(.02)
        assert backend.journal.delivery_status(operation_id, 123) == 'delivered'
        assert client.post('/telegram/webhook', json=confirm).status_code == 200
        assert client.post('/telegram/webhook', json=update(3, '/retry')).status_code == 200
    assert backend.creates == backend.generates == 1
    assert backend.prints == expected_prints
    assert sent.count('sendDocument') == 1


def test_failed_preconfirmation_read_keeps_preview_without_phantom_recovery(tmp_path, monkeypatch):
    backend = SyntheticTaxProvider(store(tmp_path / 'private/operations.sqlite'))
    worker = service(backend)
    bot = Bot(worker, None, None)
    prepared = asyncio.run(prepare(backend))
    bot.show_preview(123, prepared, parse_command(TEXT))
    original = bot.pending[123]

    async def unavailable(*args):
        raise WorkflowFailure('reconcile', None, prepared.operation_id, 'unknown')

    monkeypatch.setattr(worker, 'refresh', unavailable)
    with pytest.raises(UserProblem, match='Preview сохранён'):
        asyncio.run(bot.confirm(123, original, 'unavailable'))
    assert bot.pending[123] == original
    assert not bot.recoveries and backend.journal.get(prepared.operation_id) is None


def test_new_preview_invalidates_old_confirmed_callback(tmp_path):
    backend = SyntheticTaxProvider(store(tmp_path / 'private/operations.sqlite'))
    bot = Bot(service(backend), None, None)
    old = asyncio.run(prepare(backend))
    bot.show_preview(123, old, parse_command(TEXT))
    old_token = bot.pending[123].token
    bot.confirmed_tokens[old_token] = (123, old)
    new = old.model_copy(update={'basis': old.basis.model_copy(update={'operation_nonce': uuid4()})})
    assert new.operation_id != old.operation_id
    bot.show_preview(123, new, parse_command(TEXT))
    assert old_token not in bot.confirmed_tokens
    callback = CallbackQuery.model_validate({'id': 'old-confirm',
        'from': {'id': 123, 'is_bot': False},
        'message': {'message_id': 1, 'chat': {'id': 123, 'type': 'private'}},
        'data': f'invoice:confirm:{old_token}'})
    result = asyncio.run(bot.prepare_callback(callback, 'stale'))
    assert 'Актуальный счёт' in result.text
    assert backend.journal.get(old.operation_id) is None


def test_retry_ignores_deleted_old_operation_and_selects_live_one(tmp_path, monkeypatch):
    backend = SyntheticTaxProvider(store(tmp_path / 'private/operations.sqlite'))
    worker = service(backend)
    bot = Bot(worker, None, None)
    deleted = asyncio.run(prepare(backend))
    current = deleted.model_copy(update={'basis': deleted.basis.model_copy(update={'operation_nonce': uuid4()})})
    for prepared in (deleted, current):
        backend.journal.reserve(prepared, 123)
        bot._remember_recovery(123, prepared)

    async def read_state(prepared):
        if prepared.operation_id == deleted.operation_id:
            raise SourceMarkedForDeletion()
        return OperationState(operation_id=prepared.operation_id, status='not_started')

    monkeypatch.setattr(worker, '_read_state', read_state)
    assert asyncio.run(bot._retry_choice(123)) == current
    assert deleted.operation_id in bot.recoveries[123]
    with pytest.raises(UserProblem, match='удалён'):
        asyncio.run(bot._choose_recovery(123, deleted.operation_id[:16]))


def test_provider_changed_created_invoice_is_not_retried_as_new_create(tmp_path, monkeypatch):
    backend = SyntheticTaxProvider(store(tmp_path / 'private/operations.sqlite'))
    prepared = asyncio.run(prepare(backend))

    async def changed(*args):
        raise ReadbackMismatch()

    monkeypatch.setattr(backend, 'read_operation', changed)
    with pytest.raises(WorkflowFailure) as failure:
        asyncio.run(service(backend).execute(prepared, 'mismatch', 123))
    assert failure.value.stage == 'readback_mismatch'
    assert backend.creates == backend.generates == 0


def test_restart_resumes_confirmed_pdf_without_repeat_create_or_generate(tmp_path):
    path = tmp_path / 'private/operations.sqlite'
    backend = SyntheticTaxProvider(store(path))
    backend.tax_fault = 'pdf_timeout'
    prepared = asyncio.run(prepare(backend))
    with pytest.raises(WorkflowFailure) as failure:
        asyncio.run(service(backend).execute(prepared, 'before-restart', 123))
    assert failure.value.stage == 'tax_pdf'
    assert backend.creates == backend.generates == backend.prints == 1
    backend.tax_fault = None
    backend.journal = store(path, create=False)
    settings = Settings(token='123:' + 'x' * 32, webhook_secret='s' * 32,
        allowed_users=frozenset({123}), mode='firstbit_write', onec_write_enabled=True,
        operation_db=path, firstbit_write_schema_sha256='a' * 64)
    sent = []

    def respond(request):
        sent.append(request.url.path.rsplit('/', 1)[-1])
        return httpx.Response(200, json={'ok': True, 'result': {'message_id': 1, 'chat': {'id': 123}}})

    with TestClient(create_app(settings, backend=backend, telegram_transport=httpx.MockTransport(respond))) as client:
        bot = client.app.state.bot
        bot.defer_financial = True
        client.portal.call(bot.resume_pending)
        for _ in range(200):
            if backend.journal.delivery_status(prepared.operation_id, 123) == 'delivered':
                break
            time.sleep(.02)
        assert backend.journal.delivery_status(prepared.operation_id, 123) == 'delivered'
    assert backend.creates == backend.generates == 1
    assert backend.prints == 2 and sent.count('sendDocument') == 1


def test_bot_finishes_known_posted_operation_after_lost_generation_response(tmp_path):
    path = tmp_path / 'private/operations.sqlite'
    backend = SyntheticTaxProvider(store(path))
    backend.tax_fault = 'generate_after_commit'
    settings = Settings(token='123:' + 'x' * 32, webhook_secret='s' * 32,
        allowed_users=frozenset({123}), mode='firstbit_write', onec_write_enabled=True,
        operation_db=path, firstbit_write_schema_sha256='a' * 64)
    sent = []
    def respond(request):
        sent.append(request.url.path.rsplit('/', 1)[-1])
        return httpx.Response(200, json={'ok': True, 'result': {'message_id': 1, 'chat': {'id': 123}}})
    with TestClient(create_app(settings, backend=backend, telegram_transport=httpx.MockTransport(respond))) as client:
        client.headers['X-Telegram-Bot-Api-Secret-Token'] = 's' * 32
        def update(number, text):
            return {'update_id': number, 'message': {'message_id': number,
                'from': {'id': 123, 'is_bot': False}, 'chat': {'id': 123, 'type': 'private'}, 'text': text}}
        assert client.post('/telegram/webhook', json=update(1, TEXT)).status_code == 200
        token = client.app.state.bot.pending[123].token
        assert client.post('/telegram/webhook', json=update(2, '/confirm ' + token)).status_code == 200
    assert backend.creates == backend.generates == backend.prints == sent.count('sendDocument') == 1


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
