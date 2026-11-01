"""Candidate buttons use the real adapter with synthetic HTTP, never production data."""
import copy
import json
import re
from decimal import Decimal

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.domain import ResolvedClient
from app.main import create_app
from scripts.firstbit_fixture import FirstBitFixture, ref


TEXT = "Сформируй счёт для ООО Синтетика за сентябрь 2026"


@pytest.fixture
def flow(monkeypatch):
    fixture = FirstBitFixture()
    for key, value in fixture.env().items():
        monkeypatch.setenv(key, value)
    fixture.records["Catalog_Companies"].append({**fixture.records["Catalog_Companies"][0],
        "Ref_Key": ref(99), "ContractByDefault_Key": ref(11)})
    fixture.records["Catalog_CompanyContracts"].append({**fixture.records["Catalog_CompanyContracts"][0],
        "Ref_Key": ref(11), "Owner_Key": ref(99)})
    history = copy.deepcopy(fixture.records["Document_InventoryExpense"][0])
    history.update(Ref_Key=ref(12), Company_Key=ref(99), Contract_Key=ref(11))
    fixture.records["Document_InventoryExpense"].append(history)
    sent, controls = [], {"fail_delivery": False}

    def firstbit(request):
        if request.url.path.endswith("Document_InventoryExpense"):
            fixture.calls.append(request)
            assert request.method == "GET"
            company = re.search(r"Company_Key eq guid'([^']+)'", request.url.params["$filter"])[1]
            rows = [r for r in fixture.records["Document_InventoryExpense"] if r["Company_Key"] == company]
            return httpx.Response(200, json={"value": rows})
        return fixture.respond(request)

    def telegram(request):
        if request.url.path.endswith("answerCallbackQuery"):
            return httpx.Response(200, json={"ok": True, "result": True})
        assert request.url.path.endswith("sendMessage"), "PDF attempted"
        sent.append(json.loads(request.content))
        if controls["fail_delivery"]:
            controls["fail_delivery"] = False
            raise httpx.ReadTimeout("PRIVATE_ERROR")
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 1, "chat": {"id": sent[-1]["chat_id"]}}})

    settings = Settings(token="123:" + "x" * 32, webhook_secret="s" * 32,
                        allowed_users=frozenset({123, 456}), mode="firstbit_readonly")
    app = create_app(settings, telegram_transport=httpx.MockTransport(telegram),
                     firstbit_transport=httpx.MockTransport(firstbit))
    with TestClient(app) as client:
        client.headers["X-Telegram-Bot-Api-Secret-Token"] = "s" * 32
        yield client, fixture, sent, controls


def send(flow, text=TEXT, number=1):
    return flow[0].post("/telegram/webhook", json={"update_id": number, "message": {
        "message_id": number, "from": {"id": 123, "is_bot": False},
        "chat": {"id": 123, "type": "private"}, "text": text}})


def press(flow, data, number=2, user=123):
    return flow[0].post("/telegram/webhook", json={"update_id": number, "callback_query": {
        "id": str(number), "from": {"id": user, "is_bot": False},
        "message": {"message_id": 1, "chat": {"id": user, "type": "private"}}, "data": data}})


def button(flow, index=0):
    return flow[2][-1]["reply_markup"]["inline_keyboard"][index][0]["callback_data"]


def test_duplicate_choice_resumes_original_command_and_confirms_readonly(flow, caplog):
    assert send(flow).status_code == 200
    bot = flow[0].app.state.bot
    assert 123 not in bot.pending
    assert "TRN" in flow[2][-1]["text"]
    choice = button(flow, 1)
    assert ref(99) not in choice and len(choice.encode()) <= 64
    assert press(flow, choice).status_code == 200
    prepared = bot.pending[123].prepared
    assert prepared.request.client_id == ref(99)
    assert prepared.preview.historical_proposal.contract_id == ref(11)
    assert prepared.preview.historical_proposal.source_id == ref(12)
    assert prepared.preview.service_period.month == 9
    assert bot.contexts[123].selected_client_id == ref(99)
    assert 123 not in bot.client_choices
    confirm = flow[2][-1]["reply_markup"]["inline_keyboard"][0][0]["callback_data"]
    assert press(flow, confirm, number=3).status_code == 200
    assert "документ не создавался" in flow[2][-1]["text"]
    assert {r.method for r in flow[1].calls} == {"GET"}
    assert "Синтетика" not in caplog.text and "TEST-TRN" not in caplog.text


@pytest.mark.parametrize("invalidate", ["new_message", "cancel_command", "cancel_button", "expired"])
def test_choice_invalidated_without_financial_side_effects(flow, invalidate):
    send(flow)
    old = button(flow)
    if invalidate == "expired":
        bot = flow[0].app.state.bot
        pending = bot.client_choices[123]
        bot.client_choices[123] = type(pending)(**{**pending.model_dump(), "expires_at": 0.0})
    elif invalidate == "cancel_button":
        press(flow, button(flow, 2))
    else:
        send(flow, "/cancel" if invalidate == "cancel_command" else TEXT, number=2)
    before = len(flow[1].calls)
    assert press(flow, old, number=3).status_code == 200
    assert "устарел" in flow[2][-1]["text"]
    assert len(flow[1].calls) == before
    assert not flow[0].app.state.bot.pending


@pytest.mark.parametrize("forgery", ["token", "index", "uuid", "other_user"])
def test_forged_or_cross_user_selection_cannot_read_a_different_client(flow, forgery):
    send(flow)
    data = button(flow)
    if forgery == "token":
        data = "client:" + "0" * 32 + ":1"
    elif forgery == "index":
        data = data.rsplit(":", 1)[0] + ":19"
    elif forgery == "uuid":
        data = "client:" + ref(99) + ":1"
    before = len(flow[1].calls)
    assert press(flow, data, user=456 if forgery == "other_user" else 123).status_code == 200
    assert len(flow[1].calls) == before
    assert not flow[0].app.state.bot.pending


def test_selected_record_rechecked_and_inactive_record_blocks(flow):
    send(flow)
    data = button(flow)
    flow[1].records["Catalog_Companies"][0]["Inactive"] = True
    assert press(flow, data).status_code == 200
    assert "больше не соответствует" in flow[2][-1]["text"]
    assert not flow[0].app.state.bot.pending
    assert not any(r.url.path.endswith("Document_InventoryExpense") for r in flow[1].calls)


def test_selection_without_own_history_stays_blocked(flow):
    send(flow)
    data = button(flow)
    flow[1].records["Document_InventoryExpense"] = []
    assert press(flow, data).status_code == 200
    assert "Компания выбрана" in flow[2][-1]["text"]
    assert "нет проведённых счетов" in flow[2][-1]["text"]
    assert not flow[0].app.state.bot.pending
    assert flow[0].app.state.bot.contexts[123].selected_client_id == ref(1)


def test_service_rejects_provider_substituting_another_selected_client(flow, monkeypatch):
    send(flow)
    data = button(flow)

    async def substitute(query, *, selected_id=None):
        return ResolvedClient(client_id=ref(99), display_name="Unexpected synthetic client")

    monkeypatch.setattr(flow[0].app.state.bot.service.onec, "resolve_client", substitute)
    assert press(flow, data).status_code == 200
    assert "Не удалось получить данные 1С" in flow[2][-1]["text"]
    assert not flow[0].app.state.bot.pending
    assert not any(r.url.path.endswith("Document_InventoryExpense") for r in flow[1].calls)


def test_partial_name_requires_explicit_button_even_with_one_candidate(flow):
    flow[1].records["Catalog_Companies"] = [flow[1].records["Catalog_Companies"][0]]
    flow[1].records["Catalog_Companies"][0].update(Description="Synthetic short name",
                                                 DescriptionFull="ООО Синтетика branch")
    assert send(flow).status_code == 200
    bot = flow[0].app.state.bot
    assert not bot.pending and len(bot.client_choices[123].choices.candidates) == 1
    assert press(flow, button(flow)).status_code == 200
    assert bot.pending[123].prepared.request.client_id == ref(1)


def test_delivery_retry_keeps_same_choice_token_and_does_not_reresolve(flow):
    flow[3]["fail_delivery"] = True
    assert send(flow).status_code == 503
    original = button(flow)
    before = len(flow[1].calls)
    assert send(flow).status_code == 200
    assert button(flow) == original
    assert len(flow[1].calls) == before
    assert press(flow, original).status_code == 200
    prepared = flow[0].app.state.bot.pending[123].prepared
    assert send(flow, number=3).status_code == 200
    assert 123 not in flow[0].app.state.bot.pending
    assert 123 in flow[0].app.state.bot.client_choices
    assert prepared.request.client_id == ref(1)


def supplier_conflict(flow):
    fixture = flow[1]
    fixture.records["Catalog_Companies"] = [fixture.records["Catalog_Companies"][0]]
    fixture.records["Catalog_Entities"].append({"Ref_Key": ref(20), "DeletionMark": False,
        "Description": "Historical synthetic supplier", "DescriptionFull": "Historical synthetic supplier"})
    fixture.records["Document_InventoryExpense"][0]["Entity_Key"] = ref(20)


def test_supplier_mismatch_requires_explicit_review_before_preview(flow, caplog):
    supplier_conflict(flow)
    assert send(flow).status_code == 200
    bot = flow[0].app.state.bot
    assert not bot.pending and 123 in bot.supplier_reviews
    assert "Historical synthetic supplier" in flow[2][-1]["text"]
    assert "Synthetic issuer" in flow[2][-1]["text"]
    assert "Итого:" not in flow[2][-1]["text"]
    accept = button(flow)
    before = len(flow[1].calls)
    assert press(flow, accept).status_code == 200
    assert len(flow[1].calls) > before  # A fresh GET validates the reviewed snapshot.
    preview = bot.pending[123].prepared.preview
    assert preview.historical_proposal.entity_id == ref(20)
    assert preview.historical_proposal.contract_entity_id == ref(3)
    assert len(preview.lines) == 2
    assert "Итого:" in flow[2][-1]["text"]
    assert "Поставщик нового документа пока не подтверждён" in flow[2][-1]["text"]
    assert ref(20) not in flow[2][-1]["text"]
    confirm = button(flow)
    assert press(flow, confirm, number=3).status_code == 200
    assert "документ не создавался" in flow[2][-1]["text"]
    assert {r.method for r in flow[1].calls} == {"GET"}
    assert "Historical synthetic supplier" not in caplog.text


@pytest.mark.parametrize("invalidate", ["new_message", "cancel_command", "cancel_button", "expired", "other_user", "token"])
def test_supplier_review_is_user_scoped_revocable_and_expiring(flow, invalidate):
    supplier_conflict(flow)
    send(flow)
    data = button(flow)
    if invalidate == "expired":
        bot = flow[0].app.state.bot
        pending = bot.supplier_reviews[123]
        bot.supplier_reviews[123] = type(pending)(**{**pending.model_dump(), "expires_at": 0.0})
    elif invalidate == "token":
        data = "supplier:" + "0" * 32 + ":accept"
    elif invalidate == "cancel_button":
        data = flow[2][-1]["reply_markup"]["inline_keyboard"][0][1]["callback_data"]
        press(flow, data)
    elif invalidate != "other_user":
        send(flow, "/cancel" if invalidate == "cancel_command" else TEXT, number=2)
    before = len(flow[1].calls)
    assert press(flow, data, number=3, user=456 if invalidate == "other_user" else 123).status_code == 200
    assert len(flow[1].calls) == before
    assert not flow[0].app.state.bot.pending


def test_supplier_change_during_review_blocks_old_basis(flow):
    supplier_conflict(flow)
    send(flow)
    data = button(flow)
    flow[1].records["Catalog_Entities"].append({"Ref_Key": ref(21), "DeletionMark": False,
        "Description": "Changed synthetic supplier", "DescriptionFull": "Changed synthetic supplier"})
    flow[1].records["Document_InventoryExpense"][0]["Entity_Key"] = ref(21)
    assert press(flow, data).status_code == 200
    bot = flow[0].app.state.bot
    assert not bot.pending and bot.contexts[123].supplier_review is None
    assert "Основание изменилось" in flow[2][-1]["text"]
    assert not bot.supplier_reviews


def test_financial_change_during_supplier_review_requires_new_review(flow):
    supplier_conflict(flow)
    send(flow)
    data = button(flow)
    source = flow[1].records["Document_InventoryExpense"][0]
    source["Inventory"][0] = flow[1].line(1, "1", "1500")
    source["DocumentAmount"] = "3675.00"
    assert press(flow, data).status_code == 200
    bot = flow[0].app.state.bot
    assert not bot.pending and bot.contexts[123].supplier_review is None
    assert button(flow) != data
    assert press(flow, button(flow), number=3).status_code == 200
    assert bot.pending[123].prepared.preview.total == Decimal("3675.00")


def test_supplier_review_delivery_retry_does_not_repeat_resolution(flow):
    supplier_conflict(flow)
    flow[3]["fail_delivery"] = True
    assert send(flow).status_code == 503
    data = button(flow)
    before = len(flow[1].calls)
    assert send(flow).status_code == 200
    assert len(flow[1].calls) == before and button(flow) == data
    assert press(flow, data).status_code == 200
    count = len(flow[1].calls)
    assert press(flow, data, number=3).status_code == 200
    assert len(flow[1].calls) == count


@pytest.mark.parametrize("duplicate", [False, True])
def test_uncertain_readonly_voice_requires_company_choice_before_history(flow, monkeypatch, caplog, duplicate):
    from types import SimpleNamespace
    from app.voice import AudioFile, Transcript, UncertainTranscript
    from app.ai import Interpretation
    from app.domain import InvoiceCommand
    from app.intent import InvoiceIntent
    client, fixture, sent, _ = flow
    if not duplicate:
        fixture.records["Catalog_Companies"] = fixture.records["Catalog_Companies"][:1]
    bot = client.app.state.bot
    text = "Сформируй счёт для ООО Синтетика за сентябрь 2026"
    transcript = Transcript.model_validate({"text": text, "logprobs": [{"token": "x", "logprob": -4.0}]})
    async def transcribe(audio):
        raise UncertainTranscript(transcript, "uncertain")
    async def download(voice):
        return AudioFile(content=b"OggS" + b"OpusHead" + b"x" * 32)
    async def interpret(value, draft):
        assert value == text
        return Interpretation(command=InvoiceCommand(client="ООО Синтетика", year=2026, month=9), needs_confirmation=True)
    bot.speech = SimpleNamespace(transcribe=transcribe)
    monkeypatch.setattr(bot.telegram, "download_voice", download)
    monkeypatch.setattr(bot.interpreter, "interpret", interpret)
    update = {"update_id": 1, "message": {"message_id": 1, "from": {"id": 123, "is_bot": False},
        "chat": {"id": 123, "type": "private"}, "voice": {"file_id": "v", "file_unique_id": "u",
            "duration": 5, "mime_type": "audio/ogg"}}}
    assert client.post('/telegram/webhook', json=update).status_code == 200
    assert 123 in bot.client_choices and 123 not in bot.pending
    assert text in sent[-1]['text'] and text not in caplog.text
    assert not any(r.url.path.endswith('Document_InventoryExpense') for r in fixture.calls)
    old_button = button(flow)
    assert press(flow, old_button).status_code == 200
    assert 123 in bot.pending
    assert {r.method for r in fixture.calls} == {'GET'}


def test_readonly_retry_retains_failed_command_without_reinterpreting(flow, monkeypatch, caplog):
    from app.domain import BackendFailure
    client, fixture, sent, _ = flow
    fixture.records['Catalog_Companies'] = fixture.records['Catalog_Companies'][:1]
    bot = client.app.state.bot
    original = bot.service.onec.resolve_client
    async def unavailable(*args, **kwargs):
        raise BackendFailure('firstbit_get_failed_timeout')
    monkeypatch.setattr(bot.service.onec, 'resolve_client', unavailable)
    assert send(flow).status_code == 200
    assert '/retry' in sent[-1]['text']
    assert 'firstbit_get_failed_timeout' in caplog.text
    monkeypatch.setattr(bot.service.onec, 'resolve_client', original)
    async def no_ai(*args, **kwargs):
        pytest.fail('Retry must not interpret or transcribe again')
    monkeypatch.setattr(bot.interpreter, 'interpret', no_ai)
    assert send(flow, '/retry', 2).status_code == 200
    assert 123 in bot.pending
    assert {r.method for r in fixture.calls} == {'GET'}
    assert send(flow, '/cancel', 3).status_code == 200
    assert send(flow, '/retry', 4).status_code == 200
    assert not bot.pending


def test_uncertain_readonly_edit_cannot_change_existing_preview(flow, monkeypatch):
    from types import SimpleNamespace
    from app.voice import AudioFile, Transcript, UncertainTranscript
    from app.ai import Interpretation
    from app.intent import InvoiceIntent
    client, fixture, sent, _ = flow
    fixture.records['Catalog_Companies'] = fixture.records['Catalog_Companies'][:1]
    assert send(flow).status_code == 200
    bot = client.app.state.bot
    before = bot.pending[123].prepared
    transcript = Transcript.model_validate({'text': 'Цена 9999', 'logprobs': [{'token': 'x', 'logprob': -4.0}]})
    async def transcribe(audio):
        raise UncertainTranscript(transcript, 'Уточните цену текстом')
    async def download(voice):
        return AudioFile(content=b'OggS' + b'OpusHead' + b'x' * 32)
    async def interpret(value, draft):
        return Interpretation(intent=InvoiceIntent(action='edit', client=None, invoice_date=None, service_period=None, services=(),
            lines_mode='keep', tax=None, previous=None, clarification=None), needs_confirmation=True)
    bot.speech = SimpleNamespace(transcribe=transcribe)
    monkeypatch.setattr(bot.telegram, 'download_voice', download)
    monkeypatch.setattr(bot.interpreter, 'interpret', interpret)
    gets = len(fixture.calls)
    update = {'update_id': 2, 'message': {'message_id': 2, 'from': {'id': 123, 'is_bot': False},
        'chat': {'id': 123, 'type': 'private'}, 'voice': {'file_id': 'v', 'file_unique_id': 'u', 'duration': 5}}}
    assert client.post('/telegram/webhook', json=update).status_code == 200
    assert 123 not in bot.pending and 123 not in bot.client_choices
    assert bot.contexts[123].prepared == before
    assert len(fixture.calls) == gets
    assert 'reply_markup' not in sent[-1]


def test_name_only_discovery_before_date_without_ai_then_fresh_choice(flow, monkeypatch):
    bot = flow[0].app.state.bot
    async def no_ai(*args, **kwargs):
        pytest.fail('Directory search does not require an invoice-language call')
    monkeypatch.setattr(bot.interpreter, 'interpret', no_ai)
    assert send(flow, 'Найди компанию ООО Синтетика').status_code == 200
    assert 123 in bot.client_choices and 123 not in bot.pending
    assert bot.client_choices[123].command is None
    assert not any(r.url.path.endswith('Document_InventoryExpense') for r in flow[1].calls)
    assert press(flow, button(flow), 2).status_code == 200
    assert 'Компания выбрана' in flow[2][-1]['text']
    assert bot.contexts[123].selected_client_id == ref(1)
    assert not bot.pending


def test_numeric_company_selection_and_name_refinement_keep_invoice_scope(flow, monkeypatch):
    send(flow)
    old_button = button(flow)
    bot = flow[0].app.state.bot
    original = bot.client_choices[123].command
    async def no_ai(*args, **kwargs):
        pytest.fail('Refinement/choice must not replay AI')
    monkeypatch.setattr(bot.interpreter, 'interpret', no_ai)
    assert send(flow, 'ООО Синтетик', 2).status_code == 200
    assert bot.client_choices[123].command.year == original.year
    assert bot.client_choices[123].command.month == original.month
    assert press(flow, old_button, 3).status_code == 200
    assert not bot.pending
    assert send(flow, '1', 4).status_code == 200
    assert bot.pending[123].prepared.preview.service_period.month == 9
    assert {r.method for r in flow[1].calls} == {'GET'}


def test_discovery_rechecks_selected_identity_and_cancel_clears_scope(flow):
    send(flow, 'ООО Синтетика')
    data = button(flow)
    flow[1].records['Catalog_Companies'][0]['Inactive'] = True
    assert press(flow, data, 2).status_code == 200
    assert 123 not in flow[0].app.state.bot.contexts
    assert not flow[0].app.state.bot.pending
    send(flow, 'ООО Синтетика', 3)
    assert send(flow, '/cancel', 4).status_code == 200
    assert not flow[0].app.state.bot.client_choices and not flow[0].app.state.bot.contexts


def test_expired_numeric_choice_never_reads_or_selects(flow, monkeypatch):
    from types import SimpleNamespace
    send(flow)
    before = len(flow[1].calls)
    monkeypatch.setattr('app.bot.time', SimpleNamespace(monotonic=lambda: float('inf')))
    assert send(flow, '1', 2).status_code == 200
    assert not flow[0].app.state.bot.pending and len(flow[1].calls) == before


def test_uncertain_bare_voice_discovers_company_then_period_retains_selection(flow, monkeypatch):
    from types import SimpleNamespace
    from app.voice import Transcript, UncertainTranscript, AudioFile
    from app.ai import Interpretation
    from app.intent import InvoiceIntent, PeriodInput
    bot = flow[0].app.state.bot
    async def transcribe(audio):
        raise UncertainTranscript(Transcript.model_validate({'text': 'ООО Синтетика',
            'logprobs': [{'token': 'x', 'logprob': -4.0}]}), 'uncertain')
    async def download(voice):
        return AudioFile(content=b'OggS' + b'OpusHead' + b'x' * 32)
    bot.speech = SimpleNamespace(transcribe=transcribe)
    monkeypatch.setattr(bot.telegram, 'download_voice', download)
    async def interpret(text, draft):
        assert text == 'за декабрь 2026' and draft.client == 'ООО Синтетика'
        return Interpretation(intent=InvoiceIntent(action='edit', client=None, invoice_date=None,
            service_period=PeriodInput(evidence=text, year=2026, month=12), services=(), lines_mode='keep',
            tax=None, previous=None, clarification=None), needs_confirmation=True)
    monkeypatch.setattr(bot.interpreter, 'interpret', interpret)
    assert flow[0].post('/telegram/webhook', json={'update_id': 1, 'message': {'message_id': 1,
        'from': {'id': 123, 'is_bot': False}, 'chat': {'id': 123, 'type': 'private'},
        'voice': {'file_id': 'v', 'file_unique_id': 'u', 'duration': 5}}}).status_code == 200
    assert 123 in bot.client_choices and not bot.pending
    assert send(flow, '1', 2).status_code == 200
    assert not bot.pending and bot.contexts[123].selected_client_id == ref(1)
    assert send(flow, 'за декабрь 2026', 3).status_code == 200
    assert bot.pending[123].prepared.request.client_id == ref(1)
    assert bot.pending[123].prepared.preview.service_period.month == 12
