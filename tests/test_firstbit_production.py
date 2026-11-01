"""Actual production OneC adapter against independent synthetic OData/native UI."""
import asyncio
from uuid import UUID

import httpx
import pytest

from app.domain import WorkflowFailure
from app.firstbit import FirstBitSettings
from app.firstbit_production import FirstBitProduction, full_execution_schema
from app.operations import OperationJournal
from app.service import InvoiceService
from scripts.firstbit_fixture import ref
from test_firstbit_tax import TaxFixture, tax_record
from test_firstbit_write import prepare


class SyntheticNativeUI:
    def __init__(self,fixture,*,auto_posted=True):
        self.fixture=fixture;self.prepared=None;self.auto_posted=auto_posted
        self.posts=self.generates=self.tax_posts=self.prints=0
        self.fault=None;self.warms=[]
    async def aclose(self):pass
    async def warm_document(self,kind,reference,number):
        self.warms.append((kind,reference))
        if self.fault=='warm':
            self.fault=None
            raise TimeoutError('Synthetic pre-action login failure')
    async def post_document(self,kind,reference,number,before_action):
        await before_action()
        if kind=='InventoryExpense':
            self.posts+=1;document=self.fixture.created[0]
        else:
            self.tax_posts+=1;document=self.fixture.tax[0]
        if self.fault==('tax_post_before_commit' if kind=='TaxInvoice' else 'post_before_commit'):raise TimeoutError('Synthetic timeout before native commit')
        document['Posted']=True
        document['DataVersion']='posted-v2'
        if self.fault==('tax_post_after_commit' if kind=='TaxInvoice' else 'post_after_commit'):raise TimeoutError('Synthetic native response lost')
    async def generate_tax_invoice(self,reference,number,before_action,*,before_send):
        await before_action()
        if self.fault=='generate_preflight':raise BackendFailure('firstbit_ui_session_unavailable')
        await before_send();self.generates+=1
        if self.fault=='generate_before_commit':raise TimeoutError('Synthetic generation result unknown')
        record=tax_record(self.fixture,self.prepared);record['Posted']=self.auto_posted
        self.fixture.tax.append(record)
        if self.fault=='generate_after_commit':raise TimeoutError('Synthetic response lost after generation')
    async def print_tax_invoice(self,reference,number,before_action):
        await before_action();self.prints+=1
        import pymupdf
        document=pymupdf.open();page=document.new_page(width=842,height=595)
        page.insert_text((30,30),'SYNTHETIC TEST ONLY - Tax Invoice '+number)
        result=document.tobytes();document.close();return result


def backend(fixture,path,ui):
    settings=FirstBitSettings(base_url=fixture.env()['FIRSTBIT_BASE_URL'],username='synthetic_writer',
        password='SYNTHETIC-ONLY',readonly_account=False,write_account=True,bookkeeping_item_id=UUID(ref(5)))
    return FirstBitProduction(settings,journal=OperationJournal(path,namespace='synthetic-production',create=True),
        schema_sha256=full_execution_schema(fixture.metadata).sha256,ui=ui,transport=httpx.MockTransport(fixture.respond))


@pytest.mark.parametrize('auto_posted',[True,False])
def test_complete_production_adapter_contract_and_restart_reuses_both_documents(tmp_path,auto_posted):
    fixture=TaxFixture();ui=SyntheticNativeUI(fixture,auto_posted=auto_posted);path=tmp_path/'private/operations.sqlite'
    async def scenario():
        provider=backend(fixture,path,ui);prepared=await prepare(provider);ui.prepared=prepared
        service=InvoiceService(provider,journal=provider.journal,allow_real_writes=True)
        result=await service.execute(prepared,'confirmed',123)
        assert result.invoice.posted and result.tax_invoice.posted
        assert result.pdf.content.startswith(b'%PDF-')
        assert ui.posts==ui.generates==ui.prints==fixture.posts==1
        assert ui.tax_posts==(0 if auto_posted else 1)
        await provider.aclose()
        provider=backend(fixture,path,ui)
        try:
            repeated=await InvoiceService(provider,journal=provider.journal,allow_real_writes=True).execute(prepared,'restart',123)
            assert repeated==result and ui.generates==ui.prints==1 and fixture.posts==1
        finally:await provider.aclose()
    asyncio.run(scenario())


@pytest.mark.parametrize('fault',['post_before_commit','post_after_commit','generate_before_commit','generate_after_commit','tax_post_before_commit','tax_post_after_commit'])
def test_real_adapter_lost_native_response_never_repeats_a_mutation(tmp_path,fault):
    fixture=TaxFixture();ui=SyntheticNativeUI(fixture,auto_posted=not fault.startswith('tax_post'));ui.fault=fault;path=tmp_path/'private/operations.sqlite'
    async def scenario():
        provider=backend(fixture,path,ui);prepared=await prepare(provider);ui.prepared=prepared
        with pytest.raises(WorkflowFailure):
            await InvoiceService(provider,journal=provider.journal,allow_real_writes=True).execute(prepared,'confirm',123)
        await provider.aclose()
        ui.fault=None;provider=backend(fixture,path,ui)
        try:
            service=InvoiceService(provider,journal=provider.journal,allow_real_writes=True)
            if fault.endswith('after_commit'):
                result=await service.execute(prepared,'restart-reconcile',123)
                assert result.tax_invoice.posted
            else:
                with pytest.raises(WorkflowFailure):await service.execute(prepared,'unknown-reconcile',123)
            assert fixture.posts==1 and ui.posts==1 and ui.generates<=1 and ui.tax_posts<=1
        finally:await provider.aclose()
    asyncio.run(scenario())


def test_ui_readonly_warmup_failure_does_not_consume_create_or_send_claim(tmp_path):
    fixture=TaxFixture();ui=SyntheticNativeUI(fixture);path=tmp_path/'private/operations.sqlite'
    async def scenario():
        provider=backend(fixture,path,ui);prepared=await prepare(provider);ui.prepared=prepared;ui.fault='warm'
        service=InvoiceService(provider,journal=provider.journal,allow_real_writes=True)
        with pytest.raises(WorkflowFailure):await service.execute(prepared,'before-create',123)
        assert fixture.posts==0 and provider.journal.get(prepared.operation_id).phase=='reserved'
        result=await service.execute(prepared,'safe-retry-before-any-write',123)
        assert result.tax_invoice.posted and fixture.posts==1
        await provider.aclose()
    asyncio.run(scenario())

def test_application_factory_selects_native_production_adapter_only_with_explicit_flag(tmp_path,monkeypatch):
    import hashlib
    from app.config import Settings
    from app.main import create_app
    import app.firstbit_production as module
    import app.firstbit_ui as ui_module
    fixture=TaxFixture()
    for key,value in fixture.env().items():monkeypatch.setenv(key,value)
    monkeypatch.setenv('FIRSTBIT_INTEGRATION_ACCOUNT','true')
    path=(tmp_path/'private/operations.sqlite').resolve()
    OperationJournal(path,namespace='invoice:v1:firstbit_write:'+hashlib.sha256(fixture.env()['FIRSTBIT_BASE_URL'].encode()).hexdigest(),create=True)
    observed=[]
    original=module.FirstBitProduction
    class ObservedProduction(original):
        def __init__(self,*args,**kwargs):
            super().__init__(*args,**kwargs);observed.append(self)
    monkeypatch.setattr(module,'FirstBitProduction',ObservedProduction)
    monkeypatch.setattr(ui_module,'FirstBitUI',lambda *args,**kwargs:SyntheticNativeUI(fixture))
    settings=Settings(token='123:'+'x'*30,webhook_secret='x'*32,allowed_users=frozenset({123}),
        mode='firstbit_write',onec_write_enabled=True,firstbit_native_ui_enabled=True,
        operation_db=path,firstbit_write_schema_sha256=full_execution_schema(fixture.metadata).sha256)
    app=create_app(settings,firstbit_transport=httpx.MockTransport(fixture.respond))
    assert app is not None and len(observed)==1
    assert observed[0].requires_tax_invoice and observed[0].native_pdf_available and observed[0].posting_enabled
    assert observed[0].journal.path==path
    asyncio.run(observed[0].aclose())

def test_native_path_accepts_server_lifecycle_flag_without_relaxing_financial_readback(tmp_path):
    class LifecycleFixture(TaxFixture):
        def respond(self,request):
            response=super().respond(request)
            if request.method=='POST' and request.url.path.endswith('/Document_InventoryExpense'):
                self.created[0]['TaxInvoiceIsRequired']=not self.created[0]['TaxInvoiceIsRequired']
            return response
    fixture=LifecycleFixture();ui=SyntheticNativeUI(fixture)
    async def scenario():
        provider=backend(fixture,tmp_path/'private/operations.sqlite',ui)
        prepared=await prepare(provider);ui.prepared=prepared
        result=await InvoiceService(provider,journal=provider.journal,allow_real_writes=True).execute(prepared,'confirmed',123)
        assert result.invoice.posted and result.tax_invoice.posted and fixture.posts==1 and ui.generates==1
        assert result.pdf.content.startswith(b'%PDF-')
        await provider.aclose()
    asyncio.run(scenario())

def test_new_schema_can_reconcile_legacy_posted_snapshot_but_never_write_it(tmp_path):
    from app.domain import PreparedInvoice,BillingBasis,InvoicePreview,WritesDisabled
    from app.firstbit_production import legacy_execution_schema
    from app.firstbit_write import _canonical
    from app.firstbit_tax import read_tax_operation
    fixture=TaxFixture();ui=SyntheticNativeUI(fixture)
    async def scenario():
        provider=backend(fixture,tmp_path/'private/operations.sqlite',ui)
        current=await prepare(provider)
        review=current.preview.execution_review.model_copy(update={
            'schema_sha256':legacy_execution_schema(fixture.metadata).sha256,
            'references':tuple(r for r in current.preview.execution_review.references if not r.role.startswith('issuer:vat_'))})
        preview=InvoicePreview(**{**current.preview.model_dump(),
            'issuer':current.preview.issuer.model_copy(update={'tax_number':None}),'execution_review':review})
        old=PreparedInvoice(**{**current.model_dump(),'basis':BillingBasis(**{**current.basis.model_dump(),'preview':preview})})
        ui.prepared=old
        provider.journal.reserve(old,123)
        payload=provider._payload(old.preview,review,old.basis.client_id)
        fixture.respond(httpx.Request('POST',fixture.env()['FIRSTBIT_BASE_URL']+'Document_InventoryExpense',
            content=_canonical({**payload,'Comment':provider._marker(old.basis,old.operation_id)})))
        fixture.created[0]['Posted']=True
        await provider._schema()
        source=await provider._remote(old.basis,old.operation_id)
        provider.journal.observe(old.operation_id,source)
        fixture.tax=[tax_record(fixture,old)]
        provider.journal.claim_tax_generation(old.operation_id)
        state=await read_tax_operation(provider,old.basis,source,old.operation_id)
        provider.journal.observe_tax(old.operation_id,state.invoice)
        result=await InvoiceService(provider,journal=provider.journal,allow_real_writes=True).execute(old,'legacy-recovery',123)
        assert result.tax_invoice.posted and result.pdf and fixture.posts==1
        assert ui.posts==ui.generates==ui.tax_posts==0
        with pytest.raises(WritesDisabled):await provider.ensure_draft(old.basis,old.operation_id)
        with pytest.raises(WritesDisabled):await provider.ensure_posted(old.basis,source,old.operation_id)
        await provider.aclose()
    asyncio.run(scenario())


def test_restart_after_unsent_generation_preflight_continues_same_confirmed_operation(tmp_path):
    fixture=TaxFixture();ui=SyntheticNativeUI(fixture)
    ui.fault='generate_preflight';path=tmp_path/'private/operations.sqlite'
    async def scenario():
        provider=backend(fixture,path,ui);prepared=await prepare(provider);ui.prepared=prepared
        try:
            with pytest.raises(WorkflowFailure):
                await InvoiceService(provider,journal=provider.journal,allow_real_writes=True).execute(prepared,'confirm',123)
            assert fixture.posts==1 and ui.posts==1 and ui.generates==0
            assert provider.journal.tax_generation_unsubmitted(prepared.operation_id)
        finally:await provider.aclose()
        ui.fault=None
        provider=backend(fixture,path,ui)
        try:
            service=InvoiceService(provider,journal=provider.journal,allow_real_writes=True)
            result=await service.execute(prepared,'restart',123)
            assert result.tax_invoice.posted and result.pdf.content.startswith(b'%PDF-')
            assert fixture.posts==ui.posts==ui.generates==ui.prints==1
            assert await service.execute(prepared,'repeat',123)==result
            assert fixture.posts==ui.generates==1
            assert not provider.journal.tax_generation_unsubmitted(prepared.operation_id)
        finally:await provider.aclose()
    asyncio.run(scenario())
