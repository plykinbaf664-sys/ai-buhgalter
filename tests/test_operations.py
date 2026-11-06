"""Durability proofs use synthetic accounting data, never a live FirstBit write."""
import asyncio
from concurrent.futures import ProcessPoolExecutor
from datetime import date
import hashlib
import multiprocessing
import os
from pathlib import Path
import sqlite3
from uuid import UUID

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.domain import Invoice, InvoiceCommand, InvoiceConflict, OperationState, SourceMarkedForDeletion, UserProblem, WorkflowFailure
from app.fake_onec import FakeOneC
from app.main import create_app
from app.operations import JournalUnavailable, MutationUncertain, OperationJournal
from app.parser import parse_command
from app.service import InvoiceService

TEXT = "Сформируй счёт для ООО Ромашка за сентябрь 2026"


def journal(path):
    return OperationJournal(path, namespace="synthetic-provider", create=True)


def prepared(backend=None):
    return asyncio.run(InvoiceService(backend or FakeOneC()).prepare(parse_command(TEXT), "prepare", 123))


def prepared_on(backend, day, client="ООО Ромашка"):
    return asyncio.run(InvoiceService(backend).prepare(
        InvoiceCommand(client=client, invoice_date=day), "prepare", 123))


def _claim_in_process(path):
    store = journal(Path(path))
    operation_id = prepared().operation_id
    try:
        store.claim_mutation(operation_id, "create")
        return "claimed"
    except MutationUncertain:
        return "uncertain"


def test_cross_process_atomic_claim_and_reopen(tmp_path):
    path = tmp_path / "state" / "operations.sqlite"
    value = prepared()
    journal(path).reserve(value, 123)
    with ProcessPoolExecutor(max_workers=3, mp_context=multiprocessing.get_context("spawn")) as pool:
        results = list(pool.map(_claim_in_process, [str(path)] * 6))
    assert results.count("claimed") == 1 and results.count("uncertain") == 5
    reopened = journal(path)
    assert reopened.get(value.operation_id).phase == "create_started"
    assert reopened.recoveries() == {123: value}


def test_multiple_unfinished_operations_are_restored_without_choosing_one(tmp_path):
    backend = FakeOneC()
    first = prepared_on(backend, date(2026, 9, 1))
    second = prepared_on(backend, date(2026, 10, 1))
    store = journal(tmp_path / "state" / "operations.sqlite")
    store.reserve(first, 123)
    store.reserve(second, 123)
    restored = journal(store.path).pending_recoveries()
    assert {item.operation_id for item in restored[123]} == {first.operation_id, second.operation_id}
    with pytest.raises(JournalUnavailable):
        store.recoveries()


def test_legacy_and_independent_operation_share_business_basis_without_journal_collision(tmp_path):
    old = prepared()
    new_basis = old.basis.model_copy(update={'operation_nonce': UUID(int=17)})
    new = old.model_copy(update={'basis': new_basis})
    store = journal(tmp_path / 'state' / 'operations.sqlite')
    store.reserve(old, 123)
    store.reserve(new, 123)
    assert old.basis.key == new.basis.key and old.operation_id != new.operation_id
    assert store.get(old.operation_id).prepared == old
    assert journal(store.path).get(new.operation_id).prepared == new


def test_distinct_invoice_can_be_confirmed_while_old_operation_waits(tmp_path):
    backend = FakeOneC()
    first = prepared_on(backend, date(2026, 9, 1), "ООО Двойник 1")
    second = prepared_on(backend, date(2026, 10, 1), "ООО Двойник 2")
    store = OperationJournal(tmp_path / "state" / "operations.sqlite",
        namespace="invoice:v1:mock:" + hashlib.sha256(b"FakeOneC").hexdigest(), create=True)
    store.reserve(first, 123)
    store.reserve(second, 123)
    settings = app_settings(store.path)
    sent = []

    def respond(request):
        sent.append(request.url.path.rsplit("/", 1)[-1])
        if request.url.path.endswith("answerCallbackQuery"):
            return httpx.Response(200, json={"ok": True, "result": True})
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 1, "chat": {"id": 123}}})

    def app():
        return create_app(settings, backend=backend, telegram_transport=httpx.MockTransport(respond))

    with TestClient(app()) as client:
        client.headers["X-Telegram-Bot-Api-Secret-Token"] = "s" * 32
        bot = client.app.state.bot
        waiting = asyncio.run(bot._retry_choice(123))
        assert len(waiting.reply_markup.inline_keyboard) == 2
        original_read = bot.service._read_state
        async def with_deleted_old(item):
            if item.operation_id == first.operation_id:
                raise SourceMarkedForDeletion()
            return OperationState(operation_id=item.operation_id, status='not_started')
        bot.service._read_state = with_deleted_old
        assert asyncio.run(bot._retry_choice(123)) == second
        bot.service._read_state = original_read
        with pytest.raises(UserProblem):
            asyncio.run(bot._choose_recovery(456, first.operation_id[:16]))
        current = prepared_on(backend, date(2026, 11, 1))
        prompt = bot.show_preview(123, current, InvoiceCommand(client="ООО Ромашка", invoice_date=date(2026, 11, 1)))
        assert any(button.callback_data.startswith("invoice:confirm:")
                   for row in prompt.reply_markup.inline_keyboard for button in row)
        token = bot.pending[123].token
        assert client.post("/telegram/webhook", json=update(1, "/confirm " + token)).status_code == 200
        assert len(backend.documents) == 1
        assert set(bot.recoveries[123]) == {first.operation_id, second.operation_id}
        same = bot.show_preview(123, first, InvoiceCommand(client="ООО Двойник 1", invoice_date=date(2026, 9, 1)))
        assert not any(button.callback_data.startswith("invoice:confirm:")
                       for row in same.reply_markup.inline_keyboard for button in row)
        independent = first.model_copy(update={'basis': first.basis.model_copy(
            update={'operation_nonce': UUID(int=19)})})
        fresh = bot.show_preview(123, independent,
            InvoiceCommand(client="ООО Двойник 1", invoice_date=date(2026, 9, 1)))
        assert any(button.callback_data.startswith("invoice:confirm:")
                   for row in fresh.reply_markup.inline_keyboard for button in row)
    with TestClient(app()) as client:
        client.headers["X-Telegram-Bot-Api-Secret-Token"] = "s" * 32
        bot = client.app.state.bot
        assert set(bot.recoveries[123]) == {first.operation_id, second.operation_id}
        next_invoice = prepared_on(backend, date(2026, 12, 1))
        bot.show_preview(123, next_invoice, InvoiceCommand(client="ООО Ромашка", invoice_date=date(2026, 12, 1)))
        next_token = bot.pending[123].token
        assert client.post("/telegram/webhook", json=update(2, "/retry")).status_code == 200
        callback = {"update_id": 3, "callback_query": {"id": "recovery-choice",
            "from": {"id": 123, "is_bot": False}, "message": {"message_id": 1,
            "chat": {"id": 123, "type": "private"}}, "data": "recovery:" + first.operation_id[:16]}}
        assert client.post("/telegram/webhook", json=callback).status_code == 200
        assert len(backend.documents) == 2
        assert set(bot.recoveries[123]) == {second.operation_id}
        assert bot.pending[123].token == next_token
        assert bot.contexts[123].prepared.operation_id == next_invoice.operation_id
        assert client.post("/telegram/webhook", json=callback).status_code == 200
        assert len(backend.documents) == 2


def test_confirmed_snapshot_conflict_and_provider_scope(tmp_path):
    path = tmp_path / "state" / "operations.sqlite"
    value = prepared()
    store = journal(path)
    store.reserve(value, 123)
    with pytest.raises(InvoiceConflict):
        store.reserve(type(value)(**{**value.model_dump(), "display_name": "Another scope"}), 123)
    with pytest.raises(JournalUnavailable):
        OperationJournal(path, namespace="different-provider")
    assert journal(path).get(value.operation_id).prepared == value


def test_missing_durable_store_is_not_automatically_reinitialized(tmp_path):
    path = tmp_path / "state" / "operations.sqlite"
    with pytest.raises(JournalUnavailable):
        OperationJournal(path, namespace="synthetic-provider")
    assert not path.exists()


def test_namespace_and_permissions_are_part_of_the_private_store(tmp_path):
    path = tmp_path / "private" / "operations.sqlite"
    store = journal(path)
    if os.name != "nt":
        assert path.stat().st_mode & 0o777 == 0o600
        assert path.parent.stat().st_mode & 0o777 == 0o700
        path.chmod(0o644)
        with pytest.raises(JournalUnavailable):
            journal(path)
        path.chmod(0o600)
    with sqlite3.connect(path) as db:
        db.execute("PRAGMA user_version=99")
    with pytest.raises(JournalUnavailable):
        store.recoveries()


@pytest.mark.parametrize("corruption", ["empty_existing", "unknown_version", "bad_snapshot", "unknown_phase"])
def test_unknown_or_corrupt_state_never_auto_resets(tmp_path, corruption):
    path = tmp_path / "state" / "operations.sqlite"
    value = prepared()
    store = journal(path)
    store.reserve(value, 123)
    if corruption == "empty_existing":
        path.write_bytes(b"")
    else:
        with sqlite3.connect(path) as db:
            if corruption == "unknown_version":
                db.execute("PRAGMA user_version=99")
            elif corruption == "bad_snapshot":
                db.execute("UPDATE operations SET digest=?", ("0" * 64,))
            else:
                db.execute("UPDATE operations SET phase='not_started'")
    with pytest.raises(JournalUnavailable):
        journal(path).get(value.operation_id)


def test_persisted_create_intent_and_absent_readback_never_creates_again(tmp_path):
    backend = FakeOneC()
    value = prepared(backend)
    path = tmp_path / "state" / "operations.sqlite"
    store = journal(path)
    store.reserve(value, 123)
    store.claim_mutation(value.operation_id, "create")
    for _ in range(2):
        service = InvoiceService(backend, journal=journal(path))
        with pytest.raises(WorkflowFailure) as failure:
            asyncio.run(service.execute(value, "retry", 123))
        assert failure.value.state == "unknown"
    assert not backend.documents
    assert journal(path).get(value.operation_id).phase == "create_started"


@pytest.mark.parametrize("fault", ["create_lost_response", "post_lost_response"])
def test_lost_committed_response_restart_and_repeat_keep_one_document(tmp_path, fault):
    backend = FakeOneC(fault)
    value = prepared(backend)
    path = tmp_path / "state" / "operations.sqlite"
    with pytest.raises(WorkflowFailure):
        asyncio.run(InvoiceService(backend, journal=journal(path)).execute(value, "first", 123))
    restored = journal(path).recoveries()[123]
    first = asyncio.run(InvoiceService(backend, journal=journal(path)).execute(restored, "restart", 123))
    second = asyncio.run(InvoiceService(backend, journal=journal(path)).execute(restored, "repeat", 123))
    assert len(backend.documents) == 1
    assert first == second and first.invoice.posted
    assert journal(path).get(value.operation_id).pdf == first.pdf


def test_lost_uncommitted_post_is_not_blindly_repeated(tmp_path):
    class FailingPost(FakeOneC):
        calls = 0
        async def ensure_posted(self, *args):
            self.calls += 1
            raise TimeoutError("synthetic uncommitted posting")
    backend = FailingPost()
    value = prepared(backend)
    path = tmp_path / "state" / "operations.sqlite"
    with pytest.raises(WorkflowFailure):
        asyncio.run(InvoiceService(backend, journal=journal(path)).execute(value, "first", 123))
    assert journal(path).get(value.operation_id).phase == "post_started"
    with pytest.raises(WorkflowFailure) as failure:
        asyncio.run(InvoiceService(backend, journal=journal(path)).execute(value, "restart", 123))
    assert failure.value.state == "unknown"
    assert backend.calls == 1 and len(backend.documents) == 1


def test_only_unsent_or_proved_session_rejected_post_can_resume_same_draft(tmp_path):
    backend=FakeOneC()
    value=prepared(backend)
    store=journal(tmp_path/'state/operations.sqlite')
    store.reserve(value,123)
    store.claim_mutation(value.operation_id,'create')
    invoice=asyncio.run(backend.ensure_draft(value.basis,value.operation_id))
    store.observe(value.operation_id,invoice)
    store.claim_mutation(value.operation_id,'post')
    with pytest.raises(MutationUncertain):
        store.claim_mutation(value.operation_id,'post')
    store.claim_mutation(value.operation_id,'post',allow_unsubmitted=True)
    store.claim_provider_request(value.operation_id,'post')
    with pytest.raises(MutationUncertain):
        store.claim_mutation(value.operation_id,'post',allow_unsubmitted=True)
    store.reject_native_post_before_application(value.operation_id,'post')
    reopened=journal(store.path)
    reopened.claim_mutation(value.operation_id,'post',allow_unsubmitted=True)
    reopened.claim_provider_request(value.operation_id,'post')
    with pytest.raises(MutationUncertain):
        reopened.claim_provider_request(value.operation_id,'post')
    assert reopened.get(value.operation_id).invoice==invoice


def test_unknown_after_committed_create_requires_later_readback_not_second_create(tmp_path):
    class Uncertain(FakeOneC):
        creates = 0
        read_fault = False
        async def ensure_draft(self, basis, operation_id):
            self.creates += 1
            await super().ensure_draft(basis, operation_id)
            self.read_fault = True
            raise TimeoutError("synthetic committed response lost")
        async def read_operation(self, basis, operation_id):
            if self.read_fault:
                return OperationState(operation_id=operation_id, status="unknown")
            return await super().read_operation(basis, operation_id)
    backend = Uncertain()
    value = prepared(backend)
    path = tmp_path / "private" / "operations.sqlite"
    with pytest.raises(WorkflowFailure) as failure:
        asyncio.run(InvoiceService(backend, journal=journal(path)).execute(value, "lost", 123))
    assert failure.value.state == "unknown" and backend.creates == 1
    backend.read_fault = False
    result = asyncio.run(InvoiceService(backend, journal=journal(path)).execute(value, "reconcile", 123))
    assert result.invoice.posted and backend.creates == 1 and len(backend.documents) == 1


def test_journal_failure_precedes_any_mutation(tmp_path):
    backend = FakeOneC()
    value = prepared(backend)
    path = tmp_path / "state" / "operations.sqlite"
    store = journal(path)
    path.write_bytes(b"not a database")
    with pytest.raises(WorkflowFailure):
        asyncio.run(InvoiceService(backend, journal=store).execute(value, "bad-disk", 123))
    assert not backend.documents


def test_document_and_pdf_identity_cannot_move_between_operations(tmp_path):
    backend = FakeOneC()
    value = prepared(backend)
    store = journal(tmp_path / "state" / "operations.sqlite")
    result = asyncio.run(InvoiceService(backend, journal=store).execute(value, "complete", 123))
    wrong = Invoice(**{**result.invoice.model_dump(), "document_id": "synthetic-other-document"})
    with pytest.raises(InvoiceConflict):
        store.observe(value.operation_id, wrong)
    with pytest.raises(InvoiceConflict):
        store.cache_pdf(value.operation_id, wrong, result.pdf)
    with sqlite3.connect(store.path) as db:
        db.execute("UPDATE operations SET pdf_sha256=?", ("0" * 64,))
    with pytest.raises(JournalUnavailable):
        store.get(value.operation_id)


def app_settings(path):
    return Settings(token="123:" + "x" * 32, webhook_secret="s" * 32,
                    allowed_users=frozenset({123}), operation_db=path)


def update(number, text):
    return {"update_id": number, "message": {"message_id": number,
        "from": {"id": 123, "is_bot": False}, "chat": {"id": 123, "type": "private"}, "text": text}}


@pytest.mark.parametrize("lose_delivery", [False, True])
def test_actual_app_restart_restores_confirmed_operation_and_never_resends_pdf(tmp_path, lose_delivery):
    backend = FakeOneC("create_lost_response")
    settings = app_settings(tmp_path / "state" / "operations.sqlite")
    calls = []
    def respond(request):
        calls.append(request.url.path.rsplit("/", 1)[-1])
        if request.url.path.endswith("sendDocument") and lose_delivery:
            raise httpx.ReadTimeout("synthetic lost PDF acknowledgement", request=request)
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 1, "chat": {"id": 123}}})
    def app():
        return create_app(settings, backend=backend, telegram_transport=httpx.MockTransport(respond))
    with TestClient(app()) as client:
        client.headers["X-Telegram-Bot-Api-Secret-Token"] = "s" * 32
        assert client.post('/telegram/webhook', json=update(1, TEXT)).status_code == 200
        token = client.app.state.bot.pending[123].token
        assert client.post('/telegram/webhook', json=update(2, '/confirm ' + token)).status_code == 200
        assert len(backend.documents) == 1
    with TestClient(app()) as client:
        assert 123 in client.app.state.bot.recoveries
        client.headers["X-Telegram-Bot-Api-Secret-Token"] = "s" * 32
        response = client.post('/telegram/webhook', json=update(3, '/retry'))
        assert response.status_code == (503 if lose_delivery else 200)
    with TestClient(app()) as client:
        client.headers["X-Telegram-Bot-Api-Secret-Token"] = "s" * 32
        assert client.post('/telegram/webhook', json=update(3, '/retry')).status_code == 200
    assert calls.count('sendDocument') == 1
    assert len(backend.documents) == 1


def test_unconfirmed_preview_is_not_restored_as_write_permission(tmp_path):
    backend = FakeOneC()
    settings = app_settings(tmp_path / "state" / "operations.sqlite")
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={
        "ok": True, "result": {"message_id": 1, "chat": {"id": 123}}}))
    with TestClient(create_app(settings, backend=backend, telegram_transport=transport)) as client:
        client.headers['X-Telegram-Bot-Api-Secret-Token'] = 's' * 32
        assert client.post('/telegram/webhook', json=update(1, TEXT)).status_code == 200
        old = client.app.state.bot.pending[123].token
    with TestClient(create_app(settings, backend=backend, telegram_transport=transport)) as client:
        assert not client.app.state.bot.recoveries
        client.headers['X-Telegram-Bot-Api-Secret-Token'] = 's' * 32
        assert client.post('/telegram/webhook', json=update(2, '/confirm ' + old)).status_code == 200
    assert not backend.documents


def test_repeated_confirm_and_redelivery_after_restart_do_not_duplicate(tmp_path):
    backend = FakeOneC()
    settings = app_settings(tmp_path / "private" / "operations.sqlite")
    sent = []
    def respond(request):
        sent.append(request.url.path.rsplit('/', 1)[-1])
        return httpx.Response(200, json={'ok': True, 'result': {'message_id': 1, 'chat': {'id': 123}}})
    def app():return create_app(settings, backend=backend, telegram_transport=httpx.MockTransport(respond))
    with TestClient(app()) as client:
        client.headers['X-Telegram-Bot-Api-Secret-Token'] = 's' * 32
        client.post('/telegram/webhook', json=update(1, TEXT))
        token = client.app.state.bot.pending[123].token
        confirm = update(2, '/confirm ' + token)
        assert client.post('/telegram/webhook', json=confirm).status_code == 200
        assert client.post('/telegram/webhook', json=confirm).status_code == 200
    with TestClient(app()) as client:
        client.headers['X-Telegram-Bot-Api-Secret-Token'] = 's' * 32
        assert client.post('/telegram/webhook', json=confirm).status_code == 200
        client.post('/telegram/webhook', json=update(3, TEXT))
        assert 123 not in client.app.state.bot.pending
        assert client.app.state.bot.service.journal.delivery_status(prepared().operation_id, 123) == 'delivered'
    assert len(backend.documents) == 1 and sent.count('sendDocument') == 1


def test_restart_between_cached_pdf_and_delivery_resumes_same_document(tmp_path):
    backend = FakeOneC()
    settings = app_settings(tmp_path / "private" / "operations.sqlite")
    sent = []
    def respond(request):
        sent.append(request.url.path.rsplit('/', 1)[-1])
        return httpx.Response(200, json={'ok': True, 'result': {'message_id': 1, 'chat': {'id': 123}}})
    def app():return create_app(settings, backend=backend, telegram_transport=httpx.MockTransport(respond))
    with TestClient(app()) as client:
        client.headers['X-Telegram-Bot-Api-Secret-Token'] = 's' * 32
        client.post('/telegram/webhook', json=update(1, TEXT))
        token = client.app.state.bot.pending[123].token
        def fail_before_send(*args):raise JournalUnavailable()
        client.app.state.bot.service.journal.claim_delivery = fail_before_send
        assert client.post('/telegram/webhook', json=update(2, '/confirm ' + token)).status_code == 500
        assert len(backend.documents) == 1 and sent.count('sendDocument') == 0
    with TestClient(app()) as client:
        client.headers['X-Telegram-Bot-Api-Secret-Token'] = 's' * 32
        assert client.post('/telegram/webhook', json=update(3, '/retry')).status_code == 200
    assert len(backend.documents) == 1 and sent.count('sendDocument') == 1
