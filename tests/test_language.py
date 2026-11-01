from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.domain import UserProblem
from app.language import LanguageIntent, SourceSpan


def patch(*lines):
    return LanguageIntent.model_validate({"action": "edit", "client_change": None,
        "date_change": None, "period_change": None, "line_changes": tuple(lines),
        "tax_change": None, "previous_hint_request": None, "clarification": None})


def test_source_span_preserves_actual_inflection_and_spaces():
    assert SourceSpan(first_word=2, last_word=3).text("Добавь юридическую  консультацию.") == "юридическую  консультацию"


@pytest.mark.parametrize("start,end", [(0, 1), (3, 2), (True, 2), ("1", 2)])
def test_invalid_word_indexes_are_rejected(start, end):
    with pytest.raises(ValidationError):
        SourceSpan(first_word=start, last_word=end)


def test_missing_source_words_fail_closed():
    with pytest.raises(UserProblem):
        SourceSpan(first_word=1, last_word=3).text("два слова")


def test_quantity_patch_changes_only_targeted_quantity():
    result = patch({"kind": "quantity", "line_number": 2,
        "quantity": {"source_span": {"first_word": 6, "last_word": 6}, "value": Decimal("2")}}
    ).to_intent("Во второй строке поставь количество два")
    assert result.line_number == 2 and result.quantity == 2
    assert result.quantity_evidence == "два" and not result.services and result.client is None


def test_addition_cannot_target_an_existing_row():
    result = patch({"kind": "add", "line_number": 1, "quantity": None,
        "new_service_name": {"first_word": 2, "last_word": 3}}
    ).to_intent("Добавь юридическую консультацию")
    assert result.lines_mode == "add" and result.line_number is None
    assert result.services[0].query == "юридическую консультацию"


def test_quantity_patch_cannot_invent_service_or_price():
    base = {"kind": "quantity", "line_number": 2,
        "quantity": {"source_span": {"first_word": 1, "last_word": 1}, "value": Decimal("2")}}
    for extra in ({"price": 500}, {"new_service_name": {"first_word": 1, "last_word": 1}},
                  {"service_id": "invented"}):
        with pytest.raises(ValidationError):
            patch({**base, **extra})


def test_quantity_requires_grounding_words():
    with pytest.raises(ValidationError):
        patch({"kind": "quantity", "line_number": None, "quantity": {"value": Decimal("2")}})
