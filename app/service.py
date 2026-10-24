import asyncio
import logging
from datetime import date, datetime, timezone

from app.domain import (BillingBasis, Invoice, InvoiceCommand, InvoiceConflict, InvoiceResult, OneC,
                        OperationState, PdfDocument, PreparedInvoice, ResolvedClient,
                        ResolvedInvoiceCommand, ResolvedService, ResolvedServiceSelection, ResolvedPreviewLineOverride,
                        ServiceProblem, StaleBasis, StrictModel, UserProblem,
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
        if getattr(self.onec, "preview_only", False) is True:
            raise WritesDisabled()
        if getattr(self.onec, "is_fake", False) is not True and not self.allow_real_writes:
            raise WritesDisabled()

    async def prepare(self, command: InvoiceCommand, request_id: str, user_id: int, *,
                      existing: PreparedInvoice | None = None,
                      old_command: InvoiceCommand | None = None,
                      selected_client_id: str | None = None) -> PreparedInvoice:
        resolution_step = "client"
        try:
            command = InvoiceCommand.model_validate(command)
            client = (ResolvedClient.model_validate(await asyncio.wait_for(
                          self.onec.resolve_client(command.client, selected_id=selected_client_id), self.timeout))
                      if selected_client_id is not None else
                      ResolvedClient(client_id=existing.request.client_id, display_name=existing.display_name)
                      if existing is not None and old_command is not None and command.client == old_command.client
                      else ResolvedClient.model_validate(await asyncio.wait_for(
                          self.onec.resolve_client(command.client), self.timeout)))
            if selected_client_id is not None and client.client_id != selected_client_id:
                raise ValueError("Provider changed the explicitly selected client")
            selections = []
            resolution_step = "service"
            for number, selected in enumerate(command.services, 1):
                cached = None
                if existing is not None and old_command is not None and client.client_id == existing.request.client_id:
                    for old, resolved_old in zip(old_command.services, existing.request.services):
                        if old.query == selected.query:
                            cached = resolved_old.service_id
                            break
                try:
                    service_id = cached or ResolvedService.model_validate(await asyncio.wait_for(
                        self.onec.resolve_service(client.client_id, selected.query), self.timeout)).service_id
                except UserProblem as exc:
                    raise ServiceProblem(str(exc), number) from None
                selections.append(ResolvedServiceSelection(service_id=service_id, quantity=selected.quantity))
            period = command.period
            resolution_step = "basis"
            overrides = []
            source_id = None
            if command.preview_overrides:
                if existing is None or old_command is None or existing.request.client_id != client.client_id:
                    raise UserProblem("Сначала подготовьте preview для этого клиента, затем измените строку.")
                source = existing.preview.historical_proposal
                source_id = source.source_id if source else None
                for edit in command.preview_overrides:
                    if edit.line_number > len(existing.preview.lines):
                        raise UserProblem("В preview нет такой строки.")
                    overrides.append(ResolvedPreviewLineOverride(**edit.model_dump(),
                        source_line_number=existing.preview.lines[edit.line_number - 1].source_line_number))
            resolved = ResolvedInvoiceCommand(
                client_id=client.client_id, year=period.year if period else None, month=period.month if period else None,
                invoice_date=command.invoice_date or date.today(), service_period=period,
                services=tuple(selections), tax=command.tax, previous=command.previous,
                legacy_period=command.legacy_period or (command.invoice_date is None and command.year is not None),
                preview_overrides=tuple(overrides), preview_source_id=source_id,
            )
            basis = BillingBasis.model_validate(await asyncio.wait_for(
                self.onec.resolve_basis(resolved), self.timeout))
            if basis.preview is None:
                raise ValueError("Provider did not return a preview")
            if period is not None and basis.preview.service_period != period:
                raise ValueError("Provider changed requested service period")
            expanded_history = (basis.preview.historical_proposal is not None and len(selections) == 1
                and selections[0].quantity is None
                and all(line.service_id == selections[0].service_id for line in basis.preview.lines))
            if selections and not expanded_history and [(s.service_id, s.quantity) for s in selections] != [
                    (line.service_id, s.quantity) for s, line in zip(selections, basis.preview.lines)]:
                raise ValueError("Provider changed selected services")
            if selections and not expanded_history and len(selections) != len(basis.preview.lines):
                raise ValueError("Provider changed line count")
            for selected, line in zip(selections, basis.preview.lines):
                if selected.quantity is not None and selected.quantity != line.quantity:
                    raise ValueError("Provider changed requested quantity")
            for line in basis.preview.lines:
                if command.tax.mode == "with_tax" and line.tax.rate == 0:
                    raise ValueError("Provider ignored requested tax treatment")
                if command.tax.mode == "without_tax" and line.tax.rate != 0:
                    raise ValueError("Provider ignored requested tax treatment")
            supplied_period = basis.preview.service_period
            resolved = ResolvedInvoiceCommand(**{**resolved.model_dump(),
                "service_period": supplied_period,
                "year": supplied_period.year if supplied_period else None,
                "month": supplied_period.month if supplied_period else None,
                "services": tuple(
                ResolvedServiceSelection(service_id=line.service_id, quantity=line.quantity)
                for line in basis.preview.lines)})
            prepared = PreparedInvoice(request=resolved, basis=basis, display_name=client.display_name)
            event(request_id=request_id, user_id=user_id, stage="resolve", status="success",
                  operation_id=prepared.operation_id)
            return prepared
        except UserProblem:
            event(request_id=request_id, user_id=user_id, stage="resolve", status="clarification", error=resolution_step)
            raise
        except Exception as exc:
            event(request_id=request_id, user_id=user_id, stage="resolve", status="error", error=type(exc).__name__)
            raise WorkflowFailure("resolve", None) from None

    async def refresh(self, prepared: PreparedInvoice, request_id: str, user_id: int) -> PreparedInvoice:
        """Before confirming, refresh read-only. Existing/uncertain writes remain frozen."""
        prepared = PreparedInvoice.model_validate(prepared)
        stage, known_state = "reconcile", "unknown"
        try:
            if getattr(self.onec, "preview_only", False) is True or prepared.preview.user_overrides:
                # Verify a proposal, without claiming authoritative operation reconciliation.
                stage = "refresh"
                basis = BillingBasis.model_validate(await asyncio.wait_for(
                    self.onec.resolve_basis(prepared.request), self.timeout))
                refreshed = PreparedInvoice(request=prepared.request, basis=basis, display_name=prepared.display_name)
                if basis.key != prepared.basis.key:
                    raise UserProblem("Основание изменилось. Подготовьте новый preview.")
                return refreshed
            state = await self._read_state(prepared)
            known_state = state.status
            if state.status == "unknown":
                raise WorkflowFailure("reconcile", None, prepared.operation_id)
            if state.status != "not_started":
                return prepared
            stage = "refresh"
            basis = BillingBasis.model_validate(await asyncio.wait_for(
                self.onec.resolve_basis(prepared.request), self.timeout))
            refreshed = PreparedInvoice(request=prepared.request, basis=basis, display_name=prepared.display_name)
            if refreshed.basis.key != prepared.basis.key:
                raise ValueError("Provider changed billing identity during refresh")
            return refreshed
        except InvoiceConflict:
            raise UserProblem("На это основание уже создан счёт с другими данными. Изменять его автоматически нельзя. Обратитесь к оператору.") from None
        except (UserProblem, WorkflowFailure):
            raise
        except Exception as exc:
            event(request_id=request_id, user_id=user_id, stage="refresh", status="error", error=type(exc).__name__)
            raise WorkflowFailure("resolve" if stage == "refresh" else "reconcile", None,
                                  prepared.operation_id, known_state) from None

    @staticmethod
    def _check_invoice(invoice: Invoice, prepared: PreparedInvoice) -> Invoice:
        invoice = Invoice.model_validate(invoice)
        if invoice.client_id != prepared.request.client_id or invoice.basis_key != prepared.basis.key:
            raise ValueError("Document does not belong to resolved operation")
        if invoice.preview_digest != prepared.preview.digest:
            raise InvoiceConflict()
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
            if (prepared.preview.historical_proposal is not None or prepared.preview.user_overrides
                    or getattr(self.onec, "preview_only", False) is True):
                raise WorkflowFailure("write_disabled", None, operation_id, "not_started")
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
