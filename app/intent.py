"""Untrusted language intent and deterministic edits of a bounded invoice draft."""
from difflib import SequenceMatcher
import re
from datetime import date
from typing import Annotated, Literal
from uuid import uuid4

from pydantic import Field, WithJsonSchema, model_validator

from app.domain import (InvoiceCommand, Label, Money, PreviewLineOverride, PreviewTaxRequest,
                        PreviewLineOrigin, PreparedInvoice, Quantity, ServicePeriod, ServiceSelection,
                        StrictModel, TaxRequest, UserProblem)
from app.numbers import explicit_decimal

# Expose JSON numbers instead of Pydantic's Decimal string alternatives.
# Exact Decimal bounds and precision are still checked at runtime.
IntentQuantity = Annotated[Quantity, WithJsonSchema({"type": "number", "exclusiveMinimum": 0,
                                                   "maximum": 1000000, "multipleOf": .001})]


class CalendarInput(StrictModel):
    evidence: str = Field(min_length=1, max_length=1000, description="COPY an exact substring from the FINAL user message, preserving spelling and word endings. Never normalize or copy from Draft.")
    day: int | None = Field(ge=1, le=31)
    month: int | None = Field(ge=1, le=12)
    year: int | None = Field(ge=2000, le=2100)


class PeriodInput(StrictModel):
    evidence: str = Field(min_length=1, max_length=1000, description="Exact substring from the FINAL user message.")
    month: int = Field(ge=1, le=12)
    year: int | None = Field(ge=2000, le=2100)


class TaxInput(StrictModel):
    evidence: str = Field(min_length=1, max_length=1000, description="Exact substring from the FINAL user message expressing this tax choice.")
    mode: Literal["default", "with_tax", "without_tax", "profile"]
    query: str | None

    @model_validator(mode="after")
    def valid_request(self):
        TaxRequest(mode=self.mode, query=self.query)
        return self


class PreviousInput(StrictModel):
    evidence: str = Field(min_length=1, max_length=1000, description="Exact substring from the FINAL user message requesting a previous invoice hint.")
    kind: Literal["last", "previous_month", "usual"]


class IntentService(StrictModel):
    query: str = Field(min_length=1, max_length=500,
        description="COPY service words from FINAL user message, preserving spelling and word endings. Never translate, normalize to dictionary form or copy an old Draft row.")
    quantity: IntentQuantity | None = None
    quantity_evidence: str | None = Field(default=None, min_length=1, max_length=1000)

    @model_validator(mode="after")
    def grounded_quantity(self):
        if (self.quantity is None) != (self.quantity_evidence is None):
            raise ValueError("Service quantity requires evidence")
        return self


class IntentPreviewChange(StrictModel):
    line_number: int | None = Field(default=None, ge=1, le=20)
    price: Money | None = None
    price_evidence: str | None = Field(default=None, min_length=1, max_length=200)
    amount: Money | None = None
    amount_evidence: str | None = Field(default=None, min_length=1, max_length=200)
    currency: Literal["AED", "USD", "EUR", "GBP", "RUB"] | None = None
    description: Label | None = None
    tax: PreviewTaxRequest | None = None
    tax_evidence: str | None = Field(default=None, min_length=1, max_length=1000)
    rate_evidence: str | None = Field(default=None, min_length=1, max_length=200)

    @model_validator(mode="after")
    def evidence_pairs(self):
        if ((self.price is None) != (self.price_evidence is None)
                or (self.tax is None) != (self.tax_evidence is None)
                or (self.tax is not None and self.tax.mode == "rate") != (self.rate_evidence is not None)
                or self.currency is not None and self.price is None and self.amount is None
                or (self.amount is None) != (self.amount_evidence is None)
                or self.price is not None and self.amount is not None
                or self.price is None and self.amount is None and self.description is None and self.tax is None):
            raise ValueError("Preview change requires explicit grounded fields")
        return self


class IntentDraftMutation(StrictModel):
    kind: Literal["update", "delete", "add", "replace", "retain"]
    target: Label | None = None
    service: Label | None = None
    quantity: IntentQuantity | None = None
    price: Money | None = None
    currency: Literal["AED", "USD", "EUR", "GBP", "RUB"] | None = None
    tax: PreviewTaxRequest | None = None
    description: Label | None = None

    @model_validator(mode="after")
    def valid_operation(self):
        if self.kind in ("delete", "retain"):
            valid = self.target is not None and self.service is None and all(
                value is None for value in (self.quantity, self.price, self.currency, self.tax, self.description))
        elif self.kind == "add":
            valid = self.target is None and self.service is not None
        elif self.kind == "replace":
            valid = self.target is not None and self.service is not None
        else:
            valid = self.target is not None and self.service is None and any(
                value is not None for value in (self.quantity, self.price, self.tax, self.description))
        if not valid:
            raise ValueError("Invalid draft line mutation")
        if self.currency is not None and self.price is None:
            raise ValueError("Currency requires a unit price")
        return self


class InvoiceIntent(StrictModel):
    # Required nullable fields deliberately match the Structured Outputs contract.
    action: Literal["create", "edit", "cancel", "clarify", "reject"]
    initial_overrides: tuple[PreviewLineOverride, ...] = Field(default=(), max_length=20)
    client: str | None = Field(min_length=2, max_length=200, description="Company name explicitly present in FINAL user message. Null otherwise. Never copy from Draft.")
    invoice_date: CalendarInput | None
    service_period: PeriodInput | None
    services: tuple[IntentService, ...] = Field(max_length=20,
        description="ONLY services explicitly mentioned in FINAL user message. Never include unchanged Draft rows. Empty for date/tax-only changes.")
    lines_mode: Literal["keep", "replace", "add"]
    tax: TaxInput | None
    previous: PreviousInput | None
    clarification: Literal["client", "date", "service", "tax", "unsupported"] | None
    line_number: int | None = Field(default=None, ge=1, le=20)
    quantity: IntentQuantity | None = None
    quantity_evidence: str | None = Field(default=None, min_length=1, max_length=1000)
    preview_changes: tuple[IntentPreviewChange, ...] = Field(default=(), max_length=20)
    draft_mutations: tuple[IntentDraftMutation, ...] = Field(default=(), max_length=20)

    @model_validator(mode="after")
    def consistent(self):
        if self.services and self.lines_mode == "keep":
            raise ValueError("Line action requires service selections")
        if (self.quantity is None) != (self.quantity_evidence is None):
            raise ValueError("Quantity requires evidence")
        if self.services and self.line_number is not None and self.lines_mode == "add":
            raise ValueError("Adding a line cannot replace an existing line")
        if self.action in ("cancel", "reject") and any((self.client, self.invoice_date, self.service_period,
                                                       self.services, self.tax, self.previous, self.quantity, self.line_number,
                                                       self.preview_changes, self.draft_mutations, self.initial_overrides)):
            raise ValueError("Non-action must not carry changes")
        return self


class InvoiceDraft(StrictModel):
    client: str | None = None
    invoice_date: date | None = None
    service_period: ServicePeriod | None = None
    services: tuple[ServiceSelection, ...] = Field(default=(), max_length=20)
    tax: TaxRequest = TaxRequest()
    previous: Literal["none", "last", "previous_month", "usual"] = "none"
    incomplete_date: CalendarInput | None = None
    legacy_period: bool = False
    unresolved_line: int | None = Field(default=None, ge=1, le=20)
    preview_overrides: tuple[PreviewLineOverride, ...] = Field(default=(), max_length=20)
    initial_overrides: tuple[PreviewLineOverride, ...] = Field(default=(), max_length=20)

    @classmethod
    def from_command(cls, command: InvoiceCommand):
        return cls(client=command.client, invoice_date=command.invoice_date, service_period=command.period,
                   services=command.services, tax=command.tax, previous=command.previous,
                   preview_overrides=command.preview_overrides,
                   initial_overrides=command.initial_overrides,
                   legacy_period=command.legacy_period or (command.invoice_date is None and command.year is not None))

    def command(self) -> InvoiceCommand:
        if self.client is None:
            raise UserProblem("Укажите компанию для счёта. Остальные параметры сохранены.")
        if self.incomplete_date is not None:
            raise UserProblem("Укажите число для даты счёта. Остальные параметры сохранены.")
        return InvoiceCommand(client=self.client, invoice_date=self.invoice_date or date.today(),
                              service_period=self.service_period, services=self.services,
                              tax=self.tax, previous=self.previous, legacy_period=self.legacy_period,
                              preview_overrides=self.preview_overrides, initial_overrides=self.initial_overrides)


def ground_intent(intent: InvoiceIntent, source: str, context: InvoiceDraft | None = None) -> InvoiceIntent:
    intent = InvoiceIntent.model_validate(intent)
    for change in intent.preview_changes:
        for evidence in (change.price_evidence, change.amount_evidence, change.description, change.tax_evidence, change.rate_evidence):
            if evidence is not None and evidence.casefold() not in source.casefold():
                raise UserProblem("Не удалось подтвердить правку по вашему сообщению. Укажите её явно.")
        if change.price is not None and explicit_decimal(change.price_evidence) != change.price:
            raise UserProblem("Цена не совпала с вашим сообщением. Укажите её цифрами.")
        if change.amount is not None and explicit_decimal(change.amount_evidence) != change.amount:
            raise UserProblem("Сумма строки не совпала с сообщением.")
        if change.rate_evidence is not None and explicit_decimal(change.rate_evidence, places=3) != change.tax.rate:
            raise UserProblem("Ставка НДС не совпала с вашим сообщением. Укажите её явно.")
        if change.tax is not None and change.tax.query is not None and change.tax.query.casefold() not in source.casefold():
            raise UserProblem("Уточните название налогового профиля.")
    if intent.client is not None and intent.client.casefold() not in source.casefold():
        if context is not None and context.client is not None and intent.client.casefold() == context.client.casefold():
            # A repeated known client is not a request to change it. Keep its stable
            # resolution; a new ungrounded name is still rejected.
            intent = InvoiceIntent.model_validate({**intent.model_dump(), "client": None})
        else:
            raise UserProblem("Не удалось однозначно определить компанию. Уточните её название.")
    for field in ("invoice_date", "service_period", "tax", "previous"):
        value = getattr(intent, field)
        if value is not None and value.evidence.casefold() not in source.casefold():
            updates = {}
            if context is not None:
                if field == "tax" and TaxRequest(mode=value.mode, query=value.query) == context.tax:
                    updates["tax"] = None
                elif field == "previous" and value.kind == context.previous:
                    updates["previous"] = None
                elif field == "service_period" and context.service_period is not None and (
                        value.month, value.year) == (context.service_period.month, context.service_period.year):
                    updates["service_period"] = None
                elif field == "invoice_date" and context.invoice_date is not None and (
                        value.day, value.month, value.year) == (context.invoice_date.day, context.invoice_date.month, context.invoice_date.year):
                    updates["invoice_date"] = None
            if not updates:
                raise UserProblem("Не удалось безопасно понять правку. Уточните изменяемое поле.")
            # Repeated known values are no-op fields. This does not authorize any
            # ungrounded change; edited fields still require current-message evidence.
            intent = InvoiceIntent.model_validate({**intent.model_dump(), **updates})
    for service in intent.services:
        if service.query.casefold() not in source.casefold():
            raise UserProblem("Не удалось однозначно определить услугу. Уточните название услуги.")
        if service.quantity_evidence is not None and service.quantity_evidence.casefold() not in source.casefold():
            raise UserProblem("Уточните количество для услуги.")
    if intent.quantity_evidence is not None and intent.quantity_evidence.casefold() not in source.casefold():
        raise UserProblem("Уточните количество в строке счёта.")
    for field in ("invoice_date", "service_period"):
        value = getattr(intent, field)
        if value is not None and value.year is not None:
            years = re.findall(r"\b(?:20\d{2}|2100)\b", value.evidence)
            if years != [str(value.year)]:
                known = (context.invoice_date if field == "invoice_date" else context.service_period) if context else None
                if not years and value.year == (known.year if known else date.today().year):
                    part = type(value).model_validate({**value.model_dump(), "year": None})
                    intent = InvoiceIntent.model_validate({**intent.model_dump(), field: part})
                else:
                    raise UserProblem("Уточните год: модель не может придумывать его из отсутствующего текста.")
    return intent


def merge_intent(draft: InvoiceDraft, intent: InvoiceIntent, *, today: date | None = None) -> InvoiceDraft:
    draft, intent = InvoiceDraft.model_validate(draft), InvoiceIntent.model_validate(intent)
    today = today or date.today()
    values = draft.model_dump()
    values["services"] = draft.services
    values["preview_overrides"] = draft.preview_overrides
    values["initial_overrides"] = draft.initial_overrides
    if intent.client is not None or intent.services:
        values["initial_overrides"] = ()
    if intent.initial_overrides:
        if intent.action != "create" or not intent.services:
            raise UserProblem("Первоначальные суммы должны относиться к явно указанным услугам нового счёта.")
        values["initial_overrides"] = intent.initial_overrides
    if intent.client is not None:
        values["client"] = intent.client
    if (intent.client is not None and draft.client is not None and intent.client.casefold() != draft.client.casefold()
            or intent.services or intent.previous is not None):
        values["preview_overrides"] = ()
    if intent.invoice_date is not None:
        values["legacy_period"] = False
        part = intent.invoice_date
        old = draft.invoice_date or today
        incomplete = draft.incomplete_date
        month = part.month or (incomplete.month if incomplete else None) or old.month
        year = part.year or (incomplete.year if incomplete else None) or old.year
        day = part.day or (draft.invoice_date.day if draft.invoice_date is not None else None)
        if day is None:
            values["invoice_date"] = None
            values["incomplete_date"] = part
        else:
            try:
                values["invoice_date"] = date(year, month, day)
            except ValueError:
                raise UserProblem("Такой даты нет в календаре. Уточните дату счёта.") from None
            values["incomplete_date"] = None
    if intent.service_period is not None:
        part = intent.service_period
        values["service_period"] = ServicePeriod(year=part.year or (draft.service_period.year if draft.service_period else today.year),
                                                month=part.month)
    if intent.previous is not None:
        values["previous"] = intent.previous.kind
        # Explicit new selections take priority; otherwise request a fresh previous hint.
        if not intent.services:
            values["services"] = ()
        if intent.tax is None:
            values["tax"] = TaxRequest()
    # An empty selection never deletes rows, regardless of the redundant mode
    # emitted by the model. Only selected services authorize a line change.
    if intent.services and intent.lines_mode == "replace":
        target = intent.line_number or draft.unresolved_line
        if target is None and len(draft.services) == len(intent.services) == 1:
            target = 1
        if target is None and len(draft.services) > 1 and len(intent.services) == 1:
            raise UserProblem("В счёте несколько услуг. Уточните номер заменяемой строки; остальные строки сохранены.")
        if target is not None:
            if target > len(draft.services) or len(intent.services) != 1:
                raise UserProblem("Уточните номер изменяемой строки и одну услугу.")
            replacement = ServiceSelection(query=intent.services[0].query,
                quantity=intent.services[0].quantity if intent.services[0].quantity is not None else draft.services[target-1].quantity)
            values["services"] = draft.services[:target-1] + (replacement,) + draft.services[target:]
        else:
            values["services"] = tuple(ServiceSelection(query=s.query, quantity=s.quantity) for s in intent.services)
        values["unresolved_line"] = None
    elif intent.services and intent.lines_mode == "add":
        if not draft.services and intent.action != "create":
            raise UserProblem("Сначала подготовьте исходные услуги, затем добавьте строку.")
        values["services"] = draft.services + tuple(ServiceSelection(query=s.query, quantity=s.quantity) for s in intent.services)
    if intent.quantity is not None:
        services = tuple(values["services"])
        target = intent.line_number or (1 if len(services) == 1 else None)
        if target is None or target > len(services):
            raise UserProblem("Уточните номер строки, в которой изменить количество.")
        services = list(services)
        services[target-1] = ServiceSelection(query=services[target-1].query, quantity=intent.quantity)
        values["services"] = tuple(services)
    if intent.tax is not None:
        values["tax"] = TaxRequest(mode=intent.tax.mode, query=intent.tax.query)
    initial_edit = bool(values["initial_overrides"] and not values["preview_overrides"])
    edits = {e.line_number: e for e in (values["initial_overrides"] if initial_edit else values["preview_overrides"])}
    seen = {}
    for change in intent.preview_changes:
        count = len(values["services"])
        if not count:
            raise UserProblem("Сначала подготовьте preview, затем укажите цену, НДС или название строки.")
        if change.line_number is None and (change.price is not None or change.amount is not None or change.description is not None) and count > 1:
            raise UserProblem("В счёте несколько строк. Укажите номер строки для изменения цены или названия.")
        targets = (change.line_number,) if change.line_number is not None else tuple(range(1, count + 1))
        for number in targets:
            if number > count:
                raise UserProblem("В preview нет такой строки. Уточните её номер.")
            updates = {k: getattr(change, k) for k in ("price", "amount", "description", "tax") if getattr(change, k) is not None}
            if change.currency is not None:
                updates["currency"] = change.currency
            if change.price is not None:
                updates["amount"] = None
            if change.amount is not None:
                updates["price"] = None
            for key in updates:
                if (number, key) in seen and seen[number, key] != updates[key]:
                    raise UserProblem("Для одной строки указано несколько изменений одного поля. Уточните одно значение.")
                seen[number, key] = updates[key]
            previous = edits.get(number)
            edits[number] = PreviewLineOverride(**{**(previous.model_dump() if previous else {"line_number": number}), **updates})
        if change.tax is not None:
            values["tax"] = TaxRequest()
    values["initial_overrides" if initial_edit else "preview_overrides"] = tuple(edits[n] for n in sorted(edits))
    if len(values["services"]) > 20:
        raise UserProblem("В одном счёте поддерживается до 20 строк. Сократите список услуг; текущие данные сохранены.")
    # model_dump is a serialization boundary; immediately revalidate the edited draft.
    return InvoiceDraft.model_validate(values)


_ORDINAL_STEMS = (
    (1, r"перв"), (2, r"втор"), (3, r"трет"), (4, r"четв[её]рт"), (5, r"пят"),
    (6, r"шест"), (7, r"седьм"), (8, r"восьм"), (9, r"девят"), (10, r"десят"),
    (11, r"одиннадцат"), (12, r"двенадцат"), (13, r"тринадцат"), (14, r"четырнадцат"),
    (15, r"пятнадцат"), (16, r"шестнадцат"), (17, r"семнадцат"), (18, r"восемнадцат"),
    (19, r"девятнадцат"), (20, r"двадцат"),
)


def _target_parts(target: str) -> tuple[int | None, str]:
    text = target.casefold().replace("ё", "е")
    # Structured extraction may include the instruction after a valid row reference.
    # That instruction is never part of the service name being matched.
    text = re.split(r"\b(?:поменя\w*|измени\w*|исправ\w*|сдела\w*|постав\w*|удал\w*|убер\w*|остав\w*|количеств\w*|цен\w*)\b", text, maxsplit=1)[0]
    number_match = re.search(r"(?:строк\w*|пункт\w*|позици\w*|элемент\w*|номер|№)\s*[:#№-]?\s*(\d+)|(\d+)\s*(?:строк\w*|пункт\w*|позици\w*)", text)
    number = int(next(value for value in number_match.groups() if value)) if number_match else None
    if number is None:
        for value, stem in _ORDINAL_STEMS:
            if re.search(r"\b" + stem + r"[а-яе]*\b", text):
                number = value
                break
    name = text
    name = re.sub(r"(?:строк\w*|пункт\w*|позици\w*|элемент\w*)\s*(?:номер\s*)?(?:№\s*)?\d+", " ", name)
    name = re.sub(r"\d+\s*(?:строк\w*|пункт\w*|позици\w*)", " ", name)
    name = re.sub(r"\b(?:строк\w*|пункт\w*|позици\w*|элемент\w*|номер|№)\b", " ", name)
    for _, stem in _ORDINAL_STEMS:
        name = re.sub(r"\b" + stem + r"[а-яе]*\b", " ", name)
    name = re.sub(r"\b(?:и|или|в|во|на|пожалуйста|удали|удалить|изменить|измени|поменяй|исправь|строку|пункт|услуг\w*)\b", " ", name)
    name = re.sub(r"[^\w]+", " ", name, flags=re.UNICODE)
    return number, " ".join(name.split())


def _resolve_draft_target(target: str, prepared: PreparedInvoice, line_ids: tuple[str, ...], command: InvoiceCommand) -> str:
    number, name = _target_parts(target)
    number_id = line_ids[number - 1] if number is not None and 1 <= number <= len(line_ids) else None
    if number is not None and number_id is None:
        raise UserProblem(f"В текущем preview нет строки {number}.")
    if not name:
        if number_id is None:
            raise UserProblem("Укажите номер или название строки, которую нужно изменить.")
        return number_id
    stop = {"услуга", "услуги", "service", "services", "строка", "строки", "пункт", "позиция",
            "изменить", "измени", "исправь", "поставь", "сделай", "оставь", "удали", "удалить",
            "пожалуйста", "количество", "штук", "штуки", "шт", "цена", "цену", "ндс", "налог"}

    def tokens(value: str) -> list[str]:
        value = value.casefold().replace("ё", "е")
        value = re.sub(r"[^\w]+", " ", value, flags=re.UNICODE)
        return [token for token in value.split() if token not in stop and not token.isdecimal()]

    def score(left: str, right: str) -> float:
        wanted, actual = tokens(left), tokens(right)
        if not wanted or not actual:
            return 0.0
        similarities = [max(SequenceMatcher(None, word, candidate).ratio()
                            for candidate in actual) for word in wanted]
        return sum(similarities) / len(similarities)

    ranked: list[tuple[float, str]] = []
    exact_matches: set[str] = set()
    for index, line in enumerate(prepared.preview.lines):
        labels = [line.description]
        if index < len(command.services):
            labels.append(command.services[index].query)
        normalized_labels = {re.sub(r"[^\w]+", " ", label.casefold().replace("ё", "е")).strip()
                             for label in labels}
        if any(name == label or len(name) >= 4 and (name in label or label in name)
               for label in normalized_labels):
            exact_matches.add(line_ids[index])
            continue
        best = max((score(name, label) for label in labels), default=0.0)
        # Approximate matching only proposes an identity when the best candidate is
        # clear. Similar rows remain ambiguous and must be selected explicitly.
        if best >= 0.62:
            ranked.append((best, line_ids[index]))
    if exact_matches:
        candidates = exact_matches
        ranked = []
    else:
        ranked.sort(reverse=True)
        candidates = {line_id for value, line_id in ranked
                      if value >= 0.62 and (not ranked or ranked[0][0] - value < 0.10)}
    if number_id is not None:
        if candidates and number_id not in candidates:
            raise UserProblem("Номер строки и название указывают на разные позиции. Уточните цель правки.")
        if not candidates:
            raise UserProblem("Название в ссылке не совпало с указанной строкой preview.")
        return number_id
    if len(candidates) == 1:
        return next(iter(candidates))
    if not candidates:
        raise UserProblem(f"В preview не нашёл услугу «{target.strip()}».")
    numbers = [str(index + 1) for index, line_id in enumerate(line_ids) if line_id in candidates]
    raise UserProblem(f"Название совпадает с несколькими строками ({', '.join(numbers)}). Укажите номер.")


def apply_draft_mutations(prepared: PreparedInvoice, command: InvoiceCommand,
                          line_ids: tuple[str, ...], origins: dict[str, PreviewLineOrigin],
                          mutations: tuple[IntentDraftMutation, ...]):
    """Resolve a batch against one displayed preview, then build a new typed command."""
    if len(line_ids) != len(prepared.preview.lines) or len(command.services) != len(line_ids):
        raise UserProblem("Текущий preview изменился. Откройте последнее сообщение и повторите правку.")
    if len(set(line_ids)) != len(line_ids):
        raise UserProblem("Не удалось сохранить идентичность строк preview. Подготовьте его заново.")
    states = {line_id: {"query": command.services[index].query,
                        "quantity": command.services[index].quantity or prepared.preview.lines[index].quantity,
                        "origin": origins.get(line_id), "new": False, "override": {}}
              for index, line_id in enumerate(line_ids)}
    order = list(line_ids)
    deletes: set[str] = set()
    retained: set[str] | None = None
    issues = []
    changed_fields: dict[tuple[str, str], object] = {}

    expanded = []
    for mutation in mutations:
        if (mutation.kind == "delete" and any(other.kind == "retain" for other in mutations)
                and re.fullmatch(r"\s*остальн\w*\s*(?:удал\w*|убер\w*)\s*", mutation.target or "", re.I)):
            # "Leave only X, delete the rest" is already represented by retain.
            continue
        # One spoken command often refers to several displayed items. Expand only
        # explicit numeric lists, never a guessed range or a service-name match.
        grouped = re.fullmatch(r"\s*(?:пункт\w*|строк\w*|позици\w*)\s*(\d+(?:\s*(?:,|и)\s*(?:(?:пункт\w*|строк\w*|позици\w*)\s*)?\d+)+)\s*", mutation.target or "", re.I)
        if mutation.kind in ("delete", "retain") and grouped:
            numbers = [int(number) for number in re.findall(r"\d+", grouped[1])]
            expanded.extend(IntentDraftMutation(kind=mutation.kind, target=f"пункт {number}") for number in numbers)
        else:
            expanded.append(mutation)

    for mutation in expanded:
        if mutation.kind == "add":
            line_id = "draft:" + uuid4().hex
            states[line_id] = {"query": mutation.service, "quantity": mutation.quantity,
                               "origin": None, "new": True, "override": {key: getattr(mutation, key)
                                   for key in ("price", "currency", "tax") if getattr(mutation, key) is not None}}
            order.append(line_id)
            continue
        try:
            line_id = _resolve_draft_target(mutation.target, prepared, line_ids, command)
        except UserProblem as exc:
            issues.append(str(exc))
            continue
        state = states[line_id]
        if mutation.kind == "delete":
            deletes.add(line_id)
            continue
        if mutation.kind == "retain":
            if retained is None:
                retained = set()
            retained.add(line_id)
            continue
        if mutation.kind == "replace":
            old_index = order.index(line_id)
            replacement_id = "draft:" + uuid4().hex
            states[replacement_id] = {"query": mutation.service,
                "quantity": mutation.quantity or state["quantity"], "origin": None, "new": True,
                "override": {key: getattr(mutation, key) for key in ("price", "currency", "tax")
                    if getattr(mutation, key) is not None}}
            order[old_index] = replacement_id
            deletes.add(line_id)
            continue
        if line_id in deletes:
            raise UserProblem("Одну строку одновременно удаляют и редактируют. Уточните список правок.")
        updates = {"quantity": mutation.quantity}
        for key in ("price", "currency", "tax", "description"):
            value = getattr(mutation, key)
            if value is not None:
                updates[key] = value
        for key, value in updates.items():
            if value is None:
                continue
            identity = (line_id, key)
            if identity in changed_fields and changed_fields[identity] != value:
                raise UserProblem("Для одной строки указаны разные значения одного поля. Уточните правку.")
            changed_fields[identity] = value
            if key == "quantity":
                state["quantity"] = value
            else:
                state["override"][key] = value

    if retained is not None:
        # A keep-only request is mass deletion if misresolved, so unlike ordinary
        # edits its unresolved target must fail the whole batch below.
        if issues:
            raise UserProblem("Не удалось однозначно определить все пункты, которые нужно оставить. Preview не изменён.")
        order = [line_id for line_id in order
                 if (line_id in retained or states[line_id]["new"]) and line_id not in deletes]
    else:
        order = [line_id for line_id in order if line_id not in deletes]
    if deletes.intersection(line_id for line_id, _ in changed_fields):
        raise UserProblem("Одну строку одновременно удаляют и редактируют. Уточните список правок.")
    if not order:
        raise UserProblem("В счёте должна остаться хотя бы одна строка.")
    if len(order) > 20:
        raise UserProblem("В одном счёте поддерживается до 20 строк.")

    old_override = {edit.line_number: edit for edit in prepared.preview.user_overrides}
    next_ids, next_origins, next_services, next_selected, merged = [], {}, [], {}, {}
    for new_number, line_id in enumerate(order, 1):
        state = states[line_id]
        next_ids.append(line_id)
        if state["origin"] is not None:
            next_origins[line_id] = state["origin"]
            next_selected[new_number] = state["origin"].service_id
        elif not state["new"]:
            original_index = line_ids.index(line_id)
            line = prepared.preview.lines[original_index]
            next_selected[new_number] = line.service_id
            if line.source_id is not None and line.source_line_number is not None:
                next_origins[line_id] = PreviewLineOrigin(service_id=line.service_id, source_id=line.source_id,
                    source_line_number=line.source_line_number)
        next_services.append(ServiceSelection(query=state["query"], quantity=state["quantity"]))
        fields = {}
        if line_id in line_ids:
            old = line_ids.index(line_id)
            prior = old_override.get(old + 1)
            if prior is not None:
                fields = {key: getattr(prior, key) for key in ("price", "amount", "currency", "description", "tax")
                          if getattr(prior, key) is not None}
        fields.update(state["override"])
        if fields:
            # Amount and unit price are mutually exclusive; the latest explicit one wins.
            if "price" in state["override"]:
                fields.pop("amount", None)
            if "amount" in state["override"]:
                fields.pop("price", None)
            merged[new_number] = PreviewLineOverride(line_number=new_number, **fields)
    next_command = InvoiceCommand(**{**command.model_dump(), "services": tuple(next_services),
        "preview_overrides": tuple(merged[number] for number in sorted(merged)), "initial_overrides": ()})
    return next_command, tuple(next_ids), next_origins, next_selected, tuple(issues)
