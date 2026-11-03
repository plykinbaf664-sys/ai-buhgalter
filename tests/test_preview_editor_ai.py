"""Focused preview extraction uses literal spans and never receives ERP data."""
import asyncio
from decimal import Decimal
from types import SimpleNamespace

from pydantic import SecretStr

from app.ai import CommandInterpreter, PreviewEditRequest
from app.intent import InvoiceDraft
from app.language import DraftLineChange, SourceQuantity, SourceSpan, words


def span(source: str, fragment: str) -> SourceSpan:
    start = source.index(fragment)
    indexes = [index for index, word in enumerate(words(source), 1)
               if word.start() < start + len(fragment) and word.end() > start]
    return SourceSpan(first_word=indexes[0], last_word=indexes[-1])


def extract(source, changes):
    calls = []
    async def parse(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(output_parsed=PreviewEditRequest(
            action="edit", draft_changes=changes, clarification=None))
    interpreter = CommandInterpreter(api_key=SecretStr("synthetic"), model="gpt-5-mini",
        sdk_client=SimpleNamespace(responses=SimpleNamespace(parse=parse)), send_draft_context=False)
    result = asyncio.run(interpreter.interpret(source, InvoiceDraft(), preview_ready=True))
    assert len(calls) == 1
    assert calls[0]["text_format"] is PreviewEditRequest
    assert all("Synthetic Bookkeeping" not in item["content"] for item in calls[0]["input"])
    return result.intent


def test_focused_editor_preserves_three_independent_changes():
    source = "Пункт 2 удали, пункт 3 поменять на 5 штук, пункт 1 на 3 штуки"
    changes = (
        DraftLineChange(kind="delete", target_span=span(source, "Пункт 2"), service_span=None,
            quantity=None, price_span=None, tax=None, description_span=None),
        DraftLineChange(kind="update", target_span=span(source, "пункт 3 поменять на 5 штук"),
            service_span=None, quantity=SourceQuantity(source_span=span(source, "5"), value=Decimal(5)),
            price_span=None, tax=None, description_span=None),
        DraftLineChange(kind="update", target_span=span(source, "пункт 1"), service_span=None,
            quantity=SourceQuantity(source_span=span(source, "3 штуки"), value=Decimal(3)),
            price_span=None, tax=None, description_span=None),
    )
    intent = extract(source, changes)
    assert [(change.kind, change.quantity) for change in intent.draft_mutations] == [
        ("delete", None), ("update", 5), ("update", 3)]


def test_focused_editor_preserves_add_with_explicit_price_and_quantity():
    source = "Добавь Payroll consulting 2 штуки по цене 150 без НДС"
    change = DraftLineChange(kind="add", target_span=None, service_span=span(source, "Payroll consulting"),
        quantity=SourceQuantity(source_span=span(source, "2"), value=Decimal(2)),
        price_span=span(source, "150"), tax=None, description_span=None)
    intent = extract(source, (change,))
    assert intent.draft_mutations[0].kind == "add"
    assert intent.draft_mutations[0].service == "Payroll consulting"
    assert intent.draft_mutations[0].quantity == 2
    assert intent.draft_mutations[0].price == 150


def test_explicit_vat_rate_is_recovered_for_added_service():
    source = "Добавь Payroll consulting 2 штуки по цене 150, НДС 0%"
    change = DraftLineChange(kind="add", target_span=None, service_span=span(source, "Payroll consulting"),
        quantity=SourceQuantity(source_span=span(source, "2"), value=Decimal(2)),
        price_span=span(source, "150"), tax=None, description_span=None)
    intent = extract(source, (change,))
    assert intent.draft_mutations[0].tax.mode == "rate"
    assert intent.draft_mutations[0].tax.rate == 0


def test_one_explicit_row_and_rate_repair_model_fragmented_spans():
    from app.language import PreviewTaxChange
    source = "Пункт 1: цена 150 без НДС, количество 3, НДС 5%"
    changes = (
        DraftLineChange(kind="update", target_span=span(source, "Пункт"), service_span=None,
            quantity=SourceQuantity(source_span=span(source, "3,"), value=Decimal(3)),
            price_span=None, tax=None, description_span=None),
        DraftLineChange(kind="update", target_span=span(source, "цена"), service_span=None,
            quantity=None, price_span=span(source, "150"), tax=None, description_span=None),
        DraftLineChange(kind="update", target_span=span(source, "НДС 5%"), service_span=None,
            quantity=None, price_span=None, tax=PreviewTaxChange(kind="tax", line_number=1,
                source_span=span(source, "НДС 5%"), mode="rate", rate_span=None,
                profile_span=None), description_span=None),
    )
    intent = extract(source, changes)
    assert len(intent.draft_mutations) == 3
    assert {change.target for change in intent.draft_mutations} == {"Пункт 1"}
    assert [change.quantity for change in intent.draft_mutations if change.quantity is not None] == [3]
    assert [change.price for change in intent.draft_mutations if change.price is not None] == [150]
    assert [change.tax.rate for change in intent.draft_mutations if change.tax is not None] == [5]


def test_rename_cannot_become_catalog_service_replacement():
    source = "Услугу Tax Filing Service переименуй в Tax Return Preparation, Payroll Service удали"
    changes = (
        DraftLineChange(kind="replace", target_span=span(source, "Tax Filing Service"),
            service_span=span(source, "Tax Return Preparation"), quantity=None,
            price_span=None, tax=None, description_span=None),
        DraftLineChange(kind="delete", target_span=span(source, "Payroll Service"),
            service_span=None, quantity=None, price_span=None, tax=None,
            description_span=None),
    )
    intent = extract(source, changes)
    assert intent.draft_mutations[0].kind == "update"
    assert intent.draft_mutations[0].target == "Tax Filing Service"
    assert intent.draft_mutations[0].description == "Tax Return Preparation"
    assert intent.draft_mutations[0].service is None
    assert intent.draft_mutations[1].kind == "delete"
