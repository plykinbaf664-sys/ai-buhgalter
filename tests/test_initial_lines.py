"""Initial net amounts and multiple service histories use synthetic provider data."""
import asyncio
import copy
import json
from datetime import date
from decimal import Decimal
from uuid import UUID

import httpx
import pytest

from app.domain import (InvoiceCommand, PreviewLineOverride, PreviewTaxRequest, ServiceSelection,
    ServiceChoiceRequired, UserProblem, WorkflowFailure)
from app.firstbit import FirstBit, FirstBitSettings
from app.service import InvoiceService
from scripts.firstbit_fixture import FirstBitFixture, ref


@pytest.fixture
def data():
    data = FirstBitFixture()
    original = data.records['Document_InventoryExpense'][0]
    original['Inventory'] = [original['Inventory'][0]]
    original['DocumentAmount'] = '1050.00'
    data.records['Catalog_Items'].append({**data.records['Catalog_Items'][0], 'Ref_Key': ref(20),
        'Description': 'Tax return filing'})
    other = copy.deepcopy(original)
    other.update(Ref_Key=ref(21), Number='SYNTHETIC-002', Date='2026-08-10T00:00:00')
    other['Inventory'] = [data.line(1, '2', '500.00')]
    other['Inventory'][0].update(Item_Key=ref(20), Content='Synthetic tax filing')
    data.records['Document_InventoryExpense'].append(other)
    return data


def command(**changes):
    return InvoiceCommand(**{'client': 'ООО Синтетика', 'invoice_date': date(2026, 9, 1),
        'services': (ServiceSelection(query='бухгалтерское обслуживание'), ServiceSelection(query='Tax return filing')),
        'initial_overrides': (PreviewLineOverride(line_number=1, amount=Decimal('1800'),
            tax=PreviewTaxRequest(mode='with_tax')), PreviewLineOverride(line_number=2, amount=Decimal('1000'),
            tax=PreviewTaxRequest(mode='with_tax'))), **changes})


def run(data, task):
    async def scenario():
        backend = FirstBit(FirstBitSettings(base_url=data.env()['FIRSTBIT_BASE_URL'],
            username='integration_reader', password='synthetic-only', readonly_account=True,
            bookkeeping_item_id=UUID(ref(5))), transport=httpx.MockTransport(data.respond))
        try:
            return await task(InvoiceService(backend, timeout=20), backend)
        finally:
            await backend.aclose()
    return asyncio.run(scenario())


def test_initial_net_amounts_precede_separate_histories_and_refresh(data):
    async def task(service, backend):
        prepared = await service.prepare(command(), 'initial', 123)
        assert prepared.preview.subtotal == Decimal('2800')
        assert prepared.preview.tax_amount == Decimal('140')
        assert prepared.preview.total == Decimal('2940')
        assert [line.price for line in prepared.preview.lines] == [Decimal('1800'), Decimal('500')]
        assert [line.source_id for line in prepared.preview.lines] == [ref(8), ref(21)]
        assert [s.source_id for s in prepared.preview.historical_proposal.sources] == [ref(8), ref(21)]
        assert (await service.refresh(prepared, 'refresh', 123)) == prepared
        with pytest.raises(WorkflowFailure):
            await service.execute(prepared, 'execute-blocked', 123)
    run(data, task)
    assert {request.method for request in data.calls} == {'GET'}


def test_unspecified_second_amount_stays_in_its_own_history(data):
    async def task(service, backend):
        result = await service.prepare(command(initial_overrides=(PreviewLineOverride(line_number=1,
            amount=Decimal('1800')),)), 'initial', 123)
        assert result.preview.lines[1].price == Decimal('500')
        assert result.preview.lines[1].quantity == Decimal('2')
    run(data, task)


def test_approximate_service_requires_choice_and_chosen_id_is_rechecked(data):
    async def task(service, backend):
        with pytest.raises(ServiceChoiceRequired) as exc:
            await backend.resolve_service(ref(1), 'Tax return filng')
        assert exc.value.choices.candidates[0].service_id == ref(20)
        assert (await backend.resolve_service(ref(1), 'Tax return filng', selected_id=ref(20))).service_id == ref(20)
        with pytest.raises(UserProblem):
            await backend.resolve_service(ref(1), 'Tax return filng', selected_id=ref(5))
    run(data, task)


def test_nonprimary_source_drift_does_not_move_initial_amount(data):
    async def task(service, backend):
        prepared = await service.prepare(command(), 'initial', 123)
        source = data.records['Document_InventoryExpense'][1]
        source['Ref_Key'] = ref(22)
        with pytest.raises(UserProblem, match='Источник'):
            await service.refresh(prepared, 'refresh', 123)
    run(data, task)


@pytest.mark.parametrize('change', ['issuer', 'currency', 'missing_history'])
def test_unknown_or_incompatible_history_is_not_invented(data, change):
    other = data.records['Document_InventoryExpense'][1]
    if change == 'issuer': other['Entity_Key'] = ref(99)
    if change == 'currency': other['DocumentCurrency_Key'] = ref(99)
    if change == 'missing_history': data.records['Document_InventoryExpense'].pop()
    async def task(service, backend):
        with pytest.raises(UserProblem):
            await service.prepare(command(), 'initial', 123)
    run(data, task)


def test_net_amount_is_not_unit_price_and_cannot_silently_round(data):
    data.records['Document_InventoryExpense'][1]['Inventory'] = [data.line(1, '3', '500')]
    data.records['Document_InventoryExpense'][1]['Inventory'][0]['Item_Key'] = ref(20)
    data.records['Document_InventoryExpense'][1]['DocumentAmount'] = '1575'
    async def task(service, backend):
        with pytest.raises(UserProblem, match='копейки'):
            await service.prepare(command(), 'initial', 123)
    run(data, task)


TEXT = 'Сформируй счет для Synthetic на 1 сентября 2026 Bookkeeping на сумму 1800 с НДС Filing на сумму 1000 с НДС'


def initial_request():
    from app.language import InitialInvoiceRequest
    def span(first, last=None):
        return {'first_word': first, 'last_word': last or first}
    def line(service, amount, tax):
        return {'service_span': span(service), 'amount_span': span(amount), 'tax': {'kind': 'tax',
            'line_number': None, 'source_span': span(tax, tax + 1), 'mode': 'with_tax', 'rate_span': None, 'profile_span': None}}
    return InitialInvoiceRequest.model_validate_json(json.dumps({'action': 'create', 'client_change': span(4),
        'date_change': {'source_span': span(6, 8), 'day': 1, 'month': 9, 'year': 2026},
        'period_change': None, 'initial_lines': [line(9, 12, 13), line(15, 18, 19)], 'clarification': None}))


def test_initial_spans_decode_money_locally_and_reject_cross_line_numbers():
    from app.intent import InvoiceDraft, ground_intent, merge_intent
    from app.language import InitialInvoiceRequest
    request = initial_request()
    intent = ground_intent(request.language_intent().to_intent(TEXT), TEXT)
    draft = merge_intent(InvoiceDraft(), intent)
    assert [e.amount for e in draft.command().initial_overrides] == [Decimal('1800'), Decimal('1000')]
    changed = request.model_dump(mode='json')
    changed['initial_lines'][0]['amount_span'] = {'first_word': 18, 'last_word': 18}
    with pytest.raises(UserProblem, match='другой строке'):
        InitialInvoiceRequest.model_validate_json(json.dumps(changed)).language_intent().to_intent(TEXT)
    changed['initial_lines'][0]['amount_span'] = {'first_word': 6, 'last_word': 6}
    with pytest.raises(UserProblem):
        InitialInvoiceRequest.model_validate_json(json.dumps(changed)).language_intent().to_intent(TEXT)


def test_model_cannot_supply_numeric_money_or_ids():
    from app.language import InitialInvoiceRequest
    payload = initial_request().model_dump(mode='json')
    payload['initial_lines'][0]['amount'] = 999999
    with pytest.raises(ValueError):
        InitialInvoiceRequest.model_validate_json(json.dumps(payload))


def test_repeated_same_service_requests_stay_separate(data):
    async def task(service, backend):
        prepared = await service.prepare(command(services=(ServiceSelection(query='бухгалтерское обслуживание'),
            ServiceSelection(query='бухгалтерское обслуживание'))), 'initial', 123)
        assert len(prepared.preview.lines) == 2
        assert [r.subtotal for r in prepared.preview.lines] == [Decimal('1800'), Decimal('1000')]
        assert [r.source_line_number for r in prepared.preview.lines] == [1, 1]
    run(data, task)


def test_service_later_page_and_quoted_literal_are_safe(data):
    item = data.records['Catalog_Items'][0]
    data.records['Catalog_Items'] += [{**item, 'Ref_Key': ref(n), 'Description': 'Unrelated service '+str(n)}
        for n in range(100, 301)]
    data.records['Catalog_Items'].append({**item, 'Ref_Key': ref(400), 'Description': "Synthetic O'Neil review service"})
    async def task(service, backend):
        with pytest.raises(ServiceChoiceRequired) as choice:
            await backend.resolve_service(ref(1), "O'Neil review")
        assert choice.value.choices.candidates[0].service_id == ref(400)
        assert (await backend.resolve_service(ref(1), "Synthetic O'Neil review service")).service_id == ref(400)
    run(data, task)
    assert any(r.url.params.get('$skip') == '200' for r in data.calls)
    literals = [r.url.params['$filter'] for r in data.calls if 'Description eq' in r.url.params.get('$filter', '')]
    assert any("O''Neil" in value for value in literals)
    assert {r.method for r in data.calls} == {'GET'}


@pytest.fixture
def flow(data, monkeypatch):
    from fastapi.testclient import TestClient
    from app.ai import Interpretation
    from app.config import Settings
    from app.main import create_app
    from app.language import LanguageIntent
    data.records['Catalog_Companies'][0].update(Description='Synthetic', DescriptionFull='Synthetic')
    data.records['Catalog_Items'][0]['Description'] = 'Bookkeeping'
    for key, value in data.env().items(): monkeypatch.setenv(key, value)
    replies = []
    def telegram(request):
        if request.url.path.endswith('answerCallbackQuery'):
            return httpx.Response(200, json={'ok': True, 'result': True})
        assert request.url.path.endswith('sendMessage'), 'PDF attempted'
        replies.append(json.loads(request.content))
        return httpx.Response(200, json={'ok': True, 'result': {'message_id': 1, 'chat': {'id': replies[-1]['chat_id']}}})
    app = create_app(Settings(token='123:'+'x'*32, webhook_secret='s'*32, allowed_users=frozenset({123,456}),
        mode='firstbit_readonly'), telegram_transport=httpx.MockTransport(telegram), firstbit_transport=httpx.MockTransport(data.respond))
    async def interpret(text, context=None):
        if text == TEXT:
            intent = initial_request().language_intent().to_intent(text)
        else:
            assert text == 'Во второй строке сумма 1200'
            intent = LanguageIntent.model_validate_json(json.dumps({'action':'edit','client_change':None,
                'date_change':None,'period_change':None,'line_changes':[],'tax_change':None,
                'previous_hint_request':None,'clarification':None,'preview_changes':[{'kind':'amount','line_number':2,
                    'amount_span':{'first_word':5,'last_word':5}}]})).to_intent(text)
        return Interpretation(intent=intent, needs_confirmation=True)
    with TestClient(app) as client:
        monkeypatch.setattr(app.state.bot.interpreter, 'interpret', interpret)
        client.headers['X-Telegram-Bot-Api-Secret-Token']='s'*32
        yield client, data, replies


def send(flow, text=TEXT, update=1):
    return flow[0].post('/telegram/webhook', json={'update_id':update,'message':{'message_id':update,
        'from':{'id':123,'is_bot':False},'chat':{'id':123,'type':'private'},'text':text}})


def press(flow, data, update=2, user=123):
    return flow[0].post('/telegram/webhook',json={'update_id':update,'callback_query':{'id':str(update),
        'from':{'id':user,'is_bot':False},'message':{'message_id':1,'chat':{'id':user,'type':'private'}},'data':data}})


def button(flow):
    return flow[2][-1]['reply_markup']['inline_keyboard'][0][0]['callback_data']


def test_app_initial_service_choice_amount_revision_refresh_and_cancel(flow):
    assert send(flow).status_code == 200
    assert 123 in flow[0].app.state.bot.service_choices
    assert send(flow, '1', 2).status_code == 200
    bot = flow[0].app.state.bot
    assert bot.pending[123].prepared.preview.total == Decimal('2940')
    assert not bot.contexts[123].draft.initial_overrides
    assert send(flow, 'Во второй строке сумма 1200', 3).status_code == 200
    assert bot.pending[123].prepared.preview.lines[1].price == Decimal('600')
    assert bot.pending[123].prepared.preview.subtotal == Decimal('3000')
    assert press(flow, button(flow), 4).status_code == 200
    assert 'документ не создавался' in flow[2][-1]['text']
    assert send(flow, '/cancel', 5).status_code == 200
    assert not bot.pending and {r.method for r in flow[1].calls} == {'GET'}


def test_service_choice_cross_user_and_cancel_revoke_token(flow):
    send(flow)
    token = button(flow)
    before = len(flow[1].calls)
    assert press(flow, token, user=456).status_code == 200
    assert len(flow[1].calls) == before
    send(flow, '/cancel', 3)
    assert press(flow, token, 4).status_code == 200
    assert len(flow[1].calls) == before


def test_amount_quantity_choice_is_explicit_and_token_bound(flow):
    other = flow[1].records['Document_InventoryExpense'][1]
    other['Inventory'] = [flow[1].line(1, '3', '500')]
    other['Inventory'][0]['Item_Key'] = ref(20)
    other['DocumentAmount'] = '1575'
    send(flow)
    press(flow, button(flow))
    bot = flow[0].app.state.bot
    assert 123 in bot.initial_quantities and 123 not in bot.pending
    token = button(flow)
    before = len(flow[1].calls)
    press(flow, token, 3, user=456)
    assert len(flow[1].calls) == before
    press(flow, token, 4)
    assert bot.pending[123].prepared.preview.total == Decimal('2940')
    assert bot.pending[123].prepared.preview.lines[1].quantity == Decimal('1')


def test_initial_tax_can_be_clarified_before_preview_without_losing_amounts(flow, monkeypatch):
    from app.ai import Interpretation
    from app.intent import InvoiceIntent, TaxInput
    other = flow[1].records['Document_InventoryExpense'][1]
    line = other['Inventory'][0]
    line.update(VATRate_Key=ref(70), VATAmount='0', AmountTotal='1000')
    other['DocumentAmount'] = '1000'
    flow[1].records['Catalog_VATRates'].append({**flow[1].records['Catalog_VATRates'][0],
        'Ref_Key':ref(70), 'Description':'Synthetic exempt', 'Rate':'0', 'Exempt':True})
    send(flow)
    press(flow, button(flow))
    bot = flow[0].app.state.bot
    assert not bot.pending and bot.contexts[123].draft.initial_overrides
    assert 'ставку' in flow[2][-1]['text']
    async def interpret(text, context):
        return Interpretation(intent=InvoiceIntent(action='edit', client=None, invoice_date=None, service_period=None,
            services=(), lines_mode='keep', tax=TaxInput(evidence=text, mode='profile', query='НДС 5%'),
            previous=None, clarification=None), needs_confirmation=True)
    monkeypatch.setattr(bot.interpreter,'interpret',interpret)
    assert send(flow,'НДС 5%',3).status_code == 200
    assert bot.pending[123].prepared.preview.total == Decimal('2940')


def test_only_common_historical_issuer_is_used_for_multi_service_proposal(data):
    data.records['Document_InventoryExpense'][1]['Entity_Key'] = ref(99)
    older = copy.deepcopy(data.records['Document_InventoryExpense'][1])
    older.update(Ref_Key=ref(24), Date='2026-07-10T00:00:00', Entity_Key=ref(3), Number='SYN-OLDER')
    data.records['Document_InventoryExpense'].append(older)
    async def task(service, backend):
        result = await service.prepare(command(),'initial',123)
        assert result.preview.lines[1].source_id == ref(24)
    run(data,task)


def test_spoken_amount_words_and_model_duplicate_unit_span_are_grounded():
    from app.language import InitialInvoiceRequest
    text = TEXT.replace('1800','тысяча восемьсот')
    payload = initial_request().model_dump(mode='json')
    first, second = payload['initial_lines']
    first.update(price_span={'first_word':11,'last_word':13},amount_span={'first_word':12,'last_word':13})
    first['tax']['source_span']={'first_word':14,'last_word':15}
    second.update(service_span={'first_word':16,'last_word':16},amount_span={'first_word':19,'last_word':19})
    second['tax']['source_span']={'first_word':20,'last_word':21}
    result=InitialInvoiceRequest.model_validate_json(json.dumps(payload)).language_intent().to_intent(text)
    assert result.initial_overrides[0].amount == Decimal('1800')
    assert result.initial_overrides[0].price is None


def test_initial_currency_and_fabricated_service_filters_fail_closed(data):
    async def task(service,backend):
        with pytest.raises(UserProblem,match='Валюта'):
            await service.prepare(command(initial_overrides=(PreviewLineOverride(line_number=1,
                amount=Decimal('1800'),currency='USD'),)),'initial',123)
        query="unknown' or true or Description eq 'other"
        with pytest.raises(UserProblem):
            await backend.resolve_service(ref(1),query)
    run(data,task)
    literals=[r.url.params.get('$filter','') for r in data.calls]
    assert any("unknown'' or true or Description eq ''other" in item for item in literals)
    assert all(r.method == 'GET' for r in data.calls)


def test_service_name_refinement_preserves_initial_money_and_revokes_old_choice(flow):
    send(flow)
    old = button(flow)
    assert send(flow,'Tax return filing',2).status_code == 200
    bot=flow[0].app.state.bot
    assert bot.pending[123].prepared.preview.total == Decimal('2940')
    before=len(flow[1].calls)
    assert press(flow,old,3).status_code == 200
    assert len(flow[1].calls)==before


def test_uncertain_initial_voice_money_is_not_applied_silently(flow,monkeypatch,caplog):
    from types import SimpleNamespace
    from app.voice import AudioFile,Transcript,UncertainTranscript
    bot=flow[0].app.state.bot
    async def download(voice):
        return AudioFile(content=b'OggS'+b'OpusHead'+b'x'*32)
    async def transcribe(audio):
        raise UncertainTranscript(Transcript.model_validate({'text':TEXT,'logprobs':[{'token':'x','logprob':-4.0}]}),TEXT)
    monkeypatch.setattr(bot.telegram,'download_voice',download)
    bot.speech=SimpleNamespace(transcribe=transcribe)
    assert flow[0].post('/telegram/webhook',json={'update_id':1,'message':{'message_id':1,
        'from':{'id':123,'is_bot':False},'chat':{'id':123,'type':'private'},
        'voice':{'file_id':'v','file_unique_id':'u','duration':5}}}).status_code==200
    assert not flow[1].calls and not bot.pending and not bot.service_choices
    assert TEXT not in caplog.text and TEXT in flow[2][-1]['text']


def test_no_service_list_uses_last_invoice_even_without_bookkeeping(data):
    data.records['Document_InventoryExpense'] = data.records['Document_InventoryExpense'][1:]
    async def task(service,backend):
        result = await service.prepare(command(services=(),initial_overrides=()),'default-template',123)
        assert len(result.preview.lines)==1 and result.preview.lines[0].service_id==ref(20)
        assert result.preview.subtotal==Decimal('1000')
        assert (await service.refresh(result,'refresh',123))==result
    run(data,task)


def test_model_omission_does_not_drop_literal_amount_or_vat():
    from app.language import InitialInvoiceRequest
    payload=initial_request().model_dump(mode='json')
    payload['initial_lines'][0]['amount_span']=None
    payload['initial_lines'][0]['tax']=None
    result=InitialInvoiceRequest.model_validate_json(json.dumps(payload)).language_intent().to_intent(TEXT)
    assert result.initial_overrides[0].amount==Decimal('1800')
    assert result.initial_overrides[0].tax.mode=='with_tax'


def test_incomplete_tax_span_is_recovered_only_from_its_own_explicit_clause():
    from app.language import InitialInvoiceRequest
    payload=initial_request().model_dump(mode='json')
    payload['initial_lines'][0]['tax']['source_span']={'first_word':13,'last_word':13}
    result=InitialInvoiceRequest.model_validate_json(json.dumps(payload)).language_intent().to_intent(TEXT.replace('НДС','NDS'))
    assert result.initial_overrides[0].tax.mode=='with_tax'


def test_money_label_cannot_be_borrowed_from_the_previous_service_clause():
    from app.language import InitialInvoiceRequest
    payload=initial_request().model_dump(mode='json')
    payload['initial_lines'][1]['amount_span']={'first_word':16,'last_word':16}
    payload['initial_lines'][1]['tax']['source_span']={'first_word':17,'last_word':18}
    with pytest.raises(UserProblem):
        InitialInvoiceRequest.model_validate_json(json.dumps(payload)).language_intent().to_intent(TEXT.replace('Filing на сумму','Filing'))


def test_global_initial_vat_is_not_lost_if_model_omits_per_line_tax():
    from app.language import InitialInvoiceRequest
    text='Сформируй счет для Synthetic на 1 сентября 2026 с НДС5% Bookkeeping на сумму 1800 Filing на сумму 1000'
    payload=initial_request().model_dump(mode='json')
    first,second=payload['initial_lines']
    first.update(service_span={'first_word':11,'last_word':11},amount_span={'first_word':14,'last_word':14},tax=None)
    second.update(service_span={'first_word':15,'last_word':15},amount_span={'first_word':18,'last_word':18},tax=None)
    result=InitialInvoiceRequest.model_validate_json(json.dumps(payload)).language_intent().to_intent(text)
    assert all(edit.tax.mode=='rate' and edit.tax.rate==Decimal('5') for edit in result.initial_overrides)


@pytest.mark.parametrize('title',['Contract drafting','System support','Удаление файлов','Разработка инструкций'])
def test_service_labels_are_not_treated_as_contract_or_system_actions(title):
    from types import SimpleNamespace
    from pydantic import SecretStr
    from app.ai import CommandInterpreter
    from app.language import InitialInvoiceRequest
    payload=initial_request().model_dump(mode='json')
    text=TEXT.replace('Bookkeeping',title)
    shift=len(title.split())-1
    first,second=payload['initial_lines']
    first['service_span']['last_word']+=shift
    for field in ('amount_span',):
        first[field]={k:v+shift for k,v in first[field].items()}
    first['tax']['source_span']={k:v+shift for k,v in first['tax']['source_span'].items()}
    for field in ('service_span','amount_span'):
        second[field]={k:v+shift for k,v in second[field].items()}
    second['tax']['source_span']={k:v+shift for k,v in second['tax']['source_span'].items()}
    parsed=InitialInvoiceRequest.model_validate_json(json.dumps(payload))
    async def parse(**kwargs):
        assert kwargs['text_format'] is InitialInvoiceRequest
        return SimpleNamespace(output_parsed=parsed)
    result=asyncio.run(CommandInterpreter(api_key=SecretStr('synthetic'),model='gpt-4o-mini',
        sdk_client=SimpleNamespace(responses=SimpleNamespace(parse=parse))).interpret(text))
    assert result.intent.services[0].query==title
    assert result.intent.initial_overrides[0].amount==Decimal('1800')


def test_service_after_period_is_not_dropped_by_legacy_extraction():
    from types import SimpleNamespace
    from pydantic import SecretStr
    from app.ai import CommandInterpreter
    from app.language import LanguageIntent
    text='Выстави, пожалуйста, счёт Synthetic за сентябрь 2026 Visa cancellation'
    parsed=LanguageIntent.model_validate_json(json.dumps({'action':'create','client_change':{'first_word':4,'last_word':4},
        'date_change':None,'period_change':{'source_span':{'first_word':6,'last_word':7},'month':9,'year':2026},
        'line_changes':[{'kind':'replace','new_service_name':{'first_word':8,'last_word':9},'line_number':None,'quantity':None}],
        'tax_change':None,'previous_hint_request':None,'clarification':None}))
    async def parse(**kwargs):
        assert kwargs['text_format'] is LanguageIntent
        return SimpleNamespace(output_parsed=parsed)
    result=asyncio.run(CommandInterpreter(api_key=SecretStr('synthetic'),model='gpt-4o-mini',
        sdk_client=SimpleNamespace(responses=SimpleNamespace(parse=parse))).interpret(text))
    assert result.intent.services[0].query=='Visa cancellation'


def test_semicolon_can_separate_initial_service_rows():
    from types import SimpleNamespace
    from pydantic import SecretStr
    from app.ai import CommandInterpreter
    async def parse(**kwargs):
        return SimpleNamespace(output_parsed=initial_request())
    text=TEXT.replace('НДС Filing','НДС; Filing')
    result=asyncio.run(CommandInterpreter(api_key=SecretStr('synthetic'),model='gpt-4o-mini',
        sdk_client=SimpleNamespace(responses=SimpleNamespace(parse=parse))).interpret(text))
    assert [edit.amount for edit in result.intent.initial_overrides]==[Decimal('1800'),Decimal('1000')]


def test_leading_decimal_point_is_not_stripped_into_a_different_price():
    from app.language import SourceSpan,financial_span
    with pytest.raises(UserProblem,match='нулём'):
        financial_span('Цена .5',SourceSpan(first_word=2,last_word=2),'price')
