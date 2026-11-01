import asyncio
import logging
import re
from decimal import Decimal, ROUND_HALF_UP
from datetime import date, datetime, timezone

from app.domain import (BackendFailure, BillingBasis, ClientCandidate, ClientCandidates, ClientChoiceRequired, Invoice, InvoiceCommand, InvoiceConflict, InvoiceResult, OneC,
                        OperationState, PdfDocument, PreparedInvoice, ResolvedClient,
                        ResolvedInvoiceCommand, ResolvedService, ResolvedServiceSelection, ResolvedPreviewLineOverride,
                        ServiceProblem, ServiceChoiceRequired, InitialQuantityRequired, StaleBasis, StrictModel, UserProblem,
                        WorkflowFailure, WritesDisabled, TaxInvoice, TaxInvoiceReference, TaxInvoicePdf, TaxOperationState)
from app.operations import MutationUncertain, OperationJournal

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


def safe_backend_error(exc: Exception) -> str:
    # Only exact adapter-owned codes. Never log arbitrary exception strings.
    if isinstance(exc, BackendFailure) and len(exc.args) == 1 and isinstance(exc.args[0], str):
        code = exc.args[0]
        if re.fullmatch(r"firstbit_(?:schema_mismatch|write_schema_mismatch|create_uncertain|create_readback_mismatch|get_failed(?:_(?:timeout|http_error|http_[1-5][0-9]{2}|response_too_large|invalid_response))?)", code):
            return code
    return type(exc).__name__


class InvoiceService:
    def __init__(self, onec: OneC, timeout: float = 5, *, allow_real_writes: bool = False,
                 journal: OperationJournal | None = None):
        if type(allow_real_writes) is not bool:
            raise ValueError("Write permission must be explicit boolean")
        self.onec, self.timeout = onec, timeout
        self.allow_real_writes = allow_real_writes
        self.journal = journal

    def _write_guard(self):
        if (getattr(self.onec, "preview_only", False) is True
                and getattr(self.onec, "write_capable", False) is not True):
            raise WritesDisabled()
        if (getattr(self.onec, "is_fake", False) is not True
                and (not self.allow_real_writes or self.journal is None)):
            raise WritesDisabled()

    def readonly_preview(self, prepared: PreparedInvoice) -> bool:
        if (getattr(self.onec, "write_capable", False) is True and self.allow_real_writes
                and self.journal is not None and prepared.preview.execution_review is not None
                and self.onec.is_fake is False):
            return False
        return (getattr(self.onec, "preview_only", False) is True
                or bool(prepared.preview.user_overrides) or prepared.preview.historical_proposal is not None)

    async def prepare(self, command: InvoiceCommand, request_id: str, user_id: int, *,
                      existing: PreparedInvoice | None = None,
                      old_command: InvoiceCommand | None = None,
                      selected_client_id: str | None = None, require_client_choice: bool = False,
                      selected_service_ids: dict[int, str] | None = None) -> PreparedInvoice:
        resolution_step = "client"
        try:
            command = InvoiceCommand.model_validate(command)
            if command.initial_overrides and getattr(self.onec, "preview_only", False) is not True:
                raise UserProblem("Первоначальные денежные параметры доступны только в read-only preview.")
            client = (ResolvedClient.model_validate(await asyncio.wait_for(
                          self.onec.resolve_client(command.client, selected_id=selected_client_id), self.timeout))
                      if selected_client_id is not None else
                      ResolvedClient(client_id=existing.request.client_id, display_name=existing.display_name)
                      if existing is not None and old_command is not None and command.client == old_command.client
                      else ResolvedClient.model_validate(await asyncio.wait_for(
                          self.onec.resolve_client(command.client), self.timeout)))
            if require_client_choice and selected_client_id is None:
                raise ClientChoiceRequired(ClientCandidates(candidates=(ClientCandidate(
                    client_id=client.client_id, display_name=client.display_name, full_name=client.display_name),)))
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
                    chosen = (selected_service_ids or {}).get(number)
                    service_id = (ResolvedService.model_validate(await asyncio.wait_for(
                        self.onec.resolve_service(client.client_id, selected.query, selected_id=chosen), self.timeout)).service_id
                        if chosen is not None else cached or ResolvedService.model_validate(await asyncio.wait_for(
                        self.onec.resolve_service(client.client_id, selected.query), self.timeout)).service_id)
                    if chosen is not None and chosen != service_id:
                        raise ValueError("Provider changed the selected service")
                except ServiceChoiceRequired as exc:
                    raise ServiceChoiceRequired(exc.choices, number) from None
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
                        source_line_number=existing.preview.lines[edit.line_number - 1].source_line_number,
                        source_id=existing.preview.lines[edit.line_number - 1].source_id or source_id))
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
            if command.initial_overrides:
                source = basis.preview.historical_proposal
                if source is None:
                    raise UserProblem("Для первоначальных сумм нужен проверенный исторический образец.")
                initial = []
                aligned = len(selections) == len(basis.preview.lines) and all(
                    selected.service_id == line.service_id for selected, line in zip(selections, basis.preview.lines))
                for edit in command.initial_overrides:
                    selected = selections[edit.line_number - 1]
                    indexes = [edit.line_number - 1] if aligned else [i for i, line in enumerate(basis.preview.lines)
                        if line.service_id == selected.service_id]
                    if not indexes or len(indexes) > 1 and (edit.price is not None or edit.amount is not None or edit.description is not None):
                        raise UserProblem("Для услуги несколько исторических строк. Уточните строку суммы; объединять их нельзя.")
                    for index in indexes:
                        line = basis.preview.lines[index]
                        if edit.amount is not None:
                            unit = (edit.amount / line.quantity).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
                            if (unit * line.quantity).quantize(Decimal('.01'), rounding=ROUND_HALF_UP) != edit.amount:
                                raise InitialQuantityRequired(edit.line_number, edit.amount, line.quantity, line.uom)
                        initial.append(ResolvedPreviewLineOverride(**{**edit.model_dump(), "line_number": index + 1},
                            source_line_number=line.source_line_number, source_id=line.source_id or source.source_id))
                resolved = ResolvedInvoiceCommand(**{**resolved.model_dump(), "preview_overrides": tuple(initial),
                    "preview_source_id": source.source_id})
                basis = BillingBasis.model_validate(await asyncio.wait_for(self.onec.resolve_basis(resolved), self.timeout))
                if basis.preview is None or basis.preview.user_overrides != tuple(edit.user_edit() for edit in initial):
                    raise ValueError("Provider ignored initial user parameters")
            if period is not None and basis.preview.service_period != period:
                raise ValueError("Provider changed requested service period")
            requested_ids = [selection.service_id for selection in selections]
            returned_ids = [line.service_id for line in basis.preview.lines]
            compact = lambda ids: [key for index, key in enumerate(ids) if index == 0 or ids[index - 1] != key]
            expanded_history = (basis.preview.historical_proposal is not None and bool(selections)
                and all(selection.quantity is None for selection in selections)
                and compact(requested_ids) == compact(returned_ids)
                and all(returned_ids.count(key) >= requested_ids.count(key) for key in requested_ids))
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
            event(request_id=request_id, user_id=user_id, stage="resolve", status="error", error=safe_backend_error(exc))
            raise WorkflowFailure("resolve", None) from None

    async def refresh(self, prepared: PreparedInvoice, request_id: str, user_id: int) -> PreparedInvoice:
        """Before confirming, refresh read-only. Existing/uncertain writes remain frozen."""
        prepared = PreparedInvoice.model_validate(prepared)
        stage, known_state = "reconcile", "unknown"
        try:
            if self.readonly_preview(prepared):
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
            event(request_id=request_id, user_id=user_id, stage="refresh", status="error", error=safe_backend_error(exc))
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

    @staticmethod
    def _check_tax_invoice(tax: TaxInvoice, prepared: PreparedInvoice, source: Invoice) -> TaxInvoice:
        tax = TaxInvoice.model_validate(tax)
        if (tax.source_document_id != source.document_id or tax.client_id != prepared.request.client_id
                or tax.basis_key != prepared.basis.key or tax.preview_digest != prepared.preview.digest):
            raise InvoiceConflict()
        return tax

    async def _read_tax_state(self, prepared: PreparedInvoice, source: Invoice) -> TaxOperationState:
        state = TaxOperationState.model_validate(await asyncio.wait_for(
            self.onec.read_tax_operation(prepared.basis, source, prepared.operation_id), self.timeout))
        if state.operation_id != prepared.operation_id or state.source_document_id != source.document_id:
            raise InvoiceConflict()
        if state.invoice is not None:
            self._check_tax_invoice(state.invoice, prepared, source)
        return state

    async def _execute_tax(self, prepared: PreparedInvoice, source: Invoice,
                           request_id: str, user_id: int) -> InvoiceResult:
        operation_id = prepared.operation_id
        stage, known_state = 'tax_reconcile', 'unknown'
        try:
            if self.journal is None or not source.posted:
                raise WritesDisabled()
            state = await self._read_tax_state(prepared, source)
            known_state = state.status
            if state.status == 'unknown':
                raise WorkflowFailure(stage, source.document_id, operation_id)
            tax = state.invoice
            if tax is not None:
                self.journal.observe_tax(operation_id, tax)
            if state.status == 'not_started':
                stage = 'tax_generate'
                self._write_guard()
                self.journal.claim_tax_generation(operation_id)
                event(request_id=request_id, user_id=user_id, stage=stage, status='started',
                      operation_id=operation_id, document_id=source.document_id)
                reference = TaxInvoiceReference.model_validate(await asyncio.wait_for(
                    self.onec.ensure_tax_invoice(prepared.basis, source, operation_id), self.timeout))
                if reference.source_document_id != source.document_id:
                    raise InvoiceConflict()
                self.journal.record_tax_reference(operation_id, reference)
                # A returned reference is only a hint; the linked document needs read-back.
                state = await self._read_tax_state(prepared, source)
                if state.invoice is None or state.invoice.document_id != reference.document_id:
                    raise InvoiceConflict()
                tax, known_state = state.invoice, state.status
                self.journal.observe_tax(operation_id, tax)
            if not tax.posted:
                stage = 'tax_post'
                self._write_guard()
                self.journal.claim_tax_post(operation_id)
                event(request_id=request_id, user_id=user_id, stage=stage, status='started',
                      operation_id=operation_id, document_id=tax.document_id)
                reference = TaxInvoiceReference.model_validate(await asyncio.wait_for(
                    self.onec.ensure_tax_posted(prepared.basis, tax, operation_id), self.timeout))
                if reference.document_id != tax.document_id or reference.source_document_id != source.document_id:
                    raise InvoiceConflict()
                state = await self._read_tax_state(prepared, source)
                if state.invoice is None or not state.invoice.posted or state.invoice.document_id != tax.document_id:
                    raise InvoiceConflict()
                tax, known_state = state.invoice, state.status
                self.journal.observe_tax(operation_id, tax)
            # Native generation may update the source's link/version. Verify both documents.
            stage = 'tax_refresh'
            refreshed_source = await self._read_state(prepared)
            if refreshed_source.invoice is None or not refreshed_source.invoice.posted or refreshed_source.invoice.document_id != source.document_id:
                raise InvoiceConflict()
            source = refreshed_source.invoice
            self.journal.observe(operation_id, source)
            cached = self.journal.get(operation_id)
            pdf = cached.pdf
            if pdf is not None and not isinstance(pdf, TaxInvoicePdf):
                raise InvoiceConflict()
            if pdf is None:
                stage = 'tax_pdf'
                pdf = TaxInvoicePdf.model_validate(await asyncio.wait_for(self.onec.get_tax_invoice_pdf(tax), self.timeout))
                # Check exact native form, parent, tax document and version before caching/delivery.
                InvoiceResult(invoice=source, tax_invoice=tax, pdf=pdf)
                after_print = await self._read_tax_state(prepared, source)
                if after_print.invoice != tax or after_print.status != 'posted':
                    raise InvoiceConflict()
                source_after_print = await self._read_state(prepared)
                if (source_after_print.invoice is None or not source_after_print.invoice.posted
                        or source_after_print.invoice.document_id != source.document_id):
                    raise InvoiceConflict()
                source = source_after_print.invoice
                self.journal.observe(operation_id, source)
                self.journal.cache_tax_pdf(operation_id, source, tax, pdf)
            event(request_id=request_id, user_id=user_id, stage='tax_pdf', status='success',
                  operation_id=operation_id, document_id=tax.document_id)
            return InvoiceResult(invoice=source, tax_invoice=tax, pdf=pdf)
        except WorkflowFailure:
            raise
        except MutationUncertain:
            raise WorkflowFailure('tax_reconcile', source.document_id, operation_id, 'unknown') from None
        except WritesDisabled:
            raise WorkflowFailure('write_disabled', source.document_id, operation_id, known_state) from None
        except Exception as exc:
            if stage in ('tax_generate', 'tax_post'):
                known_state = 'unknown'
                try:
                    recovered = await self._read_tax_state(prepared, source)
                    if recovered.invoice is not None:
                        self.journal.observe_tax(operation_id, recovered.invoice)
                        known_state = recovered.status
                    # Absence after intent does not prove there is no in-flight generation.
                except Exception:
                    known_state = 'unknown'
            event(request_id=request_id, user_id=user_id, stage=stage, status=known_state,
                  operation_id=operation_id, document_id=source.document_id, error=safe_backend_error(exc))
            raise WorkflowFailure(stage, source.document_id, operation_id, known_state) from None

    async def execute(self, prepared: PreparedInvoice, request_id: str, user_id: int) -> InvoiceResult:
        prepared = PreparedInvoice.model_validate(prepared)
        stage, document_id, known_state = "reconcile", None, "unknown"
        operation_id = prepared.operation_id
        try:
            if self.readonly_preview(prepared):
                raise WorkflowFailure("write_disabled", None, operation_id, "not_started")
            if getattr(self.onec, 'requires_tax_invoice', False) is True:
                hooks = ('read_tax_operation', 'ensure_tax_invoice', 'ensure_tax_posted', 'get_tax_invoice_pdf')
                if (self.journal is None or getattr(self.onec, 'native_pdf_available', True) is False
                        or getattr(self.onec, 'posting_enabled', True) is False
                        or any(not callable(getattr(self.onec, name, None)) for name in hooks)):
                    raise WritesDisabled()
            if self.journal is not None:
                # This path is entered only after confirmation. Persist the exact
                # frozen request before any possible external mutation.
                self.journal.reserve(prepared, user_id)
            state = await self._read_state(prepared)
            known_state = state.status
            event(request_id=request_id, user_id=user_id, stage=stage, status=known_state,
                  operation_id=operation_id)
            if known_state == "unknown":
                raise WorkflowFailure(stage, None, operation_id)
            invoice = state.invoice
            if self.journal is not None and invoice is not None:
                self.journal.observe(operation_id, invoice)
            if known_state == "not_started":
                stage = "create"
                self._write_guard()
                if self.journal is not None:
                    self.journal.claim_mutation(operation_id, "create")
                event(request_id=request_id, user_id=user_id, stage=stage, status="started", operation_id=operation_id)
                invoice = self._check_invoice(await asyncio.wait_for(
                    self.onec.ensure_draft(prepared.basis, operation_id), self.timeout), prepared)
                if self.journal is not None:
                    self.journal.observe(operation_id, invoice)
            document_id = invoice.document_id
            known_state = "posted" if invoice.posted else "draft"
            if not invoice.posted and getattr(self.onec, "posting_enabled", True) is False:
                event(request_id=request_id, user_id=user_id, stage="create", status="verified_draft_posting_blocked",
                      operation_id=operation_id, document_id=document_id)
                return InvoiceResult(invoice=invoice)
            if not invoice.posted:
                stage = "post"
                self._write_guard()
                if self.journal is not None:
                    self.journal.claim_mutation(operation_id, "post")
                event(request_id=request_id, user_id=user_id, stage=stage, status="started",
                      operation_id=operation_id, document_id=document_id)
                posted = self._check_invoice(await asyncio.wait_for(
                    self.onec.ensure_posted(prepared.basis, invoice, operation_id), self.timeout), prepared)
                if not posted.posted or posted.document_id != document_id:
                    raise ValueError("Invalid posting result")
                invoice, known_state = posted, "posted"
                if self.journal is not None:
                    self.journal.observe(operation_id, invoice)
            if getattr(self.onec, 'requires_tax_invoice', False) is True:
                return await self._execute_tax(prepared, invoice, request_id, user_id)
            stage = "pdf"
            if getattr(self.onec, "native_pdf_available", True) is False:
                event(request_id=request_id, user_id=user_id, stage="post", status="success_pdf_unavailable",
                      operation_id=operation_id, document_id=document_id)
                return InvoiceResult(invoice=invoice)
            cached = self.journal.get(operation_id) if self.journal is not None else None
            pdf = cached.pdf if cached is not None else None
            if pdf is None:
                pdf = PdfDocument.model_validate(await asyncio.wait_for(self.onec.get_pdf(invoice), self.timeout))
                if self.journal is not None:
                    self.journal.cache_pdf(operation_id, invoice, pdf)
            event(request_id=request_id, user_id=user_id, stage=stage, status="success",
                  operation_id=operation_id, document_id=document_id)
            return InvoiceResult(invoice=invoice, pdf=pdf)
        except WorkflowFailure:
            raise
        except MutationUncertain:
            # A persisted intent may still be in flight. Even a transient absent
            # remote result does not permit another create/post request.
            raise WorkflowFailure("reconcile", document_id, operation_id, "unknown") from None
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
                    if self.journal is not None and recovered.invoice is not None:
                        self.journal.observe(operation_id, recovered.invoice)
                    known_state = recovered.status
                    if recovered.invoice is not None:
                        document_id = recovered.invoice.document_id
                except Exception as recovery_error:
                    event(request_id=request_id, user_id=user_id, stage="reconcile", status="unknown",
                          operation_id=operation_id, document_id=document_id, error=type(recovery_error).__name__)
            event(request_id=request_id, user_id=user_id, stage=stage, status=known_state,
                  operation_id=operation_id, document_id=document_id, error=safe_backend_error(exc))
            raise WorkflowFailure("stale" if isinstance(exc, StaleBasis) else stage,
                                  document_id, operation_id, known_state) from None
