import asyncio
import copy
import json
from datetime import date
from decimal import Decimal
from uuid import UUID

import httpx
import pytest
from pydantic import ValidationError

from app.config import Settings
from app.domain import (BackendFailure, ClientChoiceRequired, InvoiceCommand, ResolvedInvoiceCommand, ServiceSelection,
                        UserProblem, WorkflowFailure, WritesDisabled)
from app.firstbit import FirstBit, FirstBitSettings
from app.service import InvoiceService
from scripts.firstbit_fixture import FirstBitFixture, ref


@pytest.fixture
def fixture():
    return FirstBitFixture()


def provider(fixture):
    return FirstBit(FirstBitSettings(base_url=fixture.env()["FIRSTBIT_BASE_URL"],
        username="integration_reader", password="DO_NOT_LOG_SECRET", readonly_account=True,
        bookkeeping_item_id=UUID(ref(5))), transport=httpx.MockTransport(fixture.respond))


async def prepare(backend, **kwargs):
    return await InvoiceService(backend, timeout=30).prepare(InvoiceCommand(
        client="ООО Синтетика", invoice_date=date(2026, 9, 1), **kwargs), "test-1", 123)


def run(fixture, task):
    async def scenario():
        backend = provider(fixture)
        try:
            return await task(backend)
        finally:
            await backend.aclose()
    return asyncio.run(scenario())


def test_real_service_prepare_preserves_history_and_digest(fixture):
    async def scenario(backend):
        prepared = await prepare(backend)
        assert prepared.preview.total == Decimal("3150")
        assert [r.quantity for r in prepared.preview.lines] == [Decimal("1"), Decimal("2")]
        assert len({r.description for r in prepared.preview.lines}) == 2
        assert prepared.preview.historical_proposal.source_id == ref(8)
        assert prepared.preview.bank is None and prepared.preview.terms is None
        assert prepared.preview.supply_date is None
        assert prepared.preview.digest == (await prepare(backend)).preview.digest
        assert (await backend.read_operation(prepared.basis, prepared.operation_id)).status == "unknown"
    run(fixture, scenario)
    assert {r.method for r in fixture.calls} == {"GET"}
    assert not any("ItemPrices" in str(r.url) for r in fixture.calls)
    history = next(r for r in fixture.calls if r.url.path.endswith("Document_InventoryExpense"))
    assert "Company_Key eq guid'" + ref(1) in history.url.params["$filter"]
    assert "Contract_Key eq guid'" + ref(2) in history.url.params["$filter"]
    assert history.url.params["$top"] == "30"


def test_single_service_expands_all_rows_and_quantity_edit_keeps_operation(fixture):
    async def scenario(backend):
        original = await prepare(backend, services=(ServiceSelection(query="бухгалтерское обслуживание"),))
        assert len(original.preview.lines) == 2
        service = InvoiceService(backend)
        command = InvoiceCommand(client="ООО Синтетика", invoice_date=date(2026, 9, 1), services=(
            ServiceSelection(query=original.preview.lines[0].description, quantity=Decimal("3")),
            ServiceSelection(query=original.preview.lines[1].description, quantity=Decimal("2"))))
        old = InvoiceCommand(client=command.client, invoice_date=command.invoice_date, services=tuple(
            ServiceSelection(query=l.description, quantity=l.quantity) for l in original.preview.lines))
        changed = await service.prepare(command, "edit", 123, existing=original, old_command=old)
        assert changed.preview.total == Decimal("5250")
        assert changed.operation_id == original.operation_id
        assert changed.basis.revision != original.basis.revision
    run(fixture, scenario)


@pytest.mark.parametrize("flag", ["IsFolder", "DeletionMark", "Inactive"])
def test_unusable_company_excluded(fixture, flag):
    fixture.records["Catalog_Companies"][0][flag] = True
    with pytest.raises(UserProblem):
        run(fixture, lambda b: b.resolve_client("ООО Синтетика"))


def test_company_ambiguity_and_normalization(fixture):
    found = run(fixture, lambda b: b.resolve_client("  ООО   СИНТЕТИКА "))
    assert found.client_id == ref(1)
    fixture.records["Catalog_Companies"].append({**fixture.records["Catalog_Companies"][0], "Ref_Key": ref(99)})
    with pytest.raises(ClientChoiceRequired) as exc:
        run(fixture, lambda b: b.resolve_client("ООО Синтетика"))
    assert {c.client_id for c in exc.value.choices.candidates} == {ref(1), ref(99)}


def test_company_not_found_is_distinct_from_duplicate_name(fixture):
    with pytest.raises(UserProblem, match="Не нашёл похожих компаний"):
        run(fixture, lambda b: b.resolve_client("Missing synthetic client"))


def test_reviewed_alias_selects_explicit_record_among_identical_names(fixture):
    fixture.records["Catalog_Companies"].append({**fixture.records["Catalog_Companies"][0], "Ref_Key": ref(99)})

    async def scenario(backend):
        backend.settings = FirstBitSettings.model_validate({**backend.settings.model_dump(),
            "client_aliases": {"reviewed synthetic client": UUID(ref(99))}})
        selected = await backend.resolve_client("reviewed synthetic client")
        assert selected.client_id == ref(99)

    run(fixture, scenario)
    assert fixture.calls[-1].url.params["$filter"] == f"Ref_Key eq guid'{ref(99)}'"
    assert {request.method for request in fixture.calls} == {"GET"}


def test_full_name_candidates_require_local_exact_match(fixture):
    row = fixture.records["Catalog_Companies"][0]
    row["Description"] = "Synthetic short name"
    assert run(fixture, lambda b: b.resolve_client("ООО Синтетика")).client_id == ref(1)
    row["DescriptionFull"] = "ООО Синтетика branch"
    with pytest.raises(ClientChoiceRequired) as exc:
        run(fixture, lambda b: b.resolve_client("ООО Синтетика"))
    assert len(exc.value.choices.candidates) == 1


@pytest.mark.parametrize("selected", [ref(99), "not-a-uuid"])
def test_explicit_client_selection_cannot_escape_current_candidates(fixture, selected):
    with pytest.raises((UserProblem, ValueError)):
        run(fixture, lambda b: b.resolve_client("ООО Синтетика", selected_id=selected))


@pytest.mark.parametrize("flag", ["Inactive", "DeletionMark", "IsFolder"])
def test_explicit_client_selection_rechecks_active_state(fixture, flag):
    fixture.records["Catalog_Companies"][0][flag] = True
    with pytest.raises(UserProblem):
        run(fixture, lambda b: b.resolve_client("ООО Синтетика", selected_id=ref(1)))


def test_selected_company_must_still_match_original_name(fixture):
    fixture.records["Catalog_Companies"][0].update(Description="Unrelated", DescriptionFull="Unrelated")
    with pytest.raises(UserProblem):
        run(fixture, lambda b: b.resolve_client("ООО Синтетика", selected_id=ref(1)))


@pytest.mark.parametrize("change", ["wrong_owner", "inactive", "deleted", "zero_entity", "ambiguous_fallback"])
def test_contract_fail_closed(fixture, change):
    contract = fixture.records["Catalog_CompanyContracts"][0]
    if change == "wrong_owner":
        contract["Owner_Key"] = ref(99)
    elif change == "zero_entity":
        contract["Entity_Key"] = ref(0)
    elif change == "ambiguous_fallback":
        fixture.records["Catalog_Companies"][0]["ContractByDefault_Key"] = ref(0)
        fixture.records["Catalog_CompanyContracts"].append({**contract, "Ref_Key": ref(99)})
    else:
        contract["Inactive" if change == "inactive" else "DeletionMark"] = True
    with pytest.raises((UserProblem, WorkflowFailure)):
        run(fixture, prepare)


def test_unique_fallback_contract(fixture):
    fixture.records["Catalog_Companies"][0]["ContractByDefault_Key"] = ref(0)
    assert run(fixture, prepare).preview.historical_proposal.contract_id == ref(2)


@pytest.mark.parametrize("field,value", [("Posted", False), ("DeletionMark", True),
    ("Company_Key", ref(99)), ("Contract_Key", ref(99)), ("Date", "2026-10-01T00:00:00"),
    ("Entity_Key", ref(99)), ("DocumentCurrency_Key", ref(99)), ("AmountVATIn", True),
    ("DocumentAmount", "999.00")])
def test_bad_historical_state_blocked(fixture, field, value):
    fixture.records["Document_InventoryExpense"][0][field] = value
    with pytest.raises((WorkflowFailure, UserProblem)):
        run(fixture, prepare)


def test_newest_matching_history_skips_unrelated_rows(fixture):
    history = fixture.records["Document_InventoryExpense"]
    newer = copy.deepcopy(history[0])
    newer.update(Ref_Key=ref(90), Date="2026-08-25T00:00:00")
    for line in newer["Inventory"]:
        line["Item_Key"] = ref(99)
    history.insert(0, newer)
    assert run(fixture, prepare).preview.historical_proposal.source_id == ref(8)
    history[1]["Inventory"][0]["Item_Key"] = ref(99)
    history[1]["Inventory"][1]["Item_Key"] = ref(99)
    with pytest.raises(UserProblem):
        run(fixture, prepare)


@pytest.mark.parametrize("field,value", [("Price", "990.00"), ("VATAmount", "0.00"),
    ("DiscountMarkupAmount", "1"), ("AutomaticDiscountRate", "2"), ("UnitOfMeasure", ref(0)),
    ("UnitOfMeasure_Type", "malicious-url"), ("VATRate_Key", ref(0)), ("Quantity", "NaN")])
def test_unknown_line_financial_semantics_blocked(fixture, field, value):
    fixture.records["Document_InventoryExpense"][0]["Inventory"][0][field] = value
    with pytest.raises((WorkflowFailure, UserProblem)):
        run(fixture, prepare)


@pytest.mark.parametrize("field,value", [("Rate", "6"), ("Calculated", True), ("Exempt", True), ("OutOfScope", True)])
def test_vat_not_guessed(fixture, field, value):
    fixture.records["Catalog_VATRates"][0][field] = value
    with pytest.raises((WorkflowFailure, UserProblem)):
        run(fixture, prepare)


def test_schema_mismatch_prevents_business_reads(fixture):
    fixture.metadata = fixture.metadata.replace(b'Name="Company_Key"', b'Name="RenamedCompany"')
    with pytest.raises(BackendFailure, match="schema_mismatch"):
        run(fixture, lambda b: b.resolve_client("ООО Синтетика"))
    assert len(fixture.calls) == 1


@pytest.mark.parametrize("status", [301, 401, 403, 500])
def test_http_errors_redacted_and_not_retried(fixture, status, caplog):
    fixture.status = status
    with pytest.raises(BackendFailure) as exc:
        run(fixture, lambda b: b.resolve_client("ООО Синтетика"))
    assert "PRIVATE_ERROR" not in str(exc.value)
    assert "DO_NOT_LOG_SECRET" not in caplog.text
    assert len(fixture.calls) == 1


def test_transport_timeout_safe(fixture):
    def timeout(request):
        raise httpx.ReadTimeout("DO_NOT_LOG_SECRET")
    fixture.respond = timeout
    with pytest.raises(BackendFailure, match="get_failed"):
        run(fixture, lambda b: b.resolve_client("ООО Синтетика"))


@pytest.mark.parametrize("failure", [httpx.ConnectError, httpx.ReadTimeout])
def test_transient_get_read_is_retried_once_without_changing_query(fixture, failure, caplog):
    original = fixture.respond
    failed = []
    def transient(request):
        if request.url.path.endswith("Catalog_Companies") and not failed:
            failed.append(request)
            fixture.calls.append(request)
            raise failure("PRIVATE_NETWORK_ERROR_DO_NOT_LOG")
        return original(request)
    fixture.respond = transient
    assert run(fixture, lambda b: b.resolve_client("ООО Синтетика")).client_id == ref(1)
    pages = [r for r in fixture.calls if "$skip" in r.url.params]
    assert len(pages) == 2 and pages[0].url == pages[1].url
    assert {r.method for r in fixture.calls} == {"GET"}
    assert "PRIVATE_NETWORK_ERROR" not in caplog.text


def test_literal_injection_is_data(fixture):
    with pytest.raises(UserProblem):
        run(fixture, lambda b: b.resolve_client("x' or true or Description eq 'x&$top=999"))
    request = fixture.calls[-1]
    # Client text now stays local entirely; only a fixed, bounded names query reaches ERP.
    assert request.url.params["$filter"] == "DeletionMark eq false and IsFolder eq false and Inactive eq false"
    assert "x'" not in str(request.url) and "999" not in str(request.url)
    assert request.url.params["$top"] == "200" and request.url.params["$skip"] == "0"
    assert set(request.url.params) == {"$format", "$select", "$filter", "$top", "$skip", "$orderby"}
    assert b"+" not in request.url.query
    assert b"%20" in request.url.query
    assert "tolower" not in request.url.params["$filter"]
    assert "DescriptionFull eq" not in request.url.params["$filter"]
    assert "substringof(" not in request.url.params["$filter"]


def test_no_mutation_even_if_caller_enables_permission(fixture):
    async def scenario(backend):
        prepared = await prepare(backend)
        before = len(fixture.calls)
        for method in (backend.ensure_draft, backend.ensure_posted, backend.get_pdf):
            with pytest.raises(WritesDisabled):
                await method()
        with pytest.raises(WorkflowFailure) as exc:
            await InvoiceService(backend, allow_real_writes=True).execute(prepared, "test", 123)
        assert exc.value.stage == "write_disabled"
        assert len(fixture.calls) == before
    run(fixture, scenario)


@pytest.mark.parametrize("value", ["http://host/db/odata/standard.odata/", "https://user:pass@host/db/odata/standard.odata/",
    "https://host/db/odata/standard.odata/?password=secret", "https://host/db/odata/standard.odata/#x"])
def test_url_and_account_security(fixture, value):
    data = {"base_url": value, "username": "administrator", "password": "SECRET",
            "readonly_account": True, "bookkeeping_item_id": UUID(ref(5))}
    with pytest.raises(ValidationError) as exc:
        FirstBitSettings(**data)
    assert "SECRET" not in str(exc.value)


def test_env_requires_explicit_readonly_attestation(fixture, monkeypatch):
    for k, v in fixture.env().items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("FIRSTBIT_READONLY_ACCOUNT", "false")
    with pytest.raises(ValueError):
        FirstBitSettings.from_env()


@pytest.mark.parametrize("mode", ["mock", "firstbit_readonly"])
def test_write_flag_always_rejected(mode):
    with pytest.raises(ValidationError):
        Settings(token="123:" + "x" * 32, webhook_secret="x" * 32, allowed_users=frozenset({123}),
                 mode=mode, onec_write_enabled=True)


@pytest.mark.parametrize("raw", [b'{', b'{"value": [], "value": []}',
    b'{"value": [], "odata.nextLink": "https://evil.invalid/"}',
    b'{"value": [], "@odata.nextLink": "https://evil.invalid/"}',
    b'{"d": {"results": []}}', b'x' * 1_000_001],
    ids=["invalid-json", "duplicate-keys", "next-link", "v4-next-link", "unknown-envelope", "oversized"])
def test_malformed_oversized_and_paginated_responses_fail_closed(fixture, raw):
    async def scenario(backend):
        await backend.check_metadata()
        fixture.raw = raw
        await backend._record("Catalog_Companies", ref(1))
    with pytest.raises(BackendFailure):
        run(fixture, scenario)
    assert len(fixture.calls) == 2


def test_historical_price_changes_are_proposals_and_refresh_changes_revision(fixture):
    async def scenario(backend):
        original = await prepare(backend)
        fixture.records["Document_InventoryExpense"][0]["Inventory"][0] = fixture.line(1, "1", "1500")
        fixture.records["Document_InventoryExpense"][0]["DocumentAmount"] = "3675.00"
        changed = await InvoiceService(backend).refresh(original, "refresh", 123)
        assert changed.preview.lines[0].price == Decimal("1500")
        assert changed.basis.revision != original.basis.revision
        assert changed.operation_id == original.operation_id
    run(fixture, scenario)


def test_historical_supplier_is_proven_and_mismatch_remains_explicit(fixture):
    fixture.records["Catalog_Entities"].append({"Ref_Key": ref(20), "DeletionMark": False,
        "Description": "Historical synthetic supplier", "DescriptionFull": "Historical synthetic supplier"})
    fixture.records["Document_InventoryExpense"][0]["Entity_Key"] = ref(20)
    prepared = run(fixture, prepare)
    assert prepared.preview.issuer.name == "Historical synthetic supplier"
    assert prepared.preview.historical_proposal.entity_id == ref(20)
    assert prepared.preview.historical_proposal.contract_entity_id == ref(3)
    assert prepared.preview.historical_proposal.contract_entity_name == "Synthetic issuer"
    from app.presentation import preview_text
    text = preview_text(prepared.preview)
    assert "Поставщик нового документа пока не подтверждён" in text
    assert ref(20) not in text and ref(3) not in text and ref(8) not in text
    assert "3 150.00" in text and len(prepared.preview.lines) == 2


def test_deleted_historical_supplier_cannot_be_offered_for_review(fixture):
    fixture.records["Catalog_Entities"][0]["DeletionMark"] = True
    with pytest.raises(UserProblem):
        run(fixture, prepare)


@pytest.mark.parametrize("query", ["бухгалтерские услуги", "ведение бухгалтерии", "бухучёт"])
def test_bookkeeping_language_aliases_resolve_only_reviewed_service(fixture, query):
    assert run(fixture, lambda b: b.resolve_service(ref(1), query)).service_id == ref(5)


def test_previous_month_does_not_silently_use_older_basis(fixture):
    fixture.records["Document_InventoryExpense"][0]["Date"] = "2026-07-20T00:00:00"
    with pytest.raises(WorkflowFailure):
        run(fixture, lambda b: prepare(b, previous="previous_month"))


def test_same_timestamp_basis_is_ambiguous(fixture):
    fixture.records["Document_InventoryExpense"].append(
        {**fixture.records["Document_InventoryExpense"][0], "Ref_Key": ref(99)})
    with pytest.raises(UserProblem):
        run(fixture, prepare)


def test_admin_identity_rejected_with_valid_url(fixture):
    with pytest.raises(ValidationError):
        FirstBitSettings(base_url=fixture.env()["FIRSTBIT_BASE_URL"], username="Administrator",
            password="SECRET", readonly_account=True, bookkeeping_item_id=UUID(ref(5)))


def test_reviewed_alias_uses_only_stable_ref(fixture):
    async def scenario(backend):
        backend.settings = FirstBitSettings(**{**backend.settings.model_dump(),
            "client_aliases": {"синт": UUID(ref(1))}})
        client = await backend.resolve_client("СИНТ")
        assert client.client_id == ref(1)
    run(fixture, scenario)
    assert fixture.calls[-1].url.params["$filter"] == "Ref_Key eq guid'" + ref(1) + "'"


def test_zero_rate_is_read_from_firstbit_not_assumed_five_percent(fixture):
    fixture.records["Catalog_VATRates"][0].update(Rate="0", Description="Synthetic zero VAT", Export=True)
    source = fixture.records["Document_InventoryExpense"][0]
    for row in source["Inventory"]:
        row.update(VATAmount="0.00", AmountTotal=row["Amount"])
    source["DocumentAmount"] = "3000.00"
    result = run(fixture, prepare)
    assert result.preview.tax_amount == 0
    assert all(line.tax.rate == 0 and line.tax.treatment == "zero_rated" for line in result.preview.lines)


def test_failed_readonly_refresh_reports_resolve_without_claiming_operation_state(fixture):
    async def scenario(backend):
        original = await prepare(backend)
        fixture.status = 503
        with pytest.raises(WorkflowFailure) as exc:
            await InvoiceService(backend).refresh(original, "refresh", 123)
        assert exc.value.stage == "resolve"
        assert exc.value.state == "unknown"
    run(fixture, scenario)


def test_smoke_client_does_not_limit_other_clients_or_reuse_their_history(fixture, monkeypatch):
    monkeypatch.setenv("FIRSTBIT_SMOKE_CLIENT", "ООО Синтетика")
    second = copy.deepcopy(fixture.records)
    second["Catalog_Companies"][0].update(Ref_Key=ref(10), Description="ООО Другой клиент",
        DescriptionFull="ООО Другой клиент", ContractByDefault_Key=ref(11))
    second["Catalog_CompanyContracts"][0].update(Ref_Key=ref(11), Owner_Key=ref(10))
    source = second["Document_InventoryExpense"][0]
    source.update(Ref_Key=ref(12), Company_Key=ref(10), Contract_Key=ref(11), DocumentAmount="6300.00")
    source["Inventory"] = [fixture.line(1, "1", "2000"), fixture.line(2, "2", "2000")]
    original = fixture.records
    original_respond = fixture.respond

    def respond(request):
        query = request.url.params.get("$filter", "")
        if request.url.path.endswith("Catalog_Companies") and "$skip" in request.url.params:
            fixture.records = {**original, "Catalog_Companies": original["Catalog_Companies"] + second["Catalog_Companies"]}
            return original_respond(request)
        other = ("другой клиент" in query.casefold() or any(ref(n) in query for n in (10, 11, 12)))
        fixture.records = second if other else original
        return original_respond(request)

    fixture.respond = respond

    async def scenario(backend):
        first = await prepare(backend)
        other = await InvoiceService(backend).prepare(InvoiceCommand(client="ООО Другой клиент",
            invoice_date=date(2026, 9, 1)), "other-client", 123)
        assert first.request.client_id == ref(1) and other.request.client_id == ref(10)
        assert first.preview.historical_proposal.contract_id == ref(2)
        assert other.preview.historical_proposal.contract_id == ref(11)
        assert first.preview.historical_proposal.source_id == ref(8)
        assert other.preview.historical_proposal.source_id == ref(12)
        assert first.preview.total == Decimal("3150") and other.preview.total == Decimal("6300")
        assert first.operation_id != other.operation_id
    run(fixture, scenario)


def test_verified_double_schema_preserves_decimal_validation(fixture):
    fixture.metadata = fixture.metadata.replace(b'Edm.Decimal', b'Edm.Double')
    for line in fixture.records["Document_InventoryExpense"][0]["Inventory"]:
        line["LineNumber"] = str(line["LineNumber"])
        for field in ("Quantity", "Price", "Amount", "AmountTotal", "VATAmount",
                      "DiscountMarkupRate", "DiscountMarkupAmount", "AutomaticDiscountRate", "AutomaticDiscountAmount"):
            line[field] = float(line[field])
    result = run(fixture, prepare)
    assert result.preview.total == Decimal("3150.00")
    assert all(isinstance(line.price, Decimal) for line in result.preview.lines)
    fixture.records["Document_InventoryExpense"][0]["Inventory"][0]["VATAmount"] = 49.99
    with pytest.raises(WorkflowFailure):
        run(fixture, prepare)


@pytest.mark.parametrize("number", ["1.0", "-1", "0", "+1", True, "9223372036854775808"])
def test_odata_int64_rejects_noncanonical_or_out_of_range_line_numbers(fixture, number):
    fixture.records["Document_InventoryExpense"][0]["Inventory"][0]["LineNumber"] = number
    with pytest.raises(WorkflowFailure):
        run(fixture, prepare)


def test_firstbit_read_failure_audit_code_is_bounded_and_redacted(fixture):
    from app.service import safe_backend_error
    fixture.status = 403
    with pytest.raises(BackendFailure) as error:
        run(fixture, lambda backend: backend.resolve_client('synthetic'))
    assert safe_backend_error(error.value) == 'firstbit_get_failed_http_403'
    assert safe_backend_error(BackendFailure('private body SECRET')) == 'BackendFailure'
    assert safe_backend_error(ValueError('private body SECRET')) == 'ValueError'
