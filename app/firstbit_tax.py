"""Bounded live TaxInvoice reconciliation; never creates, posts or prints."""
import hashlib
import json
from decimal import Decimal
from datetime import datetime
from typing import Literal
from urllib.parse import quote, urlencode
from uuid import UUID
import xml.etree.ElementTree as ET

from pydantic import Field

from app.domain import BackendFailure, ExternalModel, InvoiceConflict, Money, Quantity, TaxInvoice, TaxOperationState, Label, UserProblem
from app.firstbit import Page, Record, ZERO
from app.http import bounded_request


class SupplierVATLink(ExternalModel):
    Period: datetime
    Entity_Key: UUID
    Registration_Key: UUID


class SupplierVATRegistration(Record):
    DataVersion: Label
    Owner: UUID
    Owner_Type: Literal['StandardODATA.Catalog_Entities']
    TRNVAT: str = Field(min_length=1,max_length=500)


VAT_LINK_SET='InformationRegister_EntityRegistrationsWithTaxAuthorityAsVATPayer'
VAT_REG_SET='Catalog_RegistrationsWithTaxAuthorityAsVATPayer'


def registration_schema(raw: bytes) -> str:
    root=ET.fromstring(raw)
    local=lambda node:node.tag.rsplit('}',1)[-1]
    types={schema.attrib['Namespace']+'.'+node.attrib['Name']:node
        for schema in root.iter() if local(schema)=='Schema'
        for node in schema if local(node)=='EntityType'}
    sets={node.attrib['Name']:node for node in root.iter() if local(node)=='EntitySet'}
    expected={VAT_LINK_SET:{'Period':'Edm.DateTime','Entity_Key':'Edm.Guid','Registration_Key':'Edm.Guid'},
        VAT_REG_SET:{'Ref_Key':'Edm.Guid','DeletionMark':'Edm.Boolean','DataVersion':'Edm.String',
            'Owner':'Edm.String','Owner_Type':'Edm.String','TRNVAT':'Edm.String'}}
    critical={}
    try:
        for name,properties in expected.items():
            binding=sets[name]
            if binding.attrib['EntityType']!='StandardODATA.'+name:raise ValueError()
            critical[name]=dict(binding.attrib)
            node=types[binding.attrib['EntityType']]
            props={item.attrib['Name']:item for item in node if local(item)=='Property'}
            for key,kind in properties.items():
                if props[key].attrib['Type']!=kind:raise ValueError()
                critical[name+'.'+key]=dict(props[key].attrib)
    except (KeyError,ValueError):
        raise BackendFailure('firstbit_registration_schema_mismatch') from None
    return hashlib.sha256(json.dumps(critical,sort_keys=True,separators=(',',':')).encode()).hexdigest()


async def supplier_registration(adapter,entity: UUID,as_of: datetime):
    if entity==ZERO or as_of.tzinfo is not None:raise InvoiceConflict()
    async def query(name,model,predicate,order=None):
        params={'$format':'json','$filter':predicate,'$select':','.join(model.model_fields),'$top':'2'}
        if order:params['$orderby']=order
        url=adapter.settings.base_url+name+'?'+urlencode(params,quote_via=quote)
        raw=await bounded_request(adapter._client,'GET',url,limit=1_000_000,deadline=12)
        return Page[model].model_validate_json(raw)
    links=await query(VAT_LINK_SET,SupplierVATLink,
        f"Entity_Key eq guid'{entity}' and Period le datetime'{as_of.isoformat()}'",'Period desc')
    if not links.value:
        raise UserProblem('Для поставщика нет подтверждённой VAT-регистрации на дату счёта.')
    if len(links.value)<2 and links.next_link:raise InvoiceConflict()
    if any(row.Entity_Key!=entity or row.Period>as_of for row in links.value):raise InvoiceConflict()
    link=links.value[0]
    if len(links.value)>1 and links.value[1].Period>=link.Period:raise InvoiceConflict()
    if link.Registration_Key==ZERO:raise InvoiceConflict()
    page=await query(VAT_REG_SET,SupplierVATRegistration,f"Ref_Key eq guid'{link.Registration_Key}'")
    if page.next_link or len(page.value)!=1:raise InvoiceConflict()
    registration=page.value[0]
    if (registration.Ref_Key!=link.Registration_Key or registration.DeletionMark
        or registration.Owner!=entity or not registration.TRNVAT.strip()
        or registration.TRNVAT!=registration.TRNVAT.strip()):
        raise InvoiceConflict()
    return link,registration


class BasisReference(ExternalModel):
    DocumentBasis: str = Field(max_length=100)
    DocumentBasis_Type: str = Field(max_length=200)


class TaxLink(Record, BasisReference):
    BasisDocuments: tuple[BasisReference, ...] = Field(max_length=200)


class TaxHeader(Record, BasisReference):
    DataVersion: str = Field(min_length=1, max_length=200)
    Number: str = Field(min_length=1, max_length=200)
    Posted: bool
    Company_Key: UUID
    Contract_Key: UUID
    Entity_Key: UUID
    Summary: bool
    BasisDocuments: tuple[BasisReference, ...] = Field(max_length=200)


class TaxRow(BasisReference):
    Ref_Key: UUID
    LineNumber: str = Field(pattern=r'^[1-9][0-9]{0,18}$')
    Item: UUID
    Item_Type: Literal['StandardODATA.Catalog_Items']
    Contract_Key: UUID
    Content: str = Field(max_length=500)
    Quantity: Quantity
    Price: Money
    PriceCur: Money
    Amount: Money
    AmountCur: Money
    AmountTotal: Money
    AmountTotalCur: Money
    VATAmount: Money
    VATAmountCur: Money
    VATRate_Key: UUID
    AmountVATIn: bool
    UnitOfMeasure: UUID
    UnitOfMeasure_Type: Literal['StandardODATA.Catalog_UOMClassifier', 'StandardODATA.Catalog_UOM']
    ExchangeRate: Decimal
    DiscountMarkupAmount: Money
    AutomaticDiscountAmount: Money


class TaxRecord(TaxHeader):
    Date: datetime
    IssuingDate: datetime
    DateOfOriginalSupply: datetime
    DocumentAmount: Money
    DocumentVATAmount: Money
    DocumentCurrency_Key: UUID
    AccountingCurrency_Key: UUID
    TransactionType: Literal['Sale']
    CompanyTRN: str = Field(max_length=500)
    EntityTRN: str = Field(max_length=500)
    Inventory: tuple[TaxRow, ...] = Field(min_length=1, max_length=200)


def tax_schema(raw: bytes) -> str:
    root = ET.fromstring(raw)
    local = lambda n: n.tag.rsplit('}', 1)[-1]
    types = {schema.attrib['Namespace'] + '.' + n.attrib['Name']: n
             for schema in root.iter() if local(schema) == 'Schema'
             for n in schema if local(n) in ('EntityType', 'ComplexType')}
    sets = [n for n in root.iter() if local(n) == 'EntitySet' and n.attrib.get('Name') == 'Document_TaxInvoice']
    critical = {}
    try:
        if len(sets) != 1 or sets[0].attrib['EntityType'] != 'StandardODATA.Document_TaxInvoice':
            raise ValueError()
        critical['entity_set'] = dict(sets[0].attrib)
        def consume(node, model, prefix):
            props = {n.attrib['Name']: n for n in node if local(n) == 'Property'}
            for name, field in model.model_fields.items():
                prop = props[name]
                if name in ('Inventory', 'BasisDocuments'):
                    kind = prop.attrib['Type']
                    if not kind.startswith('Collection(') or not kind.endswith(')'): raise ValueError()
                    consume(types[kind[11:-1]], TaxRow if name == 'Inventory' else BasisReference, prefix + '.' + name)
                else:
                    expected = (('Edm.String',) if name in ('DocumentBasis','Item','UnitOfMeasure')
                        else ('Edm.Guid',) if field.annotation is UUID
                        else ('Edm.Boolean',) if field.annotation is bool
                        else ('Edm.DateTime',) if field.annotation is datetime
                        else ('Edm.Int64','Edm.Int32') if name == 'LineNumber'
                        else ('Edm.Decimal','Edm.Double') if field.annotation is Decimal
                        else ('Edm.String',))
                    if prop.attrib['Type'] not in expected: raise ValueError()
                critical[prefix + '.' + name] = dict(prop.attrib)
        consume(types[sets[0].attrib['EntityType']], TaxRecord, 'TaxInvoice')
    except (KeyError, ValueError):
        raise BackendFailure('firstbit_tax_schema_mismatch') from None
    return hashlib.sha256(json.dumps(critical, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _matches(reference: BasisReference, source_id: UUID) -> bool:
    if reference.DocumentBasis in ('', str(ZERO)): return False
    try: key = UUID(reference.DocumentBasis)
    except ValueError: raise InvoiceConflict() from None
    if key != source_id: return False
    if reference.DocumentBasis_Type != 'StandardODATA.Document_InventoryExpense': raise InvoiceConflict()
    return True


async def _get(adapter, params):
    url = adapter.settings.base_url + 'Document_TaxInvoice?' + urlencode(params, quote_via=quote)
    return await bounded_request(adapter._client, 'GET', url, limit=2_000_000, deadline=15)


async def find_tax_record(adapter, basis, source) -> TaxRecord | None:
    preview = basis.preview
    history = preview.historical_proposal
    if history is None or not source.posted: raise InvoiceConflict()
    source_id = UUID(source.document_id)
    # Universal-reference WHERE comparisons are unsupported in the real
    # publication. Scan only minimal relation keys, independently of parties:
    # a linked document with a wrong issuer must block, not look absent.
    found, seen = [], set()
    for skip in range(0, 2000, 200):
        raw = await _get(adapter, {'$format':'json','$select':','.join(TaxLink.model_fields),
            '$orderby':'Ref_Key asc','$skip':str(skip),'$top':'200'})
        page = Page[TaxLink].model_validate_json(raw)
        for row in page.value:
            if row.Ref_Key in seen:
                raise InvoiceConflict()
            seen.add(row.Ref_Key)
            if _matches(row,source_id) or any(_matches(r,source_id) for r in row.BasisDocuments):
                found.append(row)
        if len(page.value)<200:
            if page.next_link: raise InvoiceConflict()
            break
    else: raise InvoiceConflict()
    if len(found)>1: raise InvoiceConflict()
    if not found: return None
    if found[0].DeletionMark: raise InvoiceConflict()
    raw=await _get(adapter,{'$format':'json','$filter':f"Ref_Key eq guid'{found[0].Ref_Key}'",
        '$select':','.join(TaxRecord.model_fields),'$top':'2'})
    page=Page[TaxRecord].model_validate_json(raw)
    if page.next_link or len(page.value)!=1 or page.value[0].Ref_Key!=found[0].Ref_Key: raise InvoiceConflict()
    record=page.value[0]
    if record.Entity_Key!=UUID(history.entity_id) or record.IssuingDate.date()!=preview.invoice_date:
        raise InvoiceConflict()
    _,registration=await supplier_registration(adapter,record.Entity_Key,record.IssuingDate)
    validate_tax_record(record,basis,source,supplier_tax_number=registration.TRNVAT)
    return record


def validate_tax_record(record: TaxRecord, basis, source, *, supplier_tax_number: str) -> None:
    preview=basis.preview
    history=preview.historical_proposal
    refs={r.role:r.reference_id for r in preview.execution_review.references}
    currency=UUID(refs['DocumentCurrency_Key'])
    if (preview.invoice_date is None
        or any(value.date()!=preview.invoice_date for value in (record.Date,record.IssuingDate,record.DateOfOriginalSupply))
        or record.DeletionMark or record.Summary or not _matches(record,UUID(source.document_id))
        or (record.Company_Key,record.Contract_Key,record.Entity_Key)!=(UUID(basis.client_id),UUID(history.contract_id),UUID(history.entity_id))
        or record.DocumentCurrency_Key!=currency or record.AccountingCurrency_Key!=currency
        or record.DocumentAmount!=preview.total or record.DocumentVATAmount!=preview.tax_amount
        or len(record.Inventory)!=len(preview.lines)
        or record.CompanyTRN!=(preview.recipient.tax_number or '')
        or record.EntityTRN!=supplier_tax_number
        or (preview.issuer.tax_number is not None and record.EntityTRN!=preview.issuer.tax_number)):
        raise InvoiceConflict()
    rows=sorted(record.Inventory,key=lambda r:int(r.LineNumber))
    for index,(actual,expected) in enumerate(zip(rows,preview.lines),1):
        if (actual.Ref_Key!=record.Ref_Key or int(actual.LineNumber)!=index or not _matches(actual,UUID(source.document_id))
            or actual.Item!=UUID(expected.service_id) or actual.Contract_Key!=record.Contract_Key
            or actual.Content!=expected.description or actual.Quantity!=expected.quantity
            or actual.Price!=expected.price or actual.PriceCur!=expected.price
            or actual.Amount!=expected.subtotal or actual.AmountCur!=expected.subtotal
            or actual.AmountTotal!=expected.total or actual.AmountTotalCur!=expected.total
            or actual.VATAmount!=expected.tax_amount or actual.VATAmountCur!=expected.tax_amount
            or actual.VATRate_Key!=UUID(expected.tax.tax_id) or actual.AmountVATIn
            or actual.ExchangeRate!=1 or actual.DiscountMarkupAmount or actual.AutomaticDiscountAmount
            or actual.UnitOfMeasure!=UUID(refs[f'line:{index}:UnitOfMeasure'])
            or actual.UnitOfMeasure_Type!=preview.execution_review.line_uom_types[index-1]):
            raise InvoiceConflict()


async def read_tax_operation(adapter, basis, source, operation_id) -> TaxOperationState:
    raw=await adapter._get('$metadata',metadata=True)
    tax_schema(raw)
    registration_schema(raw)
    record=await find_tax_record(adapter,basis,source)
    if record is None:
        stored=adapter.journal.get(operation_id)
        status='unknown' if stored is not None and stored.tax is not None else 'not_started'
        return TaxOperationState(operation_id=operation_id,source_document_id=source.document_id,status=status)
    invoice=TaxInvoice(document_id=str(record.Ref_Key),source_document_id=source.document_id,number=record.Number,
        posted=record.Posted,client_id=basis.client_id,basis_key=basis.key,revision=record.DataVersion,
        preview_digest=preview_digest(basis))
    return TaxOperationState(operation_id=operation_id,source_document_id=source.document_id,
        status='posted' if record.Posted else 'draft',invoice=invoice)


def preview_digest(basis):
    return basis.preview.digest
