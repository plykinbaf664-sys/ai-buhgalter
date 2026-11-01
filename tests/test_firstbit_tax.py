"""Synthetic OData TaxInvoice reconciliation: no customer/production fixtures."""
import asyncio
import copy
import json
from types import SimpleNamespace
from uuid import UUID
from xml.etree.ElementTree import fromstring, SubElement, tostring

import httpx
import pytest

from app.domain import BackendFailure, Invoice, InvoiceConflict
from app.firstbit_tax import tax_schema, read_tax_operation
from app.service import InvoiceService
from test_firstbit_write import WriteFixture, provider, prepare
from scripts.firstbit_fixture import ref


def add_tax_schema(raw):
    root=fromstring(raw)
    entity=SubElement(root,'EntityType',Name='Document_TaxInvoice')
    groups={'Edm.Guid':'Ref_Key Company_Key Contract_Key Entity_Key DocumentCurrency_Key AccountingCurrency_Key',
        'Edm.String':'DataVersion Number DocumentBasis DocumentBasis_Type TransactionType CompanyTRN EntityTRN',
        'Edm.DateTime':'Date IssuingDate DateOfOriginalSupply',
        'Edm.Boolean':'DeletionMark Posted Summary','Edm.Double':'DocumentAmount DocumentVATAmount'}
    for kind,names in groups.items():
        for name in names.split():SubElement(entity,'Property',Name=name,Type=kind)
    SubElement(entity,'Property',Name='Inventory',Type='Collection(StandardODATA.SyntheticTaxRow)')
    SubElement(entity,'Property',Name='BasisDocuments',Type='Collection(StandardODATA.SyntheticTaxBasis)')
    basis=SubElement(root,'ComplexType',Name='SyntheticTaxBasis')
    for name in ('DocumentBasis','DocumentBasis_Type'):SubElement(basis,'Property',Name=name,Type='Edm.String')
    row=SubElement(root,'ComplexType',Name='SyntheticTaxRow')
    row_groups={'Edm.Guid':'Ref_Key Contract_Key VATRate_Key','Edm.Int64':'LineNumber',
        'Edm.String':'Item Item_Type UnitOfMeasure UnitOfMeasure_Type DocumentBasis DocumentBasis_Type Content',
        'Edm.Boolean':'AmountVATIn',
        'Edm.Double':'Quantity Price PriceCur Amount AmountCur AmountTotal AmountTotalCur VATAmount VATAmountCur ExchangeRate DiscountMarkupAmount AutomaticDiscountAmount'}
    for kind,names in row_groups.items():
        for name in names.split():SubElement(row,'Property',Name=name,Type=kind)
    SubElement(root.find('EntityContainer'),'EntitySet',Name='Document_TaxInvoice',EntityType='StandardODATA.Document_TaxInvoice')
    for name,groups in {
        'InformationRegister_EntityRegistrationsWithTaxAuthorityAsVATPayer':{
            'Edm.DateTime':'Period','Edm.Guid':'Entity_Key Registration_Key'},
        'Catalog_RegistrationsWithTaxAuthorityAsVATPayer':{
            'Edm.Guid':'Ref_Key','Edm.Boolean':'DeletionMark','Edm.String':'DataVersion Owner Owner_Type TRNVAT'}}.items():
        node=SubElement(root,'EntityType',Name=name)
        for kind,names in groups.items():
            for namepart in names.split():SubElement(node,'Property',Name=namepart,Type=kind)
        SubElement(root.find('EntityContainer'),'EntitySet',Name=name,EntityType='StandardODATA.'+name)
    return tostring(root)


def tax_record(fixture,prepared):
    doc=fixture.created[0]
    record={'Date':doc['Date'],'IssuingDate':doc['Date'],'DateOfOriginalSupply':doc['Date'],'Ref_Key':ref(91),'DataVersion':'tax-v1','Number':'SYN-TAX-001','Posted':True,'DeletionMark':False,
        'Company_Key':doc['Company_Key'],'Contract_Key':doc['Contract_Key'],'Entity_Key':doc['Entity_Key'],
        'DocumentBasis':doc['Ref_Key'],'DocumentBasis_Type':'StandardODATA.Document_InventoryExpense',
        'Summary':False,'BasisDocuments':[],'DocumentCurrency_Key':doc['DocumentCurrency_Key'],
        'AccountingCurrency_Key':doc['AccountingCurrency_Key'],'DocumentAmount':doc['DocumentAmount'],
        'DocumentVATAmount':float(prepared.preview.tax_amount),'TransactionType':'Sale',
        'CompanyTRN':prepared.preview.recipient.tax_number or '', 'EntityTRN':prepared.preview.issuer.tax_number or fixture.issuer_trn, 'Inventory':[]}
    for row in doc['Inventory']:
        record['Inventory'].append({'Ref_Key':record['Ref_Key'],'LineNumber':row['LineNumber'],
            'DocumentBasis':doc['Ref_Key'],'DocumentBasis_Type':'StandardODATA.Document_InventoryExpense',
            'Contract_Key':doc['Contract_Key'],'Item':row['Item_Key'],'Item_Type':'StandardODATA.Catalog_Items',
            'Content':row['Content'],'Quantity':row['Quantity'],'Price':row['Price'],'PriceCur':row['Price'],
            'Amount':row['Amount'],'AmountCur':row['Amount'],'AmountTotal':row['AmountTotal'],
            'AmountTotalCur':row['AmountTotal'],'VATAmount':row['VATAmount'],'VATAmountCur':row['VATAmount'],
            'VATRate_Key':row['VATRate_Key'],'AmountVATIn':doc['AmountVATIn'],'UnitOfMeasure':row['UnitOfMeasure'],
            'UnitOfMeasure_Type':row['UnitOfMeasure_Type'],'ExchangeRate':1,'DiscountMarkupAmount':0,'AutomaticDiscountAmount':0})
    return record


class TaxFixture(WriteFixture):
    def __init__(self):
        super().__init__();self.metadata=add_tax_schema(self.metadata);self.tax=[]
        self.issuer_trn='SYNTHETIC-ISSUER-VAT'
        self.vat_links=[{'Period':'2000-01-01T00:00:00','Entity_Key':ref(3),'Registration_Key':ref(66)}]
        self.vat_registrations=[{'Ref_Key':ref(66),'DeletionMark':False,'DataVersion':'vat-v1',
            'Owner':ref(3),'Owner_Type':'StandardODATA.Catalog_Entities','TRNVAT':self.issuer_trn}]
    def respond(self,request):
        if request.url.path.endswith('/InformationRegister_EntityRegistrationsWithTaxAuthorityAsVATPayer'):
            assert request.method=='GET'
            self.calls.append(request)
            parts=request.url.params['$filter'].split("'")
            rows=[r for r in self.vat_links if r['Entity_Key']==parts[1] and r['Period']<=parts[3]]
            rows=sorted(rows,key=lambda r:r['Period'],reverse=True)[:2]
            return httpx.Response(200,json={'value':rows})
        if request.url.path.endswith('/Catalog_RegistrationsWithTaxAuthorityAsVATPayer'):
            assert request.method=='GET'
            self.calls.append(request)
            key=request.url.params['$filter'].split("'")[1]
            return httpx.Response(200,json={'value':[r for r in self.vat_registrations if r['Ref_Key']==key]})
        if request.url.path.endswith('/Document_TaxInvoice'):
            assert request.method=='GET'
            self.calls.append(request)
            rows=self.tax
            predicate=request.url.params.get('$filter','')
            if predicate.startswith("Ref_Key eq guid'"):
                key=predicate.split("'")[1];rows=[r for r in rows if r['Ref_Key']==key]
            else:
                assert not predicate and request.url.params['$orderby']=='Ref_Key asc'
                start=int(request.url.params['$skip']);rows=rows[start:start+200]
            keys=request.url.params['$select'].split(',')
            return httpx.Response(200,json={'value':[{key:r[key] for key in keys} for r in rows]})
        return super().respond(request)


async def source_ready(fixture,tmp_path):
    backend=provider(fixture,tmp_path/'private/operations.sqlite')
    prepared=await prepare(backend)
    result=await InvoiceService(backend,journal=backend.journal,allow_real_writes=True).execute(prepared,'confirmed',123)
    fixture.created[0]['Posted']=True
    source=Invoice(**{**result.invoice.model_dump(),'posted':True})
    backend.journal.observe(prepared.operation_id,source)
    return backend,prepared,source


def test_authoritative_linked_tax_readback_checks_all_rows(tmp_path):
    fixture=TaxFixture()
    async def scenario():
        backend,prepared,source=await source_ready(fixture,tmp_path)
        try:
            fixture.tax=[tax_record(fixture,prepared)]
            state=await read_tax_operation(backend,prepared.basis,source,prepared.operation_id)
            assert state.status=='posted' and state.invoice.source_document_id==source.document_id
            assert state.invoice.preview_digest==prepared.preview.digest
            assert fixture.posts==1
        finally:await backend.aclose()
    asyncio.run(scenario())


@pytest.mark.parametrize('fault',['duplicate','deleted','foreign_parent','wrong_money','wrong_item','wrong_issuer','summary','foreign_row_parent','Date','IssuingDate','DateOfOriginalSupply'])
def test_mismatched_tax_never_becomes_verified_or_unblocks_generation(tmp_path,fault):
    fixture=TaxFixture()
    async def scenario():
        backend,prepared,source=await source_ready(fixture,tmp_path)
        try:
            record=tax_record(fixture,prepared);fixture.tax=[record]
            if fault=='duplicate':
                second=copy.deepcopy(record);second['Ref_Key']=ref(92);fixture.tax.append(second)
            elif fault=='deleted':record['DeletionMark']=True
            elif fault=='foreign_parent':record['Inventory'][0]['DocumentBasis']=ref(98)
            elif fault=='wrong_money':record['Inventory'][0]['VATAmountCur']+=1
            elif fault=='wrong_item':record['Inventory'][0]['Item']=ref(98)
            elif fault=='wrong_issuer':record['EntityTRN']='SYNTHETIC-DIFFERENT'
            elif fault=='summary':record['Summary']=True
            elif fault in ('Date','IssuingDate','DateOfOriginalSupply'):record[fault]='2020-01-01T00:00:00'
            else:record['Inventory'][0]['Ref_Key']=ref(98)
            with pytest.raises(InvoiceConflict):
                await read_tax_operation(backend,prepared.basis,source,prepared.operation_id)
            assert fixture.posts==1
        finally:await backend.aclose()
    asyncio.run(scenario())


def test_absence_after_generation_intent_remains_unknown_after_restart(tmp_path):
    fixture=TaxFixture()
    async def scenario():
        backend,prepared,source=await source_ready(fixture,tmp_path)
        try:
            assert (await read_tax_operation(backend,prepared.basis,source,prepared.operation_id)).status=='not_started'
            backend.journal.claim_tax_generation(prepared.operation_id)
            assert (await read_tax_operation(backend,prepared.basis,source,prepared.operation_id)).status=='unknown'
        finally:await backend.aclose()
        backend=provider(fixture,tmp_path/'private/operations.sqlite')
        try:
            assert (await read_tax_operation(backend,prepared.basis,source,prepared.operation_id)).status=='unknown'
        finally:await backend.aclose()
    asyncio.run(scenario())


def test_tax_schema_critical_type_change_and_missing_binding_fail_closed():
    original=TaxFixture().metadata
    baseline=tax_schema(original)
    root=fromstring(original)
    root.find("ComplexType[@Name='SyntheticTaxRow']/Property[@Name='Item']").set('Type','Edm.Guid')
    with pytest.raises(BackendFailure):tax_schema(tostring(root))
    root=fromstring(original);root.find("EntityType[@Name='Document_TaxInvoice']/Property[@Name='CompanyTRN']").set('MaxLength','50')
    assert tax_schema(tostring(root))!=baseline


@pytest.mark.parametrize('party',['Company_Key','Contract_Key','Entity_Key'])
def test_linked_tax_with_wrong_party_is_conflict_never_absence(tmp_path,party):
    fixture=TaxFixture()
    async def scenario():
        backend,prepared,source=await source_ready(fixture,tmp_path)
        fixture.tax=[tax_record(fixture,prepared)]
        fixture.tax[0][party]=ref(199)
        try:
            with pytest.raises(InvoiceConflict):
                await read_tax_operation(backend,prepared.basis,source,prepared.operation_id)
        finally:await backend.aclose()
    asyncio.run(scenario())


def test_linked_tax_is_found_after_first_relation_page(tmp_path):
    fixture=TaxFixture()
    async def scenario():
        backend,prepared,source=await source_ready(fixture,tmp_path)
        target=tax_record(fixture,prepared)
        for number in range(200):
            row=copy.deepcopy(target);row['Ref_Key']=ref(2000+number)
            row['DocumentBasis']=ref(9000+number);row['Inventory']=[]
            fixture.tax.append(row)
        fixture.tax.append(target)
        try:
            result=await read_tax_operation(backend,prepared.basis,source,prepared.operation_id)
            assert result.status=='posted' and result.invoice.document_id==target['Ref_Key']
        finally:await backend.aclose()
    asyncio.run(scenario())


@pytest.mark.parametrize('fault',['deleted','owner','trn','missing','ambiguous','zero'])
def test_supplier_vat_registration_must_be_authoritative_and_effective(tmp_path,fault):
    from app.domain import UserProblem
    fixture=TaxFixture()
    async def scenario():
        backend,prepared,source=await source_ready(fixture,tmp_path)
        fixture.tax=[tax_record(fixture,prepared)]
        if fault=='deleted':fixture.vat_registrations[0]['DeletionMark']=True
        elif fault=='owner':fixture.vat_registrations[0]['Owner']=ref(199)
        elif fault=='trn':fixture.vat_registrations[0]['TRNVAT']='DIFFERENT-SYNTHETIC'
        elif fault=='missing':fixture.vat_links=[]
        elif fault=='zero':fixture.vat_links[0]['Registration_Key']=ref(0)
        else:fixture.vat_links.append(copy.deepcopy(fixture.vat_links[0]))
        try:
            with pytest.raises((InvoiceConflict,UserProblem)):
                await read_tax_operation(backend,prepared.basis,source,prepared.operation_id)
            assert fixture.posts==1
        finally:await backend.aclose()
    asyncio.run(scenario())


def test_vat_registration_schema_drift_is_critical(tmp_path):
    from app.firstbit_tax import registration_schema
    fixture=TaxFixture()
    changed=fixture.metadata.replace(b'Name="TRNVAT" Type="Edm.String"',b'Name="TRNVAT" Type="Edm.Double"')
    with pytest.raises(BackendFailure):registration_schema(changed)
