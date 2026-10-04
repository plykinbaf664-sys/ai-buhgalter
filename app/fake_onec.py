"""Ephemeral test double. Its fixtures are NOT a local accounting database."""
import asyncio
from typing import Literal

from app.domain import (BillingBasis, Invoice, OperationState, PdfDocument, ResolvedClient,
                        ResolvedInvoiceCommand, StaleBasis, StrictModel, UserProblem)

# Static, non-financial PDF fixture. No invoice renderer or PDF dependency.
FAKE_PDF = (
    b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
    b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
    b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 150] "
    b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>\nendobj\n"
    b"4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n"
    b"5 0 obj\n<< /Length 57 >>\nstream\n"
    b"BT /F1 14 Tf 20 80 Td (MOCK ONLY - NOT AN INVOICE) Tj ET\n"
    b"endstream\nendobj\nxref\n0 6\n0000000000 65535 f \n"
    b"0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \n"
    b"0000000241 00000 n \n0000000311 00000 n \n"
    b"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n417\n%%EOF\n"
)


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
        self._lock = asyncio.Lock()

    async def resolve_client(self, query: str) -> ResolvedClient:
        name = " ".join(query.casefold().replace('"', '').replace('«', '').replace('»', '').split())
        matches = [item for item in self.clients.values() if name in item.search_names]
        if len(matches) > 1:
            raise UserProblem("Найдено несколько клиентов. Уточните полное название и ИНН; документ не создан.")
        if not matches:
            raise UserProblem("Клиент не найден. Уточните название; документ не создан.")
        client = matches[0]
        return ResolvedClient(client_id=client.client_id, display_name=client.display_name)

    async def resolve_basis(self, command: ResolvedInvoiceCommand) -> BillingBasis:
        if command.client_id == "client-004":
            raise UserProblem("Найдено несколько договоров. Уточните договор; документ не создан.")
        if command.client_id not in self.clients:
            raise UserProblem("Контрагент больше недоступен. Уточните данные; документ не создан.")
        return BillingBasis(key=f"fake-org:{command.client_id}:standard:{command.year}-{command.month:02d}",
                            client_id=command.client_id, revision=self.billing_revisions[command.client_id])

    async def read_operation(self, basis: BillingBasis, operation_id: str) -> OperationState:
        async with self._lock:
            invoice = self.documents.get(basis.key)
            return OperationState(operation_id=operation_id,
                                  status=("posted" if invoice.posted else "draft") if invoice else "not_started",
                                  invoice=invoice)

    def _check_fresh(self, basis: BillingBasis):
        if (basis.client_id not in self.clients
                or self.billing_revisions.get(basis.client_id) != basis.revision):
            raise StaleBasis()

    async def ensure_draft(self, basis: BillingBasis, operation_id: str) -> Invoice:
        async with self._lock:
            if basis.key not in self.documents:
                self._check_fresh(basis)
                self.documents[basis.key] = Invoice(
                    document_id=f"mock-{len(self.documents) + 1}", posted=False,
                    client_id=basis.client_id, basis_key=basis.key, revision="1",
                )
                self.created_basis[basis.key] = basis
                if self.fault.mode == "create_lost_response" and not self._fault_triggered:
                    self._fault_triggered = True
                    raise TimeoutError("fake 1C response intentionally lost after create")
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
                             basis_key=current.basis_key, revision="2")
            self.documents[basis.key] = posted
            if self.fault.mode == "post_lost_response" and not self._fault_triggered:
                self._fault_triggered = True
                raise TimeoutError("fake 1C response intentionally lost after post")
            return posted

    async def get_pdf(self, invoice: Invoice) -> PdfDocument:
        current = next((item for item in self.documents.values()
                        if item.document_id == invoice.document_id), None)
        if current is None or not current.posted or not invoice.posted:
            raise ValueError("Unposted fake document")
        return PdfDocument(content=FAKE_PDF)
