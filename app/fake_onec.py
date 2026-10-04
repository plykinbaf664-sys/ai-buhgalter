"""Ephemeral test double. Its fixtures are NOT a local accounting database."""
import asyncio
import calendar
import hashlib
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal

from app.domain import (BillingBasis, Invoice, InvoiceLine, InvoicePreview, OperationState, PdfDocument,
                        ResolvedClient, ResolvedService, ResolvedServiceSelection,
                        ResolvedInvoiceCommand, StaleBasis, StrictModel, UserProblem)
from app.fake_data import BANK, ISSUER, PREVIOUS, SERVICES, TAXES, TERMS, PreviousHint, amount_words, recipient
from app.mock_pdf import render_mock_pdf

class FakeClient(StrictModel):
    client_id: str
    display_name: str
    search_names: tuple[str, ...]


class FakeFault(StrictModel):
    mode: Literal["disabled", "create_lost_response", "post_lost_response"] = "disabled"


class FakeOneC:
    is_fake = True

    def __init__(self, fault: Literal["disabled", "create_lost_response", "post_lost_response"] = "disabled"):
        self.fault = FakeFault(mode=fault)
        self._fault_triggered = False
        self.documents: dict[str, Invoice] = {}
        self.clients = {
            item.client_id: item for item in (
                FakeClient(client_id="client-001", display_name="ООО Ромашка", search_names=("ромашка", "ромашке", "ооо ромашка")),
                FakeClient(client_id="client-002", display_name="ООО Двойник 1", search_names=("двойник", "ооо двойник")),
                FakeClient(client_id="client-003", display_name="ООО Двойник 2", search_names=("двойник", "ооо двойник")),
                FakeClient(client_id="client-004", display_name="ООО Договоры", search_names=("договоры", "ооо договоры")),
            )
        }
        self.billing_revisions: dict[str, str] = dict.fromkeys(self.clients, "v1")
        self.created_basis: dict[str, BillingBasis] = {}
        self.services = {item.service_id: item for item in SERVICES}
        self.taxes = {item.tax_id: item for item in TAXES}
        self.default_services = (ResolvedServiceSelection(service_id="service-accounting", quantity=Decimal("1")),)
        self.default_tax_id = "test-vat-5"
        self.previous_invoices: list[PreviousHint] = [PREVIOUS]
        self._lock = asyncio.Lock()

    async def resolve_client(self, query: str) -> ResolvedClient:
        name = " ".join(query.casefold().replace('"', '').replace('«', '').replace('»', '').split())
        matches = [item for item in self.clients.values() if name in item.search_names or name == item.display_name.casefold()]
        if len(matches) > 1:
            raise UserProblem("Найдено несколько клиентов. Уточните полное название и ИНН; документ не создан.")
        if not matches:
            raise UserProblem("Клиент не найден. Уточните название; документ не создан.")
        client = matches[0]
        return ResolvedClient(client_id=client.client_id, display_name=client.display_name)

    async def resolve_service(self, client_id: str, query: str) -> ResolvedService:
        if client_id not in self.clients:
            raise UserProblem("Клиент больше недоступен.")
        name = " ".join(query.casefold().split())
        matches = [item for item in self.services.values()
                   if name in item.search_names or name == item.description.casefold()]
        if len(matches) != 1:
            if matches:
                raise UserProblem("Уточните услугу: " + "; ".join(item.description for item in matches) + ".")
            raise UserProblem("Услуга не найдена в 1С. Уточните название услуги.")
        return ResolvedService(service_id=matches[0].service_id, display_name=matches[0].description)

    def _revision(self, client_id: str) -> str:
        # Covers the entire fake catalog/settings, including edits that forget to bump v1.
        values = [self.billing_revisions.get(client_id, ""), self.clients[client_id].model_dump_json(),
                  ISSUER.model_dump_json(), BANK.model_dump_json(), TERMS.model_dump_json(), self.default_tax_id]
        values += [item.model_dump_json() for item in self.services.values()]
        values += [item.model_dump_json() for item in self.taxes.values()]
        values += [item.model_dump_json() for item in self.default_services]
        values += [item.model_dump_json() for item in self.previous_invoices if item.client_id == client_id]
        values += [basis.preview.model_dump_json() for basis in self.created_basis.values()
                   if basis.client_id == client_id and self.documents[basis.key].posted]
        return hashlib.sha256("\n".join(values).encode()).hexdigest()

    def _previous(self, command: ResolvedInvoiceCommand) -> PreviousHint:
        candidates = [item for item in self.previous_invoices
                      if item.client_id == command.client_id and item.invoice_date < command.invoice_date]
        for basis in self.created_basis.values():
            invoice = self.documents[basis.key]
            preview = basis.preview
            if invoice.posted and basis.client_id == command.client_id and preview.invoice_date < command.invoice_date:
                tax_ids = {line.tax.tax_id for line in preview.lines}
                candidates.append(PreviousHint(reference=preview.reference, client_id=basis.client_id,
                    invoice_date=preview.invoice_date,
                    services=tuple(ResolvedServiceSelection(service_id=line.service_id, quantity=line.quantity)
                                   for line in preview.lines), tax_id=next(iter(tax_ids)) if len(tax_ids) == 1 else None))
        if command.previous == "previous_month":
            prior = command.invoice_date.replace(day=1)
            year, month = (prior.year - 1, 12) if prior.month == 1 else (prior.year, prior.month - 1)
            candidates = [item for item in candidates if (item.invoice_date.year, item.invoice_date.month) == (year, month)]
        if not candidates:
            raise UserProblem("Предыдущий счёт не найден. Укажите услуги для нового preview.")
        return max(candidates, key=lambda item: item.invoice_date)

    async def resolve_basis(self, command: ResolvedInvoiceCommand) -> BillingBasis:
        command = ResolvedInvoiceCommand.model_validate(command)
        if command.client_id == "client-004":
            raise UserProblem("Найдено несколько договоров. Уточните договор; документ не создан.")
        if command.client_id not in self.clients:
            raise UserProblem("Контрагент больше недоступен. Уточните данные; документ не создан.")
        if command.invoice_date is None:
            raise UserProblem("Укажите дату счёта.")
        period = command.service_period
        # The existing monthly contract remains unique per service period. New
        # date commands for that same period must not open a second operation.
        identity = f"{period.year}-{period.month:02d}" if period else command.invoice_date.isoformat()
        key = f"fake-org:{command.client_id}:standard:{identity}"
        previous = self._previous(command) if command.previous != "none" else None
        selections = command.services or (previous.services if previous else self.default_services)
        tax_id = previous.tax_id if previous and command.tax.mode == "default" else self.default_tax_id
        if tax_id is None:
            raise UserProblem("В предыдущем счёте несколько налоговых режимов. Уточните режим для нового preview.")
        if command.tax.mode == "with_tax":
            candidates = [item for item in self.taxes.values() if item.treatment == "standard"]
            if len(candidates) != 1:
                raise UserProblem("Уточните допустимый налоговый профиль в 1С.")
            tax_id = candidates[0].tax_id
        elif command.tax.mode == "without_tax":
            candidates = [item for item in self.taxes.values() if item.treatment == "outside_scope"]
            if len(candidates) != 1:
                raise UserProblem("Уточните допустимый режим без НДС в 1С.")
            tax_id = candidates[0].tax_id
        elif command.tax.mode == "profile":
            candidates = [item for item in self.taxes.values() if item.label.casefold() == command.tax.query.casefold()]
            if len(candidates) != 1:
                raise UserProblem("Налоговый профиль не найден или неоднозначен. Уточните режим.")
            tax_id = candidates[0].tax_id
        if tax_id not in self.taxes:
            raise UserProblem("Прежний налоговый профиль больше не допустим. Уточните режим.")
        tax = self.taxes[tax_id]
        lines = []
        for selected in selections:
            service = self.services.get(selected.service_id)
            if service is None:
                raise UserProblem("Услуга больше не доступна в 1С. Уточните услугу.")
            quantity = selected.quantity or service.quantity
            subtotal = (quantity * service.price).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            vat = (subtotal * tax.rate / 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            lines.append(InvoiceLine(service_id=service.service_id, description=service.description,
                         quantity=quantity, uom=service.uom, price=service.price, tax=tax,
                         subtotal=subtotal, tax_amount=vat, total=subtotal + vat))
        subtotal = sum((line.subtotal for line in lines), Decimal(0))
        vat = sum((line.tax_amount for line in lines), Decimal(0))
        preview = InvoicePreview(invoice_date=command.invoice_date,
            supply_date=(date(period.year, period.month, calendar.monthrange(period.year, period.month)[1])
                         if period else command.invoice_date), service_period=period, currency="AED",
            issuer=ISSUER, recipient=recipient(self.clients[command.client_id].display_name), bank=BANK, terms=TERMS,
            lines=tuple(lines), subtotal=subtotal, tax_amount=vat, total=subtotal+vat,
            amount_in_words=amount_words(subtotal+vat, "AED"),
            reference="TEST-" + hashlib.sha256(key.encode()).hexdigest()[:12].upper(),
            previous_reference=previous.reference if previous else None)
        return BillingBasis(key=key, client_id=command.client_id, revision=self._revision(command.client_id), preview=preview)

    async def read_operation(self, basis: BillingBasis, operation_id: str) -> OperationState:
        async with self._lock:
            invoice = self.documents.get(basis.key)
            return OperationState(operation_id=operation_id,
                                  status=("posted" if invoice.posted else "draft") if invoice else "not_started",
                                  invoice=invoice)

    def _check_fresh(self, basis: BillingBasis):
        if (basis.client_id not in self.clients
                or self._revision(basis.client_id) != basis.revision):
            raise StaleBasis()

    async def ensure_draft(self, basis: BillingBasis, operation_id: str) -> Invoice:
        async with self._lock:
            if basis.key not in self.documents:
                self._check_fresh(basis)
                self.documents[basis.key] = Invoice(
                    document_id=f"mock-{len(self.documents) + 1}", posted=False,
                    client_id=basis.client_id, basis_key=basis.key, revision="1",
                    preview_digest=basis.preview.digest,
                )
                self.created_basis[basis.key] = basis
                if self.fault.mode == "create_lost_response" and not self._fault_triggered:
                    self._fault_triggered = True
                    raise TimeoutError("fake 1C response intentionally lost after create")
            if self.documents[basis.key].preview_digest != basis.preview.digest:
                raise StaleBasis()
            return self.documents[basis.key]

    async def ensure_posted(self, basis: BillingBasis, invoice: Invoice, operation_id: str) -> Invoice:
        async with self._lock:
            current = self.documents.get(basis.key)
            if current is None or current.document_id != invoice.document_id:
                raise ValueError("Unknown fake document")
            if current.posted:
                return current
            self._check_fresh(basis)
            if (current.revision != invoice.revision or current.revision != "1"
                    or self.created_basis[basis.key] != basis):
                raise StaleBasis()
            posted = Invoice(document_id=current.document_id, posted=True, client_id=current.client_id,
                             basis_key=current.basis_key, revision="2", preview_digest=current.preview_digest)
            self.documents[basis.key] = posted
            if self.fault.mode == "post_lost_response" and not self._fault_triggered:
                self._fault_triggered = True
                raise TimeoutError("fake 1C response intentionally lost after post")
            return posted

    async def get_pdf(self, invoice: Invoice) -> PdfDocument:
        current = next((item for item in self.documents.values()
                        if item.document_id == invoice.document_id), None)
        if current is None or not current.posted or not invoice.posted or current != invoice:
            raise ValueError("Unposted fake document")
        return render_mock_pdf(self.created_basis[current.basis_key].preview)
