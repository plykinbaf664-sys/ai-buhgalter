"""Synthetic VAT-inclusive fixtures; no production customer data."""
import asyncio
import copy
import json
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

import pytest
from pydantic import ValidationError

from app.domain import (
    InvoiceCommand, InvoiceLine, InvoicePreview, PreviewLineOverride, ResolvedInvoiceCommand,
    ResolvedServiceSelection, ServiceSelection, TaxProfile, UserProblem, WorkflowFailure, PreviewTaxRequest,
)
from app.presentation import preview_text
from app.service import InvoiceService
from scripts.firstbit_fixture import ref
from test_firstbit_write import WriteFixture, provider, prepare
from test_firstbit_tax import TaxFixture
from test_firstbit_production import SyntheticNativeUI, backend as native_backend


def inclusive_fixture(fixture):
    source = fixture.records['Document_InventoryExpense'][0]
    source['AmountVATIn'] = True
    rates = {r['Ref_Key']: Decimal(str(r['Rate'])) for r in fixture.records['Catalog_VATRates']}
    for row in source['Inventory']:
        row['Price'] = str((Decimal(str(row['Price'])) * (100 + rates[row['VATRate_Key']]) / 100)
                           .quantize(Decimal('.01'), rounding=ROUND_HALF_UP))
        row['Amount'] = row['AmountTotal']
        row['ConnectionKey'] = str(-int(row['LineNumber']))
    return fixture


def line(qty, price, rate, net, vat, gross):
    return InvoiceLine(service_id='synthetic-service', description='Synthetic service',
        quantity=Decimal(qty), uom='Pcs', price=Decimal(price),
        tax=TaxProfile(tax_id='synthetic-tax', label='Synthetic tax',
                       treatment='standard' if Decimal(rate) else 'zero_rated', rate=Decimal(rate)),
        subtotal=Decimal(net), tax_amount=Decimal(vat), total=Decimal(gross), price_includes_tax=True)


@pytest.mark.parametrize('values', [
    ('1', '105', '5', '100', '5', '105'),
    ('3', '19.99', '5', '57.11', '2.86', '59.97'),
    ('0.5', '0.21', '5', '0.10', '0.01', '0.11'),
    ('2', '100', '0', '200', '0', '200'),
    ('1', '120', '20', '100', '20', '120'),
])
def test_inclusive_source_keeps_native_price_and_extracts_vat_exactly(values):
    original = line(*values)
    assert original.price == Decimal(values[1])
    assert InvoiceLine.model_validate_json(original.model_dump_json()) == original
    assert original.model_dump()['price_includes_tax'] is True


def test_exclusive_legacy_json_bytes_and_digest_inputs_do_not_change():
    legacy = ('{"service_id":"synthetic","description":"Legacy synthetic","quantity":"3","uom":"Pcs",'
              '"price":"100","tax":{"tax_id":"vat5","label":"5%","treatment":"standard","rate":"5"},'
              '"subtotal":"300","tax_amount":"15","total":"315","source_line_number":null,"source_id":null}')
    restored = InvoiceLine.model_validate_json(legacy)
    assert restored.price_includes_tax is False
    assert restored.model_dump_json() == legacy
    assert 'price_includes_tax' not in restored.model_dump()


def test_inclusive_arithmetic_rejects_naive_net_unit_rounding_and_double_vat():
    original = line('3', '19.99', '5', '57.11', '2.86', '59.97')
    with pytest.raises(ValidationError):
        InvoiceLine(**{**original.model_dump(), 'subtotal': Decimal('57.12'), 'total': Decimal('59.98')})
    with pytest.raises(ValidationError):
        InvoiceLine(**{**original.model_dump(), 'total': Decimal('62.83')})
    with pytest.raises(ValidationError):
        InvoiceLine(**{**original.model_dump(), 'price_includes_tax': 'true'})


def test_user_price_and_amount_remain_net_in_inclusive_preview():
    original = line('1', '105', '5', '100', '5', '105')
    edited = original.overridden(PreviewLineOverride(line_number=1, price=Decimal('1500')))
    assert (edited.price, edited.subtotal, edited.tax_amount, edited.total) == (
        Decimal('1575'), Decimal('1500'), Decimal('75'), Decimal('1575'))
    assert edited.matches_net_price(Decimal('1500'))
    exempt = TaxProfile(tax_id='synthetic-exempt',label='Exempt',treatment='exempt',rate=Decimal(0))
    without = original.overridden(PreviewLineOverride(line_number=1,
        tax=PreviewTaxRequest(mode='without_tax')),tax=exempt)
    assert (without.price, without.subtotal, without.tax_amount, without.total) == (
        Decimal('105'), Decimal('105'), Decimal('0'), Decimal('105'))
    repeated = line('3', '19.99', '5', '57.11', '2.86', '59.97')
    assert repeated.overridden(PreviewLineOverride(line_number=1, amount=Decimal('57.11'))) == repeated
    many = line('100', '1.05', '5', '100', '5', '105')
    with pytest.raises(UserProblem, match='не представима'):
        many.overridden(PreviewLineOverride(line_number=1, price=Decimal('1.01')))


def test_inclusive_real_adapter_payload_readback_repeat_and_mixed_mode_guard(tmp_path):
    fixture = inclusive_fixture(WriteFixture())
    async def scenario():
        b = provider(fixture, tmp_path/'private/operations.sqlite')
        try:
            prepared = await prepare(b)
            p = prepared.preview
            assert p.price_includes_tax and p.execution_review is not None and p.write_blocker is None
            assert all(request.method == 'GET' for request in fixture.calls)
            assert 'Цены образца включают НДС' in preview_text(p)
            payload = b._frozen_payload(prepared.basis)
            assert payload['AmountVATIn'] is True
            for actual, expected in zip(payload['Inventory'], p.lines):
                assert actual['Price'] == expected.price
                assert actual['Amount'] == actual['AmountTotal'] == expected.total
            # A document-wide pricing flag cannot silently mix inclusive/exclusive rows.
            changed = list(p.lines)
            old = changed[-1]
            net_unit = (old.subtotal/old.quantity).quantize(Decimal('.01'))
            changed[-1] = InvoiceLine(**{**old.model_dump(), 'price': net_unit, 'price_includes_tax': False})
            with pytest.raises(ValidationError, match='Mixed document VAT pricing'):
                InvoicePreview(**{**p.model_dump(), 'lines': tuple(changed)})
            service = InvoiceService(b, journal=b.journal, allow_real_writes=True)
            result = await service.execute(prepared, 'synthetic-confirm', 123)
            assert fixture.posts == 1 and not result.invoice.posted
            assert fixture.created[0]['AmountVATIn'] is True
            assert await service.execute(prepared, 'synthetic-repeat', 123) == result
            assert fixture.posts == 1
        finally:
            await b.aclose()
    asyncio.run(scenario())


def test_quantity_change_recalculates_inclusive_amounts_without_net_unit_conversion(tmp_path):
    fixture = inclusive_fixture(WriteFixture())
    src = fixture.records['Document_InventoryExpense'][0]
    src['Inventory'] = [src['Inventory'][0]]
    src['DocumentAmount'] = src['Inventory'][0]['AmountTotal']
    src['PaymentTermsStages'][0]['Amount'] = src['DocumentAmount']
    async def scenario():
        b = provider(fixture, tmp_path/'private/operations.sqlite')
        try:
            basis = await b.resolve_basis(ResolvedInvoiceCommand(client_id=ref(1), invoice_date=date(2026,9,1),
                services=(ResolvedServiceSelection(service_id=ref(5), quantity=Decimal('3')),)))
            row = basis.preview.lines[0]
            assert row.price_includes_tax
            priced = (row.price*3).quantize(Decimal('.01'))
            assert row.total == priced and row.subtotal + row.tax_amount == priced
        finally:
            await b.aclose()
    asyncio.run(scenario())


def test_initial_net_amount_can_be_representable_with_gross_unit_only(tmp_path):
    fixture = inclusive_fixture(WriteFixture())
    src = fixture.records['Document_InventoryExpense'][0]
    src['Inventory'] = [src['Inventory'][0]]
    src['Inventory'][0].update(Quantity='3', Price='19.99', Amount='59.97', VATAmount='2.86', AmountTotal='59.97')
    src['DocumentAmount'] = '59.97'
    src['PaymentTermsStages'][0]['Amount'] = '59.97'
    async def scenario():
        b = provider(fixture, tmp_path/'private/operations.sqlite')
        try:
            prepared = await InvoiceService(b,journal=b.journal,allow_real_writes=True).prepare(
                InvoiceCommand(client='ООО Синтетика',invoice_date=date(2026,9,1),
                    services=(ServiceSelection(query=fixture.records['Catalog_Items'][0]['Description']),),
                    initial_overrides=(PreviewLineOverride(line_number=1,amount=Decimal('57.11')),)),
                'synthetic-net-amount',123)
            assert prepared.preview.lines[0].price == Decimal('19.99')
            assert prepared.preview.subtotal == Decimal('57.11')
            assert prepared.preview.total == Decimal('59.97')
            assert prepared.preview.execution_review is not None and fixture.posts == 0
        finally:
            await b.aclose()
    asyncio.run(scenario())


def test_inconsistent_inclusive_history_never_reaches_write(tmp_path):
    fixture = inclusive_fixture(WriteFixture())
    fixture.records['Document_InventoryExpense'][0]['Inventory'][0]['VATAmount'] = '0.01'
    async def scenario():
        b = provider(fixture,tmp_path/'private/operations.sqlite')
        try:
            with pytest.raises(WorkflowFailure):
                await prepare(b)
            assert fixture.posts == 0 and all(r.method == 'GET' for r in fixture.calls)
        finally:
            await b.aclose()
    asyncio.run(scenario())


@pytest.mark.parametrize('auto_posted', [True, False])
@pytest.mark.parametrize('outside_scope', [False, True])
@pytest.mark.parametrize('zero_keys', [False, True])
def test_inclusive_native_tax_flow_and_restart_keep_one_document_pair(tmp_path, auto_posted, outside_scope, zero_keys):
    fixture = inclusive_fixture(TaxFixture())
    if zero_keys:
        for row in fixture.records['Document_InventoryExpense'][0]['Inventory']:
            row['ConnectionKey'] = '0'
    if outside_scope:
        vat = copy.deepcopy(fixture.records['Catalog_VATRates'][0])
        vat.update(Ref_Key=ref(83),Description='Synthetic outside scope',Rate=0,
                   Exempt=False,Export=False,OutOfScope=True,Calculated=False)
        fixture.records['Catalog_VATRates'].append(vat)
        src = fixture.records['Document_InventoryExpense'][0]
        row = src['Inventory'][-1]
        amount = str((Decimal(str(row['Quantity']))*Decimal('1000')).quantize(Decimal('.01')))
        row.update(VATRate_Key=ref(83),Price='1000',Amount=amount,AmountTotal=amount,VATAmount='0')
        total = str(sum((Decimal(str(r['AmountTotal'])) for r in src['Inventory']),Decimal(0)))
        src['DocumentAmount'] = total
        src['PaymentTermsStages'][0]['Amount'] = total
    ui = SyntheticNativeUI(fixture, auto_posted=auto_posted)
    path = tmp_path/'private/operations.sqlite'
    async def scenario():
        b = native_backend(fixture,path,ui)
        prepared = await prepare(b);ui.prepared = prepared
        try:
            result = await InvoiceService(b,journal=b.journal,allow_real_writes=True).execute(
                prepared,'synthetic-confirm',123)
            assert result.invoice.posted and result.tax_invoice.posted and result.pdf.content.startswith(b'%PDF-')
            assert fixture.posts == ui.posts == ui.generates == ui.prints == 1
            assert fixture.created[0]['AmountVATIn'] is True
            source_rows = fixture.records['Document_InventoryExpense'][0]['Inventory']
            created_rows = fixture.created[0]['Inventory']
            assert len(created_rows) == len(source_rows) == 2
            assert [int(r['ConnectionKey']) for r in created_rows] == [int(r['ConnectionKey']) for r in source_rows]
            assert all(r['AmountVATIn'] is True and r['Amount'] == r['AmountTotal'] for r in fixture.tax[0]['Inventory'])
        finally:
            await b.aclose()
        b = native_backend(fixture,path,ui)
        try:
            repeated = await InvoiceService(b,journal=b.journal,allow_real_writes=True).execute(
                prepared,'synthetic-restart',123)
            assert repeated == result
            assert fixture.posts == ui.posts == ui.generates == ui.prints == 1
        finally:
            await b.aclose()
    asyncio.run(scenario())


def test_inclusive_pricing_does_not_unlock_unverified_fx(tmp_path):
    fixture = inclusive_fixture(WriteFixture())
    fixture.records['Document_InventoryExpense'][0]['ExchangeRate'] = 2
    async def scenario():
        b = provider(fixture,tmp_path/'private/operations.sqlite')
        try:
            prepared = await prepare(b)
            assert prepared.preview.price_includes_tax and prepared.preview.execution_review is None
            assert 'Валютная конвертация' in prepared.preview.write_blocker
            with pytest.raises(WorkflowFailure):
                await InvoiceService(b,journal=b.journal,allow_real_writes=True).execute(
                    prepared,'synthetic-confirm',123)
            assert fixture.posts == 0
        finally:
            await b.aclose()
    asyncio.run(scenario())


@pytest.mark.parametrize('key', [0, -1, -(2**63)])
def test_row_linkage_keys_preserve_full_signed_int64(key):
    from app.firstbit_write import WriteLine
    fixture = inclusive_fixture(WriteFixture())
    row = fixture.records['Document_InventoryExpense'][0]['Inventory'][0]
    parsed = WriteLine.model_validate_json(json.dumps({**row,'ConnectionKey':str(key)}))
    assert parsed.ConnectionKey == key


@pytest.mark.parametrize('key', [-(2**63)-1, 2**63, None, True, '1.5'])
def test_row_linkage_keys_reject_overflow_and_non_integers(key):
    from app.firstbit_write import WriteLine
    fixture = inclusive_fixture(WriteFixture())
    row = fixture.records['Document_InventoryExpense'][0]['Inventory'][0]
    with pytest.raises(ValidationError):
        WriteLine.model_validate_json(json.dumps({**row,'ConnectionKey':key}))


def test_invalid_row_linkage_key_is_an_explicit_blocker_before_write(tmp_path):
    fixture = inclusive_fixture(WriteFixture())
    fixture.records['Document_InventoryExpense'][0]['Inventory'][0]['ConnectionKey'] = str(2**63)
    async def scenario():
        b = provider(fixture,tmp_path/'private/operations.sqlite')
        try:
            prepared = await prepare(b)
            assert prepared.preview.execution_review is None
            assert 'ConnectionKey' in prepared.preview.write_blocker
            assert fixture.posts == 0
        finally:
            await b.aclose()
    asyncio.run(scenario())
