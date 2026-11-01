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
def flow(monkeypatch):
    fixture = FirstBitFixture()
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
    assert "устарело" in flow["sent"][-1]["text"]
    press(flow, current)
    assert "документ не создавался" in flow["sent"][-1]["text"]
    assert {r.method for r in flow["fixture"].calls} == {"GET"}


def test_ambiguous_row_and_unknown_tax_revoke_confirmation(flow):
    old = button(flow)
    text = "Цена 1500"
    send(flow, text, [price(text, "1500")])
    assert "номер строки" in flow["sent"][-1]["text"]
    assert not flow["client"].app.state.bot.pending
    press(flow, old)
    assert "устарело" in flow["sent"][-1]["text"]
    text = "В первой строке НДС 10%"
    send(flow, text, [tax(text, "10%", 1)])
    assert "Налоговый профиль не найден" in flow["sent"][-1]["text"]
    assert not flow["client"].app.state.bot.pending


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
    press(flow, data)
    assert "документ не создавался" not in flow["sent"][-1]["text"]
    assert not flow["client"].app.state.bot.pending


def test_foreign_currency_gross_price_and_wrong_financial_span_are_not_accepted(flow):
    for text, fragment in [("В первой строке цена 1500 долларов", "1500"),
                            ("В первой строке цена 1500 с НДС", "1500"),
                            ("Во 2 строке цена 1500, НДС 5%", "2")]:
        before = len(flow["fixture"].calls)
        send(flow, text, [price(text, fragment, 1)])
        assert not flow["client"].app.state.bot.pending
        assert len(flow["fixture"].calls) == before


def test_source_drift_preserves_explicit_values_but_requires_new_confirmation(flow):
    text = "В первой строке цена 1500"
    send(flow, text, [price(text, "1500", 1)])
    old = prepared(flow)
    source = flow["fixture"].records["Document_InventoryExpense"][0]
    source["Inventory"][0] = flow["fixture"].line(1, "1", "1100")
    source["DocumentAmount"] = "3255.00"
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
    send(flow, text, [tax(text, "0%", 1)])
    assert not flow["client"].app.state.bot.pending
    flow["fixture"].records["Catalog_VATRates"].remove(duplicate)
    send(flow, text, [tax(text, "0%", 1)])
    assert prepared(flow).preview.lines[0].tax.rate == 0
    zero["DeletionMark"] = True
    press(flow, button(flow))
    assert not flow["client"].app.state.bot.pending


def test_model_cannot_supply_price_or_ids_instead_of_source_spans(flow):
    for fabricated in ({"kind": "price", "line_number": 1, "price": "1500"},
                       {"kind": "description", "line_number": 1, "description_span": {"first_word": 1, "last_word": 1},
                        "service_id": ref(91)}):
        before = len(flow["fixture"].calls)
        send(flow, "Цена 1500", [fabricated])
        assert not flow["client"].app.state.bot.pending
        assert len(flow["fixture"].calls) == before


@pytest.mark.parametrize("text,row,kind", [("Цена 1500", 1, "price"),
    ("Во второй строке цена 1500", 1, "price"), ("Во второй строке НДС 0%", None, "tax")])
def test_model_cannot_invent_row_or_drop_explicit_tax_target(flow, text, row, kind):
    before = len(flow["fixture"].calls)
    change = price(text, "1500", row) if kind == "price" else tax(text, "0%", row)
    send(flow, text, [change])
    assert not flow["client"].app.state.bot.pending
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
    send(flow, text, [{"kind": "tax", "line_number": 1, "source_span": span(text, "цена 1500"),
        "mode": "without_tax", "rate_span": None, "profile_span": None}])
    assert not flow["client"].app.state.bot.pending
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
    before = len(flow["fixture"].calls)
    flow["outputs"].append({"action": "create", "client_change": None, "date_change": None,
        "period_change": None, "line_changes": [], "tax_change": None,
        "previous_hint_request": None, "clarification": None,
        "preview_changes": [price(text, "1500", 1)]})
    send(flow, text)
    if new_scope:
        assert not flow["client"].app.state.bot.pending
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
    send(flow, text, [tax(text, "0%", 1), tax(text, "5%", 1)])
    assert not flow["client"].app.state.bot.pending
    assert len(flow["fixture"].calls) == before


def test_explicit_final_rename_keeps_last_word_omitted_by_model_span(flow):
    text = "В первой строке назови услугу Бухгалтерское обслуживание за тестовый период"
    send(flow, text, [name(text, "Бухгалтерское обслуживание за тестовый", 1)])
    assert prepared(flow).preview.lines[0].description == "Бухгалтерское обслуживание за тестовый период"


def test_rename_literal_cannot_move_from_explicit_second_row_to_first(flow):
    text = "В первой строке цена 1500. Во второй строке назови услугу Новое обслуживание"
    before = len(flow["fixture"].calls)
    send(flow, text, [name(text, "цена 1500.", 1)])
    assert not flow["client"].app.state.bot.pending
    assert len(flow["fixture"].calls) == before
