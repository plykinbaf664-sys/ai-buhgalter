"""Entirely synthetic GET server for repeatable application smoke; no production data."""
import copy
import json
from uuid import UUID
from xml.etree.ElementTree import Element, SubElement, tostring

import httpx


def ref(n):
    return str(UUID(int=n))


def synthetic_metadata():
    # Independent wire contract fixture. Not exported from provider models or production.
    specs = {
        "Catalog_Companies": {
            "Edm.Guid": "Ref_Key ContractByDefault_Key",
            "Edm.Boolean": "DeletionMark IsFolder Inactive",
            "Edm.String": "Description DescriptionFull TRN"},
        "Catalog_CompanyContracts": {
            "Edm.Guid": "Ref_Key Owner_Key Entity_Key AccountsCurrency_Key",
            "Edm.Boolean": "DeletionMark Inactive", "Edm.String": "Description"},
        "Catalog_Items": {"Edm.Guid": "Ref_Key", "Edm.Boolean": "DeletionMark IsFolder Inactive",
            "Edm.String": "Description ItemType"},
        "Catalog_Entities": {"Edm.Guid": "Ref_Key", "Edm.Boolean": "DeletionMark",
            "Edm.String": "Description DescriptionFull"},
        "Catalog_Currencies": {"Edm.Guid": "Ref_Key", "Edm.Boolean": "DeletionMark", "Edm.String": "Code Description"},
        "Catalog_VATRates": {"Edm.Guid": "Ref_Key", "Edm.Boolean": "DeletionMark Exempt Export OutOfScope Calculated",
            "Edm.String": "Description", "Edm.Decimal": "Rate"},
        "Document_InventoryExpense": {
            "Edm.Guid": "Ref_Key Company_Key Contract_Key Entity_Key DocumentCurrency_Key",
            "Edm.Boolean": "DeletionMark Posted AmountVATIn", "Edm.String": "Number",
            "Edm.DateTime": "Date", "Edm.Decimal": "DocumentAmount",
            "Collection(StandardODATA.HistoryRow)": "Inventory"},
        "Catalog_UOMClassifier": {"Edm.Guid": "Ref_Key", "Edm.Boolean": "DeletionMark", "Edm.String": "Description"},
        "Catalog_UOM": {"Edm.Guid": "Ref_Key", "Edm.Boolean": "DeletionMark", "Edm.String": "Description"},
        "HistoryRow": {"Edm.Int64": "LineNumber", "Edm.Guid": "Item_Key VATRate_Key",
            "Edm.String": "Content UnitOfMeasure UnitOfMeasure_Type",
            "Edm.Decimal": "Quantity Price Amount AmountTotal VATAmount DiscountMarkupRate DiscountMarkupAmount AutomaticDiscountRate AutomaticDiscountAmount"},
    }
    schema = Element("Schema", Namespace="StandardODATA")
    container = SubElement(schema, "EntityContainer", Name="DefaultContainer")
    for name, groups in specs.items():
        entity = SubElement(schema, "ComplexType" if name == "HistoryRow" else "EntityType", Name=name)
        for kind, names in groups.items():
            for field in names.split():
                SubElement(entity, "Property", Name=field, Type=kind)
        if name != "HistoryRow":
            SubElement(container, "EntitySet", Name=name, EntityType="StandardODATA." + name)
    return tostring(schema)


class FirstBitFixture:
    def __init__(self):
        self.calls = []
        self.metadata = synthetic_metadata()
        self.status = None
        self.raw = None
        self.records = {
            "Catalog_Companies": [{"Ref_Key": ref(1), "DeletionMark": False, "IsFolder": False,
                "Inactive": False, "Description": "ООО Синтетика", "DescriptionFull": "ООО Синтетика",
                "ContractByDefault_Key": ref(2), "TRN": "TEST-TRN"}],
            "Catalog_CompanyContracts": [{"Ref_Key": ref(2), "DeletionMark": False, "Owner_Key": ref(1),
                "Inactive": False, "Description": "Synthetic contract", "Entity_Key": ref(3), "AccountsCurrency_Key": ref(4)}],
            "Catalog_Items": [{"Ref_Key": ref(5), "DeletionMark": False, "IsFolder": False, "Inactive": False,
                "Description": "Accounting and bookkeeping services", "ItemType": "Service"}],
            "Catalog_Entities": [{"Ref_Key": ref(3), "DeletionMark": False, "Description": "Synthetic issuer",
                "DescriptionFull": "Synthetic issuer"}],
            "Catalog_Currencies": [{"Ref_Key": ref(4), "DeletionMark": False, "Description": "UAE Dirham", "Code": "784"}],
            "Catalog_VATRates": [{"Ref_Key": ref(6), "DeletionMark": False, "Description": "Synthetic VAT 5%",
                "Rate": "5", "Exempt": False, "Export": False, "OutOfScope": False, "Calculated": False}],
            "Catalog_UOMClassifier": [{"Ref_Key": ref(7), "DeletionMark": False, "Description": "service"}],
            "Catalog_UOM": [],
            "Document_InventoryExpense": [{"Ref_Key": ref(8), "DeletionMark": False, "Number": "SYNTHETIC-ONLY-001",
                "Date": "2026-08-20T00:00:00", "Posted": True, "Company_Key": ref(1), "Contract_Key": ref(2),
                "Entity_Key": ref(3), "DocumentCurrency_Key": ref(4), "AmountVATIn": False, "DocumentAmount": "3150.00",
                "Inventory": [self.line(1, "1", "1000.00"), self.line(2, "2", "1000.00")]}],
        }

    @staticmethod
    def line(number, quantity, price):
        from decimal import Decimal
        amount = Decimal(quantity) * Decimal(price)
        vat = amount * Decimal(".05")
        return {"LineNumber": number, "Item_Key": ref(5), "Content": "Bookkeeping synthetic row " + str(number),
            "Quantity": quantity, "UnitOfMeasure": ref(7), "UnitOfMeasure_Type": "StandardODATA.Catalog_UOMClassifier",
            "Price": price, "Amount": str(amount), "AmountTotal": str(amount + vat), "VATRate_Key": ref(6),
            "VATAmount": str(vat), "DiscountMarkupRate": "0", "DiscountMarkupAmount": "0",
            "AutomaticDiscountRate": "0", "AutomaticDiscountAmount": "0"}

    def respond(self, request):
        self.calls.append(request)
        assert request.method == "GET", "Mutation attempted"
        if self.status is not None:
            return httpx.Response(self.status, text="PRIVATE_ERROR_DO_NOT_EXPOSE")
        if self.raw is not None:
            return httpx.Response(200, content=self.raw)
        name = request.url.path.rsplit("/", 1)[-1]
        if name == "$metadata":
            return httpx.Response(200, content=self.metadata)
        rows = copy.deepcopy(self.records[name])
        filter = request.url.params["$filter"]
        if filter.startswith("Ref_Key eq guid'"):
            key = filter.split("'")[1]
            rows = [r for r in rows if r["Ref_Key"] == key]
        if name == "Catalog_Companies" and "$skip" in request.url.params:
            rows.sort(key=lambda r: r["Ref_Key"])
            skip, top = int(request.url.params["$skip"]), int(request.url.params["$top"])
            rows = rows[skip:skip + top]
            selected = request.url.params["$select"].split(",")
            rows = [{k: r[k] for k in selected} for r in rows]
        return httpx.Response(200, json={"value": rows})

    def env(self):
        return {"FIRSTBIT_BASE_URL": "https://firstbit.invalid/test/odata/standard.odata/",
            "FIRSTBIT_USERNAME": "synthetic_integration_reader", "FIRSTBIT_PASSWORD": "synthetic-fixture-secret",
            "FIRSTBIT_READONLY_ACCOUNT": "true", "FIRSTBIT_BOOKKEEPING_ITEM_ID": ref(5)}
