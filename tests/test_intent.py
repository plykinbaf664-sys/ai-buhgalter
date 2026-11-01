from datetime import date
from decimal import Decimal

import pytest
from openai import pydantic_function_tool
from pydantic import ValidationError

from app.domain import InvoiceCommand, ServiceSelection, TaxRequest, UserProblem
from app.intent import CalendarInput, InvoiceDraft, InvoiceIntent, ground_intent, merge_intent
from app.validation import validate_json


def payload(**changes):
    return {"action": "edit", "client": None, "invoice_date": None, "service_period": None,
            "services": (), "lines_mode": "keep", "tax": None, "previous": None, "clarification": None, **changes}


def test_numeric_llm_schema_keeps_runtime_decimal_validation():
    schema = pydantic_function_tool(InvoiceIntent)["function"]["parameters"]
    numeric = schema["properties"]["quantity"]["anyOf"][0]
    assert numeric["type"] == "number" and numeric["multipleOf"] == .001
    valid = validate_json(InvoiceIntent, InvoiceIntent.model_validate(payload(
        quantity=Decimal("1.125"), quantity_evidence="1.125")).model_dump_json())
    assert valid.quantity == Decimal("1.125")
    for value in (Decimal("0"), Decimal("-1"), Decimal("1.0001"), Decimal("1000001"), Decimal("NaN")):
        with pytest.raises(ValidationError):
            InvoiceIntent.model_validate(payload(quantity=value, quantity_evidence="input"))


def test_empty_service_selection_never_clears_lines_during_tax_edit():
    draft = InvoiceDraft.from_command(InvoiceCommand(client="ООО Ромашка", invoice_date=date(2026, 10, 1),
        services=(ServiceSelection(query="accounting", quantity=Decimal("2")),)))
    result = merge_intent(draft, InvoiceIntent.model_validate(payload(lines_mode="replace",
        tax={"mode": "without_tax", "query": None, "evidence": "без НДС"})))
    assert result.services == draft.services and result.tax == TaxRequest(mode="without_tax")


def test_ambiguous_singular_replacement_does_not_discard_other_lines():
    draft = InvoiceDraft(services=(ServiceSelection(query="accounting"), ServiceSelection(query="legal")))
    change = InvoiceIntent.model_validate(payload(lines_mode="replace", services=({"query": "tax"},)))
    with pytest.raises(UserProblem, match="несколько услуг"):
        merge_intent(draft, change)


def test_known_client_repeated_by_model_does_not_change_context_or_require_repetition():
    draft = InvoiceDraft(client="ООО Ромашка")
    parsed = ground_intent(InvoiceIntent.model_validate(payload(client="ООО Ромашка",
        tax={"mode": "without_tax", "query": None, "evidence": "БЕЗ НДС"})), "поставь без НДС", draft)
    assert parsed.client is None and merge_intent(draft, parsed).client == draft.client
    with pytest.raises(UserProblem):
        ground_intent(InvoiceIntent.model_validate(payload(client="ООО Другая")), "без НДС", draft)


def test_known_day_is_preserved_when_only_month_changes():
    draft = InvoiceDraft(client="ООО Ромашка", invoice_date=date(2026, 10, 5))
    parsed = InvoiceIntent.model_validate(payload(invoice_date=CalendarInput(day=None, month=11, year=None, evidence="ноябрь")))
    assert merge_intent(draft, parsed).invoice_date == date(2026, 11, 5)


def test_new_request_can_add_explicit_services_without_existing_draft():
    parsed = InvoiceIntent.model_validate(payload(action="create", client="ООО Ромашка", lines_mode="add",
        services=({"query": "accounting"},)))
    assert merge_intent(InvoiceDraft(), parsed).services == (ServiceSelection(query="accounting"),)


def test_repeated_context_fields_are_noops_but_new_ungrounded_values_are_rejected():
    draft = InvoiceDraft(client="ООО Ромашка", invoice_date=date(2026, 10, 1), tax=TaxRequest(mode="without_tax"))
    parsed = InvoiceIntent.model_validate(payload(
        invoice_date=CalendarInput(day=5, month=10, year=2026, evidence="пятое"),
        tax={"mode": "without_tax", "query": None, "evidence": "без НДС"}))
    grounded = ground_intent(parsed, "Дату поменяй на пятое", draft)
    assert grounded.tax is None and grounded.invoice_date.year is None
    assert merge_intent(draft, grounded).invoice_date == date(2026, 10, 5)
    with pytest.raises(UserProblem):
        ground_intent(InvoiceIntent.model_validate(payload(tax={"mode": "with_tax", "query": None,
            "evidence": "с НДС"})), "Дату поменяй на пятое", draft)
    with pytest.raises(UserProblem):
        ground_intent(InvoiceIntent.model_validate(payload(invoice_date=CalendarInput(day=5, month=10,
            year=2027, evidence="пятое"))), "Дату на пятое", draft)


@pytest.mark.parametrize("field", ["invoice_date", "supply_date"])
def test_preview_date_bounds(field):
    from app.domain import InvoicePreview
    from app.fake_data import BANK, ISSUER, TERMS, recipient
    # The boundary rejects the date before any provider side effect or renderer.
    with pytest.raises(ValidationError) as error:
        InvoicePreview.model_validate({"invoice_date": date(2026, 10, 1), "supply_date": date(2026, 10, 1),
            "currency": "AED", "issuer": ISSUER, "recipient": recipient("TEST"), "bank": BANK, "terms": TERMS,
            field: date(1999, 1, 1)})
    assert any(e["loc"] == (field,) and e["type"] == "greater_than_equal" for e in error.value.errors())
