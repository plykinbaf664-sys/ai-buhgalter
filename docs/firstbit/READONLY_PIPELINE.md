# FirstBit read-only adapter

Implemented in `app/firstbit.py`, selected by `APP_MODE=firstbit_readonly`; default factory mode remains mock. `is_fake=False`, `preview_only=True`. Production prepare/refresh and Telegram delivery have recorded live evidence; that is not write readiness or current uptime. Dated results: [VERIFICATION](../VERIFICATION.md). Hosting: [SERVER_DEPLOYMENT](../SERVER_DEPLOYMENT.md).

## Supported flow and source boundaries

User text/voice -> grounded command/local draft -> company identity -> contract -> active services -> posted historical sources -> verified financial lines/provenance -> historical InvoicePreview -> edit/cancel/fresh verification. Real AI never receives provider catalogs/rows/names/IDs/prices: it receives the original user input, empty draft and boolean field availability.

Company discovery/approximate selection is owned by [COMPANY_SEARCH](COMPANY_SEARCH.md). Catalog-wide Service discovery, initial user money, default service inference and per-line historical composition are owned by [INITIAL_REQUESTS](INITIAL_REQUESTS.md). Subsequent edits are owned by [PREVIEW_REVISIONS](PREVIEW_REVISIONS.md). The real reader is not restricted to a smoke client or only bookkeeping.

Contract: re-read the default reference and validate nondeleted/active/owner. A missing/deleted default or owner mismatch blocks; it is not silently replaced. An empty default reference or an inactive otherwise valid default allows a bounded owner lookup, which must return exactly one active contract.

History: only `Posted=true`, `DeletionMark=false`, selected Company+Contract, strictly before invoice date at midnight. Query the latest **30** by `Date desc,Ref_Key desc`; previous_month additionally bounds the prior calendar month. This is a supported search window, not proof of the absence of older history. No arbitrary nextLink is followed. Ties at the newest matching source timestamp block; repeated lines stay separate. Multiple services can use separate sources under the financial/source policy above.

Supported historical arithmetic: AmountVATIn=false, zero discounts/markups, positive bounded quantity, actual VAT/UOM refs, exact quantity/price/net/VAT/gross and header-total agreement. Included VAT, discounts, calculated/contradictory tax flags or unsupported currency fail closed. No fixed 5% default and no current ItemPrices lookup. An explicit per-line tax override can resolve a verified catalog profile; legacy whole-command tax constraints cannot invent a profile or silently contradict history.

## Historical provenance and supplier review

The preview is explicitly a historical proposal, not a create payload. `HistoricalProposal` retains primary source/contract/entity and `sources`; each composed line carries source ID/LineNumber. Source price/quantity/VAT are not perpetual tariffs. New-document bank/payment/supply/contact/amount-in-words and issuer-tax-registration/GL defaults are not inferred. Optional missing preview fields are allowed only for the marked historical proposal; missing line financial facts still block.

Both historical and current-contract entities are independently checked. If they differ, Bot requires an expiring, user-scoped historical-source review before presentation, with a fresh read and identity/snapshot checks. This does not choose or approve the new-document issuer. Flow details: [SYSTEM_MAP](../SYSTEM_MAP.md).

Basis identity hashes endpoint/issuer/client/contract plus service period, or invoice date when no period. Revision hashes sources, contract and preview; operation ID excludes revision. Correlation is not durable production idempotency. `BillingBasis` remains key/client_id/revision/preview, with provenance in the preview.

Confirmation refreshes basis and stops; it does not call execute or authoritative operation lookup. `read_operation` returns unknown. Service independently rejects historical/manual/preview-only execution; adapter ensure_draft/ensure_posted/get_pdf always reject. No successful preview can enable writes.

## Exact consumed EntitySets/properties

The table below describes runtime consumption, unlike the broader research snapshot. `$metadata` is an additional GET. Embedded Inventory is a collection, not a separately fetched endpoint.

| EntitySet | Consumed fields |
|---|---|
| `Catalog_Companies` | `Ref_Key,DeletionMark,IsFolder,Inactive,Description,DescriptionFull,ContractByDefault_Key,TRN` |
| `Catalog_CompanyContracts` | `Ref_Key,DeletionMark,Owner_Key,Inactive,Description,Entity_Key,AccountsCurrency_Key` |
| `Catalog_Items` | `Ref_Key,DeletionMark,IsFolder,Inactive,Description,ItemType` (`Service`), `Code` |
| `Catalog_Entities` | `Ref_Key,DeletionMark,Description,DescriptionFull` |
| `Catalog_Currencies` | `Ref_Key,DeletionMark,Code,Description`; numeric ISO `784/840/978/826/643` maps to AED/USD/EUR/GBP/RUB |
| `Catalog_VATRates` | `Ref_Key,DeletionMark,Description,Rate,Exempt,Export,OutOfScope,Calculated` |
| `Catalog_UOMClassifier`, `Catalog_UOM` | `Ref_Key,DeletionMark,Description`; selected via validated polymorphic UOM type |
| `Document_InventoryExpense` | `Ref_Key,DeletionMark,Number,Date,Posted,Company_Key,Contract_Key,Entity_Key,DocumentCurrency_Key,AmountVATIn,DocumentAmount,Inventory` |
| Embedded `Inventory` | `LineNumber,Item_Key,Content,Quantity,UnitOfMeasure,UnitOfMeasure_Type,Price,Amount,AmountTotal,VATRate_Key,VATAmount,DiscountMarkupRate,DiscountMarkupAmount,AutomaticDiscountRate,AutomaticDiscountAmount` |


No bank/GL/payment-term/price-register/PDF/write endpoints are used. `Catalog_Items.Code` was verified as Edm.String for service-choice display. The numeric ISO currency mapping currently recognizes AED/USD/EUR/GBP/RUB; other codes block instead of converting currency.

## Transport and schema safety

- Fixed internal set allowlist, explicit select/filter/top and typed UUID references. Company words never enter a query; service Description and named VAT queries are escaped literals in fixed filters, not executable user OData.
- Verified HTTPS/Basic Auth with dedicated reader, redirects and ambient proxies disabled. One extra identical GET is permitted only after transport/timeout, not HTTP status/auth/schema/financial/cancellation errors. 12s per bounded GET attempt; 1 MB business / 8 MB metadata body limits. Service calls have independent deadlines.
- Fresh consumed schema is checked on resolve_client/resolve_service/resolve_basis: required sets, property types and embedded Inventory. Numeric Double/Decimal enter exact Decimal validation, Int64 LineNumber string has a field-specific decoder. DTD/entities and malformed JSON/envelopes block.
- Required-field/type mismatch blocks reads immediately. Extra unused fields are not a drift failure. This is a consumed-field guard, not a full reviewed write-schema/whitelist/permission baseline.
- Name-only directories use fixed 200-row skip/order pages within the 5000 safety bound; completion requires a final short page. Saturation, repeated page IDs or unexpected pagination fails closed. The code does not prove a transactionally consistent snapshot under arbitrary concurrent catalog edits.
- Live wire evidence: spaces require `%20`; tolower and DescriptionFull equality are unsupported. Exact provider facts and scope: [INTEGRATION_EVIDENCE](FIRSTBIT_INTEGRATION_EVIDENCE.md).

## Configuration

Template: root `.env.example`. Ordinary factory loads process ENV only. Server protected EnvironmentFile and local literal loader are different mechanisms; `.env.local` is not deployed as source. Values and private metadata are never committed. For setup:

| Variable | Source / action |
|---|---|
| `APP_MODE=firstbit_readonly` | Select after all FirstBit fields are filled; existing default remains mock. |
| `ONEC_WRITE_ENABLED=false` | Must remain false; true is rejected in both supported modes. |
| `FAKE_ONEC_FAULT=disabled` | Required in read-only mode. |
| `FIRSTBIT_BASE_URL` | Ask FirstBit/1C administrator for the published HTTPS Standard OData root, e.g. `https://erp.example.invalid/base/odata/standard.odata/`. Include the final slash. No credentials/query/fragment in URL. |
| `FIRSTBIT_USERNAME` | Dedicated integration reader provisioned by owner/admin. No admin/personal identity. |
| `FIRSTBIT_PASSWORD` | Password for that account through your private secret channel; fill locally, never in chat, docs, CLI args or Git. Runtime uses `SecretStr`. |
| `FIRSTBIT_READONLY_ACCOUNT=true` | Set only after owner verifies actual read-only, least-privilege server rights. This is an explicit attestation, not a programmatic proof of permissions. Never test privileges by attempting a write. |
| `FIRSTBIT_BOOKKEEPING_ITEM_ID` | Ask owner/admin for verified nonzero `Ref_Key` of the exact `Accounting and bookkeeping services` Service record. It is a UUID, not catalog Code or description. |
| `FIRSTBIT_CLIENT_ALIASES={}` | Optional reviewed JSON `{ "user spelling": "Company Ref_Key UUID" }`; leave `{}` initially. No fuzzy auto-selection. |
| `FIRSTBIT_SMOKE_CLIENT` | Exact current Company `Description`/`DescriptionFull`, or a reviewed alias. Private local value used only by smoke, never a client allowlist for Telegram. |
| `FIRSTBIT_SMOKE_INVOICE_DATE` | Explicit `YYYY-MM-DD` after an existing posted bookkeeping invoice for that client/contract. Used only for smoke. |

To obtain the service UUID, the administrator can inspect the service record or perform a dedicated GET after checking live metadata, using this **fixed** query with Basic Auth held by their approved client (never in URL):

```text
Catalog_Items
$select=Ref_Key,Description,ItemType,DeletionMark,IsFolder,Inactive
$filter=Description eq 'Accounting and bookkeeping services' and DeletionMark eq false and IsFolder eq false and Inactive eq false
$top=2
```

Accept exactly one result with `ItemType=Service`; otherwise owner must identify the correct record. Do not choose an ID from a different database or copy fixture UUIDs. Ask administrator to verify GET access to the table above, valid TLS chain, exact item and contract ownership. The application does not publish objects or modify permissions. If a required set/property is absent, stop and review fresh `$metadata`; do not rename fields until confirmed.

Existing Telegram fields come from BotFather (token), independent random secret (webhook secret), and the authorized user's numeric ID (allowlist). Existing OpenAI key comes from the account's API project; `AI_MODE=openai` enables natural language and voice, with current model-selection/STT settings. No additional OpenAI permissions for FirstBit are needed.

Optional local `.env.local` loader in PowerShell (literal values, no `Invoke-Expression`; do not print the resulting ENV). Use unquoted `KEY=value` lines; no multiline values:

```powershell
Get-Content -LiteralPath .env.local -Encoding UTF8 | ForEach-Object {
    if ($_ -match '^([A-Z][A-Z0-9_]*)=(.*)$') {
        [Environment]::SetEnvironmentVariable($matches[1], $matches[2], 'Process')
    }
}
```


## Verification and remaining work

Offline application smoke: `python scripts/firstbit_readonly_smoke.py`; actual GET-only prepare/refresh: add `--live` after loading the documented private ENV. Optional `--save-preview` writes only under ignored `.local/firstbit/`. Exact commands, proof limits and latest results live once in [VERIFICATION](../VERIFICATION.md).

Missing config/TLS/auth/schema/history/financial evidence produces a controlled blocker, never fake fallback or a guessed default. All remaining write milestones are tracked in [PROJECT_CONTEXT](../PROJECT_CONTEXT.md), with the admission gate in [SECURITY](../SECURITY.md). Inspect targeted private metadata members, then full index and fresh metadata/GET for missing facts; do not load or commit a full bundle by default. Coverage: [METADATA_COVERAGE](FIRSTBIT_METADATA_COVERAGE.md).
