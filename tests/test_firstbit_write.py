"""Independent synthetic FirstBit mutation server, never production fixtures."""
import asyncio
import copy
from datetime import date
import json
from pathlib import Path
from uuid import UUID
from xml.etree.ElementTree import SubElement, tostring

import httpx
import pytest

from app.domain import InvoiceCommand, InvoiceConflict, WorkflowFailure, WritesDisabled
from app.firstbit import FirstBitSettings
from app.firstbit_write import FirstBitWrite, execution_schema
from app.operations import MutationUncertain, OperationJournal
from app.service import InvoiceService
from scripts.firstbit_fixture import FirstBitFixture, ref
from test_firstbit_write_schema import metadata


def write_metadata():
    root = metadata()
    doc = root.find("EntityType[@Name='Document_InventoryExpense']")
    SubElement(doc, 'Property', Name='DeliveryTerms_Key', Type='Edm.Guid')
    SubElement(doc, 'Property', Name='TermsAndConditions', Type='Edm.String')
    for name in ('PaymentTermsStages', 'InventorySets', 'DiscountsMarkupsInventory'):
        SubElement(doc, 'Property', Name=name, Type=f'Collection(StandardODATA.{name}Row)')
    stage = SubElement(root, 'ComplexType', Name='PaymentTermsStagesRow')
    specs = {'Edm.Int64': 'LineNumber Days', 'Edm.Decimal': 'Amount Percent',
             'Edm.DateTime': 'PayDate', 'Edm.String': 'StageType',
             'Edm.Boolean': 'BlockShipping BlockSupplying'}
    for kind, fields in specs.items():
        for name in fields.split():
            SubElement(stage, 'Property', Name=name, Type=kind)
    row = root.find("ComplexType[@Name='HistoryRow']")
    for name in ('BaseUnit_Key','BusinessActivity_Key','ExpenseItem_Key','IncomeItem_Key','TradeDiscountsGLAccount_GL_Key'):
        SubElement(row,'Property',Name=name,Type='Edm.Guid')
    SubElement(row,'Property',Name='ConnectionKey',Type='Edm.Int64')
    for name in ('BaseUnit_Key','Department_Key','PriceKind_Key'):
        SubElement(doc,'Property',Name=name,Type='Edm.Guid')
    for name in ('BaseUnitPosition','CustomerOrderPosition','IncomingDocumentInfoPosition','PositionCell','ProjectPosition','ProjectTaskPosition','Emirate','OffsetAdvancesDebtsAutomatically','GoodsOrder','DocumentBasis'):
        SubElement(doc,'Property',Name=name,Type='Edm.String')
    SubElement(doc,'Property',Name='TaxInvoiceIsRequired',Type='Edm.Boolean')
    SubElement(doc,'Property',Name='Repetition',Type='Edm.Int64')
    container = root.find('EntityContainer')
    for name in ('Catalog_BankAccounts', 'Catalog_SalesPaymentTerms', 'Catalog_SalesPaymentTermsVersions',
                 'ChartOfAccounts_GeneralChartOfAccounts','Catalog_BaseUnits','Catalog_PriceKinds','Catalog_IncomeItems','Catalog_BusinessActivities','Catalog_ExpenseItems'):
        entity = SubElement(root, 'EntityType', Name=name)
        groups = {'Edm.Guid': 'Ref_Key', 'Edm.String': 'DataVersion Description', 'Edm.Boolean': 'DeletionMark'}
        if name == 'Catalog_BankAccounts':
            groups['Edm.Guid'] += ' CashCurrency_Key'
            groups['Edm.String'] += ' Owner Owner_Type IBAN AccountNo'
            groups['Edm.DateTime'] = 'OpeningDate ClosingDate'
        if name == 'Catalog_ExpenseItems': groups['Edm.Boolean'] += ' IsFolder'
        for kind, fields in groups.items():
            for field in fields.split():
                SubElement(entity, 'Property', Name=field, Type=kind)
        SubElement(container, 'EntitySet', Name=name, EntityType='StandardODATA.' + name)
    return tostring(root)


class WriteFixture(FirstBitFixture):
    def __init__(self):
        super().__init__()
        self.metadata = write_metadata()
        self.created, self.posts = [], 0
        self.lookup_extra, self.created_ref = [], ref(90)
        self.lose_response = None
        source = self.records['Document_InventoryExpense'][0]
        source.update(DataVersion='source-version', Comment='', AccountingCurrency_Key=ref(4),
            NationalCurrency_Key=ref(4), BankAccount_Key=ref(21), PaymentTerms_Key=ref(22),
            PaymentTermsVersion_Key=ref(23), AccountsReceivableGLAccount_GL_Key=ref(24),
            AdvancesReceivedGLAccount_GL_Key=ref(25), DeliveryTerms_Key=ref(0), TermsAndConditions='',
            TransactionType='SaleToCustomer', TaxationVAT='TaxableByVAT', ExchangeRate=1,
            ExchangeRateAccCur=1, FactorAccCur='1', PriceDate='2026-08-20T16:10:00',
            InventorySets=[], DiscountsMarkupsInventory=[],
            PaymentTermsStages=[{'LineNumber': '1', 'Amount': '3150.00', 'Percent': '100', 'Days': '0',
                'PayDate': '2026-08-20T00:00:00', 'StageType': 'PaymentOnDelivery',
                'BlockShipping': False, 'BlockSupplying': False}])
        source.update(BaseUnit_Key=ref(0),Department_Key=ref(0),PriceKind_Key=ref(0),TaxInvoiceIsRequired=True,
            BaseUnitPosition='InHeader',CustomerOrderPosition='InHeader',IncomingDocumentInfoPosition='InHeader',
            PositionCell='InHeader',ProjectPosition='InHeader',ProjectTaskPosition='InTabularPart',Emirate='',
            OffsetAdvancesDebtsAutomatically='No',Repetition='1',GoodsOrder='',DocumentBasis='')
        for row in source['Inventory']:
            row.update(GLAccount_GL_Key=ref(26), SalesRevenueGLAccount_GL_Key=ref(27), OutputVATGLAccount_GL_Key=ref(0))
            row.update(BaseUnit_Key=ref(0),BusinessActivity_Key=ref(0),ExpenseItem_Key=ref(0),
                IncomeItem_Key=ref(0),TradeDiscountsGLAccount_GL_Key=ref(0),ConnectionKey=str(row['LineNumber']))
        for name in ('Catalog_BaseUnits','Catalog_PriceKinds','Catalog_IncomeItems','Catalog_BusinessActivities','Catalog_ExpenseItems'):
            self.records[name] = []

        for name, number in [('Catalog_BankAccounts', 21), ('Catalog_SalesPaymentTerms', 22),
                             ('Catalog_SalesPaymentTermsVersions', 23)]:
            self.records[name] = [{'Ref_Key': ref(number), 'DeletionMark': False,
                                   'DataVersion': 'reference-version', 'Description': 'Synthetic ' + name}]
        self.records['Catalog_BankAccounts'][0].update(Owner=ref(3), Owner_Type='StandardODATA.Catalog_Entities',
            CashCurrency_Key=ref(4), OpeningDate='2000-01-01T00:00:00', ClosingDate='0001-01-01T00:00:00',
            IBAN='SYNTHETIC-ONLY', AccountNo='SYNTHETIC-ONLY')
        self.records['ChartOfAccounts_GeneralChartOfAccounts'] = [
            {'Ref_Key': ref(number), 'DeletionMark': False, 'DataVersion': 'reference-version',
             'Description': 'Synthetic GL ' + str(number)} for number in (24, 25, 26, 27)]

    def respond(self, request):
        entity = request.url.path.rsplit('/', 1)[-1]
        if request.method == 'POST':
            self.calls.append(request)
            assert entity == 'Document_InventoryExpense', 'Posting or arbitrary mutation forbidden'
            self.posts += 1
            body = json.loads(request.content)
            assert body['Posted'] is False
            assert not {'Ref_Key', 'DataVersion', 'Number'} & body.keys()
            if self.lose_response == 'before_commit':
                raise httpx.ReadTimeout('synthetic timeout', request=request)
            self.created.append({'GoodsOrder': ref(0), 'DocumentBasis': ref(0), **body, 'Ref_Key': self.created_ref, 'DataVersion': 'created-version', 'Number': 'SYN-DRAFT-001'})
            if self.lose_response == 'after_commit':
                raise httpx.ReadTimeout('synthetic timeout', request=request)
            return httpx.Response(201, json=self.created[-1])
        if entity == 'Document_InventoryExpense' and '$skip' in request.url.params:
            self.calls.append(request)
            start = request.url.params['$filter'].split("datetime'")[1].split("'")[0][:10]
            rows = [row for row in [*self.records['Document_InventoryExpense'], *self.created, *self.lookup_extra]
                    if row['Date'][:10] == start]
            rows.sort(key=lambda row: row['Ref_Key'])
            skip, top = int(request.url.params['$skip']), int(request.url.params['$top'])
            keys = request.url.params['$select'].split(',')
            return httpx.Response(200, json={'value': [{key: row[key] for key in keys} for row in rows[skip:skip+top]]})
        if entity == 'Document_InventoryExpense' and request.url.params.get('$filter', '').startswith("Ref_Key eq guid'"):
            key = request.url.params['$filter'].split("'")[1]
            created = [row for row in self.created if row['Ref_Key'] == key]
            if created:
                self.calls.append(request)
                return httpx.Response(200, json={'value': created})
        return super().respond(request)


def provider(fixture, path):
    return FirstBitWrite(FirstBitSettings(base_url=fixture.env()['FIRSTBIT_BASE_URL'], username='synthetic_writer',
        password='SYNTHETIC-ONLY', readonly_account=False, write_account=True, bookkeeping_item_id=UUID(ref(5))),
        journal=OperationJournal(path, namespace='synthetic-firstbit-write', create=True),
        schema_sha256=execution_schema(fixture.metadata).sha256, transport=httpx.MockTransport(fixture.respond))


async def prepare(backend):
    return await InvoiceService(backend, timeout=30, journal=backend.journal, allow_real_writes=True).prepare(
        InvoiceCommand(client='ООО Синтетика', invoice_date=date(2026, 9, 1)), 'synthetic-prepare', 123)


def test_confirmed_create_readback_repeat_and_restart_keep_one_real_adapter_draft(tmp_path):
    fixture = WriteFixture()
    async def scenario():
        backend = provider(fixture, tmp_path / 'state/operations.sqlite')
        try:
            prepared = await prepare(backend)
            assert prepared.preview.execution_review is not None and prepared.preview.write_blocker is None
            service = InvoiceService(backend, journal=backend.journal, allow_real_writes=True)
            result = await service.execute(prepared, 'confirm', 123)
            assert not result.invoice.posted and result.pdf is None
            assert len(fixture.created[0]['Inventory']) == 2  # repeated service rows are not merged
            assert fixture.created[0]['PriceDate'] == '2026-08-20T16:10:00'
            assert fixture.created[0]['PaymentTermsStages'][0]['PayDate'] == '2026-09-01T00:00:00'
        finally:
            await backend.aclose()
        backend = provider(fixture, tmp_path / 'state/operations.sqlite')
        try:
            result2 = await InvoiceService(backend, journal=backend.journal, allow_real_writes=True).execute(prepared, 'repeat', 123)
            assert result == result2 and fixture.posts == 1
        finally:
            await backend.aclose()
    asyncio.run(scenario())


@pytest.mark.parametrize('lost', ['before_commit', 'after_commit'])
def test_lost_create_response_reconciles_and_never_blindly_replays(lost, tmp_path):
    fixture = WriteFixture()
    fixture.lose_response = lost
    async def scenario():
        backend = provider(fixture, tmp_path / 'state/operations.sqlite')
        try:
            prepared = await prepare(backend)
            service = InvoiceService(backend, journal=backend.journal, allow_real_writes=True)
            with pytest.raises(WorkflowFailure) as error:
                await service.execute(prepared, 'confirm', 123)
            assert error.value.state == ('draft' if lost == 'after_commit' else 'unknown')
        finally:
            await backend.aclose()
        backend = provider(fixture, tmp_path / 'state/operations.sqlite')
        try:
            service = InvoiceService(backend, journal=backend.journal, allow_real_writes=True)
            if lost == 'after_commit':
                assert not (await service.execute(prepared, 'restart-retry', 123)).invoice.posted
            else:
                with pytest.raises(WorkflowFailure):
                    await service.execute(prepared, 'restart-retry', 123)
            assert fixture.posts == 1
        finally:
            await backend.aclose()
    asyncio.run(scenario())


@pytest.mark.parametrize('change', ['foreign_bank', 'closed_bank', 'fx', 'payment_stages', 'tax'])
def test_unknown_or_incompatible_accounting_never_admits_mutation(change, tmp_path):
    fixture = WriteFixture()
    source = fixture.records['Document_InventoryExpense'][0]
    if change == 'foreign_bank':
        fixture.records['Catalog_BankAccounts'][0]['Owner'] = ref(88)
    elif change == 'closed_bank':
        fixture.records['Catalog_BankAccounts'][0]['ClosingDate'] = '2026-08-31T00:00:00'
    elif change == 'fx':
        source['ExchangeRate'] = 2
    elif change == 'payment_stages':
        source['PaymentTermsStages'][0]['Days'] = '30'
    elif change == 'supplier':
        fixture.records['Catalog_CompanyContracts'][0]['Entity_Key'] = ref(88)
        fixture.records['Catalog_Entities'].append({'Ref_Key': ref(88), 'DeletionMark': False,
            'Description': 'Synthetic second issuer', 'DescriptionFull': 'Synthetic second issuer'})
    else:
        source['TaxationVAT'] = 'UnsupportedTaxation'
    async def scenario():
        backend = provider(fixture, tmp_path / 'state/operations.sqlite')
        try:
            prepared = await prepare(backend)
            assert prepared.preview.execution_review is None and prepared.preview.write_blocker
            with pytest.raises(WorkflowFailure):
                await InvoiceService(backend, journal=backend.journal, allow_real_writes=True).execute(prepared, 'confirm', 123)
            assert fixture.posts == 0
        finally:
            await backend.aclose()
    asyncio.run(scenario())


def test_source_or_schema_drift_after_preview_blocks_create(tmp_path):
    fixture = WriteFixture()
    async def scenario():
        backend = provider(fixture, tmp_path / 'state/operations.sqlite')
        try:
            prepared = await prepare(backend)
            fixture.records['Catalog_BankAccounts'][0]['DataVersion'] = 'changed-after-preview'
            with pytest.raises(WorkflowFailure):
                await InvoiceService(backend, journal=backend.journal, allow_real_writes=True).execute(prepared, 'confirm', 123)
            assert fixture.posts == 0
        finally:
            await backend.aclose()
    asyncio.run(scenario())


def test_direct_provider_call_requires_prior_confirmation_intent_and_posting_is_closed(tmp_path):
    fixture = WriteFixture()
    async def scenario():
        backend = provider(fixture, tmp_path / 'state/operations.sqlite')
        try:
            prepared = await prepare(backend)
            with pytest.raises(WritesDisabled):
                await backend.ensure_draft(prepared.basis, prepared.operation_id)
            backend.journal.reserve(prepared, 123)
            with pytest.raises(MutationUncertain):
                await backend.ensure_draft(prepared.basis, prepared.operation_id)
            with pytest.raises(WritesDisabled):
                await backend.ensure_posted(None, None, None)
            assert fixture.posts == 0
        finally:
            await backend.aclose()
    asyncio.run(scenario())


def test_readback_financial_mismatch_does_not_create_or_post_again(tmp_path):
    fixture = WriteFixture()
    async def scenario():
        backend = provider(fixture, tmp_path / 'state/operations.sqlite')
        try:
            prepared = await prepare(backend)
            service = InvoiceService(backend, journal=backend.journal, allow_real_writes=True)
            await service.execute(prepared, 'confirm', 123)
            fixture.created[0]['Inventory'][0]['Content'] = 'Changed outside confirmation'
            with pytest.raises(WorkflowFailure):
                await service.execute(prepared, 'repeat', 123)
            assert fixture.posts == 1
        finally:
            await backend.aclose()
    asyncio.run(scenario())


def test_live_schema_drift_after_preview_prevents_any_transport_write(tmp_path):
    from xml.etree.ElementTree import fromstring
    fixture = WriteFixture()
    async def scenario():
        backend = provider(fixture, tmp_path / 'state/operations.sqlite')
        try:
            prepared = await prepare(backend)
            changed = fromstring(fixture.metadata)
            changed.find("EntityType[@Name='Catalog_BankAccounts']/Property[@Name='Owner']").set('MaxLength', '10')
            fixture.metadata = tostring(changed)
            with pytest.raises(WorkflowFailure):
                await InvoiceService(backend, journal=backend.journal, allow_real_writes=True).execute(prepared, 'confirm', 123)
            assert fixture.posts == 0
        finally:
            await backend.aclose()
    asyncio.run(scenario())


def test_user_price_revision_is_rebound_to_a_new_accounting_review(tmp_path):
    from decimal import Decimal
    from app.domain import PreviewLineOverride
    fixture = WriteFixture()
    async def scenario():
        backend = provider(fixture, tmp_path / 'state/operations.sqlite')
        try:
            original = await prepare(backend)
            service = InvoiceService(backend, journal=backend.journal, allow_real_writes=True)
            old = InvoiceCommand(client='ООО Синтетика', invoice_date=date(2026, 9, 1))
            literal = "Synthetic service'); $filter=1 eq 1"
            command = InvoiceCommand(client=old.client, invoice_date=old.invoice_date,
                preview_overrides=(PreviewLineOverride(line_number=1, price=Decimal('1800'), description=literal),))
            edited = await service.prepare(command, 'edit', 123, existing=original, old_command=old)
            assert edited.preview.execution_review is not None
            assert edited.operation_id == original.operation_id
            assert edited.preview.execution_review.payload_sha256 != original.preview.execution_review.payload_sha256
            await service.execute(edited, 'confirm-edited', 123)
            assert fixture.created[0]['Inventory'][0]['Price'] == 1800
            assert fixture.created[0]['Inventory'][0]['Content'] == literal
            assert not any(literal in str(request.url) for request in fixture.calls)
            assert fixture.created[0]['PaymentTermsStages'][0]['Amount'] == float(edited.preview.total)
        finally:
            await backend.aclose()
    asyncio.run(scenario())


def test_application_confirm_restart_retry_keeps_one_draft_and_tells_the_truth(tmp_path):
    from fastapi.testclient import TestClient
    from app.config import Settings
    from app.main import create_app
    fixture = WriteFixture()
    path = tmp_path / 'state/operations.sqlite'
    backend = provider(fixture, path)
    settings = Settings(token='123:' + 'x' * 32, webhook_secret='y' * 32, allowed_users=frozenset({123}),
        mode='firstbit_write', onec_write_enabled=True, operation_db=path,
        firstbit_write_schema_sha256=backend.schema_sha256)
    messages = []
    def telegram(request):
        if request.url.path.endswith('answerCallbackQuery'):
            return httpx.Response(200, json={'ok': True, 'result': True})
        assert request.url.path.endswith('sendMessage'), 'No mock/native PDF path is admitted'
        body = json.loads(request.content)
        messages.append(body)
        return httpx.Response(200, json={'ok': True, 'result': {'message_id': len(messages),
            'chat': {'id': 123, 'type': 'private'}, 'text': body['text']}})
    def text_update(number, text):
        return {'update_id': number, 'message': {'message_id': number, 'chat': {'id': 123, 'type': 'private'},
            'from': {'id': 123, 'is_bot': False}, 'text': text}}
    headers = {'X-Telegram-Bot-Api-Secret-Token': 'y' * 32}
    app = create_app(settings, backend=backend, telegram_transport=httpx.MockTransport(telegram))
    with TestClient(app) as client:
        assert client.post('/telegram/webhook', headers=headers,
            json=text_update(1, 'Сформируй счет для ООО Синтетика за сентябрь 2026 года')).status_code == 200
        assert fixture.posts == 0
        prompt = next(body for body in reversed(messages) if body.get('reply_markup'))
        button = prompt['reply_markup']['inline_keyboard'][0][0]
        assert 'черновик' in button['text']
        callback = {'update_id': 2, 'callback_query': {'id': 'synthetic-confirm',
            'from': {'id': 123, 'is_bot': False}, 'data': button['callback_data'],
            'message': {'message_id': 1, 'chat': {'id': 123, 'type': 'private'}}}}
        assert client.post('/telegram/webhook', headers=headers, json=callback).status_code == 200
        assert fixture.posts == 1
        assert any('Черновик счёта №SYN-DRAFT-001' in body['text'] and 'Проведение заблокировано' in body['text'] for body in messages)
        assert client.post('/telegram/webhook', headers=headers, json=callback).status_code == 200
        assert fixture.posts == 1
    asyncio.run(backend.aclose())
    backend = provider(fixture, path)
    app = create_app(settings, backend=backend, telegram_transport=httpx.MockTransport(telegram))
    with TestClient(app) as client:
        assert client.post('/telegram/webhook', headers=headers, json=text_update(3, '/retry')).status_code == 200
        assert fixture.posts == 1
    asyncio.run(backend.aclose())


def test_operation_marker_is_found_after_first_page_without_text_filter(tmp_path):
    fixture = WriteFixture()
    fixture.created_ref = ref(9000)
    fixture.lookup_extra = [{'Ref_Key': ref(100 + n), 'DeletionMark': False, 'Company_Key': ref(1),
        'Contract_Key': ref(2), 'Entity_Key': ref(3), 'Date': '2026-09-01T00:00:00',
        'Comment': 'Unrelated synthetic invoice'} for n in range(201)]
    async def scenario():
        backend = provider(fixture, tmp_path / 'state/operations.sqlite')
        try:
            prepared = await prepare(backend)
            result = await InvoiceService(backend, journal=backend.journal, allow_real_writes=True).execute(prepared, 'confirm', 123)
            assert result.invoice.document_id == ref(9000) and fixture.posts == 1
            assert any(request.url.params.get('$skip') == '200' for request in fixture.calls)
            assert not any('Comment eq' in request.url.params.get('$filter', '') for request in fixture.calls)
        finally:
            await backend.aclose()
    asyncio.run(scenario())


def test_duplicate_markers_and_lookup_limit_fail_closed(tmp_path):
    fixture = WriteFixture()
    async def scenario():
        backend = provider(fixture, tmp_path / 'state/operations.sqlite')
        try:
            prepared = await prepare(backend)
            service = InvoiceService(backend, journal=backend.journal, allow_real_writes=True)
            await service.execute(prepared, 'confirm', 123)
            fixture.created.append({**copy.deepcopy(fixture.created[0]), 'Ref_Key': ref(91)})
            with pytest.raises(WorkflowFailure):
                await service.execute(prepared, 'duplicate-marker', 123)
            fixture.created.clear()
            fixture.lookup_extra = [{'Ref_Key': ref(100 + n), 'DeletionMark': False, 'Company_Key': ref(1),
                'Contract_Key': ref(2), 'Entity_Key': ref(3), 'Date': '2026-09-01T00:00:00',
                'Comment': 'Unrelated synthetic invoice'} for n in range(1000)]
            with pytest.raises(WorkflowFailure):
                await service.execute(prepared, 'lookup-limit', 123)
            assert fixture.posts == 1
        finally:
            await backend.aclose()
    asyncio.run(scenario())


def test_write_mode_cannot_be_enabled_by_flag_without_all_admission_settings(tmp_path):
    from app.config import Settings
    from pydantic import ValidationError
    common = dict(token='123:' + 'x' * 32, webhook_secret='y' * 32, allowed_users=frozenset({123}),
                  mode='firstbit_write', onec_write_enabled=True,
                  operation_db=(tmp_path / 'operations.sqlite').resolve(), firstbit_write_schema_sha256='a' * 64)
    for change in ({'onec_write_enabled': False}, {'operation_db': None},
                   {'firstbit_write_schema_sha256': None}, {'firstbit_write_schema_sha256': 'invalid'}):
        with pytest.raises(ValidationError):
            Settings(**{**common, **change})
    settings = Settings(**common)
    assert settings.onec_write_enabled


def test_dedicated_writer_attestation_cannot_reuse_readonly_claim_or_admin_identity(tmp_path):
    from pydantic import ValidationError
    fixture = WriteFixture()
    for username, readonly, writable in [('administrator', False, True), ('synthetic_writer', True, True),
                                         ('synthetic_writer', False, False)]:
        with pytest.raises(ValidationError):
            FirstBitSettings(base_url=fixture.env()['FIRSTBIT_BASE_URL'], username=username,
                password='SYNTHETIC-ONLY', readonly_account=readonly, write_account=writable,
                bookkeeping_item_id=UUID(ref(5)))


def test_provider_transport_claim_is_durable_even_if_no_external_response(tmp_path):
    fixture = WriteFixture()
    async def scenario():
        path = tmp_path / 'state/operations.sqlite'
        backend = provider(fixture, path)
        try:
            prepared = await prepare(backend)
            backend.journal.reserve(prepared, 123)
            backend.journal.claim_mutation(prepared.operation_id, 'create')
            backend.journal.claim_provider_request(prepared.operation_id, 'create')
            reopened = OperationJournal(path, namespace='synthetic-firstbit-write')
            with pytest.raises(MutationUncertain):
                reopened.claim_provider_request(prepared.operation_id, 'create')
            with pytest.raises(MutationUncertain):
                await backend.ensure_draft(prepared.basis, prepared.operation_id)
            assert fixture.posts == 0
        finally:
            await backend.aclose()
    asyncio.run(scenario())


@pytest.mark.parametrize('field', ['IncomeItem_Key', 'ExpenseItem_Key', 'BusinessActivity_Key',
                                  'BaseUnit_Key', 'TradeDiscountsGLAccount_GL_Key', 'IsDeferral'])
def test_missing_or_unmodeled_financial_dimensions_never_disappear_from_write_admission(field, tmp_path):
    fixture = WriteFixture()
    fixture.records['Document_InventoryExpense'][0]['Inventory'][0][field] = (
        True if field == 'IsDeferral' else 1 if field == 'ConnectionKey' else ref(80))
    async def scenario():
        backend = provider(fixture, tmp_path / 'state/operations.sqlite')
        try:
            prepared = await prepare(backend)
            assert prepared.preview.execution_review is None
            assert prepared.preview.write_blocker
            with pytest.raises(WorkflowFailure):
                await InvoiceService(backend, journal=backend.journal, allow_real_writes=True).execute(prepared, 'confirm', 123)
            assert fixture.posts == 0
        finally:
            await backend.aclose()
    asyncio.run(scenario())


def test_live_analytical_references_are_preserved_and_reread(tmp_path):
    fixture = WriteFixture()
    source = fixture.records['Document_InventoryExpense'][0]
    dimensions = {'BaseUnit_Key':('Catalog_BaseUnits',71),'BusinessActivity_Key':('Catalog_BusinessActivities',72),
        'ExpenseItem_Key':('Catalog_ExpenseItems',73),'IncomeItem_Key':('Catalog_IncomeItems',74)}
    for field,(entity,number) in dimensions.items():
        fixture.records[entity] = [{'Ref_Key':ref(number),'DeletionMark':False,'DataVersion':'dimension-v1',
                                   'Description':'Synthetic reviewed dimension',**({'IsFolder':False} if field=='ExpenseItem_Key' else {})}]
        for row in source['Inventory']:row[field]=ref(number)
    async def scenario():
        backend=provider(fixture,tmp_path/'state/operations.sqlite')
        try:
            prepared=await prepare(backend)
            assert prepared.preview.execution_review is not None
            service=InvoiceService(backend,journal=backend.journal,allow_real_writes=True)
            await service.execute(prepared,'confirmed',123)
            for actual,original in zip(fixture.created[0]['Inventory'],source['Inventory']):
                for field in dimensions:assert actual[field]==original[field]
                assert actual['ConnectionKey']==original['ConnectionKey']
            fixture.created[0]['Inventory'][0]['ExpenseItem_Key']=ref(98)
            with pytest.raises(WorkflowFailure):await service.execute(prepared,'reconcile-changed',123)
            assert fixture.posts==1
        finally:await backend.aclose()
    asyncio.run(scenario())


@pytest.mark.parametrize('bad_reference',['deleted','folder','missing'])
def test_unusable_expense_dimension_blocks_before_create(tmp_path,bad_reference):
    fixture=WriteFixture()
    row=fixture.records['Document_InventoryExpense'][0]['Inventory'][0]
    row['ExpenseItem_Key']=ref(73)
    if bad_reference!='missing':
        fixture.records['Catalog_ExpenseItems']=[{'Ref_Key':ref(73),'DeletionMark':bad_reference=='deleted',
          'IsFolder':bad_reference=='folder','Description':'Synthetic expense','DataVersion':'v1'}]
    async def scenario():
        backend=provider(fixture,tmp_path/'state/operations.sqlite')
        try:
            prepared=await prepare(backend)
            assert prepared.preview.execution_review is None
            with pytest.raises(WorkflowFailure):
                await InvoiceService(backend,journal=backend.journal,allow_real_writes=True).execute(prepared,'confirm',123)
            assert fixture.posts==0
        finally:await backend.aclose()
    asyncio.run(scenario())


def test_empty_composite_reference_and_delete_marker_are_not_financial_values(tmp_path):
    fixture=WriteFixture()
    row=fixture.records['Document_InventoryExpense'][0]['Inventory'][0]
    row.update(GoodsOrder=ref(0),GoodsOrder_Type='UnavailableEntities.UnavailableEntity_'+ref(65),DeleteUUID=ref(0))
    async def scenario():
        backend=provider(fixture,tmp_path/'state/operations.sqlite')
        try:
            assert (await prepare(backend)).preview.execution_review is not None
            row['GoodsOrder']=ref(99)
            assert (await prepare(backend)).preview.execution_review is None
        finally:await backend.aclose()
    asyncio.run(scenario())


def test_historical_issuer_conflict_is_explicit_and_never_silently_uses_contract_issuer(tmp_path):
    fixture=WriteFixture()
    fixture.records['Catalog_CompanyContracts'][0]['Entity_Key']=ref(88)
    entity=copy.deepcopy(fixture.records['Catalog_Entities'][0])
    entity.update(Ref_Key=ref(88),Description='Synthetic alternative issuer',DescriptionFull='Synthetic alternative issuer')
    fixture.records['Catalog_Entities'].append(entity)
    async def scenario():
        backend=provider(fixture,tmp_path/'state/operations.sqlite')
        try:
            prepared=await prepare(backend)
            history=prepared.preview.historical_proposal
            assert history.contract_entity_id==ref(88) and history.entity_id==ref(3)
            assert prepared.preview.execution_review is not None
            references={r.role:r.reference_id for r in prepared.preview.execution_review.references}
            assert references['issuer:source']==ref(3) and references['issuer:contract']==ref(88)
            assert backend._frozen_payload(prepared.basis)['Entity_Key']==UUID(ref(3))
            with pytest.raises(WritesDisabled):await backend.ensure_draft(prepared.basis,prepared.operation_id)
            assert fixture.posts==0
        finally:await backend.aclose()
    asyncio.run(scenario())


@pytest.mark.parametrize('expected', ['Yes', 'No'])
def test_reviewed_yesno_debt_offset_policy_survives_payload_and_readback(tmp_path, expected):
    from app.presentation import preview_text
    fixture = WriteFixture()
    fixture.records['Document_InventoryExpense'][0]['OffsetAdvancesDebtsAutomatically'] = expected

    async def scenario():
        backend = provider(fixture, tmp_path / 'state/operations.sqlite')
        try:
            prepared = await prepare(backend)
            assert prepared.preview.execution_review is not None
            assert prepared.preview.write_blocker is None
            references = {item.role: item.reference_id
                          for item in prepared.preview.execution_review.references}
            assert references['header:OffsetAdvancesDebtsAutomatically'] == json.dumps(expected)
            text = preview_text(prepared.preview)
            assert ('автоматически, как в образце' if expected == 'Yes' else 'отключён, как в образце') in text
            assert 'PDF пока заблокированы' not in text
            assert backend._frozen_payload(prepared.basis)['OffsetAdvancesDebtsAutomatically'] == expected
            result = await InvoiceService(backend, journal=backend.journal,
                allow_real_writes=True).execute(prepared, 'synthetic-confirm', 123)
            assert not result.invoice.posted and fixture.posts == 1
            assert fixture.created[0]['OffsetAdvancesDebtsAutomatically'] == expected
            fixture.created[0]['OffsetAdvancesDebtsAutomatically'] = 'No' if expected == 'Yes' else 'Yes'
            with pytest.raises(InvoiceConflict):
                await backend.read_operation(prepared.basis, prepared.operation_id)
        finally:
            await backend.aclose()

    asyncio.run(scenario())


@pytest.mark.parametrize('value', ['', 'SyntheticUnsupportedPolicy', 'yes', 'invalid\nvalue', None, True])
def test_unknown_debt_offset_policy_blocks_write_with_precise_safe_reason(tmp_path, value):
    from app.bot import Bot
    fixture = WriteFixture()
    fixture.records['Document_InventoryExpense'][0]['OffsetAdvancesDebtsAutomatically'] = value

    async def scenario():
        backend = provider(fixture, tmp_path / 'state/operations.sqlite')
        try:
            service = InvoiceService(backend, journal=backend.journal, allow_real_writes=True)
            prepared = await prepare(backend)
            assert prepared.preview.execution_review is None
            assert 'OffsetAdvancesDebtsAutomatically' in prepared.preview.write_blocker
            bot = Bot(service, None, None)
            prompt = bot.show_preview(123, prepared, InvoiceCommand(
                client='ООО Синтетика', invoice_date=date(2026, 9, 1)))
            assert 'READ-ONLY' not in prompt.text
            result = await bot.confirm(123, bot.pending[123], 'synthetic-blocked-confirm')
            assert 'OffsetAdvancesDebtsAutomatically' in result
            assert 'READ-ONLY' not in result
            if value == 'SyntheticUnsupportedPolicy':
                assert value not in result
            assert fixture.posts == 0
        finally:
            await backend.aclose()

    asyncio.run(scenario())
