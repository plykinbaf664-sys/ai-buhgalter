# FirstBit Metadata Coverage Report

Voice name search reuses existing Catalog.Company name/ref/active fields; no new export or full bundle load. Runtime GET verified fixed paging (`$top/$skip`, Ref_Key ordering) and local name comparison. Name-only transient pages do not establish financial defaults. See [company search](COMPANY_SEARCH.md).

Implementation and live-validation status: [READONLY_PIPELINE.md](READONLY_PIPELINE.md). Coverage describes the private configuration snapshot; the application checks consumed live schema at runtime. Live prepare/refresh passes on the reviewed cases after confirming Double numeric fields and Int64 string serialization. An additional historical/current-contract supplier mismatch uses the same Entity references, explicit user review and non-executable provenance; targeted bundle members and fresh GETs suffice, with no guessed provider fields. This does not prove all financial variants or write compatibility.

## Result

The metadata bundle was validated against the current published MVP OData whitelist and the current read-only invoice-resolution flow.

- Full FirstBit configuration index: **1267 objects**
- Detailed metadata exports: **38 objects**
- Published MVP OData whitelist: **33 objects**
- Published objects with full detailed metadata: **32 / 33**
- Detail exports reported `not_found=[]` in every source export.
- Detail exports reported no unresolved object errors.

## Only published object without full detail export

```text
ChartOfAccounts.GeneralChartOfAccounts
```

This is **not a blocker for the current read-only Telegram → FirstBit → InvoicePreview milestone** because the current preview does not need to resolve GL account display metadata. Relevant GL references/default sources are already detailed.

It **should be exported in detail before write-enablement if the write adapter needs to validate or resolve GL account semantics/names.**

## Current read-only flow coverage

- [x] `Catalog.Companies`
- [x] `Catalog.CompanyContracts`
- [x] `Catalog.Entities`
- [x] `Catalog.Items`
- [x] `Catalog.Currencies`
- [x] `Catalog.VATRates`
- [x] `Catalog.SalesPaymentTerms`
- [x] `Catalog.SalesPaymentTermsVersions`
- [x] `Catalog.BankAccounts`
- [x] `Catalog.UOMClassifier`
- [x] `Catalog.UOM`
- [x] `Catalog.BaseUnits`
- [x] `Catalog.IncomeItems`
- [x] `InformationRegister.ItemPrices`
- [x] `InformationRegister.ItemVATRates`
- [x] `InformationRegister.VATRateParameters`
- [x] `InformationRegister.VATTaxationParameters`
- [x] `InformationRegister.EntityRegistrationsWithTaxAuthorityAsVATPayer`
- [x] `InformationRegister.ItemsGLAccounts`
- [x] `InformationRegister.CompaniesGLAccounts`
- [x] `InformationRegister.DefaultGLAccounts`
- [x] `InformationRegister.AccountsReceivablePaymentTermsVersions`
- [x] `Enum.ItemTypes`
- [x] `Enum.VATTaxationTypes`
- [x] `Enum.TransactionTypesSalesInvoice`
- [x] `Document.InventoryExpense`

### Missing detailed metadata for current read-only flow

None.

## What this proves

For the currently planned read-only pipeline, every metadata object identified as necessary for:

- company resolution;
- contract resolution;
- service/item resolution;
- historical invoice lookup;
- VAT/currency/UOM support;
- bank/payment-term support;
- relevant GL/default-reference support;
- creation of a real read-only preview

has a detailed metadata export in the bundle.

## What this does NOT prove

The bundle is not a guarantee that no new object will ever be needed.

A future requirement can reveal:
- a FirstBit business rule stored in another object;
- a new field exposed only through Standard OData `$metadata`;
- a write/post/PDF dependency not needed by read-only resolution.

If this happens, the correct behavior is:

```text
need new field/object
→ check full index
→ inspect fresh $metadata / GET
→ export only the missing object's details if needed
→ update mapping/tests/bundle
→ continue
```

Do not guess.

## Freshness rule

This bundle is a snapshot. For exact OData implementation, fresh production `$metadata` and read-only runtime responses outrank this file.

The adapter should fail closed if the live schema contradicts the reviewed mapping.

## Readiness conclusion

**Ready for implementation of the current production READ-ONLY pipeline.**

**Not yet sufficient evidence to enable production writes.**

Before write enablement, separately close:
- detailed `GeneralChartOfAccounts` if required;
- exact create semantics;
- idempotency/uniqueness;
- posting;
- PDF retrieval;
- durable restart recovery;
- metadata drift guard.
