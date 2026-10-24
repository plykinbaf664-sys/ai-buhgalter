# FirstBit read-only historical preview

## Status and navigation

Implemented: `APP_MODE=firstbit_readonly`, `app/firstbit.py`, existing service/bot flow and deterministic application smoke. After owner supplied credentials and confirmed read-only account rights, **live FirstBit GET prepare/refresh passed**, producing a one-line historical preview. Live scope is one client and supported arithmetic; real Telegram/OpenAI were not contacted in this check. No create/post/PDF is enabled.

Subsequent Telegram/OpenAI runtime checks are recorded in [LIVE_DEMO.md](LIVE_DEMO.md): actual STT/LLM pass, natural-language OpenAI -> FirstBit -> preview delivered to Telegram. An actual human voice passed STT and reached client resolution; duplicate identity and absent posted history prevented that client's preview. Candidate buttons are deployed; owner-selected option 1 was checked separately through an application-level real GET-only rehearsal, with a missing-basis blocker. Do not claim a complete human voice preview from these partial checks.

Start with [integration evidence](FIRSTBIT_INTEGRATION_EVIDENCE.md), [coverage](FIRSTBIT_METADATA_COVERAGE.md), [ExecPlan](../../.agent/plans/real-firstbit-readonly.md). Private evidence: `.local/firstbit/metadata/firstbit_metadata_bundle.json`; targeted members only, never required at application runtime.

## Application flow

```text
Telegram text / voice download -> existing STT and controlled interpreter
-> InvoiceCommand -> InvoiceService.prepare
-> fresh GET $metadata, exact client / reviewed alias / explicit candidate button
-> default contract (owner/active checks), otherwise unique active fallback
-> verified Service item -> latest matching posted invoice before requested date
-> if source issuer differs from current contract: explicit historical-supplier review + fresh GET
-> all bookkeeping rows, in LineNumber order -> typed historical InvoicePreview
-> Telegram review / line quantity or date edit / cancel
-> verify button -> fresh GET resolution -> new preview if revision changed
-> unchanged proposal: acknowledge verification; stop
```

The interpreter receives the user's message/audio, an **empty draft context** and boolean local-field availability in real mode. Those booleans prevent redundant questions about a client/date already held locally. Production-derived draft rows/names/quantities/references/TRNs remain local. Deterministic draft merging still uses local state. No catalog/history/metadata/bank/GL payload goes to OpenAI.

The real provider is `is_fake=False, preview_only=True`. `read_operation` returns `unknown`: no authoritative operation correlation is claimed. Preview verification uses a separate read-only refresh branch, without calling reconciliation or execution. Unknown financial-operation states retain their existing write/recovery safeguards. `execute()` rejects historical proposals and preview-only providers, even if a caller passes `allow_real_writes=True`. Protocol mutation/PDF methods always raise `WritesDisabled`; transport exposes GET only. A successful preview never enables writes.

## Proposal scope and fail-closed behavior

Historical prices/quantity/VAT are proposals, not current catalog tariffs. `ItemPrices` is never called. All matching same-item rows remain distinct; one explicit service without quantity expands to all historical matching rows. Replacing several rows with one quantity is rejected. Quantity edits preserve each row's verified price and tax, recalculate using the already validated simple arithmetic, and show a new preview. Compact Telegram output shows source invoice number/date and contract name; full source/contract/entity IDs remain in typed provenance/digests. Source Content is preserved per row.

### Historical supplier versus current contract

Live GET exposed a valid posted source whose issuer differs from the current contract Entity, while Company/Contract/currency agree. Both Entity records must independently exist and be nondeleted; unknown/deleted entities still block. The source's actual issuer is recorded as historical fact, and paired `HistoricalProposal.contract_entity_id/contract_entity_name` retain the current-contract mismatch. Bot withholds preview until the user explicitly chooses to view the historical sample. The token expires after five minutes, is per-user, is revoked by new input/cancel/restart, and refreshes the entire proposal before acceptance. Financial identity drift stops the old basis; changed price/revision requires renewed review. A reviewed client+contract+entity pair survives ordinary date/quantity edits locally, but never becomes an ENV alias or new-document accounting default. The final preview explicitly says the supplier of a new document is unresolved. `execute()` remains blocked independently of caller permission.

Supported Russian bookkeeping synonyms are controlled aliases of the configured verified item, not prices or arbitrary service mappings. Other services remain blocked. Low-confidence STT thresholds are unchanged; the bot shows its recognized user text in the same private chat for correction and does not send it into resolution/LLM after confidence rejection.

Supported arithmetic is deliberately narrow: **AmountVATIn=false**, zero manual/automatic discounts/markups, positive quantities, known VAT profile, and exact agreement between quantity × price, net, tax and gross amounts. Positive, zero, exempt and out-of-scope profiles come from VAT fields; no fixed 5% assumption. Included VAT, discounts, calculated VAT rates, contradictory flags, missing references, unsupported currency, invalid amounts, or schema mismatch block preview. A requested tax change is accepted only if already consistent with every historical line; named-profile overrides are blocked.

Bounded history: the newest 30 posted/nondeleted invoices before invoice date for exactly Company+Contract, ordered `Date desc,Ref_Key desc`; skip invoices without the item. `previous_month` restricts to the previous calendar month. Equal timestamps among newest matching sources are ambiguous and block selection. Missing history or too many records is a controlled blocker. No nextLink is followed; partial/paginated envelopes block resolution. `$top` limits, response byte caps, timeouts, no retries.

This is a typed **historical proposal**, not a complete new-document payload. `HistoricalProposal` marks it as non-executable. `BillingBasis` schema remains unchanged. New-document bank/payment defaults, issuer tax registration, supply date, contacts and amount in words are not invented or copied from old defaults. The corresponding preview fields may be `None` only for historical proposals; Telegram explicitly states unresolved fields and that writing is blocked. Ordinary fake/document previews still require complete details. Missing financial **line values** always block the proposal; unresolved **new-document defaults** remain explicit blockers before any draft. Historical GL/payment-version refs are never promoted to defaults.

Basis key includes endpoint/issuer/client/contract and service-period identity (or invoice date without period); revision hashes source/contract/preview; price/quantity changes preserve operation ID. This is correlation only, not production idempotency. State remains process-local; run one worker.

`FIRSTBIT_SMOKE_CLIENT` is used **only** by the smoke script, never by the application provider. Telegram supplies the client for each request. Any uniquely resolved active client can use this flow when their own contract and supported bookkeeping history exist. A new client without a verified basis is a controlled blocker; another client's prices/history are never reused. A two-client regression proves distinct contract/source/amount/operation identity even when smoke ENV names the first client.

## Verified live wire behavior

- Numeric VAT/header/line fields use `Edm.Double`; `Edm.Decimal` remains supported for compatible providers/fixtures. Both still enter bounded Decimal models and exact money/VAT arithmetic checks; nonfinite/inconsistent values fail.
- `Edm.Int64` LineNumber arrives as a positive digit string. A field-specific decoder validates canonical digits and the signed Int64 upper bound; booleans, fractional and signed strings are rejected.
- Query spaces must use RFC3986 `%20`. Live form-encoded `+` produced rows outside the filter. Params are still built from fixed internal templates and encoded with `urlencode(..., quote_via=quote)`; no raw user query syntax is accepted.
- `tolower` is explicitly unsupported by the live endpoint. Direct equality on unbounded `DescriptionFull` also fails. Client search now compares fresh bounded name-only pages locally (200/page, maximum 5000), with fixed skip/order/filter. Unique literal matches ignore case/spacing/punctuation; voice/transliteration/typo/partial matches only suggest buttons. No client query text is sent in OData. Live case probes themselves were case-insensitive; the change also removes whole-phrase spelling dependence. See [company search](COMPANY_SEARCH.md).
- Private current schema: `.local/firstbit/metadata/live-standard-odata-metadata.xml`. Private formatted review: `.local/firstbit/readonly-preview.txt`. These contain production evidence and remain ignored; never copy them into Git/AI context.

## Objects and exact consumed fields

Existing previews support [explicit user price/VAT/description revisions](PREVIEW_REVISIONS.md). These reuse the VAT catalog and historical LineNumber already consumed below; they do not enable writes or invent tariff/accounting defaults.

Client selection uses the same consumed Company fields; no additional metadata properties are assumed. `ClientChoiceRequired` carries 1–19 unique typed candidates. Bot shows full name, stable record ID and TRN when present, with numbered buttons/cancel. Original command and token are per-user and expire after five minutes. Any new text/voice invalidates those buttons; IDs never come from AI or raw callbacks. Selected ID is checked against fresh active candidates for the original query before resolving that client's contract/history. Selection persists in the draft for follow-up edits, not in global ENV aliases. Missing posted history is a separate explicit blocker; no price/default is supplied to bypass it.

All business calls use fixed EntitySets, `$format=json`, explicit `$select`, internal filter templates and bounded `$top`. UUID references are typed. Company text enters only a properly quoted string literal (`'` doubles), never OData syntax; aliases go directly to typed stable refs.

| EntitySet | Consumed fields |
|---|---|
| `Catalog_Companies` | `Ref_Key,DeletionMark,IsFolder,Inactive,Description,DescriptionFull,ContractByDefault_Key,TRN` |
| `Catalog_CompanyContracts` | `Ref_Key,DeletionMark,Owner_Key,Inactive,Description,Entity_Key,AccountsCurrency_Key` |
| `Catalog_Items` | `Ref_Key,DeletionMark,IsFolder,Inactive,Description,ItemType` (`Service`) |
| `Catalog_Entities` | `Ref_Key,DeletionMark,Description,DescriptionFull` |
| `Catalog_Currencies` | `Ref_Key,DeletionMark,Code,Description`; numeric ISO `784/840/978/826/643` maps to AED/USD/EUR/GBP/RUB |
| `Catalog_VATRates` | `Ref_Key,DeletionMark,Description,Rate,Exempt,Export,OutOfScope,Calculated` |
| `Catalog_UOMClassifier`, `Catalog_UOM` | `Ref_Key,DeletionMark,Description`; selected via validated polymorphic UOM type |
| `Document_InventoryExpense` | `Ref_Key,DeletionMark,Number,Date,Posted,Company_Key,Contract_Key,Entity_Key,DocumentCurrency_Key,AmountVATIn,DocumentAmount,Inventory` |
| Embedded `Inventory` | `LineNumber,Item_Key,Content,Quantity,UnitOfMeasure,UnitOfMeasure_Type,Price,Amount,AmountTotal,VATRate_Key,VATAmount,DiscountMarkupRate,DiscountMarkupAmount,AutomaticDiscountRate,AutomaticDiscountAmount` |

No bank, GL, payment-term, price-register, metadata-bridge, write or PDF endpoints are used. `$metadata` checks the required sets and consumed property types, including the embedded collection; no raw snapshot is persisted. Unknown wire shape fails closed. This is a minimal consumed-field guard, not the full future reviewed write-baseline drift guard.

## Configuration: what to fill and where to obtain it

Templates are in `.env.example`; the owner has now filled the FirstBit fields in ignored `.env.local`. Local APP_MODE is set to firstbit_readonly, write flag remains false, the read-only attestation is true after owner confirmation, accidental login edge spaces were removed, and invalid smoke date format was replaced with today's ISO date for the check. Neither file is auto-loaded by the application. Values must reach process ENV through your launcher, service manager or the explicit local loader below. Do not commit `.env.local` or `.local/`.

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

## Run and verify

From repository root, using the existing virtualenv:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts/firstbit_readonly_smoke.py
```

Default smoke uses **only synthetic HTTP fixtures**, including Telegram, STT, LLM and FirstBit. It tests the actual app factory/webhook/confirmation paths: text and voice, preserved rows, quantity edit, old-token revocation, refreshed revision, verify-only acknowledgement, cancellation and duplicate update. No external services contacted, no production records, no PDFs.

After filling/importing ENV, run live FirstBit service prepare/refresh (no Telegram or OpenAI calls, no business records printed):

```powershell
.\.venv\Scripts\python.exe scripts/firstbit_readonly_smoke.py --live
# Optional: save private human-readable preview under ignored .local/firstbit/
.\.venv\Scripts\python.exe scripts/firstbit_readonly_smoke.py --live --save-preview
```

Missing config, invalid TLS, 401/403, unexpected OData schema, unsupported historical arithmetic or absent history produce `BLOCKED` and nonzero exit. Output exposes only safe error type; inspect config and this document, without printing raw provider tracebacks. Do not bypass checks to get a passing smoke.

Then start the app with one worker using your existing webhook setup:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000 --no-access-log
```

`/healthz` reports `firstbit_readonly`. In Telegram, name the client (case/spacing/voice variants supported) and invoice date/period; choose a candidate if proposed, then review/edit/cancel. The button says “Проверить preview”. It verifies the proposal again and creates nothing. To disable, stop process or return `APP_MODE=mock`; never enable writes here.

## Remaining gates before controlled draft-write

- Live `$metadata`/GET prepare/refresh has passed on one client. Real Telegram text/voice and other financial/history variants still require their own verification; do not assume all clients' data is equivalent.
- Verify included-VAT/discount arithmetic before expanding supported proposals; unsupported cases currently stop safely.
- Resolve current bank/payment/delivery/supply/tax-registration/GL defaults, authoritative tax applicability and historical price approval for the new invoice. `Catalog.Banks` was found in the full metadata index but has no detailed bundle export; bank/SWIFT semantics remain outside this non-executable proposal and were not guessed.
- Prove exact draft payload/default behavior and dedicated write permissions in a separate ExecPlan/approved target.
- Durable operation identity, atomic uniqueness/freshness, lost-response reconciliation and restart-safe storage; current operation lookup deliberately returns unknown.
- Complete reviewed metadata baseline and required accounting dependencies; separate later posting and standard 1C PDF verification.

No create/post/PDF readiness is claimed by this milestone.
