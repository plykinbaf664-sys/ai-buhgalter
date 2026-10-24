"""Public webhook workflow. Telegram/STT/LLM are mocked; fake 1C remains real code."""
import json
import secrets
from collections import deque
from datetime import date
from decimal import Decimal

import httpx
import pymupdf
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.domain import OperationState
from app.fake_onec import FakeOneC
from app.intent import CalendarInput, InvoiceIntent, IntentService as ServiceSelection, PeriodInput, PreviousInput, TaxInput
from app.main import create_app
from app.language import LanguageIntent, words

TEXT = "Сформируй счёт для ООО Ромашка на 1 октября 2026 за бухгалтерское обслуживание с НДС"
AUDIO = b"OggS" + b"\x00" * 24 + b"OpusHead" + b"\x00" * 32


def language_payload(value, source):
    def span(fragment):
        if fragment is None:
            return None
        start = source.casefold().index(fragment.casefold())
        end = start + len(fragment)
        indexes = [i for i, token in enumerate(words(source), 1) if token.start() < end and token.end() > start]
        return {"first_word": indexes[0], "last_word": indexes[-1]}
    day, period, tax, previous = value.invoice_date, value.service_period, value.tax, value.previous
    return LanguageIntent.model_validate({"action": value.action, "client_change": span(value.client),
        "date_change": {"source_span": span(day.evidence), "day": day.day, "month": day.month, "year": day.year} if day else None,
        "period_change": {"source_span": span(period.evidence), "month": period.month, "year": period.year} if period else None,
        "tax_change": {"source_span": span(tax.evidence), "mode": tax.mode, "profile_span": span(tax.query)} if tax else None,
        "previous_hint_request": {"source_span": span(previous.evidence), "kind": previous.kind} if previous else None,
        "line_changes": tuple({"kind": value.lines_mode, "new_service_name": span(s.query),
            "line_number": value.line_number, "quantity": {"value": s.quantity,
            "source_span": span(s.quantity_evidence)} if s.quantity is not None else None} for s in value.services),
        "clarification": value.clarification, **({"line_changes": ({"kind": "quantity", "line_number": value.line_number,
            "quantity": {"source_span": span(value.quantity_evidence), "value": value.quantity}},)}
            if value.quantity is not None else {})})


def intent(**changes):
    return InvoiceIntent.model_validate({"action": "edit", "client": None, "invoice_date": None,
        "service_period": None, "services": (), "lines_mode": "keep", "tax": None,
        "previous": None, "clarification": None, **changes})


def initial():
    return intent(action="create", client="ООО Ромашка",
        invoice_date=CalendarInput(day=1, month=10, year=2026, evidence="1 октября 2026"),
        services=(ServiceSelection(query="бухгалтерское обслуживание"),), lines_mode="replace",
        tax=TaxInput(mode="with_tax", query=None, evidence="с НДС"))


@pytest.fixture
def workflow():
    settings = Settings(token="123:" + secrets.token_urlsafe(32), webhook_secret=secrets.token_urlsafe(32),
        allowed_users=frozenset({123}), ai_mode="openai", openai_api_key=secrets.token_urlsafe(32),
        llm_model="test-model", stt_model="gpt-4o-mini-transcribe")
    controls = {"text": TEXT, "fail": None, "telegram_fail": False}
    outputs, sent, ai_calls = deque(), [], []
    backend = FakeOneC()

    def telegram(request):
        if request.url.path.endswith("getFile"):
            return httpx.Response(200, json={"ok": True, "result": {"file_id": "f", "file_unique_id": "u",
                "file_path": "voice/a.oga", "file_size": len(AUDIO)}})
        if "/file/bot" in request.url.path:
            return httpx.Response(200, content=AUDIO)
        if request.url.path.endswith("answerCallbackQuery"):
            return httpx.Response(200, json={"ok": True, "result": True})
        sent.append(request)
        if controls["telegram_fail"]:
            controls["telegram_fail"] = False
            raise httpx.ReadTimeout("SECRET", request=request)
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 1, "chat": {"id": 123}}})

    def ai(request):
        ai_calls.append(request)
        if controls["fail"]:
            return httpx.Response(controls["fail"])
        if request.url.path.endswith("transcriptions"):
            return httpx.Response(200, json={"text": controls["text"], "logprobs": [{"token": "test", "logprob": -.1}]})
        value = outputs.popleft()
        payload = language_payload(value, controls["text"]).model_dump_json() if isinstance(value, InvoiceIntent) else json.dumps(value)
        return httpx.Response(200, json={"status": "completed", "output": [{"type": "message", "role": "assistant",
            "status": "completed", "content": [{"type": "output_text", "text": payload}]}]})

    app = create_app(settings, backend=backend, telegram_transport=httpx.MockTransport(telegram),
                     ai_transport=httpx.MockTransport(ai))
    with TestClient(app) as client:
        client.headers["X-Telegram-Bot-Api-Secret-Token"] = settings.webhook_secret.get_secret_value()
        yield client, backend, outputs, sent, controls, ai_calls


def send(w, text, result=None, number=1, *, voice=False):
    client, _, outputs, _, controls, _ = w
    if result is not None:
        outputs.append(result)
    controls["text"] = text
    message = {"message_id": number, "from": {"id": 123, "is_bot": False}, "chat": {"id": 123, "type": "private"}}
    if voice:
        message["voice"] = {"file_id": "f", "file_unique_id": "u", "duration": 5,
                            "mime_type": "audio/ogg", "file_size": len(AUDIO)}
    else:
        message["text"] = text
    return client.post("/telegram/webhook", json={"update_id": number, "message": message})


def prompt(w):
    return json.loads(w[3][-1].content)


def token(w, action="confirm"):
    return next(b["callback_data"] for row in prompt(w)["reply_markup"]["inline_keyboard"] for b in row
                if f":{action}:" in b["callback_data"])


def press(w, data, number=100):
    return w[0].post("/telegram/webhook", json={"update_id": number, "callback_query": {
        "id": str(number), "from": {"id": 123, "is_bot": False}, "message": {
            "message_id": 1, "chat": {"id": 123, "type": "private"}}, "data": data}})


def preview(w):
    return w[0].app.state.bot.pending[123].prepared.preview


def pdf_text(w):
    body = next(request.content for request in reversed(w[3]) if request.url.path.endswith("sendDocument"))
    data = body[body.index(b"%PDF-"):body.rindex(b"%%EOF") + 5]
    with pymupdf.open(stream=data, filetype="pdf") as document:
        return "\n".join(page.get_text() for page in document)


@pytest.mark.parametrize("voice", [False, True])
def test_text_and_voice_only_prepare_full_preview(workflow, voice):
    assert send(workflow, TEXT, initial(), voice=voice).status_code == 200
    assert not workflow[1].documents
    assert preview(workflow).invoice_date == date(2026, 10, 1)
    assert preview(workflow).service_period is None
    assert preview(workflow).total == Decimal("1050.00")
    assert "Дата счёта: 01.10.2026" in prompt(workflow)["text"]
    assert "1 050.00 AED" in prompt(workflow)["text"]
    assert press(workflow, token(workflow)).status_code == 200
    assert len(workflow[1].documents) == 1
    pdf = pdf_text(workflow)
    assert "ООО Ромашка" in pdf and "01.10.2026" in pdf and "1 050.00" in pdf and "TEST / MOCK" in pdf


def test_sequential_short_edits_keep_context_and_rotate_confirmation(workflow):
    send(workflow, TEXT, initial())
    original = token(workflow)
    send(workflow, "Дату поменяй на пятое", intent(invoice_date=CalendarInput(day=5, month=None, year=None, evidence="пятое")), 2)
    assert preview(workflow).invoice_date == date(2026, 10, 5)
    send(workflow, "Поставь без НДС", intent(tax=TaxInput(mode="without_tax", query=None, evidence="без НДС")), 3)
    assert preview(workflow).tax_amount == 0
    send(workflow, "Количество два", intent(quantity=Decimal("2"), quantity_evidence="два"), 4, voice=True)
    assert preview(workflow).lines[0].quantity == 2
    send(workflow, "Замени услугу на юридическую консультацию", intent(lines_mode="replace",
        services=(ServiceSelection(query="юридическую консультацию"),)), 5)
    send(workflow, "Добавь налоговую консультацию, количество два", intent(lines_mode="add",
        services=(ServiceSelection(query="налоговую консультацию", quantity=Decimal("2"), quantity_evidence="два"),)), 6)
    current = token(workflow)
    assert preview(workflow).lines[0].quantity == 2
    assert preview(workflow).total == Decimal("1600.00")
    assert len(preview(workflow).lines) == 2 and not workflow[1].documents
    assert press(workflow, original, 100).status_code == 200
    assert not workflow[1].documents
    assert press(workflow, current, 101).status_code == 200
    assert press(workflow, current, 102).status_code == 200
    assert len(workflow[1].documents) == 1
    assert sum(request.url.path.endswith("sendDocument") for request in workflow[3]) == 1
    pdf = pdf_text(workflow)
    assert "05.10.2026" in pdf and "Legal consultation" in pdf and "Tax consultation" in pdf and "1 600.00" in pdf


def test_ambiguous_added_service_preserves_other_lines_on_clarification(workflow):
    send(workflow, TEXT, initial())
    old = token(workflow)
    send(workflow, "Добавь ещё консультацию", intent(lines_mode="add", services=(ServiceSelection(query="консультацию"),)), 2)
    assert "Уточните услугу" in prompt(workflow)["text"]
    assert press(workflow, old).status_code == 200 and not workflow[1].documents
    send(workflow, "Юридическую консультацию", intent(lines_mode="replace", services=(ServiceSelection(query="Юридическую консультацию"),)), 3)
    assert [line.service_id for line in preview(workflow).lines] == ["service-accounting", "service-legal"]
    assert preview(workflow).total == Decimal("1575.00")


@pytest.mark.parametrize("mode", ["button", "text", "voice"])
def test_cancel_does_not_create_document(workflow, mode):
    send(workflow, TEXT, initial())
    confirm = token(workflow)
    if mode == "button":
        press(workflow, token(workflow, "cancel"))
    else:
        send(workflow, "Отмени этот запрос", intent(action="cancel"), 2, voice=mode == "voice")
    assert "отменена" in prompt(workflow)["text"]
    press(workflow, confirm, 101)
    assert not workflow[1].documents


def test_edit_button_keeps_draft_and_revokes_confirmation(workflow):
    send(workflow, TEXT, initial())
    confirm = token(workflow)
    press(workflow, token(workflow, "edit"))
    press(workflow, confirm, 101)
    assert not workflow[1].documents
    send(workflow, "Теперь без налога", intent(tax=TaxInput(mode="without_tax", query=None, evidence="без налога")), 2)
    assert preview(workflow).total == 1000


def test_missing_client_is_the_only_question_and_date_is_preserved(workflow):
    send(workflow, "Счёт на 1 октября 2026 с НДС", intent(action="create",
        invoice_date=CalendarInput(day=1, month=10, year=2026, evidence="1 октября 2026"),
        tax=TaxInput(mode="with_tax", query=None, evidence="с НДС")))
    assert "Укажите компанию" in prompt(workflow)["text"]
    send(workflow, "ООО Ромашка", intent(client="ООО Ромашка"), 2)
    assert preview(workflow).invoice_date == date(2026, 10, 1) and preview(workflow).total == 1050


def test_partial_date_clarification_preserves_month_and_year(workflow):
    send(workflow, "Счёт ООО Ромашка на октябрь 2026", intent(action="clarify", client="ООО Ромашка",
        invoice_date=CalendarInput(day=None, month=10, year=2026, evidence="октябрь 2026"), clarification="date"))
    send(workflow, "На пятое", intent(invoice_date=CalendarInput(day=5, month=None, year=None, evidence="пятое")), 2)
    assert preview(workflow).invoice_date == date(2026, 10, 5)


@pytest.mark.parametrize("tax", [None, "with_tax", "without_tax"])
def test_previous_invoice_is_hint_and_uses_current_catalog_prices(workflow, tax):
    backend = workflow[1]
    backend.services["service-accounting"] = backend.services["service-accounting"].model_copy(update={"price": Decimal("1200.00")})
    text = "Счёт ООО Ромашка как в прошлом месяце на 1 октября 2026" + (" с НДС" if tax == "with_tax" else " без НДС" if tax else "")
    send(workflow, text, intent(action="create", client="ООО Ромашка",
        invoice_date=CalendarInput(day=1, month=10, year=2026, evidence="1 октября 2026"),
        previous=PreviousInput(kind="previous_month", evidence="как в прошлом месяце"),
        tax=TaxInput(mode=tax, query=None, evidence="с НДС" if tax == "with_tax" else "без НДС") if tax else None))
    assert preview(workflow).lines[0].price == 1200
    assert preview(workflow).total == (1260 if tax == "with_tax" else 1200)
    assert preview(workflow).previous_reference == "TEST-PREV-2026-09"
    assert "Подсказка" in prompt(workflow)["text"] and not backend.documents


def test_revision_change_refreshes_preview_and_requires_new_confirmation(workflow):
    send(workflow, TEXT, initial())
    old = token(workflow)
    operation = workflow[0].app.state.bot.pending[123].prepared.operation_id
    backend = workflow[1]
    backend.services["service-accounting"] = backend.services["service-accounting"].model_copy(update={"price": Decimal("2000.00")})
    assert press(workflow, old).status_code == 200
    assert not backend.documents and "изменились" in prompt(workflow)["text"]
    fresh = token(workflow)
    assert fresh != old and preview(workflow).total == 2100
    assert workflow[0].app.state.bot.pending[123].prepared.operation_id == operation
    press(workflow, old, 101)
    assert not backend.documents
    press(workflow, fresh, 102)
    assert len(backend.documents) == 1 and "2 100.00" in pdf_text(workflow)


def test_race_after_refresh_is_still_atomically_blocked_and_repreviewed(workflow, monkeypatch):
    send(workflow, TEXT, initial())
    backend = workflow[1]
    original = backend.ensure_draft
    changed = False
    async def race(*args):
        nonlocal changed
        if not changed:
            changed = True
            backend.billing_revisions["client-001"] = "v2"
        return await original(*args)
    monkeypatch.setattr(backend, "ensure_draft", race)
    press(workflow, token(workflow))
    assert not backend.documents and "перед записью" in prompt(workflow)["text"]
    press(workflow, token(workflow), 101)
    assert len(backend.documents) == 1


def test_unknown_state_blocks_edit_and_retry_never_blindly_writes(workflow, monkeypatch):
    send(workflow, TEXT, initial())
    async def unknown(basis, operation_id):
        return OperationState(operation_id=operation_id, status="unknown")
    monkeypatch.setattr(workflow[1], "read_operation", unknown)
    press(workflow, token(workflow))
    assert "неизвестен" in prompt(workflow)["text"]
    send(workflow, "Другой счёт", number=2)
    assert "Сначала восстановите" in prompt(workflow)["text"]
    send(workflow, "/retry", number=3)
    assert not workflow[1].documents


@pytest.mark.parametrize("fault,state", [("create_lost_response", "draft"), ("post_lost_response", "posted")])
def test_timeout_after_real_fake_effect_recovers_same_confirmed_snapshot(workflow, fault, state):
    from app.fake_onec import FakeFault
    backend = workflow[1]
    backend.fault = FakeFault(mode=fault)
    send(workflow, TEXT, initial())
    confirmed = preview(workflow)
    press(workflow, token(workflow))
    assert len(backend.documents) == 1
    frozen = workflow[0].app.state.bot.recoveries[123]
    send(workflow, "Без НДС", number=2)
    assert "Сначала восстановите" in prompt(workflow)["text"]
    send(workflow, "/retry", number=3)
    assert len(backend.documents) == 1
    assert next(iter(backend.documents.values())).preview_digest == confirmed.digest == frozen.preview.digest
    assert "1 050.00" in pdf_text(workflow)


@pytest.mark.parametrize("status", [401, 429, 500])
def test_llm_dependency_failure_does_not_mutate(workflow, status):
    workflow[4]["fail"] = status
    assert send(workflow, TEXT).status_code == 200
    assert not workflow[1].documents and "Не удалось" in prompt(workflow)["text"]


def test_preview_delivery_retry_never_reinterprets_or_writes(workflow):
    workflow[4]["telegram_fail"] = True
    assert send(workflow, TEXT, initial()).status_code == 503
    first = token(workflow)
    assert send(workflow, TEXT).status_code == 200
    assert first == token(workflow) and len(workflow[5]) == 1 and not workflow[1].documents


def test_unsupported_natural_request_is_safely_rejected(workflow):
    send(workflow, "мусор", intent(action="reject"))
    assert not workflow[1].documents and "Укажите запрос" in prompt(workflow)["text"]


@pytest.mark.parametrize("change", [{"amount": 100}, {"tax": {"mode": "with_tax", "query": None, "evidence": "с НДС", "rate": 5}},
                                     {"client": "Выдуманная компания"}, {"services": [{"service_id": "invented"}]}])
def test_untrusted_model_cannot_invent_entities_or_financial_fields(workflow, change):
    output = initial().model_dump(mode="json")
    send(workflow, TEXT, {**output, **change})
    assert not workflow[1].documents and "reply_markup" not in prompt(workflow)


def test_missing_service_and_ambiguous_tax_stop_before_write(workflow):
    send(workflow, "Счёт ООО Ромашка за неизвестную услугу", intent(action="create", client="ООО Ромашка",
        services=(ServiceSelection(query="неизвестную услугу"),), lines_mode="replace"))
    assert "Услуга не найдена" in prompt(workflow)["text"] and not workflow[1].documents
    backend = workflow[1]
    backend.taxes["another"] = backend.taxes["test-vat-5"].model_copy(update={"tax_id": "another"})
    send(workflow, TEXT, initial(), 2)
    assert "налоговый профиль" in prompt(workflow)["text"] and not backend.documents


def test_service_period_is_separate_and_date_edit_preserves_it(workflow):
    send(workflow, TEXT + " за сентябрь 2026", intent(**{**initial().model_dump(),
        "service_period": PeriodInput(month=9, year=2026, evidence="сентябрь 2026")}))
    assert preview(workflow).invoice_date == date(2026, 10, 1)
    assert preview(workflow).supply_date == date(2026, 9, 30)
    send(workflow, "Дату на пятое", intent(invoice_date=CalendarInput(day=5, month=None, year=None, evidence="пятое")), 2)
    assert preview(workflow).invoice_date == date(2026, 10, 5)
    assert preview(workflow).service_period.month == 9
    assert preview(workflow).supply_date == date(2026, 9, 30)
    press(workflow, token(workflow))
    assert "05.10.2026" in pdf_text(workflow) and "30.09.2026" in pdf_text(workflow)


def test_short_patch_does_not_reask_a_client_already_known_locally(workflow):
    send(workflow, TEXT, initial())
    send(workflow, "Поменяй дату на пятое", intent(action="clarify", clarification="client",
        invoice_date=CalendarInput(day=5, month=None, year=None, evidence="пятое")), 2)
    assert preview(workflow).invoice_date == date(2026, 10, 5)
    assert preview(workflow).recipient.name



def test_next_invoice_can_use_last_client_and_actual_previous_document(workflow):
    send(workflow, TEXT, initial())
    press(workflow, token(workflow))
    send(workflow, "То же, что в прошлом месяце, на первое ноября 2026", intent(action="create",
        previous=PreviousInput(kind="previous_month", evidence="в прошлом месяце"),
        invoice_date=CalendarInput(day=1, month=11, year=2026, evidence="первое ноября 2026")), 2)
    body = json.loads(workflow[5][-1].content)
    assert "ООО Ромашка" in body["input"][1]["content"]
    assert preview(workflow).invoice_date == date(2026, 11, 1)
    assert preview(workflow).previous_reference.startswith("TEST-")
    assert preview(workflow).previous_reference != "TEST-PREV-2026-09"
    press(workflow, token(workflow), 101)
    assert len(workflow[1].documents) == 2


def test_repeated_request_and_different_data_never_duplicate_existing_document(workflow):
    send(workflow, TEXT, initial())
    press(workflow, token(workflow))
    send(workflow, TEXT, initial(), 2)
    press(workflow, token(workflow), 101)
    assert "уже отправлен" in prompt(workflow)["text"]
    send(workflow, TEXT, initial(), 3)
    send(workflow, "Теперь без НДС", intent(tax=TaxInput(mode="without_tax", query=None, evidence="без НДС")), 4)
    press(workflow, token(workflow), 102)
    assert "уже создан счёт с другими данными" in prompt(workflow)["text"]
    assert len(workflow[1].documents) == 1
    assert sum(r.url.path.endswith("sendDocument") for r in workflow[3]) == 1
    assert not workflow[0].app.state.bot.recoveries


def test_refresh_lookup_timeout_is_unknown_and_blocks_new_writes(workflow, monkeypatch):
    send(workflow, TEXT, initial())
    async def failed(*args):
        raise TimeoutError("PRIVATE")
    monkeypatch.setattr(workflow[1], "read_operation", failed)
    press(workflow, token(workflow))
    assert "неизвестен" in prompt(workflow)["text"]
    assert 123 in workflow[0].app.state.bot.recoveries
    send(workflow, TEXT, number=2)
    assert "Сначала восстановите" in prompt(workflow)["text"] and not workflow[1].documents


def test_refresh_data_failure_preserves_pending_and_does_not_write(workflow, monkeypatch):
    send(workflow, TEXT, initial())
    original = workflow[1].resolve_basis
    confirm = token(workflow)
    async def failed(*args):
        raise TimeoutError("PRIVATE")
    monkeypatch.setattr(workflow[1], "resolve_basis", failed)
    press(workflow, confirm)
    assert "Создание документа не запускалось" in prompt(workflow)["text"]
    assert not workflow[1].documents and not workflow[0].app.state.bot.recoveries
    monkeypatch.setattr(workflow[1], "resolve_basis", original)
    press(workflow, confirm, 101)
    assert len(workflow[1].documents) == 1


def test_invalid_calendar_edit_revokes_confirmation_and_keeps_draft(workflow):
    send(workflow, TEXT, initial())
    old = token(workflow)
    send(workflow, "На 31 февраля 2026", intent(invoice_date=CalendarInput(day=31, month=2, year=2026, evidence="31 февраля 2026")), 2)
    assert "нет в календаре" in prompt(workflow)["text"]
    press(workflow, old)
    assert not workflow[1].documents
    send(workflow, "На второе", intent(invoice_date=CalendarInput(day=2, month=None, year=None, evidence="второе")), 3)
    assert preview(workflow).invoice_date == date(2026, 10, 2)


def test_large_preview_delivers_every_line_and_buttons_only_after_all_values(workflow):
    from app.domain import ResolvedServiceSelection
    backend = workflow[1]
    backend.default_services = tuple(ResolvedServiceSelection(service_id="service-accounting", quantity=Decimal("1")) for _ in range(20))
    item = backend.services["service-accounting"]
    backend.services[item.service_id] = item.model_copy(update={"description": "Long fictitious description " * 15})
    send(workflow, "Счёт ООО Ромашка на 1 октября 2026", intent(action="create", client="ООО Ромашка",
        invoice_date=CalendarInput(day=1, month=10, year=2026, evidence="1 октября 2026")))
    messages = [json.loads(r.content) for r in workflow[3] if r.url.path.endswith("sendMessage")]
    assert len(messages) > 1
    assert all(len(m["text"]) <= 4000 for m in messages)
    assert all("reply_markup" not in m for m in messages[:-1])
    text = "\n".join(m["text"] for m in messages)
    assert all(f"{i}. Услуга:" in text for i in range(1, 21))
    assert "21 000.00 AED" in text and "reply_markup" in messages[-1]
    assert not backend.documents


def test_failed_voice_edit_revokes_old_confirmation_and_keeps_context(workflow):
    send(workflow, TEXT, initial())
    old = token(workflow)
    workflow[4]["fail"] = 500
    send(workflow, "Без НДС", number=2, voice=True)
    press(workflow, old)
    assert not workflow[1].documents and 123 in workflow[0].app.state.bot.contexts
    workflow[4]["fail"] = None
    send(workflow, "Дату на пятое", intent(invoice_date=CalendarInput(day=5, month=None, year=None, evidence="пятое")), 3)
    assert preview(workflow).invoice_date == date(2026, 10, 5)


def test_unknown_operation_blocks_voice_before_stt(workflow, monkeypatch):
    send(workflow, TEXT, initial())
    async def unknown(basis, operation_id):
        return OperationState(operation_id=operation_id, status="unknown")
    monkeypatch.setattr(workflow[1], "read_operation", unknown)
    press(workflow, token(workflow))
    count = len(workflow[5])
    send(workflow, "Без НДС", number=2, voice=True)
    assert len(workflow[5]) == count and not workflow[1].documents


def test_provider_supplied_period_is_visible_and_retained_during_edits(workflow, monkeypatch):
    from app.domain import ResolvedInvoiceCommand, ServicePeriod
    original = workflow[1].resolve_basis
    async def with_known_period(command):
        period = command.service_period or ServicePeriod(year=2026, month=9)
        return await original(ResolvedInvoiceCommand.model_validate({**command.model_dump(),
            "service_period": period, "year": period.year, "month": period.month}))
    monkeypatch.setattr(workflow[1], "resolve_basis", with_known_period)
    send(workflow, TEXT, initial())
    assert preview(workflow).service_period.month == 9
    assert workflow[0].app.state.bot.contexts[123].command.period.month == 9
    send(workflow, "Дату на пятое", intent(invoice_date=CalendarInput(day=5, month=None, year=None, evidence="пятое")), 2)
    assert preview(workflow).invoice_date == date(2026, 10, 5)
    assert preview(workflow).service_period.month == 9
    press(workflow, token(workflow))
    assert len(workflow[1].documents) == 1
