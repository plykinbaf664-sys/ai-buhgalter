"""Private durable operation/delivery journal, not an accounting authority.

Only a provider read-back can prove an external document exists or is posted.
A locally recorded mutation intent cannot be reset by an absent remote result:
the first request might still be in flight. This deliberately sacrifices blind
retry availability to keep at-most-one mutation across processes/restarts.
"""
from contextlib import contextmanager
import hashlib
import os
from pathlib import Path
import sqlite3
from typing import Literal

from pydantic import model_validator

from app.domain import (Invoice, InvoiceConflict, PdfDocument, PreparedInvoice,
                        StrictModel, TaxInvoice, TaxInvoiceReference, TaxInvoicePdf, TaxPdfProvenance)


class JournalUnavailable(Exception):
    """Safe boundary: never expose SQL, snapshots, filesystem or raw error text."""


class MutationUncertain(Exception):
    """An earlier mutation intent cannot be replayed without stronger evidence."""


class StoredTaxOperation(StrictModel):
    source_document_id: str
    phase: Literal['generation_started', 'draft', 'post_started', 'posted']
    returned_reference: TaxInvoiceReference | None = None
    invoice: TaxInvoice | None = None
    print_provenance: TaxPdfProvenance | None = None

    @model_validator(mode='after')
    def consistent_tax_operation(self):
        if (self.phase == 'generation_started') != (self.invoice is None):
            raise ValueError('Inconsistent tax generation state')
        for item in (self.returned_reference, self.invoice, self.print_provenance):
            if item is not None and item.source_document_id != self.source_document_id:
                raise ValueError('Foreign tax source')
        if self.invoice is not None:
            if self.invoice.posted != (self.phase == 'posted'):
                raise ValueError('Inconsistent tax posting state')
            if self.returned_reference is not None and self.returned_reference.document_id != self.invoice.document_id:
                raise ValueError('Tax reference changed after generation')
        if self.print_provenance is not None and (self.invoice is None or not self.invoice.posted
                or self.print_provenance.document_id != self.invoice.document_id
                or self.print_provenance.document_revision != self.invoice.revision):
            raise ValueError('Unverified tax print provenance')
        return self


class StoredOperation(StrictModel):
    prepared: PreparedInvoice
    phase: Literal["reserved", "create_started", "draft", "post_started", "posted", "pdf_ready"]
    invoice: Invoice | None = None
    pdf: TaxInvoicePdf | PdfDocument | None = None
    tax: StoredTaxOperation | None = None

    @model_validator(mode="after")
    def consistent(self):
        if (self.phase in ("reserved", "create_started")) != (self.invoice is None):
            raise ValueError("Inconsistent stored operation")
        if self.invoice is not None:
            if (self.invoice.client_id != self.prepared.request.client_id
                    or self.invoice.basis_key != self.prepared.basis.key
                    or self.invoice.preview_digest != self.prepared.preview.digest
                    or self.invoice.posted != (self.phase in ("posted", "pdf_ready"))):
                raise ValueError("Stored invoice identity mismatch")
        if (self.pdf is not None) != (self.phase == "pdf_ready"):
            raise ValueError("Inconsistent stored PDF")
        if self.tax is not None:
            if (self.invoice is None or not self.invoice.posted
                    or self.tax.source_document_id != self.invoice.document_id):
                raise ValueError('Unverified tax source invoice')
            tax = self.tax.invoice
            if tax is not None and (tax.client_id != self.prepared.request.client_id
                    or tax.basis_key != self.prepared.basis.key or tax.preview_digest != self.prepared.preview.digest):
                raise ValueError('Tax operation snapshot mismatch')
            if (self.pdf is not None) != (self.tax.print_provenance is not None):
                raise ValueError('Tax PDF metadata missing')
            if self.pdf is not None and (not isinstance(self.pdf, TaxInvoicePdf)
                    or self.pdf.provenance != self.tax.print_provenance):
                raise ValueError('Wrong tax PDF')
        elif isinstance(self.pdf, TaxInvoicePdf):
            raise ValueError('Tax PDF has no verified tax operation')
        return self


class OperationJournal:
    def __init__(self, path: Path, *, namespace: str, create: bool = False):
        if not namespace or len(namespace) > 200:
            raise ValueError("Invalid operation journal namespace")
        if type(create) is not bool:
            raise ValueError("Journal initialization must be explicit")
        self.path, self.namespace = Path(path), namespace
        created = False
        try:
            if self.path.is_symlink():
                raise JournalUnavailable()
            self.path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
            if os.name != "nt" and self.path.parent.stat().st_mode & 0o077:
                raise JournalUnavailable()
            if not self.path.exists():
                if not create:
                    raise JournalUnavailable()
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                os.close(fd)
                created = True
            if os.name != "nt" and self.path.stat().st_mode & 0o077:
                raise JournalUnavailable()
            with self._connection() as db:
                version = db.execute("PRAGMA user_version").fetchone()[0]
                if version not in (0, 1, 2, 3):
                    raise JournalUnavailable()
                if version == 0:
                    if not created:
                        raise JournalUnavailable()
                    if db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchone():
                        raise JournalUnavailable()
                    db.execute("CREATE TABLE journal_meta (namespace TEXT PRIMARY KEY)")
                    db.execute("INSERT INTO journal_meta VALUES (?)", (namespace,))
                    db.execute("""CREATE TABLE operations (
                        operation_id TEXT PRIMARY KEY, basis_key TEXT NOT NULL UNIQUE,
                        digest TEXT NOT NULL, prepared TEXT NOT NULL, phase TEXT NOT NULL,
                        invoice TEXT, pdf BLOB, pdf_sha256 TEXT)""")
                    db.execute("""CREATE TABLE deliveries (
                        operation_id TEXT NOT NULL REFERENCES operations(operation_id),
                        user_id INTEGER NOT NULL, phase TEXT NOT NULL,
                        PRIMARY KEY(operation_id,user_id))""")
                if version in (0, 1):
                    # Append-only migration: no existing identity/intent is reset.
                    db.execute("CREATE TABLE provider_requests (operation_id TEXT NOT NULL REFERENCES operations(operation_id), stage TEXT NOT NULL, PRIMARY KEY(operation_id,stage))")
                    db.execute("PRAGMA user_version=2")
                if version in (0, 1, 2):
                    db.execute('''CREATE TABLE tax_operations (
                        operation_id TEXT PRIMARY KEY REFERENCES operations(operation_id),
                        source_document_id TEXT NOT NULL UNIQUE, phase TEXT NOT NULL,
                        returned_document_id TEXT UNIQUE, tax_document_id TEXT UNIQUE,
                        invoice TEXT, pdf_meta TEXT)''')
                    db.execute('PRAGMA user_version=3')
                self._check_namespace(db)
                if db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                    raise JournalUnavailable()
        except JournalUnavailable:
            raise
        except Exception:
            raise JournalUnavailable() from None

    @contextmanager
    def _connection(self):
        db = None
        try:
            db = sqlite3.connect(self.path, timeout=1, isolation_level=None)
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("PRAGMA synchronous=FULL")
            # A rollback journal with FULL sync keeps operations atomic and avoids
            # a background writer or a new service. Each transition is tiny.
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except (JournalUnavailable, MutationUncertain, InvoiceConflict):
            if db is not None:
                db.rollback()
            raise
        except Exception:
            if db is not None:
                db.rollback()
            raise JournalUnavailable() from None
        finally:
            if db is not None:
                db.close()

    def _check_namespace(self, db):
        if db.execute("PRAGMA user_version").fetchone()[0] != 3:
            raise JournalUnavailable()
        rows = db.execute("SELECT namespace FROM journal_meta").fetchall()
        if len(rows) != 1 or rows[0][0] != self.namespace:
            raise JournalUnavailable()

    def _load(self, db, operation_id) -> StoredOperation | None:
        self._check_namespace(db)
        row = db.execute("SELECT * FROM operations WHERE operation_id=?", (operation_id,)).fetchone()
        if row is None:
            return None
        prepared = PreparedInvoice.model_validate_json(row["prepared"])
        if (prepared.operation_id != operation_id or prepared.basis.key != row["basis_key"]
                or prepared.preview.digest != row["digest"]):
            raise JournalUnavailable()
        tax_row = db.execute('SELECT * FROM tax_operations WHERE operation_id=?', (operation_id,)).fetchone()
        tax = None
        if tax_row is not None:
            tax_invoice = TaxInvoice.model_validate_json(tax_row['invoice']) if tax_row['invoice'] is not None else None
            if (tax_invoice.document_id if tax_invoice is not None else None) != tax_row['tax_document_id']:
                raise JournalUnavailable()
            tax = StoredTaxOperation(source_document_id=tax_row['source_document_id'], phase=tax_row['phase'],
                returned_reference=TaxInvoiceReference(document_id=tax_row['returned_document_id'],
                    source_document_id=tax_row['source_document_id']) if tax_row['returned_document_id'] is not None else None,
                invoice=tax_invoice,
                print_provenance=TaxPdfProvenance.model_validate_json(tax_row['pdf_meta']) if tax_row['pdf_meta'] is not None else None)
        pdf = ((TaxInvoicePdf(content=bytes(row['pdf']), provenance=tax.print_provenance)
                if tax is not None and tax.print_provenance is not None else PdfDocument(content=bytes(row['pdf'])))
               if row['pdf'] is not None else None)
        if (pdf is not None and hashlib.sha256(pdf.content).hexdigest() != row["pdf_sha256"]
                or pdf is None and row["pdf_sha256"] is not None):
            raise JournalUnavailable()
        return StoredOperation(prepared=prepared, phase=row["phase"],
            invoice=Invoice.model_validate_json(row["invoice"]) if row["invoice"] is not None else None,
            pdf=pdf, tax=tax)

    def get(self, operation_id: str) -> StoredOperation | None:
        with self._connection() as db:
            return self._load(db, operation_id)

    def reserve(self, prepared: PreparedInvoice, user_id: int) -> StoredOperation:
        prepared = PreparedInvoice.model_validate(prepared)
        if type(user_id) is not int or not 0 < user_id < 2**52:
            raise ValueError("Invalid journal owner")
        with self._connection() as db:
            existing = self._load(db, prepared.operation_id)
            if existing is not None and existing.prepared != prepared:
                # A different frozen request cannot inherit an earlier confirmation.
                raise InvoiceConflict()
            if existing is None:
                db.execute("INSERT INTO operations VALUES (?,?,?,?,?,NULL,NULL,NULL)",
                    (prepared.operation_id, prepared.basis.key, prepared.preview.digest,
                     prepared.model_dump_json(), "reserved"))
            db.execute("INSERT OR IGNORE INTO deliveries VALUES (?,?,'ready')",
                       (prepared.operation_id, user_id))
            return self._load(db, prepared.operation_id)

    def claim_mutation(self, operation_id: str, stage: Literal["create", "post"]) -> None:
        if stage not in ("create", "post"):
            raise ValueError("Invalid mutation stage")
        with self._connection() as db:
            stored = self._load(db, operation_id)
            expected = "reserved" if stage == "create" else "draft"
            if stored is None or stored.phase != expected:
                raise MutationUncertain()
            db.execute("UPDATE operations SET phase=? WHERE operation_id=?",
                       (stage + "_started", operation_id))

    def observe(self, operation_id: str, invoice: Invoice) -> None:
        """Record verified provider state; a draft never clears uncertain posting."""
        invoice = Invoice.model_validate(invoice)
        with self._connection() as db:
            stored = self._load(db, operation_id)
            if stored is None:
                raise JournalUnavailable()
            if (invoice.client_id != stored.prepared.request.client_id
                    or invoice.basis_key != stored.prepared.basis.key
                    or invoice.preview_digest != stored.prepared.preview.digest
                    or stored.invoice is not None and stored.invoice.document_id != invoice.document_id):
                raise InvoiceConflict()
            if stored.invoice is not None and stored.invoice.posted and not invoice.posted:
                raise MutationUncertain()
            if stored.pdf is not None and stored.invoice != invoice:
                raise InvoiceConflict()
            phase = ("pdf_ready" if stored.pdf is not None else "posted") if invoice.posted else (
                "post_started" if stored.phase == "post_started" else "draft")
            db.execute("UPDATE operations SET invoice=?,phase=? WHERE operation_id=?",
                       (invoice.model_dump_json(), phase, operation_id))

    def claim_provider_request(self, operation_id: str, stage: Literal["create", "post", "generate_tax", "post_tax"]) -> None:
        """Last durable claim immediately before transport; also protects direct adapter calls."""
        if stage not in ("create", "post", "generate_tax", "post_tax"):
            raise ValueError("Invalid provider stage")
        with self._connection() as db:
            stored = self._load(db, operation_id)
            expected = ('generation_started' if stage == 'generate_tax' else 'post_started')
            valid = (stored is not None and stored.tax is not None and stored.tax.phase == expected
                     if stage in ('generate_tax', 'post_tax') else stored is not None and stored.phase == stage + '_started')
            if not valid:
                raise MutationUncertain()
            cursor = db.execute("INSERT OR IGNORE INTO provider_requests VALUES (?,?)", (operation_id, stage))
            if cursor.rowcount != 1:
                raise MutationUncertain()

    @staticmethod
    def _tax_generation_unsubmitted(db, stored) -> bool:
        return bool(stored is not None and stored.invoice is not None and stored.invoice.posted
            and stored.tax is not None and stored.tax.phase == 'generation_started'
            and stored.tax.invoice is None and stored.tax.returned_reference is None
            and stored.pdf is None
            and db.execute("SELECT 1 FROM provider_requests WHERE operation_id=? AND stage='generate_tax'",
                           (stored.prepared.operation_id,)).fetchone() is None)

    def tax_generation_unsubmitted(self, operation_id: str) -> bool:
        with self._connection() as db:
            return self._tax_generation_unsubmitted(db, self._load(db, operation_id))

    def claim_tax_generation(self, operation_id: str, *, allow_unsubmitted: bool = False) -> None:
        if type(allow_unsubmitted) is not bool:
            raise ValueError('Explicit dispatch capability required')
        with self._connection() as db:
            stored = self._load(db, operation_id)
            if allow_unsubmitted and self._tax_generation_unsubmitted(db, stored):
                return  # Preserve the original intent; the unique send claim is still absent.
            if (stored is None or stored.invoice is None or not stored.invoice.posted
                    or stored.tax is not None or stored.pdf is not None):
                raise MutationUncertain()
            db.execute("INSERT INTO tax_operations VALUES (?,?,'generation_started',NULL,NULL,NULL,NULL)",
                       (operation_id, stored.invoice.document_id))

    def record_tax_reference(self, operation_id: str, reference: TaxInvoiceReference) -> None:
        reference = TaxInvoiceReference.model_validate(reference)
        with self._connection() as db:
            stored = self._load(db, operation_id)
            if stored is None or stored.tax is None or reference.source_document_id != stored.tax.source_document_id:
                raise InvoiceConflict()
            old = stored.tax.returned_reference
            if (old is not None and old != reference
                    or stored.tax.invoice is not None and stored.tax.invoice.document_id != reference.document_id):
                raise InvoiceConflict()
            db.execute('UPDATE tax_operations SET returned_document_id=? WHERE operation_id=?',
                       (reference.document_id, operation_id))

    def observe_tax(self, operation_id: str, invoice: TaxInvoice) -> None:
        invoice = TaxInvoice.model_validate(invoice)
        with self._connection() as db:
            stored = self._load(db, operation_id)
            if (stored is None or stored.invoice is None or not stored.invoice.posted
                    or invoice.source_document_id != stored.invoice.document_id
                    or invoice.client_id != stored.prepared.request.client_id
                    or invoice.basis_key != stored.prepared.basis.key
                    or invoice.preview_digest != stored.prepared.preview.digest):
                raise InvoiceConflict()
            old = stored.tax
            if old is not None:
                if (old.returned_reference is not None and old.returned_reference.document_id != invoice.document_id
                        or old.invoice is not None and old.invoice.document_id != invoice.document_id
                        or old.print_provenance is not None and old.invoice != invoice):
                    raise InvoiceConflict()
                if old.invoice is not None and old.invoice.posted and not invoice.posted:
                    raise MutationUncertain()
            elif stored.pdf is not None:
                raise InvoiceConflict()
            phase = ('posted' if invoice.posted else 'post_started' if old is not None and old.phase == 'post_started' else 'draft')
            if old is None:
                db.execute('INSERT INTO tax_operations VALUES (?,?,?,?,?,?,NULL)',
                    (operation_id, invoice.source_document_id, phase, invoice.document_id, invoice.document_id, invoice.model_dump_json()))
            else:
                db.execute('UPDATE tax_operations SET phase=?,returned_document_id=?,tax_document_id=?,invoice=? WHERE operation_id=?',
                    (phase, invoice.document_id, invoice.document_id, invoice.model_dump_json(), operation_id))

    def claim_tax_post(self, operation_id: str) -> None:
        with self._connection() as db:
            stored = self._load(db, operation_id)
            if stored is None or stored.tax is None or stored.tax.phase != 'draft':
                raise MutationUncertain()
            db.execute("UPDATE tax_operations SET phase='post_started' WHERE operation_id=?", (operation_id,))

    def cache_tax_pdf(self, operation_id: str, invoice: Invoice, tax: TaxInvoice, pdf: TaxInvoicePdf) -> None:
        pdf = TaxInvoicePdf.model_validate(pdf)
        with self._connection() as db:
            stored = self._load(db, operation_id)
            if (stored is None or stored.invoice != invoice or stored.tax is None or stored.tax.invoice != tax
                    or not tax.posted or pdf.provenance.document_id != tax.document_id
                    or pdf.provenance.source_document_id != invoice.document_id
                    or pdf.provenance.document_revision != tax.revision
                    or stored.pdf is not None and stored.pdf != pdf):
                raise InvoiceConflict()
            db.execute("UPDATE operations SET phase='pdf_ready',pdf=?,pdf_sha256=? WHERE operation_id=?",
                       (pdf.content, hashlib.sha256(pdf.content).hexdigest(), operation_id))
            db.execute('UPDATE tax_operations SET pdf_meta=? WHERE operation_id=?',
                       (pdf.provenance.model_dump_json(), operation_id))

    def finalized_without_pdf(self, operation_id: str, user_id: int) -> None:
        with self._connection() as db:
            stored = self._load(db, operation_id)
            if stored is None or stored.invoice is None or not stored.invoice.posted or stored.tax is not None:
                raise JournalUnavailable()
            db.execute("UPDATE deliveries SET phase='finalized' WHERE operation_id=? AND user_id=? AND phase='ready'",
                       (operation_id, user_id))

    def cache_pdf(self, operation_id: str, invoice: Invoice, pdf: PdfDocument) -> None:
        pdf = PdfDocument.model_validate(pdf)
        with self._connection() as db:
            stored = self._load(db, operation_id)
            if stored is None or stored.invoice != invoice or not invoice.posted or stored.tax is not None:
                raise InvoiceConflict()
            if stored.pdf is not None and stored.pdf != pdf:
                raise InvoiceConflict()
            db.execute("UPDATE operations SET phase='pdf_ready',pdf=?,pdf_sha256=? WHERE operation_id=?",
                       (pdf.content, hashlib.sha256(pdf.content).hexdigest(), operation_id))

    def delivery_status(self, operation_id: str, user_id: int) -> Literal["ready", "sending", "delivered", "finalized"] | None:
        with self._connection() as db:
            stored = self._load(db, operation_id)
            row = db.execute("SELECT phase FROM deliveries WHERE operation_id=? AND user_id=?",
                             (operation_id, user_id)).fetchone()
            if row is None:
                return None
            if stored is None or row[0] not in ("ready", "sending", "delivered", "finalized"):
                raise JournalUnavailable()
            return row[0]

    def claim_delivery(self, operation_id: str, user_id: int) -> bool:
        with self._connection() as db:
            stored = self._load(db, operation_id)
            if stored is None or stored.pdf is None:
                raise JournalUnavailable()
            cursor = db.execute("UPDATE deliveries SET phase='sending' WHERE operation_id=? AND user_id=? AND phase='ready'",
                                (operation_id, user_id))
            return cursor.rowcount == 1

    def delivered(self, operation_id: str, user_id: int) -> None:
        with self._connection() as db:
            self._load(db, operation_id)
            cursor = db.execute("UPDATE deliveries SET phase='delivered' WHERE operation_id=? AND user_id=? AND phase='sending'",
                                (operation_id, user_id))
            if cursor.rowcount != 1:
                raise JournalUnavailable()

    def recoveries(self) -> dict[int, PreparedInvoice]:
        with self._connection() as db:
            self._check_namespace(db)
            result = {}
            for row in db.execute("SELECT user_id,operation_id,phase FROM deliveries WHERE phase NOT IN ('delivered','finalized')").fetchall():
                if row["phase"] not in ("ready", "sending") or row["user_id"] in result:
                    # Never silently choose one of several unfinished operations.
                    raise JournalUnavailable()
                stored = self._load(db, row["operation_id"])
                if stored is None or not 0 < row["user_id"] < 2**52:
                    raise JournalUnavailable()
                result[row["user_id"]] = stored.prepared
            return result
