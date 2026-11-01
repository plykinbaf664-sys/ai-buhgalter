# FirstBit private metadata coverage

## What this snapshot means

The private configuration bundle is discovery evidence, not application configuration or a proof of current production publication. Original coverage review recorded: **1267 indexed objects, 38 detailed exports, 33 published MVP objects, 32/33 with detailed exports**, with empty not_found/error reports. These are snapshot counts, not an assertion that the live database still has that exact surface. Fresh metadata/GET outranks them.

Private location: `.local/firstbit/metadata/firstbit_metadata_bundle.json`; full index and selected detail members are inside that bundle. Do not load all of it for routine flow work. Runtime instead fetches fresh Standard OData metadata and verifies only the consumed contract; [READONLY_PIPELINE](READONLY_PIPELINE.md) owns the exact field table and schema bounds.

## Runtime versus research coverage

| Scope | Objects |
|---|---|
| Actually consumed by reader | Catalog.Companies, CompanyContracts, Entities, Items (including Code), Currencies, VATRates, UOMClassifier, UOM; Document.InventoryExpense and embedded Inventory |
| Exported for investigation, not consumed in current preview | SalesPaymentTerms/Versions, BankAccounts, BaseUnits, IncomeItems; ItemPrices/ItemVATRates/VAT parameter and tax-registration registers; ItemsGLAccounts/CompaniesGLAccounts/DefaultGLAccounts and receivable payment-term versions; relevant enums |
| Newly reviewed detail and fresh publication | Catalog.BusinessActivities, Catalog.ExpenseItems, Document.TaxInvoice, Enum.TransactionTypesTaxInvoice; ChartOfAccounts.GeneralChartOfAccounts detail reviewed |
| Additional index-only future dependency | Catalog.Banks: detailed export/semantics not proven for this flow |

Current consumed objects have detailed discovery coverage; live type checks and actual GET evidence remain necessary. The Code property was separately confirmed in metadata/GET. Full customer/catalog values are unnecessary for a coverage audit and must not enter docs/fixtures.

Bank/payment/GL investigation coverage **does not** prove current accounting defaults, SWIFT/bank semantics, tax applicability, authoritative current tariffs or new-document behavior. The readonly reader does not fetch these sources; the native writer consumes the reviewed subset documented in PRODUCTION_OPERATION, including effective supplier VAT registration. Historical GL/default references do not establish their current meaning. GeneralChartOfAccounts detail is now reviewed; live analytical-reference validation is still mandatory for write admission.

## Missing evidence procedure

Identify the concrete missing field/object -> inspect the full private index -> inspect only its detail -> fresh readonly `$metadata`/GET -> obtain a targeted additional export if necessary -> update reviewed mapping/synthetic tests only when proven. If still unproven, record a blocker. Do not guess names, broaden publication automatically, or treat snapshot coverage as write admission.

Provider findings are owned by [INTEGRATION_EVIDENCE](FIRSTBIT_INTEGRATION_EVIDENCE.md); remaining milestones by [PROJECT_CONTEXT](../PROJECT_CONTEXT.md). A consumed-field read guard exists now; the native write/schema/journal implementation and remaining production proof are owned by [PRODUCTION_OPERATION](PRODUCTION_OPERATION.md).
