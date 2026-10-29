import hashlib
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Annotated, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True,
                              hide_input_in_errors=True, revalidate_instances="always",
                              validate_by_name=True, allow_inf_nan=False)


class ExternalModel(StrictModel):
    # Partial views of versioned provider envelopes: validate consumed fields.
    model_config = ConfigDict(extra="ignore")


Money = Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=2)]
Quantity = Annotated[Decimal, Field(gt=0, le=1000000, decimal_places=3)]
Label = Annotated[str, Field(min_length=1, max_length=500, pattern=r"^[^\x00-\x1f]+$")]
InvoiceDate = Annotated[date, Field(ge=date(2000, 1, 1), le=date(2100, 12, 31))]


class ServicePeriod(StrictModel):
    year: int = Field(ge=2000, le=2100)
    month: int = Field(ge=1, le=12)


class ServiceSelection(StrictModel):
    query: Label
    quantity: Quantity | None = None


class ResolvedServiceSelection(StrictModel):
    service_id: Label
    quantity: Quantity | None = None


class ResolvedService(StrictModel):
    service_id: Label
    display_name: Label
    code: str | None = Field(default=None, max_length=100)


class ServiceCandidates(StrictModel):
    candidates: tuple[ResolvedService, ...] = Field(min_length=1, max_length=5)

    @model_validator(mode="after")
    def unique(self):
        if len({s.service_id for s in self.candidates}) != len(self.candidates):
            raise ValueError("Duplicate service choices")
        return self


class TaxRequest(StrictModel):
    mode: Literal["default", "with_tax", "without_tax", "profile"] = "default"
    query: Label | None = None

    @model_validator(mode="after")
    def profile_query(self):
        if (self.mode == "profile") != (self.query is not None):
            raise ValueError("A named tax profile requires a query")
        return self


class TaxProfile(StrictModel):
    tax_id: Label
    label: Label
    treatment: Literal["standard", "zero_rated", "exempt", "outside_scope"]
    rate: Decimal = Field(ge=0, le=100, decimal_places=3)

    @model_validator(mode="after")
    def valid_rate(self):
        if (self.treatment == "standard") != (self.rate > 0):
            raise ValueError("Tax treatment and rate disagree")
        return self


class PreviewTaxRequest(StrictModel):
    mode: Literal["rate", "without_tax", "with_tax", "profile"]
    rate: Decimal | None = Field(default=None, ge=0, le=100, decimal_places=3)
    query: Label | None = None

    @model_validator(mode="after")
    def explicit_choice(self):
        if (self.mode == "rate") != (self.rate is not None) or (self.mode == "profile") != (self.query is not None):
            raise ValueError("Tax choice requires its exact rate or profile name")
        return self


class PreviewLineOverride(StrictModel):
    line_number: int = Field(ge=1, le=20)
    price: Money | None = None
    amount: Money | None = None
    currency: Literal["AED", "USD", "EUR", "GBP", "RUB"] | None = None
    description: Label | None = None
    tax: PreviewTaxRequest | None = None

    @model_validator(mode="after")
    def nonempty(self):
        if self.price is not None and self.amount is not None:
            raise ValueError("Choose a unit price or a net line amount")
        if self.currency is not None and self.price is None and self.amount is None:
            raise ValueError("Currency requires an explicit amount")
        if self.price is None and self.amount is None and self.description is None and self.tax is None:
            raise ValueError("Empty preview override")
        return self


class ResolvedPreviewLineOverride(PreviewLineOverride):
    source_line_number: int | None = Field(default=None, ge=1, le=2**63 - 1)
    source_id: Label | None = None

    def user_edit(self):
        return PreviewLineOverride(**self.model_dump(exclude={"source_line_number", "source_id"}))


def tax_matches(request: PreviewTaxRequest, profile: TaxProfile) -> bool:
    if request.mode == "rate":
        return profile.rate == request.rate and profile.treatment == ("standard" if request.rate else "zero_rated")
    if request.mode == "without_tax":
        return profile.treatment == "exempt"
    if request.mode == "with_tax":
        return profile.rate > 0
    return " ".join(profile.label.split()).casefold() == " ".join(request.query.split()).casefold()


class PartyDetails(StrictModel):
    name: Label
    address: Label | None = None
    tax_number: Label | None = None
    phone: Label | None = None
    email: Label | None = None


class BankDetails(StrictModel):
    bank: Label
    iban: Label
    swift: Label
    beneficiary: Label


class PaymentTerms(StrictModel):
    payment: Label
    delivery: Label


class HistoricalSource(StrictModel):
    source_id: Label
    source_number: Label
    source_date: InvoiceDate


class HistoricalProposal(StrictModel):
    source_id: Label
    source_number: Label
    source_date: InvoiceDate
    contract_id: Label
    contract_name: Label
    entity_id: Label
    contract_entity_id: Label | None = None
    contract_entity_name: Label | None = None
    sources: tuple[HistoricalSource, ...] = Field(default=(), max_length=20)
    # This provenance is preview-only; it is never a create payload/default policy.
    policy: Literal["historical_proposal_readonly"] = "historical_proposal_readonly"

    @model_validator(mode="after")
    def paired_entity_review(self):
        if self.sources and (len({s.source_id for s in self.sources}) != len(self.sources)
                or self.sources[0].source_id != self.source_id
                or self.sources[0].source_number != self.source_number or self.sources[0].source_date != self.source_date):
            raise ValueError("Invalid historical source set")
        if (self.contract_entity_id is None) != (self.contract_entity_name is None):
            raise ValueError("Contract entity review requires both identity and display name")
        if self.contract_entity_id == self.entity_id:
            raise ValueError("An entity review must represent an actual mismatch")
        return self


class InvoiceLine(StrictModel):
    service_id: Label
    description: Label
    quantity: Quantity
    uom: Label
    price: Money
    tax: TaxProfile
    subtotal: Money
    tax_amount: Money
    total: Money
    source_line_number: int | None = Field(default=None, ge=1, le=2**63 - 1)
    source_id: Label | None = None

    @model_validator(mode="after")
    def correct_totals(self):
        # Validation of provider arithmetic, not an alternative rendering calculation.
        subtotal = (self.quantity * self.price).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        tax = (subtotal * self.tax.rate / 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if (self.subtotal, self.tax_amount, self.total) != (subtotal, tax, subtotal + tax):
            raise ValueError("Inconsistent invoice line amounts")
        return self

    def overridden(self, edit: PreviewLineOverride, tax: TaxProfile | None = None):
        if edit.tax is not None and (tax is None or not tax_matches(edit.tax, tax)):
            raise UserProblem("Налоговая правка не подтверждена профилем 1С.")
        price = self.price if edit.price is None else edit.price
        if edit.amount is not None:
            price = (edit.amount / self.quantity).quantize(Decimal(".01"), rounding=ROUND_HALF_UP)
            if (price * self.quantity).quantize(Decimal(".01"), rounding=ROUND_HALF_UP) != edit.amount:
                raise UserProblem("Сумма строки не представима с этим количеством и ценой до копейки. Уточните количество или сумму.")
        profile = tax or self.tax
        subtotal = (self.quantity * price).quantize(Decimal(".01"), rounding=ROUND_HALF_UP)
        amount = (subtotal * profile.rate / 100).quantize(Decimal(".01"), rounding=ROUND_HALF_UP)
        try:
            return InvoiceLine(**{**self.model_dump(), "price": price, "tax": profile,
                "description": edit.description if edit.description is not None else self.description,
                "subtotal": subtotal, "tax_amount": amount, "total": subtotal + amount})
        except ValueError:
            raise UserProblem("Изменённая цена или налог дают недопустимую сумму. Проверьте строку.") from None


class InvoicePreview(StrictModel):
    invoice_date: InvoiceDate
    supply_date: InvoiceDate | None = None
    service_period: ServicePeriod | None = None
    currency: Literal["AED", "USD", "EUR", "GBP", "RUB"]
    issuer: PartyDetails
    recipient: PartyDetails
    bank: BankDetails | None
    terms: PaymentTerms | None
    lines: tuple[InvoiceLine, ...] = Field(min_length=1, max_length=20)
    subtotal: Money
    tax_amount: Money
    total: Money
    amount_in_words: Label | None = None
    reference: Label
    previous_reference: Label | None = None
    historical_proposal: HistoricalProposal | None = None
    user_overrides: tuple[PreviewLineOverride, ...] = Field(default=(), max_length=20)

    @model_validator(mode="after")
    def correct_totals(self):
        if self.historical_proposal is not None and self.historical_proposal.sources:
            known_sources = {source.source_id for source in self.historical_proposal.sources}
            if any(line.source_id not in known_sources for line in self.lines):
                raise ValueError("Line source is outside the historical source set")
        if len({e.line_number for e in self.user_overrides}) != len(self.user_overrides):
            raise ValueError("Duplicate manual row override")
        for edit in self.user_overrides:
            if edit.line_number > len(self.lines):
                raise ValueError("Manual edit outside preview")
            line = self.lines[edit.line_number - 1]
            if edit.currency is not None and edit.currency != self.currency:
                raise ValueError("User amount currency mismatch")
            if (edit.price is not None and edit.price != line.price
                    or edit.amount is not None and edit.amount != line.subtotal
                    or edit.description is not None and edit.description != line.description
                    or edit.tax is not None and not tax_matches(edit.tax, line.tax)):
                raise ValueError("Preview does not reflect the explicit user edit")
        if self.historical_proposal is None and (self.bank is None or self.terms is None
                or self.supply_date is None or self.amount_in_words is None
                or any(v is None for party in (self.issuer, self.recipient)
                       for v in (party.address, party.tax_number, party.phone, party.email))):
            raise ValueError("A non-historical invoice requires complete details")
        if (self.subtotal, self.tax_amount, self.total) != (
            sum((line.subtotal for line in self.lines), Decimal(0)),
            sum((line.tax_amount for line in self.lines), Decimal(0)),
            sum((line.total for line in self.lines), Decimal(0)),
        ):
            raise ValueError("Inconsistent invoice totals")
        return self

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.model_dump_json().encode()).hexdigest()


class InvoiceCommand(StrictModel):
    action: Literal["create_invoice"] = "create_invoice"
    client: str = Field(min_length=2, max_length=200)
    # year/month are accepted for the existing period command contract only.
    year: int | None = Field(default=None, ge=2000, le=2100)
    month: int | None = Field(default=None, ge=1, le=12)
    invoice_date: InvoiceDate | None = None
    service_period: ServicePeriod | None = None
    services: tuple[ServiceSelection, ...] = Field(default=(), max_length=20)
    tax: TaxRequest = TaxRequest()
    previous: Literal["none", "last", "previous_month", "usual"] = "none"
    legacy_period: bool = False
    preview_overrides: tuple[PreviewLineOverride, ...] = Field(default=(), max_length=20)
    initial_overrides: tuple[PreviewLineOverride, ...] = Field(default=(), max_length=20)

    @model_validator(mode="after")
    def valid_period(self):
        if self.initial_overrides and (self.preview_overrides or not self.services
                or len({e.line_number for e in self.initial_overrides}) != len(self.initial_overrides)
                or any(e.line_number > len(self.services) for e in self.initial_overrides)):
            raise ValueError("Initial amounts require distinct requested service lines")
        if len({e.line_number for e in self.preview_overrides}) != len(self.preview_overrides):
            raise ValueError("Duplicate override row")
        if (self.year is None) != (self.month is None):
            raise ValueError("Incomplete service period")
        if self.service_period is not None and self.year is not None:
            if self.service_period != ServicePeriod(year=self.year, month=self.month):
                raise ValueError("Conflicting service period")
        return self

    @property
    def period(self) -> ServicePeriod | None:
        return self.service_period or (ServicePeriod(year=self.year, month=self.month)
                                       if self.year is not None else None)

    @field_validator("client")
    @classmethod
    def clean_client(cls, value: str) -> str:
        if not value.strip() or any(ord(char) < 32 for char in value):
            raise ValueError("Invalid client name")
        return value.strip()


class ResolvedClient(StrictModel):
    client_id: str = Field(min_length=1, max_length=200)
    display_name: str = Field(min_length=1, max_length=200)


class ClientCandidate(ResolvedClient):
    full_name: Label
    tax_number: Label | None = None


class ClientCandidates(StrictModel):
    candidates: tuple[ClientCandidate, ...] = Field(min_length=1, max_length=19)

    @model_validator(mode="after")
    def unique_ids(self):
        if len({c.client_id for c in self.candidates}) != len(self.candidates):
            raise ValueError("Duplicate candidate identity")
        return self


class ResolvedInvoiceCommand(StrictModel):
    client_id: str = Field(min_length=1, max_length=200)
    year: int | None = Field(default=None, ge=2000, le=2100)
    month: int | None = Field(default=None, ge=1, le=12)
    invoice_date: InvoiceDate | None = None
    service_period: ServicePeriod | None = None
    services: tuple[ResolvedServiceSelection, ...] = Field(default=(), max_length=20)
    tax: TaxRequest = TaxRequest()
    previous: Literal["none", "last", "previous_month", "usual"] = "none"
    legacy_period: bool = False
    preview_overrides: tuple[ResolvedPreviewLineOverride, ...] = Field(default=(), max_length=20)
    preview_source_id: Label | None = None

    @model_validator(mode="after")
    def valid_period(self):
        if (self.year is None) != (self.month is None):
            raise ValueError("Incomplete service period")
        if self.service_period is not None and self.year is not None:
            if self.service_period != ServicePeriod(year=self.year, month=self.month):
                raise ValueError("Conflicting service period")
        if self.legacy_period and self.service_period is None:
            raise ValueError("Legacy billing identity requires a service period")
        return self


class BillingBasis(StrictModel):
    # Opaque, resolved by 1C: organisation, client, contract, service and period.
    # The backend owns uniqueness and must revalidate the basis before writing.
    key: str = Field(min_length=1, max_length=200)
    client_id: str = Field(min_length=1, max_length=200)
    revision: str = Field(min_length=1, max_length=200)
    preview: InvoicePreview | None = None


class PreparedInvoice(StrictModel):
    request: ResolvedInvoiceCommand
    basis: BillingBasis
    display_name: str = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def same_client(self):
        if self.request.client_id != self.basis.client_id:
            raise ValueError("Resolved client does not match billing basis")
        if self.basis.preview is None:
            raise ValueError("A complete preview is required")
        if tuple(e.user_edit() for e in self.request.preview_overrides) != self.preview.user_overrides:
            raise ValueError("Provider dropped or changed explicit preview edits")
        if self.basis.preview.invoice_date != self.request.invoice_date:
            raise ValueError("Preview invoice date differs from request")
        if self.basis.preview.service_period != self.request.service_period:
            raise ValueError("Preview service period differs from request")
        if self.request.services:
            if len(self.request.services) != len(self.preview.lines):
                raise ValueError("Preview line count differs from request")
            for selected, line in zip(self.request.services, self.preview.lines):
                if (selected.service_id != line.service_id or
                        selected.quantity is not None and selected.quantity != line.quantity):
                    raise ValueError("Preview service differs from request")
        for line in self.preview.lines:
            if self.request.tax.mode == "with_tax" and line.tax.rate == 0:
                raise ValueError("Preview tax differs from request")
            if self.request.tax.mode == "without_tax" and line.tax.rate != 0:
                raise ValueError("Preview tax differs from request")
        return self

    @property
    def preview(self) -> InvoicePreview:
        return self.basis.preview

    @property
    def operation_id(self) -> str:
        # Revision is intentionally excluded: changed data must not open a new operation.
        return hashlib.sha256(("invoice:v1:" + self.basis.key).encode()).hexdigest()


class Invoice(StrictModel):
    document_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,100}$")
    posted: bool
    client_id: str = Field(min_length=1, max_length=200)
    basis_key: str = Field(min_length=1, max_length=200)
    revision: str = Field(min_length=1, max_length=200)
    preview_digest: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")


class OperationState(StrictModel):
    operation_id: str = Field(min_length=1, max_length=200)
    status: Literal["not_started", "draft", "posted", "unknown"]
    invoice: Invoice | None = None

    @model_validator(mode="after")
    def consistent(self):
        if self.status in ("draft", "posted"):
            if self.invoice is None or self.invoice.posted != (self.status == "posted"):
                raise ValueError("Inconsistent operation state")
        elif self.invoice is not None:
            raise ValueError("Unverified operation cannot carry a document")
        return self


class PdfDocument(StrictModel):
    content: bytes = Field(min_length=20, max_length=10_000_000, repr=False)

    @field_validator("content")
    @classmethod
    def pdf_signature(cls, value: bytes) -> bytes:
        if not value.startswith(b"%PDF-") or not value.rstrip().endswith(b"%%EOF"):
            raise ValueError("Invalid PDF")
        return value


class InvoiceResult(StrictModel):
    invoice: Invoice
    pdf: PdfDocument


class UserProblem(Exception):
    """Expected clarification, with an application-controlled safe message."""


class ClientChoiceRequired(UserProblem):
    def __init__(self, candidates: ClientCandidates):
        self.choices = ClientCandidates.model_validate(candidates)
        super().__init__("Нужно выбрать конкретную компанию из найденных записей.")


class ServiceProblem(UserProblem):
    def __init__(self, message: str, line_number: int):
        self.line_number = line_number
        super().__init__(message)


class ServiceChoiceRequired(UserProblem):
    def __init__(self, choices: ServiceCandidates, line_number: int = 1):
        self.choices = ServiceCandidates.model_validate(choices)
        self.line_number = line_number
        super().__init__("Выберите услугу из справочника.")


class InitialQuantityRequired(UserProblem):
    def __init__(self, line_number: int, amount: Decimal, quantity: Decimal, uom: str):
        self.line_number, self.amount, self.quantity, self.uom = line_number, amount, quantity, uom
        super().__init__("Сумма строки не представима с этой ценой до копейки. Уточните количество.")


class BackendFailure(Exception):
    """Adapter failure. Do not forward its message or payload to logs/users."""


class StaleBasis(Exception):
    """The adapter atomically refused a write because its preconditions changed."""


class InvoiceConflict(Exception):
    """An existing document is bound to a different confirmed snapshot."""


class WritesDisabled(Exception):
    pass


class WorkflowFailure(Exception):
    def __init__(self, stage: str, document_id: str | None,
                 operation_id: str | None = None, state: str = "unknown"):
        self.stage = stage
        self.document_id = document_id
        self.operation_id = operation_id
        self.state = state
        super().__init__(stage)


class OneC(Protocol):
    is_fake: bool

    async def resolve_client(self, query: str, *, selected_id: str | None = None) -> ResolvedClient:
        """Read only. Return a unique ID or typed choices. Recheck an explicit selection.

        selected_id comes only from a user's token-bound candidate choice, never AI.
        It must still belong to fresh active candidates for the original query.
        """
        ...

    async def resolve_service(self, client_id: str, query: str, *, selected_id: str | None = None) -> ResolvedService:
        """Read only. Resolve a human query to exactly one permitted stable service ID."""
        ...

    async def resolve_basis(self, command: ResolvedInvoiceCommand) -> BillingBasis:
        """Read only. Refuse missing or ambiguous client/contract/services."""
        ...

    async def read_operation(self, basis: BillingBasis, operation_id: str) -> OperationState:
        """Authoritative reconciliation, never a mutation.

        not_started means there is NO document and NO in-flight write that can later
        commit. A missing/eventually-consistent lookup is unknown, not not_started.
        """
        ...

    async def ensure_draft(self, basis: BillingBasis, operation_id: str) -> Invoice:
        """Atomically get/create ONE invoice per billing basis, also on retries.

        operation_id is stable for the basis, not the Telegram message/user.
        Atomically enforce basis freshness, backend persistence and concurrency safety.
        This is an internal requirement, not a claimed existing 1C endpoint.
        """
        ...

    async def ensure_posted(self, basis: BillingBasis, invoice: Invoice, operation_id: str) -> Invoice:
        """Check basis/document freshness atomically with posting the SAME document."""
        ...

    async def get_pdf(self, invoice: Invoice) -> PdfDocument:
        """Return the standard 1C print form; never render it in this app."""
        ...
