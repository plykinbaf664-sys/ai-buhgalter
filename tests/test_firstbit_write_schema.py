import asyncio
from xml.etree.ElementTree import fromstring, SubElement, tostring
from uuid import UUID

import httpx
import pytest

from app.domain import BackendFailure, WritesDisabled
from app.firstbit import FirstBit, FirstBitSettings
from app.firstbit_write_schema import inspect_write_schema
from scripts.firstbit_fixture import FirstBitFixture, synthetic_metadata


def metadata():
    """Independent synthetic extension; no production metadata/record fixture."""
    root = fromstring(synthetic_metadata())
    document = root.find("EntityType[@Name='Document_InventoryExpense']")
    for name in ("AccountingCurrency_Key", "NationalCurrency_Key", "BankAccount_Key", "PaymentTerms_Key",
                 "PaymentTermsVersion_Key", "AccountsReceivableGLAccount_GL_Key", "AdvancesReceivedGLAccount_GL_Key"):
        SubElement(document, "Property", Name=name, Type="Edm.Guid")
    for name in ("DataVersion", "Comment", "TransactionType", "TaxationVAT"):
        SubElement(document, "Property", Name=name, Type="Edm.String")
    for name in ("ExchangeRate", "ExchangeRateAccCur"):
        SubElement(document, "Property", Name=name, Type="Edm.Decimal")
    SubElement(document, "Property", Name="FactorAccCur", Type="Edm.Int64")
    SubElement(document, "Property", Name="PriceDate", Type="Edm.DateTime")
    row = root.find("ComplexType[@Name='HistoryRow']")
    for name in ("GLAccount_GL_Key", "SalesRevenueGLAccount_GL_Key", "OutputVATGLAccount_GL_Key"):
        SubElement(row, "Property", Name=name, Type="Edm.Guid")
    container = root.find('EntityContainer')
    action = SubElement(container, "FunctionImport", Name="Post", IsBindable="true", IsSideEffecting="true")
    SubElement(action, "Parameter", Name="bindingParameter", Type="StandardODATA.Document_InventoryExpense")
    SubElement(action, "Parameter", Name="PostingModeOperational", Type="Edm.Boolean")
    return root


def test_missing_or_wrong_pin_does_not_admit_schema():
    schema = inspect_write_schema(tostring(metadata()))
    assert schema.post_declared and not schema.declared_print_actions
    for pin in (None, "0" * 64, "x" * 64, "я" * 64, True, ""):
        with pytest.raises(WritesDisabled):
            schema.require_approved(pin)
    assert schema.require_approved(schema.sha256) == schema


@pytest.mark.parametrize('change', ['missing_default', 'wrong_money_type', 'missing_post', 'post_without_side_effect', 'new_post_parameter'])
def test_critical_schema_drift_rejected(change):
    root = metadata()
    document = root.find("EntityType[@Name='Document_InventoryExpense']")
    action = root.find("EntityContainer/FunctionImport[@Name='Post']")
    if change == 'missing_default':
        document.remove(document.find("Property[@Name='BankAccount_Key']"))
    elif change == 'wrong_money_type':
        root.find("ComplexType/Property[@Name='Price']").set('Type', 'Edm.Int64')
    elif change == 'missing_post':
        root.find('EntityContainer').remove(action)
    elif change == 'post_without_side_effect':
        action.set('IsSideEffecting', 'false')
    else:
        SubElement(action, 'Parameter', Name='Unexpected', Type='Edm.Boolean')
    with pytest.raises(BackendFailure):
        inspect_write_schema(tostring(root))


def test_critical_constraints_change_pin_but_unused_fields_do_not():
    root = metadata()
    original = inspect_write_schema(tostring(root))
    document = root.find("EntityType[@Name='Document_InventoryExpense']")
    SubElement(document, 'Property', Name='UnusedDisplayField', Type='Edm.String')
    assert inspect_write_schema(tostring(root)).sha256 == original.sha256
    document.find("Property[@Name='Comment']").set('MaxLength', '20')
    changed = inspect_write_schema(tostring(root))
    with pytest.raises(WritesDisabled):
        changed.require_approved(original.sha256)


def test_namespace_or_document_set_mismatch_cannot_pass():
    root = metadata()
    root.find("EntityContainer/EntitySet[@Name='Document_InventoryExpense']").set('EntityType','Other.Document_InventoryExpense')
    with pytest.raises(BackendFailure):
        inspect_write_schema(tostring(root))
    with pytest.raises(BackendFailure):
        inspect_write_schema(b'<!DOCTYPE Schema><Schema/>')


def test_provider_guard_refetches_metadata_and_never_enables_mutations():
    fixture = FirstBitFixture()
    fixture.metadata = tostring(metadata())
    pin = inspect_write_schema(fixture.metadata).sha256
    async def scenario():
        backend = FirstBit(FirstBitSettings.model_validate({
            'base_url': 'https://fixture.invalid/base/odata/standard.odata/',
            'username': 'synthetic_reader', 'password': 'synthetic-only', 'readonly_account': True,
            'bookkeeping_item_id': UUID(fixture.env()['FIRSTBIT_BOOKKEEPING_ITEM_ID'])}),
            transport=httpx.MockTransport(fixture.respond))
        try:
            await backend.verify_write_schema(pin)
            changed = metadata()
            changed.find("EntityType[@Name='Document_InventoryExpense']/Property[@Name='Comment']").set('MaxLength','10')
            fixture.metadata = tostring(changed)
            with pytest.raises(WritesDisabled):
                await backend.verify_write_schema(pin)
            with pytest.raises(WritesDisabled):
                await backend.ensure_draft(None, None)
            assert backend.preview_only and all(call.method == 'GET' for call in fixture.calls)
            assert len(fixture.calls) == 4
        finally:
            await backend.aclose()
    asyncio.run(scenario())
