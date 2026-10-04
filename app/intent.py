"""Untrusted language intent and deterministic edits of a bounded invoice draft."""
import re
from datetime import date
from typing import Annotated, Literal

from pydantic import Field, WithJsonSchema, model_validator

from app.domain import InvoiceCommand, Quantity, ServicePeriod, ServiceSelection, StrictModel, TaxRequest, UserProblem

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


class InvoiceIntent(StrictModel):
    # Required nullable fields deliberately match the Structured Outputs contract.
    action: Literal["create", "edit", "cancel", "clarify", "reject"]
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

    @model_validator(mode="after")
    def consistent(self):
        if self.services and self.lines_mode == "keep":
            raise ValueError("Line action requires service selections")
        if (self.quantity is None) != (self.quantity_evidence is None):
            raise ValueError("Quantity requires evidence")
        if self.services and self.line_number is not None and self.lines_mode == "add":
            raise ValueError("Adding a line cannot replace an existing line")
        if self.action in ("cancel", "reject") and any((self.client, self.invoice_date, self.service_period,
                                                       self.services, self.tax, self.previous, self.quantity, self.line_number)):
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

    @classmethod
    def from_command(cls, command: InvoiceCommand):
        return cls(client=command.client, invoice_date=command.invoice_date, service_period=command.period,
                   services=command.services, tax=command.tax, previous=command.previous,
                   legacy_period=command.legacy_period or (command.invoice_date is None and command.year is not None))

    def command(self) -> InvoiceCommand:
        if self.client is None:
            raise UserProblem("Укажите компанию для счёта. Остальные параметры сохранены.")
        if self.incomplete_date is not None:
            raise UserProblem("Укажите число для даты счёта. Остальные параметры сохранены.")
        return InvoiceCommand(client=self.client, invoice_date=self.invoice_date or date.today(),
                              service_period=self.service_period, services=self.services,
                              tax=self.tax, previous=self.previous, legacy_period=self.legacy_period)


def ground_intent(intent: InvoiceIntent, source: str, context: InvoiceDraft | None = None) -> InvoiceIntent:
    intent = InvoiceIntent.model_validate(intent)
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
    if intent.client is not None:
        values["client"] = intent.client
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
    if len(values["services"]) > 20:
        raise UserProblem("В одном счёте поддерживается до 20 строк. Сократите список услуг; текущие данные сохранены.")
    # model_dump is a serialization boundary; immediately revalidate the edited draft.
    return InvoiceDraft.model_validate(values)
