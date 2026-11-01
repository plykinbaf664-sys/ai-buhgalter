"""Critical prospective write-schema fingerprint, never a permission to write.

Field/action names were checked against actual Standard OData metadata. No
business IDs, defaults, payloads, customer data or raw schema snapshot live here.
Native printing and transactional/default semantics need separate evidence.
"""
import hashlib
import hmac
import json
import xml.etree.ElementTree as ET

from pydantic import Field

from app.domain import BackendFailure, StrictModel, WritesDisabled


GUID = "Edm.Guid"
STRING = "Edm.String"
BOOL = "Edm.Boolean"
NUMBER = ("Edm.Decimal", "Edm.Double")
HEAD = {
    **{key: GUID for key in ("Ref_Key", "Company_Key", "Contract_Key", "Entity_Key",
        "DocumentCurrency_Key", "AccountingCurrency_Key", "NationalCurrency_Key", "BankAccount_Key",
        "PaymentTerms_Key", "PaymentTermsVersion_Key", "AccountsReceivableGLAccount_GL_Key",
        "AdvancesReceivedGLAccount_GL_Key")},
    **{key: STRING for key in ("DataVersion", "Number", "Comment", "TransactionType", "TaxationVAT")},
    **{key: BOOL for key in ("Posted", "DeletionMark", "AmountVATIn")},
    **{key: NUMBER for key in ("DocumentAmount", "ExchangeRate", "ExchangeRateAccCur")},
    "FactorAccCur": ("Edm.Int32", "Edm.Int64"),
    "Date": "Edm.DateTime", "PriceDate": "Edm.DateTime",
}
LINE = {
    **{key: GUID for key in ("Item_Key", "VATRate_Key", "GLAccount_GL_Key",
                            "SalesRevenueGLAccount_GL_Key", "OutputVATGLAccount_GL_Key")},
    **{key: STRING for key in ("Content", "UnitOfMeasure", "UnitOfMeasure_Type")},
    **{key: NUMBER for key in ("Quantity", "Price", "Amount", "AmountTotal", "VATAmount",
        "DiscountMarkupRate", "DiscountMarkupAmount", "AutomaticDiscountRate", "AutomaticDiscountAmount")},
    "LineNumber": ("Edm.Int32", "Edm.Int64"),
}


class WriteSchema(StrictModel):
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    document_entity: str
    post_declared: bool
    declared_print_actions: tuple[str, ...]

    def require_approved(self, expected: str | None):
        if (type(expected) is not str or len(expected) != 64
                or any(c not in "0123456789abcdef" for c in expected)
                or not hmac.compare_digest(self.sha256, expected)):
            raise WritesDisabled()
        return self


def inspect_write_schema(raw: bytes) -> WriteSchema:
    """Validate required properties and bound Post, hash all critical attributes.

    A match proves only the reviewed structural contract, not writer rights,
    current accounting defaults, atomic create behavior or a native PDF service.
    """
    try:
        if len(raw) > 8_000_000 or b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
            raise ValueError()
        root = ET.fromstring(raw)
        local = lambda node: node.tag.rsplit("}", 1)[-1]
        types = {}
        for schema in root.iter():
            if local(schema) != "Schema":
                continue
            namespace = schema.attrib["Namespace"]
            for child in schema:
                if local(child) in ("EntityType", "ComplexType"):
                    name = namespace + "." + child.attrib["Name"]
                    if name in types:
                        raise ValueError()
                    props = [p for p in child if local(p) == "Property"]
                    if len({p.attrib["Name"] for p in props}) != len(props):
                        raise ValueError()
                    types[name] = {p.attrib["Name"]: dict(p.attrib) for p in props}
        sets = [n for n in root.iter() if local(n) == "EntitySet"
                and n.attrib.get("Name") == "Document_InventoryExpense"]
        if len(sets) != 1:
            raise ValueError()
        document_type = sets[0].attrib["EntityType"]
        props = types[document_type]
        collection = props["Inventory"]["Type"]
        if not collection.startswith("Collection(") or not collection.endswith(")"):
            raise ValueError()
        line_props = types[collection[11:-1]]

        def checked(required, actual):
            result = {}
            for name, expected in required.items():
                value = actual[name]
                if value["Type"] not in (expected if isinstance(expected, tuple) else (expected,)):
                    raise ValueError()
                result[name] = value
            return result

        functions = []
        for node in root.iter():
            if local(node) != "FunctionImport":
                continue
            params = [dict(p.attrib) for p in node if local(p) == "Parameter"]
            if any(p.get("Name") == "bindingParameter" and p.get("Type") == document_type for p in params):
                functions.append({"attributes": dict(node.attrib), "parameters": params})
        posts = [f for f in functions if f["attributes"].get("Name") == "Post"]
        if len(posts) != 1:
            raise ValueError()
        post = posts[0]
        if (post["attributes"].get("IsBindable") != "true"
                or post["attributes"].get("IsSideEffecting") != "true"
                or post["parameters"] != [{"Name": "bindingParameter", "Type": document_type},
                                           {"Name": "PostingModeOperational", "Type": BOOL}]):
            raise ValueError()
        canonical = {"entity_set": dict(sets[0].attrib), "head": checked(HEAD, props),
                     "inventory": props["Inventory"], "line": checked(LINE, line_props), "post": post}
        digest = hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        printing = tuple(sorted(f["attributes"]["Name"] for f in functions
            if any(word in f["attributes"]["Name"].casefold() for word in ("print", "pdf"))))
        return WriteSchema(sha256=digest, document_entity="Document_InventoryExpense", post_declared=True,
                           declared_print_actions=printing)
    except Exception:
        raise BackendFailure("firstbit_write_schema_mismatch") from None
