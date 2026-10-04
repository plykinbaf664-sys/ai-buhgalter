import asyncio
import logging
from datetime import datetime, timezone

from app.domain import (BillingBasis, Invoice, InvoiceCommand, InvoiceResult, OneC,
                        OperationState, PdfDocument, PreparedInvoice, ResolvedClient,
                        ResolvedInvoiceCommand, StaleBasis, StrictModel, UserProblem,
                        WorkflowFailure, WritesDisabled)

logger = logging.getLogger("invoices")


class AuditEvent(StrictModel):
    timestamp: str
    request_id: str
    telegram_user_id: int
    action: str = "create_invoice"
    stage: str
    status: str
    operation_id: str | None = None
    document_id: str | None = None
    error: str | None = None


def event(*, request_id: str, user_id: int, stage: str, status: str,
          operation_id: str | None = None, document_id: str | None = None,
          error: str | None = None) -> None:
    # Explicit fields only: never log text, exception messages, HTTP URLs or bodies.
    logger.info(AuditEvent(timestamp=datetime.now(timezone.utc).isoformat(),
                          request_id=request_id, telegram_user_id=user_id, stage=stage,
                          status=status, operation_id=operation_id, document_id=document_id,
                          error=error).model_dump_json())


class InvoiceService:
    def __init__(self, onec: OneC, timeout: float = 5, *, allow_real_writes: bool = False):
        if type(allow_real_writes) is not bool:
            raise ValueError("Write permission must be explicit boolean")
        self.onec, self.timeout = onec, timeout
        self.allow_real_writes = allow_real_writes

    def _write_guard(self):
        if getattr(self.onec, "is_fake", False) is not True and not self.allow_real_writes:
            raise WritesDisabled()

    async def prepare(self, command: InvoiceCommand, request_id: str, user_id: int) -> PreparedInvoice:
        try:
            command = InvoiceCommand.model_validate(command)
            client = ResolvedClient.model_validate(await asyncio.wait_for(
                self.onec.resolve_client(command.client), self.timeout))
            resolved = ResolvedInvoiceCommand(client_id=client.client_id, year=command.year, month=command.month)
            basis = BillingBasis.model_validate(await asyncio.wait_for(
                self.onec.resolve_basis(resolved), self.timeout))
            prepared = PreparedInvoice(request=resolved, basis=basis, display_name=client.display_name)
            event(request_id=request_id, user_id=user_id, stage="resolve", status="success",
                  operation_id=prepared.operation_id)
            return prepared
        except UserProblem:
            raise
        except Exception as exc:
            event(request_id=request_id, user_id=user_id, stage="resolve", status="error", error=type(exc).__name__)
            raise WorkflowFailure("resolve", None) from None

    @staticmethod
    def _check_invoice(invoice: Invoice, prepared: PreparedInvoice) -> Invoice:
        invoice = Invoice.model_validate(invoice)
        if invoice.client_id != prepared.request.client_id or invoice.basis_key != prepared.basis.key:
            raise ValueError("Document does not belong to resolved operation")
        return invoice

    async def _read_state(self, prepared: PreparedInvoice) -> OperationState:
        state = OperationState.model_validate(await asyncio.wait_for(
            self.onec.read_operation(prepared.basis, prepared.operation_id), self.timeout))
        if state.operation_id != prepared.operation_id:
            raise ValueError("Wrong operation returned")
        if state.invoice is not None:
            self._check_invoice(state.invoice, prepared)
        return state

    async def execute(self, prepared: PreparedInvoice, request_id: str, user_id: int) -> InvoiceResult:
        prepared = PreparedInvoice.model_validate(prepared)
        stage, document_id, known_state = "reconcile", None, "unknown"
        operation_id = prepared.operation_id
        try:
            state = await self._read_state(prepared)
            known_state = state.status
            event(request_id=request_id, user_id=user_id, stage=stage, status=known_state,
                  operation_id=operation_id)
            if known_state == "unknown":
                raise WorkflowFailure(stage, None, operation_id)
            invoice = state.invoice
            if known_state == "not_started":
                stage = "create"
                self._write_guard()
                event(request_id=request_id, user_id=user_id, stage=stage, status="started", operation_id=operation_id)
                invoice = self._check_invoice(await asyncio.wait_for(
                    self.onec.ensure_draft(prepared.basis, operation_id), self.timeout), prepared)
            document_id = invoice.document_id
            known_state = "posted" if invoice.posted else "draft"
            if not invoice.posted:
                stage = "post"
                self._write_guard()
                event(request_id=request_id, user_id=user_id, stage=stage, status="started",
                      operation_id=operation_id, document_id=document_id)
                posted = self._check_invoice(await asyncio.wait_for(
                    self.onec.ensure_posted(prepared.basis, invoice, operation_id), self.timeout), prepared)
                if not posted.posted or posted.document_id != document_id:
                    raise ValueError("Invalid posting result")
                invoice, known_state = posted, "posted"
            stage = "pdf"
            pdf = PdfDocument.model_validate(await asyncio.wait_for(self.onec.get_pdf(invoice), self.timeout))
            event(request_id=request_id, user_id=user_id, stage=stage, status="success",
                  operation_id=operation_id, document_id=document_id)
            return InvoiceResult(invoice=invoice, pdf=pdf)
        except WorkflowFailure:
            raise
        except WritesDisabled:
            raise WorkflowFailure("write_disabled", document_id, operation_id, known_state) from None
        except Exception as exc:
            # An error after invoking a mutation is an uncertain outcome. Reconcile
            # once, read-only. Never automatically retry the mutation in this call.
            if stage in ("create", "post"):
                known_state = "unknown"
                try:
                    recovered = await self._read_state(prepared)
                    if (document_id is not None and recovered.invoice is not None
                            and recovered.invoice.document_id != document_id):
                        raise ValueError("Reconciliation changed document identity")
                    known_state = recovered.status
                    if recovered.invoice is not None:
                        document_id = recovered.invoice.document_id
                except Exception as recovery_error:
                    event(request_id=request_id, user_id=user_id, stage="reconcile", status="unknown",
                          operation_id=operation_id, document_id=document_id, error=type(recovery_error).__name__)
            event(request_id=request_id, user_id=user_id, stage=stage, status=known_state,
                  operation_id=operation_id, document_id=document_id, error=type(exc).__name__)
            raise WorkflowFailure("stale" if isinstance(exc, StaleBasis) else stage,
                                  document_id, operation_id, known_state) from None
