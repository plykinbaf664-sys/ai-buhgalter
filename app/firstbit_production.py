"""Existing FirstBit writer plus native UI finalization/printing and OData authority."""
import asyncio
import httpx
import hashlib
import json
from datetime import datetime,time
from pathlib import Path
from uuid import UUID

from app.domain import BackendFailure, InvoiceConflict, TaxInvoiceReference, TaxInvoicePdf, TaxPdfProvenance, WritesDisabled, AccountingReference, InvoicePreview
from app.firstbit_write import FirstBitWrite, execution_schema, _canonical
from app.firstbit_tax import find_tax_record, read_tax_operation, tax_schema, registration_schema, supplier_registration


def legacy_execution_schema(raw):
    source=execution_schema(raw)
    combined=hashlib.sha256((source.sha256+':'+tax_schema(raw)).encode()).hexdigest()
    return source.model_copy(update={'sha256':combined})


def full_execution_schema(raw):
    legacy=legacy_execution_schema(raw)
    combined=hashlib.sha256((legacy.sha256+':'+registration_schema(raw)).encode()).hexdigest()
    return legacy.model_copy(update={'sha256':combined})


class FirstBitProduction(FirstBitWrite):
    posting_enabled=True
    native_pdf_available=True
    requires_tax_invoice=True
    generation_send_claimed_at_dispatch=True

    def __init__(self,settings,*,journal,schema_sha256,ui,transport=None):
        if ui is None:raise WritesDisabled()
        if transport is None:
            transport=httpx.AsyncHTTPTransport(retries=0,trust_env=False,
                limits=httpx.Limits(max_keepalive_connections=0))
        super().__init__(settings,journal=journal,schema_sha256=schema_sha256,transport=transport)
        self.ui=ui

    async def aclose(self):
        try:await self.ui.aclose()
        finally:await super().aclose()

    async def _schema(self):
        raw=await self._get('$metadata',metadata=True)
        full_execution_schema(raw).require_approved(self.schema_sha256)
        self._verified_legacy_schema_sha256=legacy_execution_schema(raw).sha256

    def _require_current_review(self,basis):
        if basis.preview.execution_review is None or basis.preview.execution_review.schema_sha256!=self.schema_sha256:raise WritesDisabled()

    def _frozen_readback_payload(self,basis):
        review=basis.preview.execution_review
        if review.schema_sha256==self.schema_sha256:return self._frozen_payload(basis)
        # A compatible older confirmed snapshot can reconcile already-created
        # documents without rewriting its digest. It cannot authorize a mutation.
        if (basis.preview.write_blocker or review.schema_sha256!=
                getattr(self,'_verified_legacy_schema_sha256',None)):
            raise WritesDisabled()
        payload=self._payload(basis.preview,review,basis.client_id)
        if hashlib.sha256(_canonical(payload)).hexdigest()!=review.payload_sha256:raise InvoiceConflict()
        return payload

    async def _registration(self,preview):
        return await supplier_registration(self,UUID(preview.historical_proposal.entity_id),
            datetime.combine(preview.invoice_date,time()))

    async def _prepare_preview(self,preview):
        _,registration=await self._registration(preview)
        issuer=preview.issuer.model_copy(update={'tax_number':registration.TRNVAT})
        return InvoicePreview(**{**preview.model_dump(),'issuer':issuer})

    async def _plan(self,preview,client_id):
        review=await super()._plan(preview,client_id)
        link,registration=await self._registration(preview)
        if preview.issuer.tax_number!=registration.TRNVAT:raise InvoiceConflict()
        refs=(AccountingReference(role='issuer:vat_registration',reference_id=str(registration.Ref_Key),
                label='VAT registration'),
            AccountingReference(role='issuer:vat_period',reference_id=str(registration.Ref_Key),
                label='VAT effective period'))
        return review.model_copy(update={'references':(*review.references,*refs),
            'evidence_sha256':hashlib.sha256((review.evidence_sha256+link.model_dump_json()+registration.model_dump_json()).encode()).hexdigest()})

    async def read_operation(self,basis,operation_id):
        await self._schema()
        state=await super().read_operation(basis,operation_id)
        # Browser preparation is read-only and precedes durable financial intent.
        # A login/navigation failure must not consume an Invoice create/post claim.
        if state.status=='not_started':
            history=basis.preview.historical_proposal
            await self.ui.warm_document('InventoryExpense',UUID(history.source_id),history.source_number)
        elif state.status=='draft':
            await self.ui.warm_document('InventoryExpense',UUID(state.invoice.document_id),state.invoice.number)
        return state

    async def ensure_posted(self,basis,invoice,operation_id):
        self._require_current_review(basis)
        stored=self.journal.get(operation_id)
        if stored is None or stored.prepared.basis!=basis:raise WritesDisabled()
        current=await self._remote(basis,operation_id)
        if current is None or current.document_id!=invoice.document_id:raise InvoiceConflict()
        if current.posted:return current
        if current!=invoice:raise InvoiceConflict()
        async def before_action():
            await self._schema()
            _,registration=await self._registration(basis.preview)
            if registration.TRNVAT!=basis.preview.issuer.tax_number:raise InvoiceConflict()
            if await self._remote(basis,operation_id)!=current:raise InvoiceConflict()
            self.journal.claim_provider_request(operation_id,'post')
        await self.ui.post_document('InventoryExpense',UUID(current.document_id),current.number,before_action)
        posted=None
        for attempt in range(12):
            posted=await self._remote(basis,operation_id)
            if posted is not None and posted.posted:break
            await asyncio.sleep(.5)
        if posted is None or not posted.posted or posted.document_id!=current.document_id:
            raise BackendFailure('firstbit_post_uncertain')
        return posted

    async def read_tax_operation(self,basis,source,operation_id):
        state=await read_tax_operation(self,basis,source,operation_id)
        if state.status=='not_started':
            await self.ui.warm_document('InventoryExpense',UUID(source.document_id),source.number)
        elif state.status=='draft':
            await self.ui.warm_document('TaxInvoice',UUID(state.invoice.document_id),state.invoice.number)
        return state

    async def ensure_tax_invoice(self,basis,source,operation_id):
        self._require_current_review(basis)
        current=await self._remote(basis,operation_id)
        if current!=source or not current.posted:raise InvoiceConflict()
        existing=await find_tax_record(self,basis,source)
        if existing is not None:
            return TaxInvoiceReference(document_id=str(existing.Ref_Key),source_document_id=source.document_id)
        async def before_action():
            await self._schema()
            _,registration=await self._registration(basis.preview)
            if registration.TRNVAT!=basis.preview.issuer.tax_number:raise InvoiceConflict()
            if await self._remote(basis,operation_id)!=source:raise InvoiceConflict()
            if await find_tax_record(self,basis,source) is not None:raise InvoiceConflict()
        async def before_send():
            self.journal.claim_provider_request(operation_id,'generate_tax')
        await self.ui.generate_tax_invoice(UUID(source.document_id),source.number,before_action,
                                           before_send=before_send)
        created=None
        for attempt in range(12):
            created=await find_tax_record(self,basis,source)
            if created is not None:break
            await asyncio.sleep(.5)
        if created is None:raise BackendFailure('firstbit_tax_generate_uncertain')
        return TaxInvoiceReference(document_id=str(created.Ref_Key),source_document_id=source.document_id)

    async def ensure_tax_posted(self,basis,invoice,operation_id):
        self._require_current_review(basis)
        stored=self.journal.get(operation_id)
        if stored is None or stored.invoice is None:raise WritesDisabled()
        source=await self._remote(basis,operation_id)
        if source is None or not source.posted:raise InvoiceConflict()
        current=await find_tax_record(self,basis,source)
        if current is None or str(current.Ref_Key)!=invoice.document_id:raise InvoiceConflict()
        if current.Posted:return TaxInvoiceReference(document_id=invoice.document_id,source_document_id=source.document_id)
        if current.DataVersion!=invoice.revision:raise InvoiceConflict()
        async def before_action():
            await self._schema()
            fresh=await find_tax_record(self,basis,source)
            if fresh!=current:raise InvoiceConflict()
            self.journal.claim_provider_request(operation_id,'post_tax')
        await self.ui.post_document('TaxInvoice',UUID(invoice.document_id),invoice.number,before_action)
        posted=None
        for attempt in range(12):
            posted=await find_tax_record(self,basis,source)
            if posted is not None and posted.Posted:break
            await asyncio.sleep(.5)
        if posted is None or not posted.Posted or str(posted.Ref_Key)!=invoice.document_id:
            raise BackendFailure('firstbit_tax_post_uncertain')
        return TaxInvoiceReference(document_id=invoice.document_id,source_document_id=source.document_id)

    async def get_tax_invoice_pdf(self,invoice):
        # Same stable key-to-operation rule as PreparedInvoice.operation_id.
        operation_id=hashlib.sha256(('invoice:v1:'+invoice.basis_key).encode()).hexdigest()
        stored=self.journal.get(operation_id)
        if stored is None or stored.tax is None or stored.tax.invoice!=invoice:raise InvoiceConflict()
        basis=stored.prepared.basis
        source=await self._remote(basis,operation_id)
        if source is None or not source.posted or source.document_id!=invoice.source_document_id:raise InvoiceConflict()
        async def before_action():
            await self._schema()
            current=await find_tax_record(self,basis,source)
            if current is None or not current.Posted or str(current.Ref_Key)!=invoice.document_id or current.DataVersion!=invoice.revision:
                raise InvoiceConflict()
        content=await self.ui.print_tax_invoice(UUID(invoice.document_id),invoice.number,before_action)
        pdf=TaxInvoicePdf(content=content,provenance=TaxPdfProvenance(document_id=invoice.document_id,
            source_document_id=source.document_id,document_revision=invoice.revision,
            print_manager='Document.TaxInvoice',template='TaxInvoiceLandscapeEN'))
        self._verify_native_pdf(pdf,invoice)
        await before_action()  # Bind the downloaded artifact to the still-current document.
        archive=self.journal.path.parent/'native-pdf'
        if archive.is_symlink():raise BackendFailure('firstbit_pdf_private_path')
        archive.mkdir(mode=0o700,exist_ok=True)
        artifact=archive/(operation_id+'.pdf')
        if artifact.is_symlink():raise BackendFailure('firstbit_pdf_private_path')
        temporary=archive/(operation_id+'.tmp')
        if temporary.is_symlink():raise BackendFailure('firstbit_pdf_private_path')
        temporary.write_bytes(pdf.content);temporary.chmod(0o600);temporary.replace(artifact)
        manifest=archive/(operation_id+'.json')
        if manifest.is_symlink():raise BackendFailure('firstbit_pdf_private_path')
        manifest.write_text(json.dumps({'operation_id':operation_id,'invoice_ref':source.document_id,
            'tax_invoice_ref':invoice.document_id,'tax_revision':invoice.revision,
            'sha256':hashlib.sha256(pdf.content).hexdigest(),'path':str(artifact)}))
        manifest.chmod(0o600)
        return pdf

    @staticmethod
    def _verify_native_pdf(pdf,invoice):
        import pymupdf
        try:
            with pymupdf.open(stream=pdf.content,filetype='pdf') as document:
                if not 1<=len(document)<=20 or document.is_encrypted:
                    raise ValueError()
                if any(page.rect.width<=page.rect.height for page in document):raise ValueError()
                text=' '.join(' '.join(page.get_text().split()) for page in document)
                if not invoice.number or invoice.number not in text or 'tax invoice' not in text.casefold():
                    raise ValueError()
        except Exception:
            raise BackendFailure('firstbit_native_pdf_provenance_mismatch') from None
