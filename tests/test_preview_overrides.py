"""User money is decoded from spans; 1C remains authoritative for tax definitions."""
from collections import deque
from decimal import Decimal
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.domain import WorkflowFailure
from app.language import words
from app.main import create_app
from app.numbers import explicit_decimal
from scripts.firstbit_fixture import FirstBitFixture, ref


@pytest.mark.parametrize("text,value", [("1500", "1500"), ("1 500,50", "1500.50"),
    ("тысяча пятьсот", "1500"), ("две тысячи тридцать пять", "2035"),
    ("ноль запятая ноль пять", ".05"), ("пятьдесят", "50"), ("ноль", "0")])
def test_explicit_money_words_and_digits(text, value):
    assert explicit_decimal(text) == Decimal(value)


@pytest.mark.parametrize("text", ["-1", "NaN", "1e3", "1,500", "1500 1600", "двадцать десять",
    "ноль тысяч", "полторы тысячи", "1500.123", "10000000000000", "", "пять пять"])
def test_ambiguous_or_unsupported_money_fails_closed(text):
    from app.domain import UserProblem
    with pytest.raises(UserProblem):
        explicit_decimal(text)


def span(text, fragment):
    start = text.index(fragment)
    indexes = [i for i, word in enumerate(words(text), 1) if word.start() < start + len(fragment) and word.end() > start]
    return {"first_word": indexes[0], "last_word": indexes[-1]}


def price(text, fragment, row=None):
    return {"kind": "price", "line_number": row, "amount_span": span(text, fragment)}


def name(text, fragment, row=None):
    return {"kind": "description", "line_number": row, "description_span": span(text, fragment)}


def tax(text, fragment, row=None):
    return {"kind": "tax", "line_number": row, "source_span": span(text, "НДС " + fragment),
        "mode": "rate", "rate_span": span(text, fragment), "profile_span": None}


@pytest.fixture
def flow(monkeypatch, request):
    fixture = FirstBitFixture()
    from decimal import Decimal
    source = fixture.records["Document_InventoryExpense"][0]
    line_count = getattr(request, "param", 2)
    source["Inventory"] = [fixture.line(index, "1" if index != 2 else "2", "1000.00")
                            for index in range(1, line_count + 1)]
    payroll = {**fixture.records["Catalog_Items"][0], "Ref_Key": ref(15),
               "Description": "Payroll services", "Code": "SYN-015"}
    fixture.records["Catalog_Items"].append(payroll)
    payroll_line = fixture.line(99, "1", "250.00")
    payroll_line["Item_Key"] = ref(15)
    payroll_line["Content"] = "Payroll services"
    source["Inventory"].append(payroll_line)
    source["DocumentAmount"] = str(sum((Decimal(row["AmountTotal"]) for row in source["Inventory"]), Decimal(0)))
    for key, value in fixture.env().items():
        monkeypatch.setenv(key, value)
    vat = fixture.records["Catalog_VATRates"][0]
    fixture.records["Catalog_VATRates"].extend([
        {**vat, "Ref_Key": ref(13), "Description": "Synthetic zero", "Rate": "0"},
        {**vat, "Ref_Key": ref(14), "Description": "Synthetic exempt", "Rate": "0", "Exempt": True}])
    sent, outputs, ai_calls = [], deque(), []
    audio = b"OggS" + b"\0" * 24 + b"OpusHead" + b"\0" * 32
    controls = {"voice_text": ""}

    def telegram(request):
        if request.url.path.endswith("getFile"):
            return httpx.Response(200, json={"ok": True, "result": {"file_id": "f", "file_unique_id": "u",
                "file_size": len(audio), "file_path": "voice/fixture.oga"}})
        if "/file/bot" in request.url.path:
            return httpx.Response(200, content=audio)
        if request.url.path.endswith("answerCallbackQuery"):
            return httpx.Response(200, json={"ok": True, "result": True})
        assert request.url.path.endswith("sendMessage"), "PDF/mutation attempted"
        sent.append(json.loads(request.content))
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 1, "chat": {"id": 123}}})

    def ai(request):
        ai_calls.append(request)
        if request.url.path.endswith("transcriptions"):
            return httpx.Response(200, json={"text": controls["voice_text"], "logprobs": [{"token": "fixture", "logprob": -.01}]})
        context = json.loads(request.content)["input"][1]["content"]
        assert "Синтетика" not in context and "TEST-TRN" not in context and ref(8) not in context
        assert '"services":[]' in context
        payload = outputs.popleft()
        return httpx.Response(200, json={"status": "completed", "output": [{"type": "message", "role": "assistant",
            "status": "completed", "content": [{"type": "output_text", "text": json.dumps(payload)}]}]})

    settings = Settings(token="123:" + "x" * 32, webhook_secret="s" * 32, mode="firstbit_readonly",
        allowed_users=frozenset({123}), ai_mode="openai", openai_api_key="fixture", llm_model="fixture", stt_model="gpt-4o-mini-transcribe")
    app = create_app(settings, telegram_transport=httpx.MockTransport(telegram), ai_transport=httpx.MockTransport(ai),
                     firstbit_transport=httpx.MockTransport(fixture.respond))
    with TestClient(app) as client:
        client.headers["X-Telegram-Bot-Api-Secret-Token"] = "s" * 32
        state = {"client": client, "fixture": fixture, "sent": sent, "outputs": outputs,
                 "controls": controls, "calls": ai_calls, "number": 0}
        send(state, "Сформируй счёт для ООО Синтетика за сентябрь 2026")
        yield state


def send(flow, text, changes=None, *, voice=False, tax_change=None):
    flow["number"] += 1
    n = flow["number"]
    if changes is not None or tax_change is not None:
        flow["outputs"].append({"action": "edit", "client_change": None, "date_change": None,
            "period_change": None, "line_changes": [], "tax_change": tax_change,
            "previous_hint_request": None, "clarification": None, "preview_changes": changes or []})
    message = {"message_id": n, "from": {"id": 123, "is_bot": False}, "chat": {"id": 123, "type": "private"}}
    flow["controls"]["voice_text"] = text
    message.update({"voice": {"file_id": "f", "file_unique_id": "u", "duration": 5, "mime_type": "audio/ogg"}} if voice else {"text": text})
    assert flow["client"].post("/telegram/webhook", json={"update_id": n, "message": message}).status_code == 200


def source_quantity(text, fragment, value):
    return {"source_span": span(text, fragment), "value": value}


def test_existing_preview_prompt_uses_one_batch_contract():
    from app.language import LANGUAGE_PROMPT
    assert "For an EXISTING preview, put every requested line change in draft_changes" in LANGUAGE_PROMPT
    assert "For quantity-only changes use ONE entry with kind=quantity" not in LANGUAGE_PROMPT
    assert "All three belong in\ndraft_changes" in LANGUAGE_PROMPT


def draft_change(text, kind, *, target=None, service=None, quantity=None,
                 price_span=None, tax=None, description=None):
    return {"kind": kind,
            "target_span": span(text, target) if target else None,
            "service_span": span(text, service) if service else None,
            "quantity": source_quantity(text, quantity[0], quantity[1]) if quantity else None,
            "price_span": span(text, price_span) if price_span else None,
            "tax": tax,
            "description_span": span(text, description) if description else None}


def initial_line(text, service, quantity=None, price=None):
    return {"service_span": span(text, service),
        "quantity": {"source_span": span(text, quantity[0]), "value": quantity[1]} if quantity else None,
        "price_span": span(text, price) if price else None, "amount_span": None, "tax": None}


def send_draft_changes(flow, text, changes, *, voice=False):
    flow["outputs"].append({"action": "edit", "client_change": None, "date_change": None,
        "period_change": None, "line_changes": [], "tax_change": None,
        "previous_hint_request": None, "clarification": None, "preview_changes": [],
        "initial_lines": [], "draft_changes": changes})
    send(flow, text, voice=voice)


def press(flow, data):
    flow["number"] += 1
    n = flow["number"]
    assert flow["client"].post("/telegram/webhook", json={"update_id": n, "callback_query": {
        "id": str(n), "from": {"id": 123, "is_bot": False}, "message": {
            "message_id": 1, "chat": {"id": 123, "type": "private"}}, "data": data}}).status_code == 200


def button(flow):
    return flow["sent"][-1]["reply_markup"]["inline_keyboard"][0][0]["callback_data"]


def prepared(flow):
    return flow["client"].app.state.bot.pending[123].prepared


@pytest.mark.parametrize("voice", [False, True])
def test_price_tax_and_description_preserve_id_other_row_and_readonly_confirmation(flow, voice):
    original = prepared(flow)
    old_button = button(flow)
    text = "В первой строке цена тысяча пятьсот, НДС 0%, название Новое обслуживание"
    send(flow, text, [price(text, "тысяча пятьсот,", 1), tax(text, "0%", 1), name(text, "Новое обслуживание", 1)], voice=voice)
    edited = prepared(flow)
    assert edited.preview.lines[0].price == 1500 and edited.preview.lines[0].tax.rate == 0
    assert edited.preview.lines[0].description == "Новое обслуживание"
    assert edited.preview.lines[0].service_id == original.preview.lines[0].service_id
    assert edited.preview.lines[1] == original.preview.lines[1]
    assert edited.preview.total == 3600 and len(edited.preview.user_overrides) == 1
    assert edited.request.preview_source_id == ref(8)
    assert edited.request.preview_overrides[0].source_line_number == 1
    assert edited.operation_id == original.operation_id
    assert edited.preview.digest != original.preview.digest and edited.basis.revision != original.basis.revision
    assert "Изменено пользователем" in flow["sent"][-1]["text"]
    current = button(flow)
    press(flow, old_button)
    assert "последнем сообщении" in flow["sent"][-1]["text"]
    press(flow, current)
    assert "READ-ONLY" in flow["sent"][-1]["text"]
    assert {r.method for r in flow["fixture"].calls} == {"GET"}


@pytest.mark.parametrize("flow", [5], indirect=True)
@pytest.mark.parametrize("voice", [False, True])
def test_real_reported_multi_line_edit_returns_new_preview_and_invalidates_only_old_confirm(flow, voice):
    original = prepared(flow)
    old_button = button(flow)
    old_context = flow["client"].app.state.bot.contexts[123]
    text = "Строка 2 исправить на 4 штуки. Строка 3, строка 4 удалить."
    changes = [
        draft_change(text, "update", target="Строка 2", quantity=("4", 4)),
        draft_change(text, "delete", target="Строка 3"),
        draft_change(text, "delete", target="строка 4"),
    ]
    send_draft_changes(flow, text, changes, voice=voice)
    assert 123 in flow["client"].app.state.bot.pending, flow["sent"][-1]["text"]
    edited = prepared(flow)
    context = flow["client"].app.state.bot.contexts[123]
    assert [line.source_line_number for line in edited.preview.lines] == [1, 2, 5]
    assert [line.quantity for line in edited.preview.lines] == [1, 4, 1]
    assert [line.description for line in edited.preview.lines] == [
        "Bookkeeping synthetic row 1", "Bookkeeping synthetic row 2", "Bookkeeping synthetic row 5"]
    assert edited.preview.subtotal == 6000
    assert edited.preview.tax_amount == 300
    assert edited.preview.total == 6300
    assert edited.operation_id == original.operation_id
    assert edited.preview.digest != original.preview.digest
    assert context.line_ids == (old_context.line_ids[0], old_context.line_ids[1], old_context.line_ids[4])
    assert len(set(context.line_ids)) == 3
    assert [origin.source_line_number for origin in context.line_origins.values()] == [1, 2, 5]
    assert "Предварительный счёт" in flow["sent"][-1]["text"]
    assert "Всего без НДС: 6 000.00 AED" in flow["sent"][-1]["text"]
    current_button = button(flow)
    assert old_button != current_button
    press(flow, old_button)
    assert "последнем сообщении" in flow["sent"][-1]["text"]
    press(flow, current_button)
    assert "документ не создавался" in flow["sent"][-1]["text"]
    assert {request.method for request in flow["fixture"].calls} == {"GET"}


@pytest.mark.parametrize("flow", [5], indirect=True)
@pytest.mark.parametrize("legacy_quantity", [False, True])
def test_live_wording_applies_multi_item_batch_and_legacy_quantity(flow, legacy_quantity):
    original = prepared(flow)
    old_button = button(flow)
    text = "Удали второй пункт и третий пункт, а в пятом пункте поменяй количество на 5"
    operations = [
        draft_change(text, "delete", target="второй пункт"),
        draft_change(text, "delete", target="третий пункт")]
    if legacy_quantity:
        line_changes = [{"kind": "quantity", "line_number": 5, "quantity": source_quantity(text, "5", 5)}]
    else:
        line_changes = []
        operations.append(draft_change(text, "update", target="в пятом пункте", quantity=("5", 5)))
    flow["outputs"].append({"action": "edit", "client_change": None, "date_change": None,
        "period_change": None, "line_changes": line_changes, "tax_change": None,
        "previous_hint_request": None, "clarification": None, "preview_changes": [],
        "initial_lines": [], "draft_changes": operations})
    send(flow, text)
    edited = prepared(flow)
    context = flow["client"].app.state.bot.contexts[123]
    assert [line.source_line_number for line in edited.preview.lines] == [1, 4, 5]
    assert [line.quantity for line in edited.preview.lines] == [1, 1, 5]
    assert len(set(context.line_ids)) == 3
    assert edited.preview.subtotal == 7000
    assert edited.preview.tax_amount == 350
    assert edited.preview.total == 7350
    assert edited.request.client_id == original.request.client_id
    assert edited.preview.historical_proposal.contract_id == original.preview.historical_proposal.contract_id
    assert edited.operation_id == original.operation_id
    assert edited.preview.digest != original.preview.digest
    assert "Пункт 1." in flow["sent"][-1]["text"]
    assert "Строка 1" not in flow["sent"][-1]["text"]
    assert button(flow) != old_button
    press(flow, old_button)
    assert "последнем сообщении" in flow["sent"][-1]["text"]
    assert {request.method for request in flow["fixture"].calls} == {"GET"}


def test_edit_misclassified_as_initial_lines_recovers_existing_preview(flow):
    original = prepared(flow)
    old_confirmation = button(flow)
    service_name = original.preview.lines[0].description
    text = f"Сформируй счёт: пункт 1 {service_name} сделай 3 штуки по цене 1260 соответственно"
    flow["outputs"].append({"action": "edit", "client_change": None, "date_change": None,
        "period_change": None, "line_changes": [], "tax_change": None,
        "previous_hint_request": None, "clarification": None, "preview_changes": [],
        "initial_lines": [initial_line(text, service_name, ("3", 3), "1260")],
        "draft_changes": []})
    send(flow, text)
    updated = prepared(flow)
    assert updated.preview.lines[0].quantity == 3
    assert updated.preview.lines[0].service_id == original.preview.lines[0].service_id
    assert updated.preview.total != original.preview.total
    assert updated.request.client_id == original.request.client_id
    assert updated.preview.historical_proposal.contract_id == original.preview.historical_proposal.contract_id
    assert button(flow) != old_confirmation
    assert "Пункт 1." in flow["sent"][-1]["text"]
    request = json.loads(flow["calls"][-1].content)
    assert "draft_changes" in request["text"]["format"]["schema"]["properties"]


@pytest.mark.parametrize("text,quantity,target", [
    ("Пункт 1 услугу поставь 3 штуки по цене 1260", 3, "пункт 1"),
    ("Для пункта 2 количество 4 шт., цена 1260", 4, "пункта 2"),
])
def test_quantity_grounding_uses_quantity_marker_not_adjacent_price(text, quantity, target):
    from app.language import SourceSpan, grounded_quantity
    bad_span = span(text, "3 штуки по цене 1260") if quantity == 3 else span(text, "4 шт., цена 1260")
    assert grounded_quantity(text, SourceSpan(**bad_span), Decimal(quantity)) == Decimal(quantity)


@pytest.mark.parametrize("flow", [3], indirect=True)
def test_keep_named_items_and_remove_everything_else_is_one_preview_mutation(flow):
    original = prepared(flow)
    old_confirmation = button(flow)
    names = [line.description for line in original.preview.lines]
    text = f"Оставь {names[0]} и {names[1]}, остальные пункты удали"
    send_draft_changes(flow, text, [
        draft_change(text, "retain", target=names[0]),
        draft_change(text, "retain", target=names[1]),
    ])
    updated = prepared(flow)
    assert len(updated.preview.lines) == 2
    assert updated.preview.lines[0].service_id == original.preview.lines[0].service_id
    assert updated.preview.lines[1].description == names[1]
    assert button(flow) != old_confirmation


def test_ambiguous_keep_target_never_removes_unselected_items(flow):
    original = prepared(flow)
    old_confirmation = button(flow)
    text = "Оставь Bookkeeping synthetic, остальные удали"
    send_draft_changes(flow, text, [draft_change(text, "retain", target="Bookkeeping synthetic")])
    assert prepared(flow) == original
    assert flow["client"].app.state.bot.pending[123].token == old_confirmation.split(":")[-1]
    assert "несколькими строками" in flow["sent"][-1]["text"]


@pytest.mark.parametrize("flow", [1], indirect=True)
def test_service_target_tolerates_small_transcription_typo_but_preserves_identity(flow):
    original = prepared(flow)
    service_name = original.preview.lines[0].description
    typo = service_name.replace("synthetic", "synthetik")
    text = f"{typo} сделай 4 штуки"
    send_draft_changes(flow, text, [draft_change(text, "update", target=typo,
        quantity=("4", 4))])
    updated = prepared(flow)
    assert updated.preview.lines[0].service_id == original.preview.lines[0].service_id
    assert updated.preview.lines[0].quantity == 4


@pytest.mark.parametrize("flow", [3], indirect=True)
def test_batch_edit_delete_and_service_quantity_preserve_original_targets(flow):
    original = prepared(flow)
    text = "Пункт 2 исправь на 4 штуки, пункт 3 удали"
    send_draft_changes(flow, text, [
        draft_change(text, "update", target="Пункт 2", quantity=("4", 4)),
        draft_change(text, "delete", target="пункт 3"),
    ])
    updated = prepared(flow)
    assert len(updated.preview.lines) == len(original.preview.lines) - 1
    assert updated.preview.lines[1].quantity == 4
    assert updated.preview.total == updated.preview.subtotal + updated.preview.tax_amount


@pytest.mark.parametrize("flow", [4], indirect=True)
def test_natural_mixed_delete_and_two_quantities_survive_commas(flow):
    text = ("Смотри, нужно удалить пункт 2, пункт 3 поменять на 5 штук, "
            "а в пункте 1 поменять на 3 штуки, цены оставить прежними")
    original = prepared(flow)
    send_draft_changes(flow, text, [
        draft_change(text, "delete", target="пункт 2"),
        draft_change(text, "update", target="пункт 3",
            quantity=("5 штук, а в пункте 1 поменять на 3 штуки", 5)),
        draft_change(text, "update", target="пункте 1",
            quantity=("3 штуки, цены оставить прежними", 3)),
    ])
    updated = prepared(flow)
    assert [line.source_line_number for line in updated.preview.lines] == [1, 3, 4]
    assert [line.quantity for line in updated.preview.lines] == [3, 5, 1]
    assert updated.request.client_id == original.request.client_id
    assert updated.preview.historical_proposal.contract_id == original.preview.historical_proposal.contract_id
    assert updated.preview.total == updated.preview.subtotal + updated.preview.tax_amount


@pytest.mark.parametrize("flow", [3], indirect=True)
def test_natural_service_name_quantity_and_following_deletions(flow):
    original = prepared(flow)
    service_name = original.preview.lines[0].description
    text = (f"Смотри, услуга {service_name} поменяй на 3 штуки, "
            "пункт 2 удали, пункт 3 удали")
    send_draft_changes(flow, text, [
        draft_change(text, "update", target=service_name,
            quantity=("3 штуки, пункт 2 удали, пункт 3 удали", 3)),
        draft_change(text, "delete", target="пункт 2"),
        draft_change(text, "delete", target="пункт 3"),
    ])
    updated = prepared(flow)
    assert [line.source_line_number for line in updated.preview.lines] == [1]
    assert updated.preview.lines[0].service_id == original.preview.lines[0].service_id
    assert updated.preview.lines[0].quantity == 3


@pytest.mark.parametrize("text,fragment,expected", [
    ("Удали второй пункт, а в пятом пункте поменяй количество на 5", "5", 5),
    ("Удалить пункт 4 и изменить количество в строке номер 2 на 3", "3", 2),
    ("Delete item 7 and set quantity on item 5 to 2", "2", 5),
])
def test_legacy_quantity_target_grounding_accepts_item_wording(text, fragment, expected):
    from app.language import explicit_line_target
    quantity_word = next(word for word in words(text) if text[word.start():word.end()] == fragment)
    assert explicit_line_target(text, quantity_word.start()) == expected


def test_named_mixed_and_ordinal_targets_keep_current_line_identity(flow):
    original = prepared(flow)
    text = "У Bookkeeping synthetic row 1 количество 3, а у строки 2 (Bookkeeping synthetic row 2) сделай 5 штук."
    changes = [
        draft_change(text, "update", target="Bookkeeping synthetic row 1", quantity=("3", 3)),
        draft_change(text, "update", target="строки 2 (Bookkeeping synthetic row 2)", quantity=("5", 5)),
    ]
    send_draft_changes(flow, text, changes)
    updated = prepared(flow)
    assert [line.quantity for line in updated.preview.lines] == [3, 5]
    assert updated.preview.lines[0].source_line_number == 1
    assert updated.preview.lines[1].source_line_number == 2
    assert updated.preview.lines[0].description == "Bookkeeping synthetic row 1"
    assert updated.preview.lines[0].quantity == 3
    assert updated.preview.total == 8400
    assert updated.request.client_id == original.request.client_id
    assert updated.preview.issuer == original.preview.issuer


def test_add_and_replace_service_use_live_historical_basis_without_merging_rows(flow):
    before = prepared(flow)
    text = "Добавь Payroll services 2 штуки"
    send_draft_changes(flow, text, [draft_change(text, "add", service="Payroll services", quantity=("2", 2))])
    added = prepared(flow)
    assert not flow["client"].app.state.bot.contexts[123].command.initial_overrides
    assert len(flow["client"].app.state.bot.contexts[123].line_origins) == 3
    assert len(added.preview.lines) == 3
    assert [line.description for line in added.preview.lines] == [
        "Bookkeeping synthetic row 1", "Bookkeeping synthetic row 2", "Payroll services"]
    assert added.preview.lines[2].quantity == 2
    assert added.preview.total == before.preview.total + 525
    assert added.preview.lines[2].service_id == ref(15)
    assert added.operation_id == before.operation_id

    text = "Замени пункт 2 на Payroll services, количество 1"
    send_draft_changes(flow, text, [draft_change(text, "replace", target="пункт 2",
        service="Payroll services", quantity=("1", 1))])
    replaced = prepared(flow)
    assert len(replaced.preview.lines) == 3
    assert [line.description for line in replaced.preview.lines] == [
        "Bookkeeping synthetic row 1", "Payroll services", "Payroll services"], flow["sent"][-1]["text"]
    assert [line.quantity for line in replaced.preview.lines] == [1, 1, 2]
    assert replaced.preview.lines[1].service_id == ref(15)


@pytest.mark.parametrize("flow", [4], indirect=True)
def test_model_broad_targets_and_grouped_delete_apply_against_displayed_preview(flow):
    text = ("Пункт 1 поменять на 3 штуки, пункты 2 и 3 удали, "
            "пункт 4 поменять на 5 штук")
    send_draft_changes(flow, text, [
        draft_change(text, "update", target="Пункт 1 поменять на 3 штуки", quantity=("3", 3)),
        draft_change(text, "delete", target="пункты 2 и 3"),
        draft_change(text, "update", target="пункт 4 поменять на 5 штук", quantity=("5", 5)),
    ])
    updated = prepared(flow)
    assert [line.source_line_number for line in updated.preview.lines] == [1, 4]
    assert [line.quantity for line in updated.preview.lines] == [3, 5]
    assert updated.preview.total == updated.preview.subtotal + updated.preview.tax_amount


def test_add_service_with_explicit_quantity_price_and_tax_in_one_message(flow):
    text = "Добавь Payroll services 2 штуки по цене 150, НДС 0%"
    tax_request = {"kind": "tax", "line_number": None, "source_span": span(text, "НДС 0%"),
        "mode": "rate", "rate_span": span(text, "0%"), "profile_span": None}
    send_draft_changes(flow, text, [draft_change(text, "add", service="Payroll services",
        quantity=("2", 2), price_span="150", tax=tax_request)])
    added = prepared(flow)
    assert len(added.preview.lines) == 3, flow["sent"][-1]["text"]
    line = added.preview.lines[-1]
    assert line.quantity == 2 and line.price == 150 and line.tax.rate == 0
    assert line.total == 300


def test_replace_service_with_explicit_quantity_price_and_tax_in_one_message(flow):
    text = "Замени пункт 2 на Payroll services, количество 3, цена 150, НДС 0%"
    tax_request = {"kind": "tax", "line_number": None, "source_span": span(text, "НДС 0%"),
        "mode": "rate", "rate_span": span(text, "0%"), "profile_span": None}
    send_draft_changes(flow, text, [draft_change(text, "replace", target="пункт 2",
        service="Payroll services", quantity=("3", 3), price_span="150", tax=tax_request)])
    updated = prepared(flow)
    assert len(updated.preview.lines) == 2, flow["sent"][-1]["text"]
    line = updated.preview.lines[1]
    assert line.service_id == ref(15) and line.quantity == 3
    assert line.price == 150 and line.tax.rate == 0 and line.total == 450


def test_target_generic_service_noun_is_not_part_of_name(flow):
    name = prepared(flow).preview.lines[-1].description
    text = f"Услугу {name} сделай 3 штуки"
    send_draft_changes(flow, text, [draft_change(text, "update", target=f"Услугу {name}", quantity=("3", 3))])
    assert prepared(flow).preview.lines[-1].quantity == 3


def test_keep_only_ignores_redundant_delete_the_rest(flow):
    text = "Оставь только Bookkeeping synthetic row 1; остальные удали"
    send_draft_changes(flow, text, [
        draft_change(text, "retain", target="Bookkeeping synthetic row 1"),
        draft_change(text, "delete", target="остальные удали"),
    ])
    assert [line.description for line in prepared(flow).preview.lines] == ["Bookkeeping synthetic row 1"], flow["sent"][-1]["text"]


@pytest.mark.parametrize("flow", [4], indirect=True)
@pytest.mark.parametrize("voice", [False, True])
def test_actual_bot_uses_focused_editor_for_multi_action_text_and_voice(flow, voice):
    from types import SimpleNamespace
    from pydantic import SecretStr
    from app.ai import CommandInterpreter, PreviewEditRequest
    text = "Пункт 2 удали, пункт 3 поменяй на 5 штук, пункт 1 сделай 3 штуки"
    changes = [draft_change(text, "delete", target="Пункт 2"),
        draft_change(text, "update", target="пункт 3", quantity=("5", 5)),
        draft_change(text, "update", target="пункт 1", quantity=("3", 3))]
    async def parse(**kwargs):
        assert kwargs["text_format"] is PreviewEditRequest
        return SimpleNamespace(output_parsed=PreviewEditRequest.model_validate_json(json.dumps({
            "action": "edit", "draft_changes": changes, "clarification": None})))
    flow["client"].app.state.bot.interpreter = CommandInterpreter(api_key=SecretStr("synthetic"),
        model="gpt-5-mini", sdk_client=SimpleNamespace(responses=SimpleNamespace(parse=parse)),
        send_draft_context=False)
    send(flow, text, voice=voice)
    updated = prepared(flow)
    assert [line.source_line_number for line in updated.preview.lines] == [1, 3, 4]
    assert [line.quantity for line in updated.preview.lines] == [3, 5, 1]
    assert "Предварительный счёт" in flow["sent"][-1]["text"]


def test_price_tax_and_rename_can_be_one_grounded_mutation(flow):
    original = prepared(flow)
    text = "В первой строке цена 1200, НДС 0%, название Bookkeeping Q4 service"
    tax_change = {"kind": "tax", "line_number": None, "source_span": span(text, "НДС 0%"),
        "mode": "rate", "rate_span": span(text, "0%"), "profile_span": None}
    changes = [draft_change(text, "update", target="первой строке", price_span="1200",
        tax=tax_change, description="Bookkeeping Q4 service")]
    send_draft_changes(flow, text, changes)
    updated = prepared(flow)
    first, second = updated.preview.lines
    assert first.description == "Bookkeeping Q4 service"
    assert first.service_id == original.preview.lines[0].service_id
    assert first.price == 1200 and first.tax.rate == 0 and first.tax.treatment == "zero_rated"
    assert second == original.preview.lines[1]
    assert updated.preview.subtotal == 3200
    assert updated.preview.tax_amount == 100
    assert updated.preview.total == 3300


def test_repeated_edit_addresses_new_display_numbers_after_delete(flow):
    initial = prepared(flow)
    text = "Удали первую строку"
    send_draft_changes(flow, text, [draft_change(text, "delete", target="первую строку")])
    after_delete = prepared(flow)
    assert [line.source_line_number for line in after_delete.preview.lines] == [2]
    assert after_delete.preview.lines[0].quantity == initial.preview.lines[1].quantity
    text = "Теперь строку 1 поставь 4 штуки"
    send_draft_changes(flow, text, [draft_change(text, "update", target="строку 1", quantity=("4", 4))])
    after_update = prepared(flow)
    assert len(after_update.preview.lines) == 1
    assert after_update.preview.lines[0].source_line_number == 2
    assert after_update.preview.lines[0].quantity == 4
    assert after_update.operation_id == initial.operation_id
    assert after_update.preview.digest != after_delete.preview.digest


def test_ambiguous_part_is_reported_but_clear_operations_apply_and_context_survives(flow):
    old_button = button(flow)
    old = prepared(flow)
    text = "У второй строки количество 4, AML services удали."
    changes = [
        draft_change(text, "update", target="второй строки", quantity=("4", 4)),
        draft_change(text, "delete", target="AML services"),
    ]
    send_draft_changes(flow, text, changes)
    updated = prepared(flow)
    assert updated.preview.lines[1].quantity == 4
    assert len(updated.preview.lines) == 2
    assert updated.request.client_id == old.request.client_id
    assert updated.preview.historical_proposal.contract_id == old.preview.historical_proposal.contract_id
    assert "Применил однозначные правки" in flow["sent"][-1]["text"]
    assert "не нашёл услугу" in flow["sent"][-1]["text"]
    assert button(flow) != old_button


def test_ambiguous_target_only_preserves_preview_and_confirmation(flow):
    old_button = button(flow)
    old = prepared(flow)
    text = "У bookkeeping поставь 4 штуки"
    send_draft_changes(flow, text, [draft_change(text, "update", target="bookkeeping", quantity=("4", 4))])
    assert prepared(flow) == old
    assert flow["client"].app.state.bot.pending[123].token == old_button.split(":")[-1]
    press(flow, old_button)
    assert "READ-ONLY" in flow["sent"][-1]["text"]


def test_ambiguous_row_and_unknown_tax_preserve_confirmation(flow):
    old = button(flow)
    token = old.split(":")[-1]
    text = "Цена 1500"
    send(flow, text, [price(text, "1500")])
    assert "номер строки" in flow["sent"][-1]["text"]
    assert flow["client"].app.state.bot.pending[123].token == token
    text = "В первой строке НДС 10%"
    send(flow, text, [tax(text, "10%", 1)])
    assert "Налоговый профиль не найден" in flow["sent"][-1]["text"]
    assert flow["client"].app.state.bot.pending[123].token == token


def test_exempt_is_catalog_profile_and_differs_from_zero_rate(flow):
    text = "Поставь без НДС"
    send(flow, text, tax_change={"source_span": span(text, "без НДС"), "mode": "without_tax", "profile_span": None})
    p = prepared(flow)
    assert p.preview.tax_amount == 0 and p.preview.total == 3000
    assert all(l.tax.tax_id == ref(14) and l.tax.treatment == "exempt" for l in p.preview.lines)


@pytest.mark.parametrize("kind", ["source", "row", "invalid_source_money"])
def test_refresh_never_rebinds_or_repairs_historical_source(flow, kind):
    text = "В первой строке цена 1500"
    send(flow, text, [price(text, "1500", 1)])
    data = button(flow)
    source = flow["fixture"].records["Document_InventoryExpense"][0]
    if kind == "source":
        source["Ref_Key"] = ref(91)
    elif kind == "row":
        source["Inventory"][0]["LineNumber"] = 9
    else:
        source["Inventory"][0]["Price"] = "999"
    if kind == "invalid_source_money":
        from decimal import Decimal
        source["Inventory"][0]["Amount"] = "999.00"
        source["Inventory"][0]["AmountTotal"] = "1048.95"
    if kind != "source":
        from decimal import Decimal
        source["DocumentAmount"] = str(sum((Decimal(row["AmountTotal"]) for row in source["Inventory"]), Decimal(0)))
    press(flow, data)
    assert "документ не создавался" not in flow["sent"][-1]["text"]
    assert not flow["client"].app.state.bot.pending


def test_foreign_currency_gross_price_and_wrong_financial_span_are_not_accepted(flow):
    for text, fragment in [("В первой строке цена 1500 долларов", "1500"),
                            ("В первой строке цена 1500 с НДС", "1500"),
                            ("Во 2 строке цена 1500, НДС 5%", "2")]:
        before = len(flow["fixture"].calls)
        token = flow["client"].app.state.bot.pending[123].token
        send(flow, text, [price(text, fragment, 1)])
        assert flow["client"].app.state.bot.pending[123].token == token
        assert len(flow["fixture"].calls) == before


def test_source_drift_preserves_explicit_values_but_requires_new_confirmation(flow):
    text = "В первой строке цена 1500"
    send(flow, text, [price(text, "1500", 1)])
    old = prepared(flow)
    source = flow["fixture"].records["Document_InventoryExpense"][0]
    source["Inventory"][0] = flow["fixture"].line(1, "1", "1100")
    from decimal import Decimal
    source["DocumentAmount"] = str(sum((Decimal(row["AmountTotal"]) for row in source["Inventory"]), Decimal(0)))
    press(flow, button(flow))
    updated = prepared(flow)
    assert updated.preview.lines[0].price == 1500
    assert updated.basis.revision != old.basis.revision
    assert "Данные 1С изменились" in flow["sent"][-1]["text"]


def test_manual_edits_cannot_execute_even_if_caller_enables_writes(flow):
    import asyncio
    from app.service import InvoiceService
    text = "В первой строке цена 1500"
    send(flow, text, [price(text, "1500", 1)])
    p = prepared(flow)
    backend = flow["client"].app.state.bot.service.onec
    async def scenario():
        with pytest.raises(WorkflowFailure) as exc:
            await InvoiceService(backend, allow_real_writes=True).execute(p, "blocked", 123)
        assert exc.value.stage == "write_disabled"
    before = len(flow["fixture"].calls)
    asyncio.run(scenario())
    assert len(flow["fixture"].calls) == before


def test_manual_fields_survive_date_and_quantity_edits(flow):
    text = "В первой строке цена 1500, НДС 0%, название Новое обслуживание"
    send(flow, text, [price(text, "1500,", 1), tax(text, "0%", 1), name(text, "Новое обслуживание", 1)])
    original = prepared(flow)
    text = "Поставь дату на 5 ноября 2026"
    flow["outputs"].append({"action": "edit", "client_change": None,
        "date_change": {"source_span": span(text, "5 ноября 2026"), "day": 5, "month": 11, "year": 2026},
        "period_change": None, "line_changes": [], "tax_change": None,
        "previous_hint_request": None, "clarification": None})
    send(flow, text)
    assert str(prepared(flow).preview.invoice_date) == "2026-11-05"
    assert prepared(flow).preview.user_overrides == original.preview.user_overrides
    text = "В первой строке количество 2"
    flow["outputs"].append({"action": "edit", "client_change": None, "date_change": None,
        "period_change": None, "line_changes": [{"kind": "quantity", "line_number": 1,
            "quantity": {"source_span": span(text, "2"), "value": "2"}}], "tax_change": None,
        "previous_hint_request": None, "clarification": None})
    send(flow, text)
    result = prepared(flow)
    assert result.preview.lines[0].subtotal == 3000
    assert result.preview.user_overrides == original.preview.user_overrides
    assert result.preview.lines[0].service_id == original.preview.lines[0].service_id


def test_ambiguous_tax_catalog_and_deleted_tax_on_refresh_fail_closed(flow):
    zero = flow["fixture"].records["Catalog_VATRates"][1]
    duplicate = {**zero, "Ref_Key": ref(15)}
    flow["fixture"].records["Catalog_VATRates"].append(duplicate)
    text = "В первой строке НДС 0%"
    token = flow["client"].app.state.bot.pending[123].token
    send(flow, text, [tax(text, "0%", 1)])
    assert flow["client"].app.state.bot.pending[123].token == token
    flow["fixture"].records["Catalog_VATRates"].remove(duplicate)
    send(flow, text, [tax(text, "0%", 1)])
    assert prepared(flow).preview.lines[0].tax.rate == 0
    zero["DeletionMark"] = True
    press(flow, button(flow))
    assert not flow["client"].app.state.bot.pending


def test_model_cannot_supply_price_or_ids_instead_of_source_spans(flow):
    token = flow["client"].app.state.bot.pending[123].token
    for fabricated in ({"kind": "price", "line_number": 1, "price": "1500"},
                       {"kind": "description", "line_number": 1, "description_span": {"first_word": 1, "last_word": 1},
                        "service_id": ref(91)}):
        before = len(flow["fixture"].calls)
        send(flow, "Цена 1500", [fabricated])
        assert flow["client"].app.state.bot.pending[123].token == token
        assert len(flow["fixture"].calls) == before


@pytest.mark.parametrize("text,row,kind", [("Цена 1500", 1, "price"),
    ("Во второй строке цена 1500", 1, "price"), ("Во второй строке НДС 0%", None, "tax")])
def test_model_cannot_invent_row_or_drop_explicit_tax_target(flow, text, row, kind):
    before = len(flow["fixture"].calls)
    token = flow["client"].app.state.bot.pending[123].token
    change = price(text, "1500", row) if kind == "price" else tax(text, "0%", row)
    send(flow, text, [change])
    assert flow["client"].app.state.bot.pending[123].token == token
    assert len(flow["fixture"].calls) == before


def test_duplicate_model_catalog_addition_is_only_display_rename(flow):
    text = "В первой строке цена 1500, назови услугу Новое обслуживание"
    flow["outputs"].append({"action": "edit", "client_change": None, "date_change": None,
        "period_change": None, "line_changes": [{"kind": "add", "line_number": None,
            "new_service_name": span(text, "Новое обслуживание"), "quantity": None}], "tax_change": None,
        "previous_hint_request": None, "clarification": None,
        "preview_changes": [price(text, "1500,", 1), name(text, "Новое обслуживание", 1)]})
    before = prepared(flow)
    send(flow, text)
    after = prepared(flow)
    assert len(after.preview.lines) == len(before.preview.lines) == 2
    assert after.preview.lines[0].description == "Новое обслуживание"
    assert after.preview.lines[0].service_id == before.preview.lines[0].service_id


def test_model_cannot_invent_tax_mode_without_tax_evidence(flow):
    text = "В первой строке цена 1500"
    before = len(flow["fixture"].calls)
    token = flow["client"].app.state.bot.pending[123].token
    send(flow, text, [{"kind": "tax", "line_number": 1, "source_span": span(text, "цена 1500"),
        "mode": "without_tax", "rate_span": None, "profile_span": None}])
    assert flow["client"].app.state.bot.pending[123].token == token
    assert len(flow["fixture"].calls) == before


def test_fake_manual_proposal_is_also_non_executable():
    import asyncio
    from app.domain import InvoiceCommand, PreviewLineOverride
    from app.fake_onec import FakeOneC
    from app.service import InvoiceService
    async def scenario():
        backend = FakeOneC()
        service = InvoiceService(backend, allow_real_writes=True)
        command = InvoiceCommand(client="ООО Ромашка", year=2026, month=9)
        old = await service.prepare(command, "test", 123)
        edit = InvoiceCommand(**{**command.model_dump(), "preview_overrides": (
            PreviewLineOverride(line_number=1, price=Decimal("1500"), description="Новое обслуживание"),)})
        new = await service.prepare(edit, "test", 123, existing=old, old_command=command)
        assert new.operation_id == old.operation_id and new.preview.lines[0].price == 1500
        assert (await service.refresh(new, "test", 123)).preview.digest == new.preview.digest
        with pytest.raises(WorkflowFailure) as exc:
            await service.execute(new, "test", 123)
        assert exc.value.stage == "write_disabled" and not backend.documents
    asyncio.run(scenario())


def test_legacy_model_label_cannot_turn_explicit_zero_percent_into_exempt_or_drop_row(flow):
    text = "Во второй строке НДС ноль процентов"
    send(flow, text, tax_change={"source_span": span(text, "НДС ноль процентов"),
        "mode": "without_tax", "profile_span": None})
    result = prepared(flow)
    assert result.preview.lines[0].tax.rate == 5
    assert result.preview.lines[1].tax.rate == 0
    assert result.preview.lines[1].tax.treatment == "zero_rated"


def test_model_tax_label_is_normalized_from_literal_percentage_and_rename_prefix_is_removed(flow):
    text = "В первой строке НДС ноль процентов, Назови услугу «Новое обслуживание»"
    send(flow, text, [{"kind": "tax", "line_number": 1, "source_span": span(text, "НДС ноль процентов,"),
        "mode": "without_tax", "rate_span": None, "profile_span": None},
        name(text, "Назови услугу «Новое обслуживание»", 1)])
    result = prepared(flow)
    assert result.preview.lines[0].tax.treatment == "zero_rated"
    assert result.preview.lines[0].description == "Новое обслуживание"


@pytest.mark.parametrize("new_scope", [False, True])
def test_model_create_label_on_field_patch_is_repaired_only_for_existing_scope(flow, new_scope):
    text = ("Создай новый счёт, " if new_scope else "") + "В первой строке цена 1500"
    old = button(flow)
    token = old.split(":")[-1]
    before = len(flow["fixture"].calls)
    flow["outputs"].append({"action": "create", "client_change": None, "date_change": None,
        "period_change": None, "line_changes": [], "tax_change": None,
        "previous_hint_request": None, "clarification": None,
        "preview_changes": [price(text, "1500", 1)]})
    send(flow, text)
    if new_scope:
        assert flow["client"].app.state.bot.pending[123].token == token
        assert len(flow["fixture"].calls) == before
    else:
        assert prepared(flow).preview.lines[0].price == 1500
        assert button(flow) != old


def test_legacy_rename_and_duplicate_identical_tax_are_one_grounded_patch(flow):
    text = "В первой строке цена 1500, НДС 0%, назови услугу Новое обслуживание"
    flow["outputs"].append({"action": "create", "client_change": None, "date_change": None,
        "period_change": None, "line_changes": [{"kind": "add", "line_number": None,
            "new_service_name": span(text, "Новое обслуживание"), "quantity": None}],
        "tax_change": {"source_span": span(text, "НДС 0%,"), "mode": "profile", "profile_span": span(text, "0%,")},
        "previous_hint_request": None, "clarification": None,
        "preview_changes": [price(text, "1500,", 1), tax(text, "0%,", 1)]})
    original = prepared(flow)
    send(flow, text)
    result = prepared(flow)
    assert result.preview.lines[0].price == 1500 and result.preview.lines[0].tax.rate == 0
    assert result.preview.lines[0].description == "Новое обслуживание"
    assert result.preview.lines[0].service_id == original.preview.lines[0].service_id
    assert result.preview.lines[1] == original.preview.lines[1]
    assert len(result.preview.user_overrides) == 1


def test_different_tax_values_in_one_message_still_fail_closed(flow):
    text = "В первой строке НДС 0% и НДС 5%"
    before = len(flow["fixture"].calls)
    token = flow["client"].app.state.bot.pending[123].token
    send(flow, text, [tax(text, "0%", 1), tax(text, "5%", 1)])
    assert flow["client"].app.state.bot.pending[123].token == token
    assert len(flow["fixture"].calls) == before


def test_explicit_final_rename_keeps_last_word_omitted_by_model_span(flow):
    text = "В первой строке назови услугу Бухгалтерское обслуживание за тестовый период"
    send(flow, text, [name(text, "Бухгалтерское обслуживание за тестовый", 1)])
    assert prepared(flow).preview.lines[0].description == "Бухгалтерское обслуживание за тестовый период"


def test_rename_literal_cannot_move_from_explicit_second_row_to_first(flow):
    text = "В первой строке цена 1500. Во второй строке назови услугу Новое обслуживание"
    before = len(flow["fixture"].calls)
    token = flow["client"].app.state.bot.pending[123].token
    send(flow, text, [name(text, "цена 1500.", 1)])
    assert flow["client"].app.state.bot.pending[123].token == token
    assert len(flow["fixture"].calls) == before
