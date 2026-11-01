"""FirstBit historical proposals. This provider has no mutation transport path."""
import asyncio
import hashlib
import json
import os
import re
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Annotated, Generic, Literal, TypeVar
from urllib.parse import quote, unquote, urlencode, urlsplit
from uuid import UUID
from xml.etree import ElementTree as ET

import httpx
from pydantic import Field, SecretStr, field_validator, model_validator

from app.domain import (BackendFailure, BillingBasis, ClientCandidate, ClientCandidates, ClientChoiceRequired, ExternalModel,
                        HistoricalProposal, InvoiceLine, InvoicePreview, Label, Money,
                        OperationState, PartyDetails, Quantity,
                        ResolvedClient, ResolvedInvoiceCommand, ResolvedService, ResolvedServiceSelection,
                        StrictModel, TaxProfile, UserProblem, WritesDisabled)
from app.http import ExternalFailure, bounded_request, disable_wire_logs
from app.validation import validate_json
from app.domain import PreviewTaxRequest, tax_matches
from app.domain import HistoricalSource, ServiceCandidates, ServiceChoiceRequired
from app.company_names import exact_key, similarity

ZERO = UUID(int=0)
Ref = Annotated[UUID, Field()]
T = TypeVar("T")


def normalized(value: str) -> str:
    return " ".join(value.split()).casefold()


class FirstBitSettings(StrictModel):
    base_url: str = Field(repr=False)
    username: SecretStr
    password: SecretStr
    readonly_account: bool
    write_account: bool = False
    bookkeeping_item_id: UUID
    client_aliases: dict[str, UUID] = Field(default_factory=dict, repr=False)
    service_aliases: tuple[Label, ...] = ("Accounting and bookkeeping services",
        "бухгалтерское обслуживание", "бухгалтерское обслуживание с ндс",
        "бухгалтерские услуги", "ведение бухгалтерии", "бухучёт", "бухучет",
        "ведение бухгалтерского учета", "ведение бухгалтерского учёта")

    @field_validator("base_url")
    @classmethod
    def safe_url(cls, value):
        url = urlsplit(value)
        path = unquote(url.path)
        if (url.scheme != "https" or not url.hostname or url.username or url.password
                or url.query or url.fragment or not path.endswith("/odata/standard.odata/")
                or any(p in (".", "..") for p in path.split("/"))):
            raise ValueError("FirstBit requires a credential-free HTTPS Standard OData root ending in /")
        return value

    @model_validator(mode="after")
    def dedicated_account(self):
        name = self.username.get_secret_value().strip()
        if (not self.readonly_account and not self.write_account
                or self.readonly_account and self.write_account
                or not name or re.search(r"admin|админ|administrator|администратор", name, re.I)
                or not self.password.get_secret_value().strip() or self.bookkeeping_item_id == ZERO
                or any(ref == ZERO for ref in self.client_aliases.values())):
            raise ValueError("A dedicated read-only account and non-empty references are required")
        if len({normalized(k) for k in self.client_aliases}) != len(self.client_aliases):
            raise ValueError("Duplicate normalized aliases")
        return self

    @classmethod
    def from_env(cls, *, writable: bool = False):
        if type(writable) is not bool:
            raise ValueError('Account mode must be explicit boolean')
        # JSON is an intentional ENV serialization boundary; UUIDs remain typed.
        try:
            return cls.model_validate_json(json.dumps({
                "base_url": os.environ.get("FIRSTBIT_BASE_URL", ""),
                "username": os.environ.get("FIRSTBIT_USERNAME", ""),
                "password": os.environ.get("FIRSTBIT_PASSWORD", ""),
                "readonly_account": not writable and os.environ.get("FIRSTBIT_READONLY_ACCOUNT") == "true",
                "write_account": writable and os.environ.get("FIRSTBIT_INTEGRATION_ACCOUNT") == "true",
                "bookkeeping_item_id": os.environ.get("FIRSTBIT_BOOKKEEPING_ITEM_ID", ""),
                "client_aliases": json.loads(os.environ.get("FIRSTBIT_CLIENT_ALIASES", "{}")),
            }))
        except (ValueError, TypeError):
            raise ValueError("Invalid FirstBit ENV configuration; see docs/firstbit/READONLY_PIPELINE.md") from None


class Record(ExternalModel):
    Ref_Key: Ref
    DeletionMark: bool

    @field_validator("Ref_Key")
    @classmethod
    def nonempty_ref(cls, value):
        if value == ZERO:
            raise ValueError("Empty record identity")
        return value


class CompanyName(Record):
    IsFolder: bool
    Inactive: bool
    Description: Label
    DescriptionFull: str = Field(max_length=500)


class Company(CompanyName):
    ContractByDefault_Key: Ref
    TRN: str = Field(max_length=500)


class Contract(Record):
    Owner_Key: Ref
    Inactive: bool
    Description: Label
    Entity_Key: Ref
    AccountsCurrency_Key: Ref


class Item(Record):
    IsFolder: bool
    Inactive: bool
    Description: Label
    ItemType: Literal["Service"]
    Code: str = Field(default="", max_length=100)


class Entity(Record):
    Description: Label
    DescriptionFull: str = Field(max_length=500)


class Currency(Record):
    # ISO numeric Code/Description must agree with an explicit supported currency.
    Code: str = Field(max_length=10)
    Description: Label


class VAT(Record):
    Description: Label
    Rate: Decimal = Field(ge=0, le=100, decimal_places=3)
    Exempt: bool
    Export: bool
    OutOfScope: bool
    Calculated: bool


class NamedRecord(Record):
    Description: Label


class HistoricalLine(ExternalModel):
    LineNumber: int = Field(ge=1, le=2**63 - 1)
    Item_Key: Ref
    Content: str = Field(max_length=500)
    Quantity: Quantity
    UnitOfMeasure: Ref
    UnitOfMeasure_Type: Literal["StandardODATA.Catalog_UOMClassifier", "StandardODATA.Catalog_UOM"]
    Price: Money
    Amount: Money
    AmountTotal: Money
    VATRate_Key: Ref
    VATAmount: Money
    DiscountMarkupRate: Decimal
    DiscountMarkupAmount: Decimal
    AutomaticDiscountRate: Decimal
    AutomaticDiscountAmount: Decimal

    @field_validator("LineNumber", mode="before")
    @classmethod
    def odata_int64(cls, value):
        # OData v3 serializes Edm.Int64 as decimal digit strings (verified live).
        if isinstance(value, str) and re.fullmatch(r"[1-9][0-9]{0,18}", value):
            return int(value)
        return value


class HistoricalInvoice(Record):
    Number: Label
    Date: datetime
    Posted: bool
    Company_Key: Ref
    Contract_Key: Ref
    Entity_Key: Ref
    DocumentCurrency_Key: Ref
    AmountVATIn: bool
    DocumentAmount: Money
    Inventory: tuple[HistoricalLine, ...] = Field(max_length=200)


class Page(ExternalModel, Generic[T]):
    value: tuple[T, ...] = Field(max_length=200)
    next_link: str | None = Field(default=None, alias="odata.nextLink")


# Minimal reviewed contract, not a metadata dump. Each GET selects only these fields.
MODELS = {"Catalog_Companies": Company, "Catalog_CompanyContracts": Contract,
          "Catalog_Items": Item, "Catalog_Entities": Entity, "Catalog_Currencies": Currency,
          "Catalog_VATRates": VAT, "Catalog_UOMClassifier": NamedRecord, "Catalog_UOM": NamedRecord,
          "Document_InventoryExpense": HistoricalInvoice}


def fields(model):
    return tuple(model.model_fields)


class FirstBit:
    is_fake = False
    preview_only = True

    def __init__(self, settings: FirstBitSettings, *, transport: httpx.AsyncBaseTransport | None = None):
        self.settings = FirstBitSettings.model_validate(settings)
        disable_wire_logs()
        self._client = httpx.AsyncClient(
            auth=httpx.BasicAuth(settings.username.get_secret_value(), settings.password.get_secret_value()),
            transport=transport, timeout=httpx.Timeout(10, connect=3), verify=True,
            follow_redirects=False, trust_env=False,
        )

    async def aclose(self):
        await self._client.aclose()

    async def _get(self, path: str, *, params=None, metadata=False) -> bytes:
        # Internal allowlist. No method parameter, arbitrary URL, or nextLink execution.
        if path != "$metadata" and path not in MODELS:
            raise BackendFailure("firstbit_path")
        try:
            url = httpx.URL(self.settings.base_url + path)
            if params:
                # Live FirstBit treats form-encoded '+' as a literal in $filter.
                # RFC3986 %20 preserves fixed filter semantics; values remain escaped data.
                url = url.copy_with(query=urlencode(params, quote_via=quote).encode("ascii"))
            for attempt in range(2):
                try:
                    return await bounded_request(self._client, "GET", str(url),
                        headers={"Accept": "application/xml" if metadata else "application/json"},
                        limit=8_000_000 if metadata else 1_000_000, deadline=12)
                except ExternalFailure as exc:
                    # Re-read only: fixed identical GET, never HTTP status/auth/schema errors.
                    if attempt or exc.code not in ("timeout", "http_error"):
                        raise
                    await asyncio.sleep(.2)
        except ExternalFailure as exc:
            # bounded_request emits application-controlled codes, never provider text.
            code = exc.code if exc.code in {"timeout", "http_error", "response_too_large",
                *(f"http_{status}" for status in range(100, 600))} else "invalid_response"
            raise BackendFailure("firstbit_get_failed_" + code) from None
        except Exception:
            raise BackendFailure("firstbit_get_failed") from None

    async def check_metadata(self):
        """Fresh, consumed-field/type verification. Never persist/auto-accept a baseline."""
        raw = await self._get("$metadata", metadata=True)
        try:
            if b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
                raise ValueError()
            root = ET.fromstring(raw)
            types = {}
            sets = {}
            for schema in root.iter():
                if schema.tag.rsplit("}", 1)[-1] == "Schema":
                    namespace = schema.attrib["Namespace"]
                    for child in schema:
                        if child.tag.rsplit("}", 1)[-1] in ("EntityType", "ComplexType"):
                            types[namespace + "." + child.attrib["Name"]] = {
                                p.attrib["Name"]: p.attrib["Type"] for p in child
                                if p.tag.rsplit("}", 1)[-1] == "Property"}
            for node in root.iter():
                if node.tag.rsplit("}", 1)[-1] == "EntitySet":
                    sets[node.attrib["Name"]] = node.attrib["EntityType"]
            for entity_set, model in MODELS.items():
                props = types[sets[entity_set]]
                self._check_fields(model, props)
                if model is HistoricalInvoice:
                    collection = props["Inventory"]
                    if not collection.startswith("Collection("):
                        raise ValueError()
                    self._check_fields(HistoricalLine, types[collection[11:-1]])
        except Exception:
            raise BackendFailure("firstbit_schema_mismatch") from None

    @staticmethod
    def _check_fields(model, props):
        for name in fields(model):
            actual = props[name]
            if name == "Inventory":
                continue
            annotation = model.model_fields[name].annotation
            expected = ("Edm.Guid" if name.endswith("_Key") else
                "Edm.String" if name in ("UnitOfMeasure", "UnitOfMeasure_Type") else
                "Edm.Boolean" if annotation is bool else
                "Edm.Decimal" if annotation is Decimal else
                "Edm.DateTime" if annotation is datetime else
                "Edm.Int64" if annotation is int else "Edm.String")
            # Verified live FirstBit metadata uses Double for numeric fields.
            # JSON values still enter bounded Decimal models and exact arithmetic checks.
            if annotation is Decimal and actual in ("Edm.Decimal", "Edm.Double"):
                continue
            if actual != expected and not (annotation is int and actual == "Edm.Int32"):
                raise ValueError()

    async def _rows(self, entity_set, *, filter, top=2, order=None, skip=None, model=None):
        model = model or MODELS[entity_set]
        params = {"$format": "json", "$select": ",".join(fields(model)),
                  "$filter": filter, "$top": str(top)}
        if order:
            params["$orderby"] = order
        if skip is not None:
            params["$skip"] = str(skip)
        raw = await self._get(entity_set, params=params)
        try:
            page = validate_json(Page[model], raw)
            # Unknown envelope pagination conventions must not hide ambiguity.
            decoded = json.loads(raw)
            if page.next_link or any("next" in key.lower() for key in decoded):
                raise ValueError()
            if len(page.value) > top:
                raise ValueError()
            return page.value
        except Exception:
            raise BackendFailure("firstbit_response_invalid") from None

    async def _record(self, entity_set, ref):
        ref = UUID(str(ref))
        if ref == ZERO:
            raise UserProblem("В 1С отсутствует обязательная связанная запись. Подготовка счёта остановлена.")
        rows = await self._rows(entity_set, filter=f"Ref_Key eq guid'{ref}'")
        if len(rows) != 1 or rows[0].Ref_Key != ref or rows[0].DeletionMark:
            raise UserProblem("Не удалось однозначно проверить связанную запись 1С.")
        return rows[0]

    async def resolve_client(self, query: str, *, selected_id: str | None = None) -> ResolvedClient:
        await self.check_metadata()
        source_query = query
        query = normalized(query)
        if not 2 <= len(query) <= 200 or not exact_key(query):
            raise UserProblem("Укажите название компании или его узнаваемую часть.")
        aliases = {normalized(k): v for k, v in self.settings.client_aliases.items()}
        if query in aliases:
            rows = (await self._record("Catalog_Companies", aliases[query]),)
        else:
            rows = await self._company_names()
        key = exact_key(source_query)
        candidates = [r for r in rows if not (r.DeletionMark or r.IsFolder or r.Inactive)
                      and (query in aliases or any(key in exact_key(name) or similarity(source_query, name) > 0
                           for name in (r.Description, r.DescriptionFull)))]
        matches = [r for r in candidates if query in aliases or key in (exact_key(r.Description), exact_key(r.DescriptionFull))]
        if not matches:
            # Rank only locally. Fuzzy/transliterated/partial suggestions always need a button.
            candidates.sort(key=lambda r: (-max(similarity(source_query, r.Description),
                similarity(source_query, r.DescriptionFull)), normalized(r.Description), str(r.Ref_Key)))
            candidates = candidates[:5]
        if selected_id is not None:
            selected = UUID(selected_id)
            matches = [r for r in candidates if r.Ref_Key == selected]
            if len(matches) != 1:
                raise UserProblem("Выбранная компания больше не соответствует запросу или недоступна. Повторите поиск.")
        elif len(matches) != 1 and candidates:
            choices = matches if matches else candidates
            if len(choices) > 19:
                raise UserProblem("Слишком много совпадений компаний. Уточните узнаваемую часть названия.")
            # Fresh records supply choice details; the name-only index never implies a contract/default.
            choices = [await self._checked_company(r, source_query, alias=query in aliases) for r in choices]
            raise ClientChoiceRequired(ClientCandidates(candidates=tuple(ClientCandidate(
                client_id=str(r.Ref_Key), display_name=r.Description,
                full_name=r.DescriptionFull or r.Description, tax_number=r.TRN or None) for r in choices)))
        if not matches:
            raise UserProblem("Не нашёл похожих компаний. Напишите короткую часть названия или произнесите её ещё раз.")
        record = await self._checked_company(matches[0], source_query, alias=query in aliases,
            exact=selected_id is None)
        return ResolvedClient(client_id=str(record.Ref_Key), display_name=record.Description)

    async def _company_names(self):
        # Fresh, bounded, name-only discovery: no business dump, cache, files, nextLink or AI.
        # Live GET verified $skip / Ref_Key asc, avoiding unsupported tolower().
        result, seen = [], set()
        for skip in range(0, 5000, 200):
            page = await self._rows("Catalog_Companies", model=CompanyName, top=200, skip=skip,
                order="Ref_Key asc", filter="DeletionMark eq false and IsFolder eq false and Inactive eq false")
            for row in page:
                if row.Ref_Key in seen:
                    raise BackendFailure("firstbit_name_page_changed")
                seen.add(row.Ref_Key)
                result.append(row)
            if len(page) < 200:
                return result
        raise UserProblem("Справочник компаний превышает безопасный предел поиска. Нужна проверенная адресная настройка поиска.")

    async def _checked_company(self, candidate, query, *, alias=False, exact=False):
        record = await self._record("Catalog_Companies", candidate.Ref_Key)
        names = (record.Description, record.DescriptionFull)
        fits = (any(exact_key(query) == exact_key(n) for n in names) if exact else
                any(exact_key(query) in exact_key(n) or similarity(query, n) > 0 for n in names))
        if record.IsFolder or record.Inactive or not (alias or fits):
            raise UserProblem("Выбранная компания больше не соответствует запросу или недоступна. Повторите поиск.")
        return record

    async def _item(self):
        item = await self._record("Catalog_Items", self.settings.bookkeeping_item_id)
        if item.IsFolder or item.Inactive:
            raise UserProblem("Услуга бухгалтерского обслуживания недоступна в 1С.")
        return item

    async def resolve_service(self, client_id: str, query: str, *, selected_id: str | None = None) -> ResolvedService:
        await self.check_metadata()
        UUID(client_id)
        if not 2 <= len(query.strip()) <= 200 or not exact_key(query) or any(ord(char) < 32 for char in query):
            raise UserProblem("Укажите название услуги или узнаваемую часть.")
        alias = normalized(query) in {normalized(x) for x in self.settings.service_aliases}
        if alias:
            candidates = [await self._item()]
        else:
            # Verified Description equality is a bounded fast path; only a quoted
            # literal varies, never entity/filter syntax. Approximate search still
            # scans the complete bounded directory before proposing identities.
            literal = query.strip().replace("'", "''")
            rows = await self._rows("Catalog_Items", top=6, filter="DeletionMark eq false and IsFolder eq false "
                "and Inactive eq false and ItemType eq 'Service' and Description eq '" + literal + "'")
            if any(exact_key(row.Description) != exact_key(query) or row.DeletionMark or row.IsFolder or row.Inactive for row in rows):
                raise BackendFailure("firstbit_service_filter_scope")
            if len(rows) >= 6:
                raise UserProblem("Слишком много одинаковых услуг. Уточните запись в справочнике.")
            if not rows:
                rows = await self._service_names()
            candidates = [r for r in rows if not (r.DeletionMark or r.IsFolder or r.Inactive)
                and (exact_key(query) in exact_key(r.Description) or similarity(query, r.Description) > 0)]
        matches = candidates if alias else [r for r in candidates if exact_key(query) == exact_key(r.Description)]
        if not matches:
            candidates.sort(key=lambda r: (-similarity(query, r.Description), normalized(r.Description), str(r.Ref_Key)))
            candidates = candidates[:5]
        if selected_id is not None:
            matches = [r for r in (matches or candidates) if r.Ref_Key == UUID(selected_id)]
        elif len(matches) != 1 and candidates:
            choices = matches or candidates
            if len(choices) > 5:
                raise UserProblem("Слишком много одинаковых услуг. Уточните название.")
            raise ServiceChoiceRequired(ServiceCandidates(candidates=tuple(ResolvedService(
                service_id=str(r.Ref_Key), display_name=r.Description, code=r.Code or None) for r in choices)))
        if len(matches) != 1:
            raise UserProblem("Услуга не найдена однозначно в 1С. Уточните название или другую его часть.")
        item = await self._record("Catalog_Items", matches[0].Ref_Key)
        if (item.IsFolder or item.Inactive or not alias and not
                (exact_key(query) in exact_key(item.Description) or similarity(query, item.Description) > 0)):
            raise UserProblem("Выбранная услуга изменилась или недоступна. Повторите поиск.")
        return ResolvedService(service_id=str(item.Ref_Key), display_name=item.Description, code=item.Code or None)

    async def _service_names(self):
        rows, seen = [], set()
        for skip in range(0, 5000, 200):
            page = await self._rows("Catalog_Items", model=Item, top=200, skip=skip, order="Ref_Key asc",
                filter="DeletionMark eq false and IsFolder eq false and Inactive eq false and ItemType eq 'Service'")
            for item in page:
                if item.Ref_Key in seen:
                    raise BackendFailure("firstbit_service_page_changed")
                seen.add(item.Ref_Key)
                rows.append(item)
            if len(page) < 200:
                return rows
        raise UserProblem("Справочник услуг превышает безопасный предел поиска; уточните настройки интеграции.")

    async def _contract(self, company):
        if company.ContractByDefault_Key != ZERO:
            default = await self._record("Catalog_CompanyContracts", company.ContractByDefault_Key)
            if default.Owner_Key != company.Ref_Key:
                raise UserProblem("Владелец договора по умолчанию не совпадает с клиентом.")
            if not default.Inactive:
                return default
        rows = await self._rows("Catalog_CompanyContracts", filter=
            f"Owner_Key eq guid'{company.Ref_Key}' and Inactive eq false and DeletionMark eq false")
        if len(rows) != 1 or rows[0].Inactive or rows[0].DeletionMark or rows[0].Owner_Key != company.Ref_Key:
            raise UserProblem("Не удалось однозначно определить активный договор клиента.")
        return rows[0]

    async def _history_rows(self, company, contract, command):
        cutoff = command.invoice_date
        lower = None
        if command.previous == "previous_month":
            cutoff = cutoff.replace(day=1)
            lower = (cutoff - timedelta(days=1)).replace(day=1)
        base_filter = (f"Company_Key eq guid'{company.Ref_Key}' and Contract_Key eq guid'{contract.Ref_Key}' "
                       f"and Posted eq true and DeletionMark eq false and Date lt datetime'{cutoff.isoformat()}T00:00:00'")
        if lower is not None:
            base_filter += f" and Date ge datetime'{lower.isoformat()}T00:00:00'"
        # Deliberately bounded historical search; no full history dump or arbitrary nextLink.
        rows = await self._rows("Document_InventoryExpense", filter=base_filter, top=30, order="Date desc,Ref_Key desc")
        if not rows:
            raise UserProblem("Для выбранной компании и договора нет проведённых счетов до указанной даты. "
                              "Историческая цена и состав услуг не подтверждены; preview заблокирован.")
        last = None
        for invoice in rows:
            if (not invoice.Posted or invoice.DeletionMark or invoice.Company_Key != company.Ref_Key
                    or invoice.Contract_Key != contract.Ref_Key or invoice.Date.date() >= cutoff
                    or lower is not None and invoice.Date.date() < lower
                    or last is not None and invoice.Date > last):
                raise BackendFailure("firstbit_history_scope")
            last = invoice.Date
        return rows

    async def _history(self, company, contract, command, item):
        rows = await self._history_rows(company, contract, command)
        return self._source_for(rows, item)

    def _source_for(self, rows, item):
        candidates = [r for r in rows if any(line.Item_Key == item.Ref_Key for line in r.Inventory)]
        if not candidates:
            raise UserProblem("В последних 30 проведённых счетах до выбранной даты нет истории услуги «" + item.Description
                + "». Нужен подтверждённый источник; цену, количество или налог из другой услуги не подставляем.")
        source = candidates[0]
        if len([r for r in candidates if r.Date == source.Date]) > 1:
            raise UserProblem("Нашёл несколько счетов с этой услугой на одно время. Нельзя однозначно выбрать образец.")
        return source

    async def _line(self, row, item, *, quantity=None,
                    vats: dict[UUID, VAT], uoms: dict[tuple[str, UUID], NamedRecord]):
        if (row.DiscountMarkupRate or row.DiscountMarkupAmount
                or row.AutomaticDiscountRate or row.AutomaticDiscountAmount):
            raise UserProblem("Историческая строка содержит скидку/наценку. Такая арифметика пока заблокирована.")
        if row.VATRate_Key not in vats:
            vats[row.VATRate_Key] = await self._record("Catalog_VATRates", row.VATRate_Key)
        vat = vats[row.VATRate_Key]
        if vat.Calculated or sum((vat.Exempt, vat.Export, vat.OutOfScope)) > 1:
            raise UserProblem("Не удалось подтвердить налоговую ставку. Подготовка счёта остановлена.")
        treatment = ("exempt" if vat.Exempt else "outside_scope" if vat.OutOfScope else
                     "standard" if vat.Rate > 0 else "zero_rated")
        if (vat.Exempt or vat.OutOfScope or vat.Export) and vat.Rate != 0:
            raise UserProblem("Налоговая ставка и режим НДС в 1С противоречат друг другу. Подготовка счёта остановлена.")
        uom_key = (row.UnitOfMeasure_Type, row.UnitOfMeasure)
        if uom_key not in uoms:
            uoms[uom_key] = await self._record(row.UnitOfMeasure_Type.removeprefix("StandardODATA."), row.UnitOfMeasure)
        uom = uoms[uom_key]
        tax = TaxProfile(tax_id=str(vat.Ref_Key), label=vat.Description, treatment=treatment, rate=vat.Rate)
        # Verify historical values BEFORE any human quantity edit. Never repair a bad source.
        line = InvoiceLine(service_id=str(item.Ref_Key), description=row.Content or item.Description,
            quantity=row.Quantity, uom=uom.Description, price=row.Price, tax=tax,
            subtotal=row.Amount, tax_amount=row.VATAmount, total=row.AmountTotal, source_line_number=row.LineNumber)
        if quantity is not None and quantity != line.quantity:
            subtotal = (quantity * line.price).quantize(Decimal(".01"), rounding=ROUND_HALF_UP)
            amount = (subtotal * tax.rate / 100).quantize(Decimal(".01"), rounding=ROUND_HALF_UP)
            line = InvoiceLine(**{**line.model_dump(), "quantity": quantity,
                "subtotal": subtotal, "tax_amount": amount, "total": subtotal + amount})
        return line

    def _tax_profile(self, vat):
        if (vat.DeletionMark or vat.Calculated or sum((vat.Exempt, vat.Export, vat.OutOfScope)) > 1
                or (vat.Exempt or vat.OutOfScope or vat.Export) and vat.Rate != 0):
            raise UserProblem("Налоговый профиль в 1С противоречив или недоступен.")
        treatment = "exempt" if vat.Exempt else "outside_scope" if vat.OutOfScope else "standard" if vat.Rate > 0 else "zero_rated"
        return TaxProfile(tax_id=str(vat.Ref_Key), label=vat.Description, treatment=treatment, rate=vat.Rate)

    async def _preview_tax(self, request: PreviewTaxRequest, current: TaxProfile):
        record = await self._record("Catalog_VATRates", current.tax_id)
        profile = self._tax_profile(record)
        if tax_matches(request, profile) and (request.mode != "rate" or not record.Export):
            return profile
        if request.mode == "with_tax":
            raise UserProblem("Укажите точную ставку НДС, например «НДС 5%».")
        filter = "DeletionMark eq false and Calculated eq false"
        if request.mode == "rate":
            filter += f" and Rate eq {request.rate} and Exempt eq false and OutOfScope eq false and Export eq false"
        elif request.mode == "without_tax":
            filter += " and Rate eq 0 and Exempt eq true and OutOfScope eq false and Export eq false"
        else:
            filter += " and Description eq '" + request.query.replace("'", "''") + "'"
        records = await self._rows("Catalog_VATRates", filter=filter, top=20)
        if len(records) == 20:
            raise UserProblem("Слишком много налоговых профилей. Уточните название в 1С.")
        profiles = [self._tax_profile(r) for r in records if not r.DeletionMark and not r.Calculated
                    and (request.mode != "rate" or not r.Export)]
        matches = [p for p in profiles if tax_matches(request, p)]
        if len(matches) != 1:
            raise UserProblem("Налоговый профиль не найден однозначно в 1С. Уточните ставку или точное название профиля.")
        return matches[0]

    async def resolve_basis(self, command: ResolvedInvoiceCommand) -> BillingBasis:
        command = ResolvedInvoiceCommand.model_validate(command)
        await self.check_metadata()
        company = await self._record("Catalog_Companies", command.client_id)
        if company.IsFolder or company.Inactive:
            raise UserProblem("Компания неактивна или является папкой.")
        contract = await self._contract(company)
        default_history = None
        if not command.services:
            default_history = await self._history_rows(company, contract, command)
            template = default_history[0]
            if len([source for source in default_history if source.Date == template.Date]) > 1:
                raise UserProblem("Несколько последних счетов имеют одинаковую дату/время. Уточните исторический образец.")
            has_bookkeeping = any(row.Item_Key == self.settings.bookkeeping_item_id
                for source in default_history for row in source.Inventory)
            if (any(row.Item_Key != self.settings.bookkeeping_item_id for row in template.Inventory)
                    and (not has_bookkeeping or command.previous in ("last", "usual"))):
                inferred = ResolvedInvoiceCommand(**{**command.model_dump(), "services": tuple(
                    ResolvedServiceSelection(service_id=str(row.Item_Key), quantity=row.Quantity)
                    for row in sorted(template.Inventory, key=lambda row: row.LineNumber))})
                return await self._resolve_many_basis(inferred, company, contract, history=default_history)
        if command.services and any(s.service_id != str(self.settings.bookkeeping_item_id) for s in command.services):
            return await self._resolve_many_basis(command, company, contract)
        item = await self._item()
        if any(s.service_id != str(item.Ref_Key) for s in command.services):
            raise UserProblem("Выбрана неподдерживаемая услуга.")
        source = self._source_for(default_history, item) if default_history is not None else await self._history(company, contract, command, item)
        if command.preview_overrides and command.preview_source_id != str(source.Ref_Key):
            raise UserProblem("Исторический образец изменился. Подготовьте новый preview перед ручными правками.")
        if source.DocumentCurrency_Key != contract.AccountsCurrency_Key:
            raise UserProblem("Валюта исторического счёта отличается от договора. Нельзя безопасно подготовить preview.")
        if source.AmountVATIn:
            raise UserProblem("Исторический счёт содержит цены с включённым НДС. Такая арифметика пока заблокирована.")
        if sum((r.AmountTotal for r in source.Inventory), Decimal(0)) != source.DocumentAmount:
            raise UserProblem("Сумма исторического документа не совпадает со строками.")
        rows = sorted((r for r in source.Inventory if r.Item_Key == item.Ref_Key), key=lambda r: r.LineNumber)
        if len({r.LineNumber for r in source.Inventory}) != len(source.Inventory):
            raise BackendFailure("firstbit_duplicate_line")
        selections = command.services
        if len(selections) > 1 and len(rows) == 1:
            return await self._resolve_many_basis(command, company, contract)
        # A single service without a quantity means all historical rows for this service.
        expand = len(selections) == 1 and selections[0].quantity is None
        if selections and not expand and len(selections) != len(rows):
            raise UserProblem("Нельзя объединять или удалять исторические строки автоматически. Укажите изменения по строкам.")
        vats: dict[UUID, VAT] = {}
        uoms: dict[tuple[str, UUID], NamedRecord] = {}
        lines = tuple([await self._line(row, item, quantity=(selections[i].quantity
            if selections and not expand else None), vats=vats, uoms=uoms) for i, row in enumerate(rows)])
        if len({e.line_number for e in command.preview_overrides}) != len(command.preview_overrides):
            raise UserProblem("Для строки заданы противоречивые ручные правки.")
        edited_lines = list(lines)
        for edit in command.preview_overrides:
            if edit.line_number > len(rows) or rows[edit.line_number - 1].LineNumber != edit.source_line_number:
                raise UserProblem("Строки исторического образца изменились. Ручные правки не перенесены; нужен новый preview.")
            if edit.source_id not in (None, str(source.Ref_Key)):
                raise UserProblem("Источник строки изменился; ручные значения не перенесены.")
            line = edited_lines[edit.line_number - 1]
            tax = await self._preview_tax(edit.tax, line.tax) if edit.tax is not None else None
            edited_lines[edit.line_number - 1] = line.overridden(edit.user_edit(), tax)
        lines = tuple(edited_lines)
        if command.tax.mode == "profile" or any(
            command.tax.mode == "with_tax" and line.tax.rate == 0 or
            command.tax.mode == "without_tax" and line.tax.rate != 0 for line in lines):
            raise UserProblem("Запрошенный налоговый режим отличается от исторического. Нужна отдельная проверка 1С.")
        return await self._compose_basis(command, company, contract, source, lines)

    async def _resolve_many_basis(self, command, company, contract, *, history=None):
        items = {}
        for selection in command.services:
            if selection.service_id not in items:
                item = await self._record("Catalog_Items", selection.service_id)
                if item.IsFolder or item.Inactive:
                    raise UserProblem("Услуга неактивна или является папкой.")
                items[selection.service_id] = item
        history = await self._history_rows(company, contract, command) if history is None else history
        latest = {key: self._source_for(history, item) for key, item in items.items()}
        issuers = {source.Entity_Key for source in latest.values()}
        if len(issuers) != 1:
            common = set.intersection(*[{source.Entity_Key for source in history
                if any(row.Item_Key == item.Ref_Key for row in source.Inventory)} for item in items.values()])
            if len(common) != 1:
                raise UserProblem("Источники услуг относятся к разным поставщикам. Уточните исторический образец; автоматически смешивать их нельзя.")
            issuer = next(iter(common))
            latest = {key: self._source_for([s for s in history if s.Entity_Key == issuer], item)
                      for key, item in items.items()}
        sources = list({str(source.Ref_Key): source for source in latest.values()}.values())
        primary = sources[0]
        if command.preview_overrides and command.preview_source_id != str(primary.Ref_Key):
            raise UserProblem("Основной исторический образец изменился. Подготовьте новый preview.")
        for source in sources:
            if source.DocumentCurrency_Key != contract.AccountsCurrency_Key or source.AmountVATIn:
                raise UserProblem("Валюта или арифметика исторического источника не поддерживается. Preview остановлен.")
            if sum((r.AmountTotal for r in source.Inventory), Decimal(0)) != source.DocumentAmount:
                raise UserProblem("Сумма исторического документа не совпадает со строками.")
            if len({r.LineNumber for r in source.Inventory}) != len(source.Inventory):
                raise BackendFailure("firstbit_duplicate_line")
        lines, used = [], {}
        vats, uoms = {}, {}
        for selection in command.services:
            item, source = items[selection.service_id], latest[selection.service_id]
            rows = sorted((r for r in source.Inventory if r.Item_Key == item.Ref_Key), key=lambda r: r.LineNumber)
            count = sum(s.service_id == selection.service_id for s in command.services)
            occurrence = used.get(selection.service_id, 0)
            used[selection.service_id] = occurrence + 1
            if count == 1 and selection.quantity is None:
                selected_rows = rows
            elif len(rows) == 1:
                selected_rows = rows
            elif count == len(rows):
                selected_rows = [rows[occurrence]]
            else:
                raise UserProblem("Для услуги найдено несколько исторических строк. Уточните состав; строки не объединяем.")
            for row in selected_rows:
                line = await self._line(row, item, quantity=selection.quantity, vats=vats, uoms=uoms)
                lines.append(InvoiceLine(**{**line.model_dump(), "source_id": str(source.Ref_Key)}))
        edits = {e.line_number: e for e in command.preview_overrides}
        if len(lines) > 20:
            raise UserProblem("В историческом образце больше 20 строк. Уточните состав услуг.")
        for index, edit in edits.items():
            if index > len(lines):
                raise UserProblem("В preview нет такой строки.")
            line = lines[index - 1]
            if line.source_id != edit.source_id or line.source_line_number != edit.source_line_number:
                raise UserProblem("Источник или номер исторической строки изменился. Значения не перенесены.")
            tax = await self._preview_tax(edit.tax, line.tax) if edit.tax else None
            lines[index - 1] = line.overridden(edit.user_edit(), tax)
        if command.tax.mode == "profile" or any(
                command.tax.mode == "with_tax" and line.tax.rate == 0 or
                command.tax.mode == "without_tax" and line.tax.rate != 0 for line in lines):
            raise UserProblem("Укажите налог отдельно по строкам и проверьте профиль 1С.")
        return await self._compose_basis(command, company, contract, primary, tuple(lines), sources=tuple(sources))

    async def _compose_basis(self, command, company, contract, source, lines, *, sources=()):
        # Show only proven historical facts. A different current contract issuer
        # requires explicit UI review; it is never silently used as a new default.
        entity = await self._record("Catalog_Entities", source.Entity_Key)
        contract_entity = (await self._record("Catalog_Entities", contract.Entity_Key)
                           if source.Entity_Key != contract.Entity_Key else None)
        currency = await self._record("Catalog_Currencies", contract.AccountsCurrency_Key)
        codes = {"AED": "784", "USD": "840", "EUR": "978", "GBP": "826", "RUB": "643"}
        currency_code = next((code for code, numeric in codes.items() if numeric == currency.Code), None)
        if currency_code is None:
            raise UserProblem("Не подтверждена ISO валюта договора.")
        if any(edit.currency is not None and edit.currency != currency_code for edit in command.preview_overrides):
            raise UserProblem("Валюта суммы отличается от договора. Конвертация не выполняется.")
        # Payment/bank/default resolution is deliberately NOT inferred from old references.
        # Read-only proposal has no payment instructions; these are draft-write blockers.
        preview = InvoicePreview(invoice_date=command.invoice_date, service_period=command.service_period,
            currency=currency_code, issuer=PartyDetails(name=entity.DescriptionFull or entity.Description),
            recipient=PartyDetails(name=company.DescriptionFull or company.Description, tax_number=company.TRN or None),
            bank=None, terms=None, lines=lines,
            user_overrides=tuple(e.user_edit() for e in command.preview_overrides),
            subtotal=sum((r.subtotal for r in lines), Decimal(0)),
            tax_amount=sum((r.tax_amount for r in lines), Decimal(0)), total=sum((r.total for r in lines), Decimal(0)),
            reference="READONLY historical proposal", previous_reference=source.Number,
            historical_proposal=HistoricalProposal(source_id=str(source.Ref_Key), source_number=source.Number,
                source_date=source.Date.date(), contract_id=str(contract.Ref_Key), contract_name=contract.Description,
                entity_id=str(entity.Ref_Key),
                sources=tuple(HistoricalSource(source_id=str(s.Ref_Key), source_number=s.Number,
                    source_date=s.Date.date()) for s in sources),
                contract_entity_id=str(contract_entity.Ref_Key) if contract_entity else None,
                contract_entity_name=(contract_entity.DescriptionFull or contract_entity.Description) if contract_entity else None))
        identity = f"{self.settings.base_url}|{entity.Ref_Key}|{company.Ref_Key}|{contract.Ref_Key}|"
        identity += (f"{command.service_period.year}-{command.service_period.month:02d}"
                     if command.service_period else str(command.invoice_date))
        revision = hashlib.sha256(b"".join(s.model_dump_json().encode() for s in (sources or (source,))) + contract.model_dump_json().encode()
                                  + preview.model_dump_json().encode()).hexdigest()
        return BillingBasis(key="firstbit:" + hashlib.sha256(identity.encode()).hexdigest(),
                            client_id=str(company.Ref_Key), revision=revision, preview=preview)

    async def read_operation(self, basis, operation_id):
        # No durable FirstBit operation correlation exists in this phase.
        return OperationState(operation_id=operation_id, status="unknown")

    async def verify_write_schema(self, expected_sha256: str | None):
        # Discovery/verification only: does not change preview_only or enable a
        # mutation transport. A future writer must call this before mutation.
        from app.firstbit_write_schema import inspect_write_schema
        await self.check_metadata()
        evidence = inspect_write_schema(await self._get("$metadata", metadata=True))
        return evidence.require_approved(expected_sha256)

    async def ensure_draft(self, *args, **kwargs):
        raise WritesDisabled()

    async def ensure_posted(self, *args, **kwargs):
        raise WritesDisabled()

    async def get_pdf(self, *args, **kwargs):
        raise WritesDisabled()
