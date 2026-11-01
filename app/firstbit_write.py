"""Controlled draft creation over the existing FirstBit reader.

No posting: Standard OData Post has no proved atomic expected-revision guard.
Historical accounting is an explicit frozen proposal, never current defaults.
"""
import hashlib
import json
import re
from datetime import datetime, time, timedelta
from decimal import Decimal
from typing import Annotated, Literal
from urllib.parse import quote, urlencode
from uuid import UUID
import xml.etree.ElementTree as ET

from pydantic import ConfigDict, Field, field_validator, model_validator

from app.domain import (AccountingReference, BackendFailure, BillingBasis, ExecutionReview,
                        ExternalModel, Invoice, InvoiceConflict, InvoicePreview, Label,
                        Money, OperationState, UserProblem, WritesDisabled)
from app.firstbit import FirstBit, HistoricalInvoice, HistoricalLine, Page, Record, ZERO
from app.firstbit_write_schema import inspect_write_schema
from app.http import bounded_request, ExternalFailure
from app.operations import OperationJournal


class VersionedReference(Record):
    Description: str = Field(max_length=500)
    DataVersion: Label


class ExpenseReference(VersionedReference):
    IsFolder: bool


class BankReference(VersionedReference):
    Owner: UUID
    Owner_Type: Literal['StandardODATA.Catalog_Entities']
    CashCurrency_Key: UUID
    OpeningDate: datetime
    ClosingDate: datetime
    IBAN: str = Field(max_length=100)
    AccountNo: str = Field(max_length=100)


class WriteLine(HistoricalLine):
    model_config = ConfigDict(extra='allow')
    GLAccount_GL_Key: UUID
    SalesRevenueGLAccount_GL_Key: UUID
    OutputVATGLAccount_GL_Key: UUID
    BaseUnit_Key: UUID
    BusinessActivity_Key: UUID
    ExpenseItem_Key: UUID
    IncomeItem_Key: UUID
    TradeDiscountsGLAccount_GL_Key: UUID
    ConnectionKey: int = Field(ge=1, le=2**63-1)

    @field_validator('ConnectionKey', mode='before')
    @classmethod
    def connection_int64(cls, value):
        if isinstance(value, str) and value.isascii() and value.isdigit():
            return int(value)
        return value

    @model_validator(mode='after')
    def no_unsupported_accounting(self):
        value = self.model_extra or {}
        if value:
            def neutral(key, item):
                if item is None or item is False or isinstance(item, (int, float, Decimal)) and item == 0:
                    return True
                if not isinstance(item, str):
                    return False
                return (item == '' or (key.endswith('_Key') or key in ('DeleteUUID','GoodsOrder')) and item == str(ZERO)
                    or key in ('DeferredRevenueStartDate', 'DeferredRevenueEndDate', 'IncomingDocumentDate',
                               'DistributionFrom', 'DistributionTo') and item == '0001-01-01T00:00:00'
                    or key in ('ConnectionKey', 'DELETESerialNumbersConnectionKey', 'RowHash', 'RowID', 'RetentionPeriod')
                       and re.fullmatch(r'0+', item) is not None)
            for key, item in value.items():
                if key == 'Ref_Key' or neutral(key, item):
                    continue
                if key.endswith('_Type') and item == 'StandardODATA.Undefined' and neutral(key[:-5], value.get(key[:-5])):
                    continue
                if (key == 'GoodsOrder_Type' and value.get('GoodsOrder') in ('', str(ZERO))
                        and isinstance(item, str) and re.fullmatch(
                            r'(StandardODATA\.[A-Za-z0-9_]+|UnavailableEntities\.UnavailableEntity_[a-f0-9-]{36})', item)):
                    # An empty composite reference can retain its declared concrete
                    # type. This does not authorize any nonempty linked order.
                    continue
                # Do not drop nonzero income/expense/activity/unit/retention or
                # unfamiliar row linkage just because the core reader ignores it.
                raise UserProblem('Образец содержит непроверенные учётные аналитики. Для записи нужно штатное заполнение и проверка в 1С.')
        return self

    def known_fields(self):
        return self.model_dump(include=set(type(self).model_fields))


class PaymentStage(ExternalModel):
    LineNumber: int = Field(ge=1, le=2**63-1)
    Amount: Money
    BlockShipping: bool
    BlockSupplying: bool
    Days: int = Field(ge=0, le=3650)
    PayDate: datetime
    Percent: Decimal = Field(ge=0, le=100)
    StageType: Label

    @field_validator('LineNumber', 'Days', mode='before')
    @classmethod
    def int64(cls, value):
        if isinstance(value, str) and value.isascii() and value.isdigit():
            return int(value)
        return value


class WriteDocument(HistoricalInvoice):
    DataVersion: Label
    Comment: str = Field(max_length=2000)
    AccountingCurrency_Key: UUID
    NationalCurrency_Key: UUID
    BankAccount_Key: UUID
    PaymentTerms_Key: UUID
    PaymentTermsVersion_Key: UUID
    AccountsReceivableGLAccount_GL_Key: UUID
    AdvancesReceivedGLAccount_GL_Key: UUID
    DeliveryTerms_Key: UUID
    TermsAndConditions: str = Field(max_length=2000)
    TransactionType: Label
    TaxationVAT: Label
    ExchangeRate: Decimal
    ExchangeRateAccCur: Decimal
    FactorAccCur: int = Field(ge=1, le=2**63-1)
    PriceDate: datetime
    BaseUnit_Key: UUID
    Department_Key: UUID
    PriceKind_Key: UUID
    TaxInvoiceIsRequired: bool
    BaseUnitPosition: Label
    CustomerOrderPosition: Label
    IncomingDocumentInfoPosition: Label
    PositionCell: Label
    ProjectPosition: Label
    ProjectTaskPosition: Label
    Emirate: str = Field(max_length=100)
    OffsetAdvancesDebtsAutomatically: Literal['No']
    Repetition: int = Field(ge=1, le=1)
    GoodsOrder: str = Field(pattern=r'^(|00000000-0000-0000-0000-000000000000)$')
    DocumentBasis: str = Field(pattern=r'^(|00000000-0000-0000-0000-000000000000)$')
    Inventory: tuple[WriteLine, ...] = Field(max_length=200)
    PaymentTermsStages: tuple[PaymentStage, ...] = Field(max_length=20)
    InventorySets: tuple[()]
    DiscountsMarkupsInventory: tuple[()]

    @field_validator('FactorAccCur', 'Repetition', mode='before')
    @classmethod
    def int64(cls, value):
        return PaymentStage.int64(value)

    @model_validator(mode='after')
    def row_parent_identity(self):
        for row in self.Inventory:
            parent = (row.model_extra or {}).get('Ref_Key')
            if parent is not None and UUID(str(parent)) != self.Ref_Key:
                raise ValueError('Row belongs to a different document')
        return self


class LookupDocument(Record):
    Company_Key: UUID
    Contract_Key: UUID
    Entity_Key: UUID
    Date: datetime
    Comment: str = Field(max_length=2000)


REFERENCE_MODELS = {
    'Catalog_BankAccounts': BankReference,
    'Catalog_SalesPaymentTerms': VersionedReference,
    'Catalog_SalesPaymentTermsVersions': VersionedReference,
    'ChartOfAccounts_GeneralChartOfAccounts': VersionedReference,
    'Catalog_BaseUnits': VersionedReference,
    'Catalog_PriceKinds': VersionedReference,
    'Catalog_IncomeItems': VersionedReference,
    'Catalog_BusinessActivities': VersionedReference,
    'Catalog_ExpenseItems': ExpenseReference,
}
HEADER_REFS = {
    'BankAccount_Key': 'Catalog_BankAccounts',
    'PaymentTerms_Key': 'Catalog_SalesPaymentTerms',
    'PaymentTermsVersion_Key': 'Catalog_SalesPaymentTermsVersions',
    'AccountsReceivableGLAccount_GL_Key': 'ChartOfAccounts_GeneralChartOfAccounts',
    'AdvancesReceivedGLAccount_GL_Key': 'ChartOfAccounts_GeneralChartOfAccounts',
}
LINE_GL = ('GLAccount_GL_Key', 'SalesRevenueGLAccount_GL_Key', 'OutputVATGLAccount_GL_Key', 'TradeDiscountsGLAccount_GL_Key')
OPTIONAL_HEADER_REFS = {'BaseUnit_Key': 'Catalog_BaseUnits', 'Department_Key': 'Catalog_BaseUnits', 'PriceKind_Key': 'Catalog_PriceKinds'}
LINE_REFS = {'BaseUnit_Key': 'Catalog_BaseUnits', 'BusinessActivity_Key': 'Catalog_BusinessActivities', 'ExpenseItem_Key': 'Catalog_ExpenseItems', 'IncomeItem_Key': 'Catalog_IncomeItems'}
HEADER_VALUES = ('TaxInvoiceIsRequired', 'BaseUnitPosition', 'CustomerOrderPosition', 'IncomingDocumentInfoPosition', 'PositionCell', 'ProjectPosition', 'ProjectTaskPosition', 'Emirate', 'OffsetAdvancesDebtsAutomatically', 'Repetition')


def _canonical(value) -> bytes:
    """JSON numbers roundtrip through Double without silent decimal truncation."""
    def wire(item):
        if isinstance(item, Decimal):
            number = float(item)
            if not item.is_finite() or Decimal(str(number)) != item:
                raise ValueError('Financial serialization loss')
            return number
        if isinstance(item, (UUID, datetime)):
            return str(item) if isinstance(item, UUID) else item.isoformat()
        if isinstance(item, dict):
            return {key: wire(value) for key, value in item.items()}
        if isinstance(item, (list, tuple)):
            return [wire(value) for value in item]
        return item
    return json.dumps(wire(value), sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def execution_schema(raw: bytes):
    """Pin every additional consumed write/reference property, not just core schema."""
    core = inspect_write_schema(raw)
    root = ET.fromstring(raw)
    local = lambda n: n.tag.rsplit('}', 1)[-1]
    types = {schema.attrib['Namespace'] + '.' + child.attrib['Name']: child
             for schema in root.iter() if local(schema) == 'Schema'
             for child in schema if local(child) in ('EntityType', 'ComplexType')}
    sets = {n.attrib['Name']: n.attrib['EntityType']
            for n in root.iter() if local(n) == 'EntitySet'}
    set_nodes = [n for n in root.iter() if local(n) == 'EntitySet']
    if len(sets) != len(set_nodes):
        raise BackendFailure('firstbit_write_schema_mismatch')
    groups = {'Document_InventoryExpense': (WriteDocument, ('Inventory', 'PaymentTermsStages', 'InventorySets', 'DiscountsMarkupsInventory')),
              **{name: (model, ()) for name, model in REFERENCE_MODELS.items()}}
    consumed = {}
    try:
        for name, (model, collections) in groups.items():
            consumed[name + '.entity_set'] = next(dict(n.attrib) for n in set_nodes if n.attrib['Name'] == name)
            props = {n.attrib['Name']: dict(n.attrib) for n in types[sets[name]] if local(n) == 'Property'}
            for key, field in model.model_fields.items():
                actual = props[key]
                expected = (('Edm.String',) if key == 'Owner' else
                            ('Edm.Int64', 'Edm.Int32') if field.annotation is int else
                            ('Edm.Decimal', 'Edm.Double') if field.annotation is Decimal else
                            ('Edm.Guid',) if field.annotation is UUID else
                            ('Edm.Boolean',) if field.annotation is bool else
                            ('Edm.DateTime',) if field.annotation is datetime else ('Edm.String',))
                if key not in collections and actual['Type'] not in expected:
                    raise ValueError()
                consumed[name + '.' + key] = actual
                if key in ('Inventory', 'PaymentTermsStages'):
                    row_type = actual['Type']
                    if not row_type.startswith('Collection(') or not row_type.endswith(')'):
                        raise ValueError()
                    row = types[row_type[11:-1]]
                    row_props = {n.attrib['Name']: dict(n.attrib) for n in row if local(n) == 'Property'}
                    row_model = WriteLine if key == 'Inventory' else PaymentStage
                    for row_key, row_field in row_model.model_fields.items():
                        prop = row_props[row_key]
                        row_expected = (('Edm.Int64', 'Edm.Int32') if row_field.annotation is int else
                                        ('Edm.Decimal', 'Edm.Double') if row_field.annotation is Decimal else
                                        ('Edm.Guid',) if row_key.endswith('_Key') else
                                        ('Edm.Boolean',) if row_field.annotation is bool else
                                        ('Edm.DateTime',) if row_field.annotation is datetime else ('Edm.String',))
                        if prop['Type'] not in row_expected:
                            raise ValueError()
                        consumed[name + '.' + key + '.' + row_key] = prop
        sha = hashlib.sha256(_canonical({'core': core.sha256, 'consumed': consumed})).hexdigest()
        return core.model_copy(update={'sha256': sha})
    except (KeyError, ValueError):
        raise BackendFailure('firstbit_write_schema_mismatch') from None


class FirstBitWrite(FirstBit):
    """Real controlled-create provider; posting/PDF admission stays closed."""
    write_capable = True
    posting_enabled = False
    native_pdf_available = False

    def __init__(self, settings, *, journal: OperationJournal, schema_sha256: str, transport=None):
        if not settings.write_account or settings.readonly_account or not isinstance(journal, OperationJournal):
            raise WritesDisabled()
        if type(schema_sha256) is not str or len(schema_sha256) != 64 or any(c not in '0123456789abcdef' for c in schema_sha256):
            raise WritesDisabled()
        super().__init__(settings, transport=transport)
        self.journal, self.schema_sha256 = journal, schema_sha256

    async def _schema(self):
        await self.check_metadata()
        return execution_schema(await self._get('$metadata', metadata=True)).require_approved(self.schema_sha256)

    async def _selected(self, entity, model, predicate):
        if entity not in ('Document_InventoryExpense', *REFERENCE_MODELS):
            raise BackendFailure('firstbit_path')
        params = {'$format': 'json', '$filter': predicate, '$select': ','.join(model.model_fields), '$top': '2'}
        url = self.settings.base_url + entity + '?' + urlencode(params, quote_via=quote)
        try:
            raw = await bounded_request(self._client, 'GET', url, limit=1_000_000, deadline=12)
            page = Page[model].model_validate_json(raw)
            if page.next_link or len(page.value) > 1:
                raise ValueError()
            return page.value[0] if page.value else None
        except ExternalFailure:
            raise BackendFailure('firstbit_get_failed') from None

    async def _source(self, reference):
        result = await self._selected('Document_InventoryExpense', WriteDocument,
                                      f"Ref_Key eq guid'{UUID(reference)}'")
        if result is None or result.Ref_Key != UUID(reference) or result.DeletionMark or not result.Posted:
            raise UserProblem('Исторический источник изменён или недоступен для записи.')
        return result

    async def _plan(self, preview, client_id):
        await self._schema()
        history = preview.historical_proposal
        if history is None:
            raise UserProblem('Запись заблокирована: поставщик договора и образца должен совпадать.')
        source_ids = tuple(dict.fromkeys(line.source_id or history.source_id for line in preview.lines))
        sources = {key: await self._source(key) for key in source_ids}
        primary = sources[source_ids[0]]
        references, evidence, cache = [], [], {}
        if history.contract_entity_id is not None:
            references.extend((AccountingReference(role='issuer:source',reference_id=history.entity_id,label=preview.issuer.name),
                AccountingReference(role='issuer:contract',reference_id=history.contract_entity_id,label=history.contract_entity_name or 'Contract entity')))

        async def reference(role, entity, key):
            key = UUID(str(key))
            if key == ZERO:
                references.append(AccountingReference(role=role, reference_id=str(key), label='Пустая ссылка в историческом образце'))
                return None
            identity = (entity, key)
            if identity not in cache:
                value = await self._selected(entity, REFERENCE_MODELS[entity], f"Ref_Key eq guid'{key}'")
                if value is None or value.DeletionMark or value.Ref_Key != key or getattr(value, 'IsFolder', False):
                    raise UserProblem('Учётная ссылка образца удалена или недоступна. Запись заблокирована.')
                cache[identity] = value
                evidence.append(value.model_dump_json())
            value = cache[identity]
            references.append(AccountingReference(role=role, reference_id=str(key), label=value.Description or str(key)))
            return value

        for source in sources.values():
            if (str(source.Company_Key) != client_id or str(source.Contract_Key) != history.contract_id
                    or str(source.Entity_Key) != history.entity_id or source.AmountVATIn
                    or source.TransactionType != 'SaleToCustomer' or source.TaxationVAT != 'TaxableByVAT'
                    or source.TermsAndConditions or source.DeliveryTerms_Key != ZERO
                    or len(source.PaymentTermsStages) != 1):
                raise UserProblem('Учётная структура образца пока не поддерживается для безопасной записи.')
            if (source.DocumentCurrency_Key != source.AccountingCurrency_Key
                    or source.DocumentCurrency_Key != source.NationalCurrency_Key
                    or (source.ExchangeRate, source.ExchangeRateAccCur, source.FactorAccCur) != (Decimal(1), Decimal(1), 1)):
                raise UserProblem('Валютная конвертация для записи не подтверждена. Запись заблокирована.')
            stage = source.PaymentTermsStages[0]
            if (stage.Percent != 100 or stage.Days != 0 or stage.StageType != 'PaymentOnDelivery'
                    or stage.BlockShipping or stage.BlockSupplying or stage.Amount != source.DocumentAmount):
                raise UserProblem('Для этих условий оплаты требуется штатное заполнение в 1С.')
            if any(getattr(source, key) != getattr(primary, key) for key in (*HEADER_REFS, *OPTIONAL_HEADER_REFS, *HEADER_VALUES,
                    'DocumentCurrency_Key', 'AccountingCurrency_Key', 'NationalCurrency_Key')):
                raise UserProblem('Учётные реквизиты источников различаются. Запись заблокирована.')
            evidence.append(source.model_dump_json())
        for key, entity in {**HEADER_REFS, **OPTIONAL_HEADER_REFS}.items():
            value = await reference(key, entity, getattr(primary, key))
            if value is None and key in HEADER_REFS:
                raise UserProblem('В образце отсутствует обязательный учётный реквизит для записи.')
            if isinstance(value, BankReference) and (
                    value.Owner != primary.Entity_Key or value.CashCurrency_Key != primary.DocumentCurrency_Key
                    or value.OpeningDate.date() > preview.invoice_date
                    or value.ClosingDate.year != 1 and value.ClosingDate.date() <= preview.invoice_date):
                raise UserProblem('Банковский счёт образца не подходит поставщику, валюте или дате.')
        for key in ('DocumentCurrency_Key', 'AccountingCurrency_Key', 'NationalCurrency_Key'):
            references.append(AccountingReference(role=key, reference_id=str(getattr(primary, key)), label=preview.currency))
        for key in HEADER_VALUES:
            references.append(AccountingReference(role='header:'+key, reference_id=json.dumps(getattr(primary,key)), label=key))
        uom_types = []
        for index, line in enumerate(preview.lines, 1):
            source = sources[line.source_id or history.source_id]
            matches = [row for row in source.Inventory if row.LineNumber == line.source_line_number]
            if len(matches) != 1 or str(matches[0].Item_Key) != line.service_id:
                raise UserProblem('Источник строки изменён. Запись заблокирована.')
            row = matches[0]
            if str(row.VATRate_Key) != line.tax.tax_id:
                raise UserProblem('Изменённый налог требует штатной проверки заполнения в 1С. Запись заблокирована.')
            for key in LINE_GL:
                await reference(f'line:{index}:{key}', 'ChartOfAccounts_GeneralChartOfAccounts', getattr(row, key))
            for key, entity in LINE_REFS.items():
                await reference(f'line:{index}:{key}', entity, getattr(row, key))
            references.append(AccountingReference(role=f'line:{index}:ConnectionKey',
                reference_id=str(row.ConnectionKey), label='Historical row connection'))

            references.append(AccountingReference(role=f'line:{index}:UnitOfMeasure', reference_id=str(row.UnitOfMeasure), label=line.uom))
            uom_types.append(row.UnitOfMeasure_Type)
        try:
            review = ExecutionReview(policy='confirmed_historical_carryover_v1', schema_sha256=self.schema_sha256,
                payload_sha256='0' * 64, evidence_sha256=hashlib.sha256(''.join(evidence).encode()).hexdigest(),
                references=tuple(references), payment_date=preview.invoice_date, price_date=primary.PriceDate,
                line_uom_types=tuple(uom_types))
            payload = self._payload(preview, review, client_id)
            return ExecutionReview(**{**review.model_dump(), 'payload_sha256': hashlib.sha256(_canonical(payload)).hexdigest()})
        except ValueError:
            raise UserProblem('Учётный план не прошёл проверку. Запись заблокирована.') from None

    @staticmethod
    def _payload(preview, review, client_id):
        raw_refs = {item.role: item.reference_id for item in review.references}
        refs = {role: UUID(value) for role,value in raw_refs.items() if not role.startswith('header:') and not role.endswith(':ConnectionKey')}
        if len(raw_refs) != len(review.references) or len(review.line_uom_types) != len(preview.lines):
            raise InvoiceConflict()
        history = preview.historical_proposal
        if history is None:
            raise InvoiceConflict()
        result = {key: refs[key] for key in (*HEADER_REFS, *OPTIONAL_HEADER_REFS, 'DocumentCurrency_Key', 'AccountingCurrency_Key', 'NationalCurrency_Key')}
        result.update(Company_Key=UUID(client_id), Contract_Key=UUID(history.contract_id), Entity_Key=UUID(history.entity_id),
                      Date=datetime.combine(preview.invoice_date, time()), PriceDate=review.price_date,
                      TransactionType='SaleToCustomer', TaxationVAT='TaxableByVAT', AmountVATIn=False,
                      DocumentAmount=preview.total, ExchangeRate=Decimal(1), ExchangeRateAccCur=Decimal(1), FactorAccCur='1',
                      DeliveryTerms_Key=ZERO, TermsAndConditions='', Posted=False, DeletionMark=False)
        result.update({key: json.loads(raw_refs['header:'+key]) for key in HEADER_VALUES})
        result['Repetition'] = str(result['Repetition'])
        lines = []
        for index, line in enumerate(preview.lines, 1):
            lines.append({**{key: refs[f'line:{index}:{key}'] for key in LINE_GL},
                **{key: refs[f'line:{index}:{key}'] for key in LINE_REFS},
                'ConnectionKey': raw_refs[f'line:{index}:ConnectionKey'], 'LineNumber': str(index), 'Item_Key': UUID(line.service_id), 'Content': line.description,
                'Quantity': line.quantity, 'Price': line.price, 'Amount': line.subtotal, 'AmountTotal': line.total,
                'VATAmount': line.tax_amount, 'VATRate_Key': UUID(line.tax.tax_id),
                'UnitOfMeasure': refs[f'line:{index}:UnitOfMeasure'], 'UnitOfMeasure_Type': review.line_uom_types[index - 1],
                'DiscountMarkupRate': Decimal(0), 'DiscountMarkupAmount': Decimal(0),
                'AutomaticDiscountRate': Decimal(0), 'AutomaticDiscountAmount': Decimal(0)})
        if len({row['ConnectionKey'] for row in lines}) != len(lines):
            raise InvoiceConflict()
        result['Inventory'] = lines
        result['PaymentTermsStages'] = [{'LineNumber': '1', 'Amount': preview.total, 'Percent': Decimal(100),
            'Days': '0', 'PayDate': datetime.combine(review.payment_date, time()), 'StageType': 'PaymentOnDelivery',
            'BlockShipping': False, 'BlockSupplying': False}]
        result['InventorySets'], result['DiscountsMarkupsInventory'] = [], []
        return result

    async def _prepare_preview(self,preview):
        return preview

    async def _compose_basis(self, *args, **kwargs):
        basis = await super()._compose_basis(*args, **kwargs)
        try:
            candidate = await self._prepare_preview(basis.preview)
            review = await self._plan(candidate, basis.client_id)
            preview = InvoicePreview(**{**candidate.model_dump(), 'execution_review': review})
        except UserProblem as exc:
            preview = InvoicePreview(**{**basis.preview.model_dump(), 'write_blocker': str(exc)})
        except ValueError:
            preview = InvoicePreview(**{**basis.preview.model_dump(), 'write_blocker': 'Учётные данные образца не прошли проверку для записи.'})
        return BillingBasis(**{**basis.model_dump(), 'preview': preview,
            'revision': hashlib.sha256((basis.revision + preview.model_dump_json()).encode()).hexdigest()})

    @staticmethod
    def _marker(basis, operation_id):
        if operation_id != hashlib.sha256(('invoice:v1:' + basis.key).encode()).hexdigest():
            raise InvoiceConflict()
        return 'ai-buhgalter:v1:' + operation_id + ':' + basis.preview.digest

    def _frozen_payload(self, basis):
        review = basis.preview.execution_review
        if review is None or review.schema_sha256 != self.schema_sha256 or basis.preview.write_blocker:
            raise WritesDisabled()
        payload = self._payload(basis.preview, review, basis.client_id)
        if hashlib.sha256(_canonical(payload)).hexdigest() != review.payload_sha256:
            raise InvoiceConflict()
        return payload

    def _frozen_readback_payload(self,basis):
        return self._frozen_payload(basis)

    async def _remote(self, basis, operation_id):
        marker = self._marker(basis, operation_id)
        # Scope by typed identities/date, page minimal headers, match marker locally.
        # No string-search syntax or arbitrary query is needed for reconciliation.
        history = basis.preview.historical_proposal
        company, contract, entity = UUID(basis.client_id), UUID(history.contract_id), UUID(history.entity_id)
        start = datetime.combine(basis.preview.invoice_date, time())
        end = start + timedelta(days=1)
        predicate = (f"Company_Key eq guid'{company}' and Contract_Key eq guid'{contract}' "
            f"and Entity_Key eq guid'{entity}' and Date ge datetime'{start.isoformat()}' "
            f"and Date lt datetime'{end.isoformat()}'")
        matches, seen = [], set()
        for skip in range(0, 1000, 200):
            params = {'$format': 'json', '$filter': predicate, '$select': ','.join(LookupDocument.model_fields),
                      '$orderby': 'Ref_Key asc', '$top': '200', '$skip': str(skip)}
            url = self.settings.base_url + 'Document_InventoryExpense?' + urlencode(params, quote_via=quote)
            try:
                raw = await bounded_request(self._client, 'GET', url, limit=1_000_000, deadline=12)
                page = Page[LookupDocument].model_validate_json(raw)
            except ExternalFailure:
                raise BackendFailure('firstbit_get_failed') from None
            for row in page.value:
                if (row.Ref_Key in seen or row.Company_Key != company or row.Contract_Key != contract
                        or row.Entity_Key != entity or not start <= row.Date < end):
                    raise InvoiceConflict()
                seen.add(row.Ref_Key)
                if row.Comment == marker:
                    matches.append(row.Ref_Key)
            if len(page.value) < 200:
                if page.next_link:
                    raise InvoiceConflict()
                break
        else:
            raise InvoiceConflict()
        if len(matches) > 1:
            raise InvoiceConflict()
        if not matches:
            return None
        value = await self._selected('Document_InventoryExpense', WriteDocument, f"Ref_Key eq guid'{matches[0]}'")
        if value is None or value.Ref_Key != matches[0]:
            raise InvoiceConflict()
        expected = self._frozen_readback_payload(basis)
        actual = value.model_dump()
        for key in ('FactorAccCur', 'Repetition'):
            actual[key] = str(actual[key])
        actual['Inventory'] = [{**row.known_fields(), 'LineNumber': str(row.LineNumber), 'ConnectionKey': str(row.ConnectionKey)} for row in value.Inventory]
        actual['PaymentTermsStages'] = [{**row.model_dump(), 'LineNumber': str(row.LineNumber), 'Days': str(row.Days)} for row in value.PaymentTermsStages]
        actual['Posted'] = False  # independently checked below; never set via payload for posting
        compared=expected
        if getattr(self,'requires_tax_invoice',False) is True:
            # Production create read-back proved 1C changes this lifecycle flag.
            # The full native path always reconciles/creates and validates the
            # linked TaxInvoice itself; this flag is never tax/existence authority.
            # Keep every financial/accounting value and the frozen create body exact.
            compared={key:entry for key,entry in expected.items() if key!='TaxInvoiceIsRequired'}
        if value.DeletionMark or value.Comment != marker or _canonical({key: actual[key] for key in compared}) != _canonical(compared):
            raise InvoiceConflict()
        return Invoice(document_id=str(value.Ref_Key), number=value.Number, posted=value.Posted, client_id=basis.client_id,
            basis_key=basis.key, revision=value.DataVersion, preview_digest=basis.preview.digest)

    async def read_operation(self, basis, operation_id):
        self._frozen_readback_payload(basis)
        invoice = await self._remote(basis, operation_id)
        if invoice is not None:
            return OperationState(operation_id=operation_id, status='posted' if invoice.posted else 'draft', invoice=invoice)
        stored = self.journal.get(operation_id)
        status = 'not_started' if stored is None or stored.phase == 'reserved' else 'unknown'
        return OperationState(operation_id=operation_id, status=status)

    async def ensure_draft(self, basis, operation_id):
        expected = self._frozen_payload(basis)
        stored = self.journal.get(operation_id)
        if stored is None or stored.prepared.basis != basis:
            raise WritesDisabled()
        existing = await self._remote(basis, operation_id)
        if existing is not None:
            return existing
        # Reread source/references/schema; changed evidence revokes admission.
        if await self._plan(basis.preview, basis.client_id) != basis.preview.execution_review:
            raise InvoiceConflict()
        self.journal.claim_provider_request(operation_id, 'create')
        payload = {**expected, 'Comment': self._marker(basis, operation_id)}
        try:
            await bounded_request(self._client, 'POST', self.settings.base_url + 'Document_InventoryExpense',
                content=_canonical(payload), headers={'Content-Type': 'application/json', 'Accept': 'application/json'},
                limit=1_000_000, deadline=20)
        except ExternalFailure:
            raise BackendFailure('firstbit_create_uncertain') from None
        invoice = await self._remote(basis, operation_id)
        if invoice is None or invoice.posted:
            raise BackendFailure('firstbit_create_readback_mismatch')
        return invoice

    async def read_tax_operation(self, basis, source, operation_id):
        from app.firstbit_tax import read_tax_operation
        return await read_tax_operation(self, basis, source, operation_id)

    async def ensure_posted(self, *args, **kwargs):
        # Never replace a posting action with Posted=true or assume If-Match works.
        raise WritesDisabled()
