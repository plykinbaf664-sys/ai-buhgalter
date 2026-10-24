# FirstBit / 1C Integration Evidence

## Purpose

This document is the stable, repository-safe orientation for the real FirstBit integration.

It does **not** replace:
- current code and tests;
- `docs/onec-contract.md`;
- fresh FirstBit `$metadata`;
- read-only runtime evidence.

It exists so a coding agent can understand what has already been proven, what remains unknown, and where to look before changing the real 1C adapter.

Implementation/configuration: [READONLY_PIPELINE.md](READONLY_PIPELINE.md). The GET-only provider is implemented, offline-tested and has now passed live prepare/refresh on one client. No production mutations or real Telegram/OpenAI calls were part of that live check. The earlier investigation below remains context; current implementation findings are recorded separately here and in the guide.

## Current adapter live verification

Owner confirmed dedicated read-only account rights. GET metadata and Company/Contract/Item/history/VAT/UOM/Entity/Currency reads produced a typed historical preview and an unchanged re-read snapshot. No IDs, names, amounts, credentials or business payloads are recorded in this tracked evidence.

Verified wire differences from initial synthetic assumptions:
- numeric fields are Edm.Double and are validated as bounded Decimal values;
- LineNumber (Edm.Int64) is serialized as a positive digit string;
- query spaces require `%20`, not form-encoded `+`;
- tolower is rejected by the endpoint;
- DescriptionFull equality fails because the field is unbounded; substringof candidates work, with mandatory local normalized exact match and a bounded candidate limit.

Private metadata/response diagnostics and a formatted preview remain under ignored `.local/firstbit/`. FIRSTBIT_SMOKE_CLIENT is a test input only; the application resolves the client specified by each Telegram request.

Subsequent targeted GETs exposed a separate historical source/current-contract issuer mismatch, with both entities independently verified and currency agreeing. Exact bundle members confirm both Entity references but do not justify silently overriding the current contract for a new document. The app therefore requires an explicit historical-supplier review before showing that non-executable proposal, retaining the mismatch in provenance and blocking any future write admission. Actual owner Telegram review/preview delivery passed; synthetic voice through real OpenAI/FirstBit and read-only refresh also passed. No new provider fields were needed. Full verification scope: [LIVE_DEMO.md](LIVE_DEMO.md).

## Security classification

The Git repository may be public.

Therefore this document must not contain:
- FirstBit credentials;
- Basic Auth headers;
- production passwords/tokens;
- full production metadata dumps;
- customer directories;
- bank-account dumps;
- invoice-history dumps;
- TRN lists;
- GL exports;
- raw production responses;
- real customer names or production document payloads unless explicitly approved.

Raw production evidence belongs only in a local/private ignored directory or another approved private store.

Recommended local layout:

```text
.local/firstbit/
├── metadata/
│   ├── index.json
│   ├── details.json
│   ├── posting-dependencies.json
│   └── standard-odata-metadata.xml
├── samples/
│   ├── companies.json
│   ├── contracts.json
│   ├── items.json
│   ├── invoices.json
│   └── item-prices.json
└── README.md
```

The repository now ignores all `.local/` in `.gitignore`.

Coding agents may read these files when they are available locally, but application code and tests must not depend on their presence.

Production-derived test fixtures committed to Git must be minimized, anonymized and sanitized.

## Source-of-truth order

For exact FirstBit behavior:

1. current application code and tests;
2. fresh FirstBit `$metadata`;
3. current read-only FirstBit responses;
4. reviewed provider mapping/config;
5. this document;
6. old notes/chat history.

Never guess an OData EntitySet, property or accounting rule because it "looks like normal 1C".

## Environment already identified

The production system is FirstBit ERP on 1C.

Confirmed during integration discovery:
- standard OData is supported and published;
- Basic Auth works for the dedicated integration user;
- read-only production requests have succeeded;
- a limited MVP OData surface was explicitly published;
- current work is still read-only;
- production create/post/PDF behavior has not yet been proven.

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

Observed OData fields required by the current resolution flow include:

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

Rules:
- folders are not customers;
- deleted records are ignored;
- exact normalized `Description` / `DescriptionFull` is preferred;
- reviewed aliases may map to a stable Ref;
- fuzzy matching may suggest candidates but must not silently choose an ambiguous customer;
- after resolution the application works with the stable Ref, not free text.

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

Rules:
- try `Company.ContractByDefault_Key` first;
- verify contract owner matches selected Company;
- verify contract is active;
- if default contract is unusable, search active contracts by owner;
- exactly one fallback contract may be selected automatically;
- zero GUID means an empty reference, not a real entity.

Important evidence:

A valid active customer contract can have empty PriceKind, SalesPaymentTerms and DeliveryTerms.

The adapter must not assume these values always come from the contract.

## Service / item resolution

The current bookkeeping flow uses a real FirstBit Service item representing accounting and bookkeeping services.

The exact production Ref belongs in private reviewed mapping/config, not scattered as magic strings in source.

The adapter must preserve stable Item refs after resolution.

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

For the current read-only MVP, the latest matching posted invoice for the selected Company + Contract may be used as a **proposal source** for bookkeeping rows.

Historical values are not permanent tariffs and still require human confirmation.

## Historical invoice resolution

For the current bookkeeping MVP:

1. resolve Company;
2. resolve Contract;
3. query posted, non-deleted `Document_InventoryExpense` records for that Company + Contract;
4. inspect newest first;
5. find the newest invoice containing the bookkeeping Item;
6. preserve **all** matching rows from that invoice;
7. build the proposal/preview from verified data.

Never collapse multiple same-Item rows into one.

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

The exact current whitelist should live in private reviewed evidence/config or an approved internal repository.

Do not:
- auto-publish metadata objects;
- broaden the OData surface "just in case";
- change publication from application runtime.

Before write enablement, review the published surface again and remove anything not required.

## Metadata drift

The intended safety model is:

```text
fresh metadata
→ compare with reviewed mapping/baseline
→ unchanged: continue
→ changed: block write and investigate
```

Rules:
- no guessed mappings;
- no automatic baseline acceptance;
- read-only discovery may continue where safe;
- production mutation must stop on relevant schema drift.

If the project keeps a schema baseline in Git, it must be sanitized and approved for the repository's visibility.
Otherwise keep the raw baseline in private storage and commit only the minimal reviewed contract required by code/tests.

## LLM boundary

OpenAI is used to understand natural-language intent.

Do not send bulk FirstBit data to the LLM.

The LLM must not receive:
- full customer catalog;
- full invoice history;
- bank-account catalog;
- GL chart;
- tax-registration dump;
- OData metadata;
- FirstBit credentials.

Resolution of Company, Contract, Item, VAT, GL and historical basis is deterministic application/provider work after language parsing.

## Current safe rollout

Current allowed production scope:

```text
Telegram / local command
→ language parsing
→ real FirstBit GET
→ Company resolution
→ Contract resolution
→ historical bookkeeping basis
→ real read-only preview
```

Current forbidden production scope:

```text
create
update
post
unpost
delete
change OData publication
change FirstBit configuration
```

Do not enable real write merely because read-only resolution succeeds.

## Write prerequisites

Before the first real draft creation, the project must separately prove:
- least-privilege integration-user permissions;
- exact create payload semantics;
- which FirstBit defaults/business logic run through Standard OData;
- durable operation identity;
- atomic uniqueness / duplicate prevention;
- stale-basis protection;
- lost-response reconciliation;
- restart-safe recovery;
- controlled draft-only test;
- later, separate posting test;
- later, separate standard-PDF retrieval test.

## How Codex should use this document

For ordinary application changes, Codex does not need to read raw FirstBit evidence.

For FirstBit adapter work:

1. read `AGENTS.md`;
2. read `docs/ARCHITECTURE.md`, `docs/SECURITY.md`, `docs/onec-contract.md`;
3. read this document;
4. inspect current code/tests;
5. only then inspect the minimum relevant file under `.local/firstbit/`;
6. update typed models/mapping/tests from evidence;
7. never copy raw production payloads into committed fixtures;
8. report exactly which private evidence was used.

The private evidence is supporting evidence, not application configuration and not runtime storage.

## Known unknowns

Still not proven:
- direct production create behavior;
- automatic defaults during OData create;
- production posting contract;
- standard PDF retrieval contract;
- durable FirstBit-side idempotency mechanism;
- restart-safe application operation state;
- final PaymentTermsVersion selection;
- complete cross-currency behavior.

Treat these as open engineering questions, not missing values to guess.
