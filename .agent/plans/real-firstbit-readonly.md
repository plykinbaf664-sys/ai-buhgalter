# FirstBit production read-only preview

> Historical execution record, closed for current rollout. Statements, counts and pending observations below describe that checkpoint, not current availability or present requirements. Current behavior: [docs/firstbit/READONLY_PIPELINE.md](../../docs/firstbit/READONLY_PIPELINE.md); current verification: [VERIFICATION](../../docs/VERIFICATION.md).

## Goal and scope
Telegram text/voice uses the existing interpreter, service, typed preview and edit/cancel flow with a new GET-only FirstBit provider. Stop at preview verification. No draft, posting, PDF, publication changes or persistence work.

## Repository and external evidence
Read `AGENTS.md`, context router, architecture/security/work style, verification, `onec-contract.md`, existing domain/service/bot/main/config/HTTP code. Actual evidence filenames are `docs/firstbit/FIRSTBIT_INTEGRATION_EVIDENCE.md` and `FIRSTBIT_METADATA_COVERAGE.md`. Inspect only selected members in the private metadata bundle; missing exact OData facts require full index then fresh metadata/GET or a blocker.

## Changes and domain impact
Add `app/firstbit.py` with dedicated typed ENV settings, bounded HTTPS GET transport and typed provider responses. Add `APP_MODE=firstbit_readonly` wiring and lifecycle ownership in `main.py`. Retain BillingBasis shape; extend preview only where verified historical proposal semantics need it. Preserve operation ID/revision/digest and fake behavior. Add explicit provenance and a read-only confirmation path that refreshes preview without claiming any financial mutation. Keep unknown reconciliation unknown.

## Provider/security contract
Only reviewed Catalog Companies, CompanyContracts, Items, Entities, Currencies, VATRates, BankAccounts, payment/UOM support if evidenced, and Document InventoryExpense. Record exact consumed fields in implementation documentation after targeted inspection. Query templates are internal constants; free text is escaped data, stable refs validated UUIDs. Explicit select/top, bounded pagination/history; never follow provider next links. Fresh metadata must validate consumed properties/types before business reads. Schema mismatch, ambiguous records, missing financial facts, unsupported arithmetic and unsafe state fail closed.

Dedicated least-privilege integration identity only; ENV/SecretStr credentials; HTTPS with certificate verification, no redirects/proxies/retries/wire logs. No production records sent to AI: sanitize production-derived draft context before interpreter calls. No runtime metadata/business dumps in Git; ignore all `.local/`. No mutation transport API; mutation/PDF protocol methods fail unconditionally, even with misconfigured caller. No rollback needed; reconciliation remains unknown until future durable operation design. Disable by reverting APP_MODE to mock or stopping the process. Account privilege attestation is configuration, not a proof of server permissions.

## Failure/recovery and rollout
Timeout/401/403/malformed/oversized/schema drift -> safe provider failure; no automatic retries. No usable contract/history or unsupported financial semantics -> controlled blocker. Changes to historical source/preview -> new revision and renewed confirmation. Read-only confirmation verifies preview only and never enters write/recovery state machine. Existing fake recovery unchanged.

## Verification
Focused real adapter/security/domain/webhook tests -> full pytest -> existing demo/smoke -> application-level FirstBit smoke using synthetic GET fixtures. Live smoke only if dedicated ENV credentials available; never enable write. Report simulated versus live external services explicitly.

## Progress
- [x] Context/code/evidence discovery; `.local/` ignored.
- [x] Targeted metadata mapping and implementation.
- [x] Focused/full regression and application smoke.
- [x] Live GET-only smoke or explicit credential blocker: owner confirmed no credentials; deferred live execution until ENV is filled.
- [x] Update context structure/index and results.

## Initial unknowns
FirstBit credentials are absent from current process ENV and `.env.local` key names. Exact OData wire schema and bank/contact/payment/VAT semantics require targeted inspection; do not invent defaults to complete a preview.

## Decisions and discoveries

- Actual evidence filenames have `FIRSTBIT_` prefix; routers now use existing names.
- Inspected selected bundle members for Companies/Contracts/Entities/Items/Currencies/VAT/UOM/InventoryExpense and supporting bank/payment/VAT sources, not the whole bundle in model context. Full index confirms `Catalog.Banks`; no detailed bank/SWIFT evidence or credentials, so those defaults are unresolved rather than guessed.
- Historical proposal is a deliberate public `InvoicePreview` extension with typed provenance. BillingBasis remains unchanged. Optional new-document fields are allowed only for non-executable historical proposals; full fake previews retain completeness requirements. This is not a complete draft payload.
- Supported historical arithmetic is VAT excluded, no discounts, exact source/net/tax/gross agreement. Unsupported variants fail closed. Quantity edits use verified simple arithmetic; all original service rows remain separate.
- Fresh consumed-field schema validation precedes business resolution; exact live wire compatibility still requires credentials. Synthetic schemas are independent fixtures, never production dumps.
- Verify-only refresh never claims not_started reconciliation. Unknown operation lookup stays unknown, while a failed proposal refresh does not invent a financial recovery operation.
- `.env.local` gained blank FIRSTBIT fields only; existing secrets/settings were preserved. Full `.local/` ignored, with no tracked files under it.

## Completed checkpoint result

The GET-only provider, typed historical proposal, consumed-schema guard and verify-only confirmation were implemented. Original synthetic regression and offline smoke passed; subsequent dedicated-reader GET prepare/refresh also passed. Intermediate credential/encoding/search investigations are archived privately instead of retained as alternative implementation instructions. Current provider facts/mapping: READONLY_PIPELINE and FIRSTBIT_INTEGRATION_EVIDENCE; current proof scope: VERIFICATION.

BillingBasis stayed small; provenance is in the preview. No real create/post/PDF was enabled. Later generic-service, per-line-source, initial-money and Linux-hosting extensions supersede this original bookkeeping rollout without changing its read-only boundary. This historical record is not the current search algorithm, configuration procedure or milestone backlog.
