# FirstBit integration evidence

Repository-safe provider findings, distinguished from code behavior. Fresh FirstBit metadata/GET establishes provider facts; code/tests establish what this adapter actually implements. This document is a research inventory, not a second runtime contract.

Current implementation/consumed fields and limits: [READONLY_PIPELINE](READONLY_PIPELINE.md). Feature behavior: [INITIAL_REQUESTS](INITIAL_REQUESTS.md), [COMPANY_SEARCH](COMPANY_SEARCH.md), [PREVIEW_REVISIONS](PREVIEW_REVISIONS.md). Private snapshot coverage: [METADATA_COVERAGE](FIRSTBIT_METADATA_COVERAGE.md). Dated proof scope: [VERIFICATION](../VERIFICATION.md).

## Verified wire and business observations

- Standard OData/Basic Auth reads succeeded with the owner-attested dedicated reader and TLS. Rights attestation is not a programmatic permissions audit.
- Double numerics, digit-string Int64 LineNumber and `%20` query spaces were confirmed by actual metadata/GET. tolower and equality on unbounded DescriptionFull were unsupported. Company lookup now uses local name pages; old substring probes are not its current implementation.
- Posted source issuer and current contract issuer can differ despite agreeing client/contract/currency. Both entity references can be verified, but this does not establish which issuer is correct for a new document. The non-executable historical proposal preserves the mismatch.
- Catalog_Items.Code is a verified Edm.String used for service-choice display. Current reader supports active Service items beyond the configured bookkeeping item, when per-service history is proven.
- Runtime consumption is a smaller subset of the observed fields below. An observed additional field is not automatically required, selected or a current accounting default.

Raw evidence/diagnostics stay only under ignored `.local/firstbit/`; no customer names, Ref_Key values, TRNs, credentials, metadata/business dumps or production fixtures belong here. Tests use synthetic data. Private evidence is neither a runtime dependency nor application storage. Do not guess an OData field or financial rule from ordinary 1C conventions.

## Native adapter interface evidence

Production create/read-back proved that FirstBit can normalize TaxInvoiceIsRequired independently of the submitted historical carryover value. It is a lifecycle flag, not authoritative proof of TaxInvoice existence. The full native provider checks the actual linked TaxInvoice and preserves exact financial/accounting read-back; the base controlled-draft provider retains its strict comparison. This observation does not authorize ignoring other field mismatches.



Fresh publication exposes Catalog_BusinessActivities, Catalog_ExpenseItems and Document_TaxInvoice. The InventoryExpense Department association targets Catalog_BaseUnits. Historical analytical refs must be checked as live records; publication/detail coverage does not establish accounting defaults.

A fresh dedicated-user browser opened an existing TaxInvoice by standard native navigation link, and its native GetURL -> Show link returned the same reference. The standard internal reference encoding reorders UUID segments; app/firstbit_ui.py implements and tests the reversible conversion without saved sessions.

Native Print -> Tax Invoice (EN, landscape) -> Save Printable Document -> Save to Local Folder with PDF only produced a genuine one-page landscape PDF containing that TaxInvoice number. The adapter also exercised printing after fresh OData schema/document guards. The Moxel form initializes asynchronously; a visible command bar alone is not proof that a command has completed. The dedicated Generate Tax Invoice action invoked the observed GenerateTaxInvoice function and produced a linked TaxInvoice. Generic Create Based On -> Tax Invoice instead opens an unsaved Tax Invoice (create) form and is not an admitted substitute. The controlled source and TaxInvoice were both posted and verified; native PDF delivery completed through recovery.

TaxInvoice exposes Date, IssuingDate and DateOfOriginalSupply as Edm.DateTime. In the inspected native case their dates agree with the source Invoice. This is observed case evidence; read-back must check the confirmed date rather than assuming every future generation uses it.

## Environment already identified

The production system is FirstBit ERP on 1C.

Confirmed during integration discovery:
- standard OData is supported and published;
- Basic Auth works for the dedicated integration user;
- read-only production requests have succeeded;
- a limited MVP OData surface was explicitly published;
- readonly application mode remains read-only;
- native PDF and a controlled new Invoice/linked TaxInvoice production flow with recovery and Telegram delivery are proved; dated results belong to VERIFICATION.

Exact endpoint, credentials and production identifiers must come from ENV/private local evidence, not this tracked document.

## Core document mapping

The normal customer invoice in this FirstBit configuration is:

```text
1C metadata object:
Document.InventoryExpense

Standard OData:
Document_InventoryExpense
```

Do not substitute Proforma Invoice, Tax Invoice, or another invoice-like document unless a separate business requirement explicitly calls for it.

## Company resolution

Relevant 1C object:

```text
Catalog.Companies
```

Observed fields during research include the following; only the subset in READONLY_PIPELINE is consumed at runtime:

```text
Ref_Key
DeletionMark
IsFolder
Code
Description
DescriptionFull
ContractByDefault_Key
Inactive
TRN
VATTaxpayer
PricesIncludeVAT
```

Current canonical/fuzzy/alias/choice behavior is owned by [COMPANY_SEARCH](COMPANY_SEARCH.md). These observed fields do not all enter runtime selects.

## Contract resolution

Relevant object:

```text
Catalog.CompanyContracts
```

Observed fields include:

```text
Ref_Key
Owner_Key
Description
AccountsCurrency_Key
Entity_Key
PriceKind_Key
SalesPaymentTerms_Key
DeliveryTerms_Key
Inactive
```

Current default/fallback validation is owned by [READONLY_PIPELINE](READONLY_PIPELINE.md); a reference's existence alone does not prove active ownership or accounting defaults.

Important evidence:

A valid active customer contract can have empty PriceKind, SalesPaymentTerms and DeliveryTerms.

The adapter must not assume these values always come from the contract.

## Pricing evidence

This is the most important integration-specific finding.

For the bookkeeping service, the investigated production FirstBit database did **not** provide a usable authoritative current price through the published `ItemPrices` register.

Historical invoices showed:
- different clients can have different recurring prices;
- the same client can keep the same price for many months;
- a client's price can change over time;
- quantity can change independently of price;
- discounts can exist;
- one invoice can contain multiple rows of the same bookkeeping Item with different price/quantity.

Therefore:

**Do not copy the FakeOneC pricing assumption into the real FirstBit adapter.**

Posted matching history is a proposal source, not an authoritative current tariff. Exact service/source selection and explicit user overrides are implemented as documented in INITIAL_REQUESTS.

Historical values are not permanent tariffs and still require human confirmation.

## Observed invoice header fields

Real posted invoice responses have included fields such as:

```text
Ref_Key
Date
Posted
Company_Key
Contract_Key
Entity_Key
DocumentCurrency_Key
AccountingCurrency_Key
NationalCurrency_Key
PriceKind_Key
PaymentTerms_Key
PaymentTermsVersion_Key
BankAccount_Key
BaseUnit_Key
Department_Key
AmountVATIn
TaxationVAT
TaxInvoiceIsRequired
TransactionType
DocumentAmount
PriceDate
ExchangeRate
AccountsReceivableGLAccount_GL_Key
AdvancesReceivedGLAccount_GL_Key
```

Only use fields actually required by the application flow.

`PaymentTermsVersion_Key` from an old invoice is historical/reference data only. Do not blindly reuse it for a new document.

## Observed invoice-line fields

Real `Inventory` rows have included:

```text
Item_Key
Content
Quantity
UnitOfMeasure
Price
Amount
AmountTotal
VATRate_Key
VATAmount
DiscountMarkupRate
DiscountMarkupAmount
IncomeItem_Key
ExpenseItem_Key
GLAccount_GL_Key
SalesRevenueGLAccount_GL_Key
OutputVATGLAccount_GL_Key
TradeDiscountsGLAccount_GL_Key
BusinessActivity_Key
BaseUnit_Key
```

The real adapter must preserve fields independently.

Do not infer a missing field from another field unless the FirstBit rule has been verified.

## VAT behavior

Production invoices demonstrate that VAT behavior is not a single fixed formula.

Observed differences include:
- taxable and zero/non-taxable lines in the same invoice;
- `AmountVATIn` can be true or false;
- VAT amount behavior changes when VAT is included in the amount.

Therefore:
- never assume "VAT is always 5%";
- do not reuse the simplified FakeOneC arithmetic for production unless it is proven equivalent;
- prefer values and semantics resolved from FirstBit;
- fail closed when tax treatment cannot be established safely.

## Price date and document date

`PriceDate` can differ from the invoice `Date`.

Do not assume they are interchangeable.

The application also distinguishes invoice date and service period.

Historical invoice date does not automatically become the date of a new invoice.

## GL/default evidence

Relevant published FirstBit sources were identified for later deterministic resolution:

```text
InformationRegister.ItemsGLAccounts
InformationRegister.CompaniesGLAccounts
InformationRegister.DefaultGLAccounts
ChartOfAccounts.GeneralChartOfAccounts
```

They are intended to help resolve/verify line/header accounting references.

Do not hardcode GL refs from a single observed invoice.

## Payment-term evidence

Relevant sources include:

```text
Catalog.SalesPaymentTerms
Catalog.SalesPaymentTermsVersions
InformationRegister.AccountsReceivablePaymentTermsVersions
```

Historical `PaymentTermsVersion_Key` must not be copied as the new-document version without a verified rule.

## Register/OData behavior

Do not assume all FirstBit registers expose dimensions as top-level filterable fields.

Observed pattern:

```text
InformationRegister_ItemPrices
```

can expose a recorder/RecordSet wrapper, while:

```text
InformationRegister_ItemPrices_RecordType
```

exposes flattened rows suitable for filtering.

Always inspect actual `$metadata` and response shape.

## OData publication

A deliberately limited MVP set of FirstBit objects was published for the integration.

The reviewed whitelist snapshot should live in private reviewed evidence/config or an approved internal repository.

Do not:
- auto-publish metadata objects;
- broaden the OData surface "just in case";
- change publication from application runtime.

Before write enablement, review the published surface again and remove anything not required.

## Unproven semantics and next evidence

Observed PriceDate, GL/payment-version/bank references and VAT variants do not prove defaults for a new document. Included VAT/discount/cross-currency rules, legal tax applicability and authoritative tariff/default sources need explicit proof before support. Current reader deliberately accepts only the narrow checked arithmetic in READONLY_PIPELINE.

Real integration create/default execution, posting, durable uniqueness, restart-safe reconciliation and a write baseline are not established by this research. Native UI generation/printing evidence below does not establish a supported external API. The milestone/admission sequence is owned by [PROJECT_CONTEXT](../PROJECT_CONTEXT.md) and [SECURITY](../SECURITY.md), with transactional requirements in [onec-contract](../onec-contract.md).

## Native Tax Invoice generation and PDF: captured flow

Reviewed HAR and fresh production GET on 2026-10-31 establish:

- A native exported server function `GenerateTaxInvoice` accepts one source Invoice reference and returns a distinct Tax Invoice reference. Native exported names `TaxInvoiceFor`, `TaxInvoiceListFor`, `TaxInvoicesByBasis` also occur; their semantics/signatures are not established by their names.
- The captured linked document is `Document.TaxInvoice`. Printing uses manager `Document.TaxInvoice`, template `TaxInvoiceLandscapeEN`, user form `Tax Invoice (EN, landscape)`, through `CommonForm.PrintDocuments`, spreadsheet/Moxel export and `PutSpreadsheetDocumentsInTempStorage` with PDF format. The returned temporary-storage address matches the captured download; decoded bytes are a real landscape PDF produced by 1C. The printed reference matches the generation result, not the source Invoice reference.
- The captured case reports an already-posted Tax Invoice. This does not prove that every generation automatically posts. New operations must read the actual state; an already-posted document must not be posted again.
- Fresh live Standard OData metadata exposes InventoryExpense and its Post action, but no TaxInvoice entity set, GenerateTaxInvoice action or native print/PDF action. Captured source Invoice read-back confirms a posted, non-deleted document. No financial mutation was made during investigation.
- HAR generation/printing calls are internal web-client RPC, bound to session/module/version state. They are evidence, not a supported external integration API. Module ownership of GenerateTaxInvoice, transaction/uniqueness rules, external publication, exact native print signatures and independent TaxInvoice read-back remain unproved. Do not replay captured sessions or temporary URLs.

Raw capture, linked references, native PDF, fresh metadata and technical correlation summaries stay only in ignored `.local/firstbit/tax-invoice-flow/`. No production identities belong in fixtures. Next evidence: targeted configuration source/publication review, including both document managers and the actual module containing the captured exports. Runtime metadata alone cannot export module bodies. Integration status and admission: [PRODUCTION_OPERATION](PRODUCTION_OPERATION.md).

### Backend interface and accounting-reference verification

Additional production GET investigation on 2026-10-31 checked the service document, fresh metadata, publication bootstrap and standard SOAP/HTTP service roots, not just OData actions. OData metadata/service document and web bootstrap respond 200. The native `e1cib/modules/defs` path without captured session/module identifiers responds 403 with the integration identity. The SOAP root responds 500 `Service not found`; the HTTP root responds 404 and neither exposes service links. HAR contains no `/ws/` or `/hs/` service paths. These root responses **do not prove that all named SOAP/HTTP services are absent**; those routes are not a universal service directory. A supported existing service URL/WSDL/contract or publication inventory is the next minimal discovery input. New endpoint implementation or full configuration-source access is not established as necessary by these probes. Platform publication behavior: [1C publication settings](https://1c-dn.com/anticrisis/tools-and-technologies/embedded-web-client/setting-up/).

> Historical pre-publication checkpoint, superseded by the fresh publication/native adapter evidence above. The earlier absence/404 results below do not describe current publication.

Fresh scoped read-back of the selected posted, non-deleted historical source confirms two inventory rows with nonempty accounting dimensions. Exact referenced BaseUnit, IncomeItem and TradeDiscountsGLAccount records are readable and non-deleted. Referenced BusinessActivity and ExpenseItem catalogs exist in the full private configuration index but remain absent from fresh OData metadata; exact reference GETs return 404. Inventory row metadata supplies no navigation route to them. The controlled-create admission check still returns PROPOSAL_BLOCKED before mutation: the writer does not model/validate/carry all those dimensions and row connections. Published references alone do not remove that guard. These are source-document and reference read-backs, **not read-back of a newly created Invoice**.

Private bounded responses and summaries: ignored `.local/firstbit/backend-interface-proof/`. No create/post/generate call or captured-session replay was performed. An address/contract for an already available native integration service could close the discovery gap without source delivery; alternatively the missing references need a supported read/validation method and the native operations need a supported callable contract. Do not claim that publishing TaxInvoice alone exposes GenerateTaxInvoice or printing.


## Authoritative supplier VAT registration

Published InformationRegister_EntityRegistrationsWithTaxAuthorityAsVATPayer exposes Period, Entity_Key and Registration_Key. Catalog_RegistrationsWithTaxAuthorityAsVATPayer exposes Ref_Key, DeletionMark, DataVersion, Owner, Owner_Type and TRNVAT. Owner is a polymorphic string UUID whose observed type is StandardODATA.Catalog_Entities.

GET verified an effective registration for the approved supplier, a live nondeleted catalog record owned by that entity, and exact equality between TRNVAT and the native TaxInvoice.EntityTRN. Choose a unique latest effective Period, not a guessed flat entity property or an arbitrary historical TRN. Missing/zero/ambiguous/deleted/foreign registrations block. Catalog_Entities names alone never established an empty supplier TRN.

Direct WHERE comparisons on TaxInvoice.DocumentBasis were rejected by this publication. Reconciliation therefore scans bounded, ordered minimal relation keys without party filtering, then validates the matched full document. A linked record with wrong parties must be a conflict rather than invisible to duplicate protection. No full customer/invoice dump or arbitrary nextLink is required.
