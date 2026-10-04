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


class PartyDetails(StrictModel):
    name: Label
    address: Label
    tax_number: Label
    phone: Label
    email: Label


class BankDetails(StrictModel):
    bank: Label
    iban: Label
    swift: Label
    beneficiary: Label


class PaymentTerms(StrictModel):
    payment: Label
    delivery: Label


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

    @model_validator(mode="after")
    def correct_totals(self):
        # Validation of provider arithmetic, not an alternative rendering calculation.
        subtotal = (self.quantity * self.price).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        tax = (subtotal * self.tax.rate / 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if (self.subtotal, self.tax_amount, self.total) != (subtotal, tax, subtotal + tax):
            raise ValueError("Inconsistent invoice line amounts")
        return self


class InvoicePreview(StrictModel):
    invoice_date: InvoiceDate
    supply_date: InvoiceDate
    service_period: ServicePeriod | None = None
    currency: Literal["AED", "USD", "EUR", "GBP", "RUB"]
    issuer: PartyDetails
    recipient: PartyDetails
    bank: BankDetails
    terms: PaymentTerms
    lines: tuple[InvoiceLine, ...] = Field(min_length=1, max_length=20)
    subtotal: Money
    tax_amount: Money
    total: Money
    amount_in_words: Label
    reference: Label
    previous_reference: Label | None = None

    @model_validator(mode="after")
    def correct_totals(self):
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

    @model_validator(mode="after")
    def valid_period(self):
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


class ServiceProblem(UserProblem):
    def __init__(self, message: str, line_number: int):
        self.line_number = line_number
        super().__init__(message)


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

    async def resolve_client(self, query: str) -> ResolvedClient:
        """Read only. Return exactly one stable 1C ID, or ask for clarification."""
        ...

    async def resolve_service(self, client_id: str, query: str) -> ResolvedService:
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
