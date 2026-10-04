import hashlib
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True,
                              hide_input_in_errors=True, revalidate_instances="always",
                              validate_by_name=True, allow_inf_nan=False)


class ExternalModel(StrictModel):
    # Partial views of versioned provider envelopes: validate consumed fields.
    model_config = ConfigDict(extra="ignore")


class InvoiceCommand(StrictModel):
    action: Literal["create_invoice"] = "create_invoice"
    client: str = Field(min_length=2, max_length=200)
    year: int = Field(ge=2000, le=2100)
    month: int = Field(ge=1, le=12)

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
    year: int = Field(ge=2000, le=2100)
    month: int = Field(ge=1, le=12)


class BillingBasis(StrictModel):
    # Opaque, resolved by 1C: organisation, client, contract, service and period.
    # The backend owns uniqueness and must revalidate the basis before writing.
    key: str = Field(min_length=1, max_length=200)
    client_id: str = Field(min_length=1, max_length=200)
    revision: str = Field(min_length=1, max_length=200)


class PreparedInvoice(StrictModel):
    request: ResolvedInvoiceCommand
    basis: BillingBasis
    display_name: str = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def same_client(self):
        if self.request.client_id != self.basis.client_id:
            raise ValueError("Resolved client does not match billing basis")
        return self

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


class BackendFailure(Exception):
    """Adapter failure. Do not forward its message or payload to logs/users."""


class StaleBasis(Exception):
    """The adapter atomically refused a write because its preconditions changed."""


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
