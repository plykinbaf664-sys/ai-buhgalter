"""Case-sensitive ERP, spoken names and approximate matches keep human identity choice."""
import asyncio
import json
from uuid import UUID

import httpx
import pytest
from fastapi.testclient import TestClient

from app.company_names import exact_key, similarity
from app.config import Settings
from app.domain import BackendFailure, ClientChoiceRequired, UserProblem
from app.firstbit import FirstBit, FirstBitSettings
from app.main import create_app
from app.language import LanguageIntent, explicit_client_phrase
from scripts.firstbit_fixture import FirstBitFixture, ref


@pytest.fixture
def fixture():
    result = FirstBitFixture()
    result.records["Catalog_Companies"][0].update(Description="SYN GROUP FZCO", DescriptionFull="SYN GROUP FZCO")
    return result


def resolve(fixture, query, selected=None):
    async def run():
        settings = FirstBitSettings(base_url=fixture.env()["FIRSTBIT_BASE_URL"], username="synthetic_reader",
            password="synthetic-only", readonly_account=True, bookkeeping_item_id=UUID(ref(5)))
        backend = FirstBit(settings, transport=httpx.MockTransport(fixture.respond))
        try:
            return await backend.resolve_client(query, selected_id=selected)
        finally:
            await backend.aclose()
    return asyncio.run(run())


@pytest.mark.parametrize("query", ["syn group fzco", "Syn Group Fzco", "SYNGROUPFZCO",
    "  sYn   GrOuP  FzCo ", "SYN GROUP F.Z.C.O.", "SYN—GROUP ‘FZCO’", "ＳＹＮ GROUP FZCO"])
def test_case_spacing_punctuation_are_exact_equivalents_without_server_text_search(fixture, query):
    original = fixture.respond
    def case_sensitive_server(request):
        # A sensitive server cannot hide names: only fixed name pages / UUID reads are sent.
        if request.url.path.endswith("Catalog_Companies"):
            filter = request.url.params["$filter"]
            assert "substringof" not in filter and "tolower" not in filter
            assert query not in filter
        return original(request)
    fixture.respond = case_sensitive_server
    assert resolve(fixture, query).client_id == ref(1)
    names = next(r for r in fixture.calls if "$skip" in r.url.params)
    assert set(names.url.params["$select"].split(",")) == {
        "Ref_Key", "DeletionMark", "IsFolder", "Inactive", "Description", "DescriptionFull"}
    assert {r.method for r in fixture.calls} == {"GET"}


@pytest.mark.parametrize("query", ["СИН Групп", "Эс Уай Эн Груп", "эсуайэн груп фзко", "эсуайэнгрупп",
    "Эс Уай Эн Груп Эф Зет Си Оу", "СИНГруппФЗКО", "SYN Grup FZCO", "SYN GROUP", "SYN", "SYN GROOP FZCO"])
def test_spoken_partial_and_typo_names_are_suggestions_never_auto_selection(fixture, query):
    with pytest.raises(ClientChoiceRequired) as exc:
        resolve(fixture, query)
    assert [c.client_id for c in exc.value.choices.candidates] == [ref(1)]
    assert resolve(fixture, query, ref(1)).client_id == ref(1)
    assert not any(r.url.path.endswith("Document_InventoryExpense") for r in fixture.calls)


@pytest.mark.parametrize("query", ["Алан Тестов", "Тестов Алан", "Alan Testoff"])
def test_person_names_transliteration_and_word_order_require_choice(fixture, query):
    row = fixture.records["Catalog_Companies"][0]
    row.update(Description="Alan Testov", DescriptionFull="Alan Testov")
    fixture.records["Catalog_Companies"].append({**row, "Ref_Key": ref(99)})
    with pytest.raises(ClientChoiceRequired) as exc:
        resolve(fixture, query)
    assert {c.client_id for c in exc.value.choices.candidates} == {ref(1), ref(99)}


def test_canonical_duplicates_are_not_lost_by_server_spelling_or_case(fixture):
    row = fixture.records["Catalog_Companies"][0]
    fixture.records["Catalog_Companies"].append({**row, "Ref_Key": ref(99),
        "Description": "syn-group fzco", "DescriptionFull": "syn-group fzco"})
    with pytest.raises(ClientChoiceRequired) as exc:
        resolve(fixture, "sYn group FZCO")
    assert len(exc.value.choices.candidates) == 2


@pytest.mark.parametrize("query", ["Кантервилл", "Кантервил", "Кантервел", "Cantervile"])
def test_spoken_short_brand_matches_inside_long_legal_name_only_as_choice(fixture, query):
    row = fixture.records["Catalog_Companies"][0]
    row.update(Description="CANTERVILLE AB CD SPARE PARTS TRADING LLC",
               DescriptionFull="CANTERVILLE AB CD SPARE PARTS TRADING LLC")
    with pytest.raises(ClientChoiceRequired) as exc:
        resolve(fixture, query)
    assert [c.client_id for c in exc.value.choices.candidates] == [ref(1)]
    assert resolve(fixture, query, ref(1)).client_id == ref(1)


def test_unrelated_words_legal_forms_and_short_fuzzy_names_do_not_auto_resolve(fixture):
    for query in ("Неизвестное название", "LLC", "группа", "Би", "bm"):
        try:
            result = resolve(fixture, query)
        except UserProblem:
            continue
        pytest.fail("Unrelated/partial query resolved automatically: " + result.client_id)
    assert similarity("Amir", "Unrelated synthetic company") == 0
    assert exact_key("SYN—Group") == exact_key("syn group")


@pytest.mark.parametrize("text,company", [
    ("Сформируй счет для SYN Group на 1 ноября 2026 года за бухгалтерское обслуживание", "SYN Group"),
    ("Сформируй счёт для Эс Уай Эн Груп на первое ноября 2026", "Эс Уай Эн Груп"),
    ("Выстави счёт для компании Алан Тестов за октябрь 2026", "Алан Тестов"),
    ("Подготовь счёт для Кафе на Пушкина на 5 ноября 2026", "Кафе на Пушкина"),
    ("Подготовь счёт для Кафе на Первой Линии на 5 ноября 2026", "Кафе на Первой Линии"),
    ('Сформируй счёт для «За бухгалтерское обслуживание» на 5 ноября 2026', '«За бухгалтерское обслуживание»'),
    ("Сделай счёт для Synthetic Company", "Synthetic Company")])
def test_missing_model_client_is_recovered_only_from_verbatim_explicit_phrase(text, company):
    assert explicit_client_phrase(text) == company
    parsed = LanguageIntent.model_validate_json(json.dumps({"action": "clarify", "client_change": None,
        "date_change": None, "period_change": None, "line_changes": [], "tax_change": None,
        "previous_hint_request": None, "clarification": "client"})).to_intent(text)
    assert parsed.client == company and parsed.action == "create" and parsed.clarification is None


@pytest.mark.parametrize("text", ["Поставь дату на 5 ноября", "Цена 1500 для первой строки",
    "Сформируй счёт для цены 1500", "Сформируй счёт для X для Y", "Назови услугу Счёт для Synthetic",
    'Сформируй счёт для «незакрытое название на 5 ноября 2026'])
def test_explicit_company_fallback_does_not_guess_from_edit_or_ambiguous_directive(text):
    assert explicit_client_phrase(text) is None


def test_name_paging_finds_later_company_and_does_not_select_before_scan_completes(fixture):
    target = fixture.records["Catalog_Companies"][0]
    fixture.records["Catalog_Companies"] = [{**target, "Ref_Key": ref(n),
        "Description": "Unrelated synthetic " + str(n), "DescriptionFull": "Unrelated synthetic " + str(n)}
        for n in range(20, 220)] + [{**target, "Ref_Key": ref(300)}]
    assert resolve(fixture, "syn group fzco").client_id == ref(300)
    pages = [r for r in fixture.calls if "$skip" in r.url.params]
    assert [r.url.params["$skip"] for r in pages] == ["0", "200"]


def test_incomplete_names_scan_cannot_auto_select_even_an_early_exact_match(fixture):
    target = fixture.records["Catalog_Companies"][0]
    fixture.records["Catalog_Companies"] = [target] + [{**target, "Ref_Key": ref(n),
        "Description": "Unrelated synthetic " + str(n), "DescriptionFull": "Unrelated synthetic " + str(n)}
        for n in range(20, 5019)]
    with pytest.raises(UserProblem, match="предел"):
        resolve(fixture, "SYN GROUP FZCO")
    pages = [r for r in fixture.calls if "$skip" in r.url.params]
    assert len(pages) == 25
    assert not any(r.url.params.get("$filter", "").startswith("Ref_Key eq") for r in fixture.calls)


def test_duplicate_name_page_stops_without_selection(fixture):
    original = fixture.respond
    row = fixture.records["Catalog_Companies"][0]
    fixture.records["Catalog_Companies"] = [{**row, "Ref_Key": ref(n)} for n in range(1, 201)]
    def repeat(request):
        if request.url.params.get("$skip") == "200":
            fixture.calls.append(request)
            return httpx.Response(200, json={"value": [row]})
        return original(request)
    fixture.respond = repeat
    with pytest.raises(BackendFailure, match="page_changed"):
        resolve(fixture, "SYN GROUP FZCO")


@pytest.mark.parametrize("change", ["Inactive", "DeletionMark", "rename"])
def test_fresh_record_blocks_a_changed_suggested_company(fixture, change):
    original = fixture.respond
    def changed(request):
        if request.url.params.get("$filter", "").startswith("Ref_Key eq"):
            row = fixture.records["Catalog_Companies"][0]
            if change == "rename":
                row.update(Description="Unrelated", DescriptionFull="Unrelated")
            else:
                row[change] = True
        return original(request)
    fixture.respond = changed
    with pytest.raises(UserProblem):
        resolve(fixture, "Эс Уай Эн Груп", ref(1))


@pytest.mark.parametrize("missing_model_client", [False, True])
def test_voice_to_candidate_button_to_real_adapter_preview_keeps_directory_out_of_ai(fixture, monkeypatch, caplog, missing_model_client):
    for k, v in fixture.env().items():
        monkeypatch.setenv(k, v)
    sent, ai_calls = [], []
    audio = b"OggS" + b"\0" * 24 + b"OpusHead" + b"\0" * 32
    def telegram(request):
        if request.url.path.endswith("getFile"):
            return httpx.Response(200, json={"ok": True, "result": {"file_id": "voice", "file_unique_id": "voice",
                "file_size": len(audio), "file_path": "voice/test.oga"}})
        if "/file/bot" in request.url.path:
            return httpx.Response(200, content=audio)
        if request.url.path.endswith("answerCallbackQuery"):
            return httpx.Response(200, json={"ok": True, "result": True})
        assert request.url.path.endswith("sendMessage"), "No PDF/financial mutation"
        sent.append(json.loads(request.content))
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 1, "chat": {"id": 123}}})
    def ai(request):
        ai_calls.append(request)
        if request.url.path.endswith("transcriptions"):
            return httpx.Response(200, json={"text": "Выстави счёт для Эс Уай Эн Груп на 1 сентября 2026" if missing_model_client
                else "Выстави счёт Эс Уай Эн Груп за сентябрь 2026",
                "logprobs": [{"token": "fixture", "logprob": -.01}]})
        body = request.content.decode()
        assert "SYN GROUP FZCO" not in body and "TEST-TRN" not in body and ref(1) not in body
        result = {"action": "create_invoice", "client": "Эс Уай Эн Груп", "year": 2026, "month": 9}
        if missing_model_client:
            # Reproduce actual structured output: date/service parsed, company omitted.
            result = {"action": "create", "client_change": None,
                "date_change": {"source_span": {"first_word": 9, "last_word": 11}, "day": 1, "month": 9, "year": 2026},
                "period_change": None,
                "line_changes": [], "tax_change": None, "previous_hint_request": None, "clarification": None}
        return httpx.Response(200, json={"status": "completed", "output": [{"type": "message", "role": "assistant",
            "status": "completed", "content": [{"type": "output_text", "text": json.dumps(result)}]}]})
    settings = Settings(token="123:" + "x" * 32, webhook_secret="s" * 32, allowed_users=frozenset({123}),
        mode="firstbit_readonly", ai_mode="openai", openai_api_key="fixture", llm_model="fixture", stt_model="gpt-4o-mini-transcribe")
    app = create_app(settings, telegram_transport=httpx.MockTransport(telegram), ai_transport=httpx.MockTransport(ai),
        firstbit_transport=httpx.MockTransport(fixture.respond))
    with TestClient(app) as client:
        client.headers["X-Telegram-Bot-Api-Secret-Token"] = "s" * 32
        assert client.post("/telegram/webhook", json={"update_id": 1, "message": {"message_id": 1,
            "from": {"id": 123, "is_bot": False}, "chat": {"id": 123, "type": "private"},
            "voice": {"file_id": "voice", "file_unique_id": "voice", "duration": 8, "mime_type": "audio/ogg"}}}).status_code == 200
        assert not app.state.bot.pending and 123 in app.state.bot.client_choices
        button = sent[-1]["reply_markup"]["inline_keyboard"][0][0]["callback_data"]
        assert client.post("/telegram/webhook", json={"update_id": 2, "callback_query": {"id": "2",
            "from": {"id": 123, "is_bot": False}, "message": {"message_id": 1,
                "chat": {"id": 123, "type": "private"}}, "data": button}}).status_code == 200
        prepared = app.state.bot.pending[123].prepared
        assert prepared.request.client_id == ref(1) and len(prepared.preview.lines) == 2
        assert prepared.preview.total == 3150
        assert len(ai_calls) == 2
        assert {r.method for r in fixture.calls} == {"GET"}
        assert "SYN GROUP FZCO" not in caplog.text and "Эс Уай Эн" not in caplog.text


@pytest.mark.parametrize('query', ['syn', 'SYM', 'син'])
def test_misheard_short_acronym_only_suggests_candidates(fixture, query):
    fixture.records['Catalog_Companies'][0]['Description'] = 'SYN GROUP FZCO'
    fixture.records['Catalog_Companies'][0]['DescriptionFull'] = 'SYN GROUP FZCO'
    with pytest.raises(ClientChoiceRequired) as choice:
        resolve(fixture, query)
    assert choice.value.choices.candidates[0].client_id == ref(1)
    assert resolve(fixture, query, ref(1)).client_id == ref(1)


@pytest.mark.parametrize("query", ["NRP Equipment", "nrp equipment", " NRP—EQUIPMENT ",
    "NRP Equipment LLC", "NRP Equipment L.L.C."])
def test_shortened_multiword_name_and_legal_suffix_preserve_explicit_choice(fixture, query):
    fixture.records["Catalog_Companies"][0].update(
        Description="N R P EQUIPMENT TRADING", DescriptionFull="N R P EQUIPMENT TRADING L.L.C")
    with pytest.raises(ClientChoiceRequired) as choice:
        resolve(fixture, query)
    assert [c.client_id for c in choice.value.choices.candidates] == [ref(1)]
    assert resolve(fixture, query, ref(1)).client_id == ref(1)
    assert all(r.method == "GET" for r in fixture.calls)


@pytest.mark.parametrize("query", ["nrp equipment trading llc", " N.R.P. EQUIPMENT—TRADING L.L.C. ",
    "ＮＲＰ EQUIPMENT TRADING LLC"])
def test_descriptionfull_is_an_exact_identity_even_when_short_description_differs(fixture, query):
    fixture.records["Catalog_Companies"][0].update(
        Description="Synthetic branch", DescriptionFull="N R P EQUIPMENT TRADING L.L.C")
    assert resolve(fixture, query).client_id == ref(1)


@pytest.mark.parametrize("query", ["NRP Equipment", "nrp equipment trading llc"])
def test_later_page_full_name_and_short_name_are_not_lost(fixture, query):
    row = fixture.records["Catalog_Companies"][0]
    fixture.records["Catalog_Companies"] = [{**row, "Ref_Key": ref(n),
        "Description": "Unrelated branch " + str(n), "DescriptionFull": "Unrelated branch " + str(n)}
        for n in range(20, 421)] + [{**row, "Ref_Key": ref(500),
        "Description": "Synthetic branch", "DescriptionFull": "N R P EQUIPMENT TRADING L.L.C"}]
    if query == "NRP Equipment":
        with pytest.raises(ClientChoiceRequired) as choice:
            resolve(fixture, query)
        assert [c.client_id for c in choice.value.choices.candidates] == [ref(500)]
    else:
        assert resolve(fixture, query).client_id == ref(500)
    pages = [r for r in fixture.calls if "$skip" in r.url.params]
    assert [r.url.params["$skip"] for r in pages] == ["0", "200", "400"]
    assert all(r.url.params["$orderby"] == "Ref_Key asc" and r.url.params["$top"] == "200" for r in pages)
    assert resolve(fixture, query, ref(500)).client_id == ref(500)


def test_short_name_ambiguity_across_pages_never_chooses_first_record(fixture):
    row = fixture.records["Catalog_Companies"][0]
    row.update(Description="N R P EQUIPMENT TRADING", DescriptionFull="N R P EQUIPMENT TRADING LLC")
    fixture.records["Catalog_Companies"] += [{**row, "Ref_Key": ref(n),
        "Description": "Unrelated branch " + str(n), "DescriptionFull": "Unrelated branch " + str(n)}
        for n in range(20, 420)] + [{**row, "Ref_Key": ref(500),
        "Description": "N R P EQUIPMENT RENTAL", "DescriptionFull": "N R P EQUIPMENT RENTAL LLC"}]
    with pytest.raises(ClientChoiceRequired) as choice:
        resolve(fixture, "NRP Equipment")
    assert {c.client_id for c in choice.value.choices.candidates} == {ref(1), ref(500)}
    assert [r.url.params["$skip"] for r in fixture.calls if "$skip" in r.url.params] == ["0", "200", "400"]


def test_month_year_language_sdk_to_real_resolver_and_historical_preview(fixture):
    from openai import AsyncOpenAI
    from pydantic import SecretStr
    from app.ai import CommandInterpreter, Extraction
    from app.intent import InvoiceDraft
    from app.service import InvoiceService

    text = "Пожалуйста, сформируй счет для NRP Equipment за декабрь 2026 года"
    fixture.records["Catalog_Companies"][0].update(
        Description="N R P EQUIPMENT TRADING", DescriptionFull="N R P EQUIPMENT TRADING L.L.C")
    inputs, model_requests = [], []

    class TracedProvider(FirstBit):
        async def resolve_client(self, query, *, selected_id=None):
            inputs.append(query)
            return await super().resolve_client(query, selected_id=selected_id)

    def model_response(request):
        payload = json.loads(request.content)
        model_requests.append(payload)
        schema = payload["text"]["format"]["schema"]
        assert set(schema["properties"]) == {"action", "client", "year", "month"}
        assert schema["additionalProperties"] is False
        assert "N R P EQUIPMENT TRADING" not in request.content.decode()
        return httpx.Response(200, json={"id": "resp_test", "object": "response", "created_at": 1,
            "status": "completed", "model": "gpt-4o-mini", "output": [{"id": "msg_test", "type": "message",
                "role": "assistant", "status": "completed", "content": [{"type": "output_text", "annotations": [],
                    "text": Extraction(action="create_invoice", client="NRP Equipment", year=2026, month=12).model_dump_json()}]}]})

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(model_response)) as transport:
            sdk = AsyncOpenAI(api_key="synthetic", base_url="https://api.openai.com/v1",
                http_client=transport, max_retries=0)
            interpreter = CommandInterpreter(api_key=SecretStr("synthetic"), model="gpt-4o-mini",
                sdk_client=sdk, send_draft_context=False)
            parsed = await interpreter.interpret(text)
            draft = InvoiceDraft.from_command(parsed.command)
            assert draft.client == "NRP Equipment" and draft.service_period.month == 12
            settings = FirstBitSettings(base_url=fixture.env()["FIRSTBIT_BASE_URL"], username="synthetic_reader",
                password="synthetic-only", readonly_account=True, bookkeeping_item_id=UUID(ref(5)))
            backend = TracedProvider(settings, transport=httpx.MockTransport(fixture.respond))
            try:
                service = InvoiceService(backend)
                with pytest.raises(ClientChoiceRequired):
                    await service.prepare(parsed.command, "test-choice", 123)
                prepared = await service.prepare(parsed.command, "test-choice-selected", 123, selected_client_id=ref(1))
                assert prepared.request.client_id == ref(1) and len(prepared.preview.lines) == 2
                assert prepared.preview.service_period.month == 12
            finally:
                await backend.aclose()
                await sdk.close()
    asyncio.run(scenario())
    assert inputs == ["NRP Equipment", "NRP Equipment"]
    assert len(model_requests) == 1 and all(r.method == "GET" for r in fixture.calls)


@pytest.mark.parametrize("text", [
    "Сформируй счет для для NRP Equipment за декабрь 2026 года",
    "Сформируй счет\nдля\tNRP Equipment за за декабрь 2026 г.",
    "Сформируй счет для N.R.P. Equipment L.L.C. за декабрь 2026 года",
])
def test_clear_period_requests_with_stutters_need_no_model(text):
    from app.ai import CommandInterpreter
    parsed = asyncio.run(CommandInterpreter().interpret(text))
    assert parsed.command.client in {"NRP Equipment", "N.R.P. Equipment L.L.C."}
    assert parsed.command.year == 2026 and parsed.command.month == 12


@pytest.mark.parametrize("query", ["NRP Equipmnet", "NRP Equipmnt", "NRP Equiipment",
    "NPR Equipment", "Эн ар пи эквипмент", "эн ар пи экипмент"])
def test_typo_and_phonetic_tokens_inside_long_names_are_candidates(fixture, query):
    fixture.records['Catalog_Companies'][0].update(Description='N R P EQUIPMENT TRADING',
        DescriptionFull='N R P EQUIPMENT TRADING L.L.C')
    with pytest.raises(ClientChoiceRequired) as choice:
        resolve(fixture, query)
    assert ref(1) in {c.client_id for c in choice.value.choices.candidates}
    assert resolve(fixture, query, ref(1)).client_id == ref(1)


def test_explicit_service_month_repairs_incomplete_date_classification():
    from app.intent import CalendarInput, InvoiceIntent
    from app.language import ground_explicit_period
    intent = InvoiceIntent(action='clarify', client='Synthetic brand', invoice_date=CalendarInput(
        evidence='декабрь 2026', day=None, month=12, year=2026), service_period=None,
        services=(), lines_mode='keep', tax=None, previous=None, clarification='date')
    result = ground_explicit_period(intent, 'Мне нужен инвойс за декабрь 2026 для Synthetic brand')
    assert result.action == 'create' and result.clarification is None and result.invoice_date is None
    assert result.service_period.month == 12 and result.service_period.year == 2026


def test_period_does_not_replace_explicit_invoice_day_or_parse_quoted_company():
    from app.intent import CalendarInput, InvoiceIntent
    from app.language import ground_explicit_period
    intent = InvoiceIntent(action='create', client='Synthetic brand', invoice_date=CalendarInput(
        evidence='1 ноября 2026', day=1, month=11, year=2026), service_period=None,
        services=(), lines_mode='keep', tax=None, previous=None, clarification=None)
    assert ground_explicit_period(intent, 'Счёт для Synthetic brand на 1 ноября 2026 за декабрь 2026').invoice_date == intent.invoice_date
    assert ground_explicit_period(intent, 'Счёт для «За декабрь 2026» на 1 ноября 2026').service_period is None
