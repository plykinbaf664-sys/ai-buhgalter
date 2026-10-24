# FirstBit production read-only preview

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

## Result

Implementation, synthetic application smoke and regression are complete. Live GET smoke is BLOCKED before network access because credentials/client/date are not configured, as confirmed by owner. The owner will fill ENV later using `docs/firstbit/READONLY_PIPELINE.md`. No production FirstBit contact, no production side effects, no create/post/PDF. Final verification commands/results are recorded in `docs/VERIFICATION.md`.

Final results: 330 tests passed (267 existing + 63 new); synthetic application smoke PASS (61 GETs, 3 mocked AI requests, zero mutations/PDFs); existing demo and HTTP smoke PASS; pip check, compileall and diff whitespace checks PASS. Production-derived files remain ignored and untracked.

## Live validation follow-up

Owner supplied credentials and explicitly confirmed read-only account rights. Set the attestation true; removed accidental outer whitespace in the login. Initial auth failed 401, then GET metadata succeeded 200. Private live metadata is saved only in ignored `.local/firstbit/metadata/live-standard-odata-metadata.xml` (234691 bytes). Targeted schema inspection proves numeric VAT/document/line fields use Edm.Double, unlike the synthetic Edm.Decimal fixture. Extend the reviewed numeric wire guard to support those two finite numeric representations while preserving exact Decimal/domain/arithmetic validation; unknown field types still block. Add regression proving alternate clients are independent of FIRSTBIT_SMOKE_CLIENT. Continue only GET, stop before writes. Smoke date is malformed in local ENV; use today's date for the read-only verification and document this assumption.

Bounded live GET comparison proved the endpoint mishandles form-encoded `+` in filter spaces: `DeletionMark eq false` with HTTPX QueryParams returned a deleted row, while RFC3986 `%20` returned a nondeleted row (both selected two fields with top=1). Use structured internal params encoded with `urlencode(..., quote_via=quote)`; retain literal escaping and UUID validation. Add an injection/encoding regression before continuing business resolution. No mutation was sent.

The next GET returned HTTP 400 explicitly rejecting the `tolower` function. Replace it with exact Description/DescriptionFull equality preserving input spelling, followed by existing normalized local equality/ambiguity validation. No fuzzy match or catalog scan is introduced.

Fresh GET then proved equality on unbounded DescriptionFull is rejected (HTTP 500, incompatible/unbounded comparison). Targeted bounded GETs independently verified Description equality and substringof on DescriptionFull both work and return one locally exact candidate. Use bounded Description equality OR DescriptionFull substring candidates, and still select ONLY normalized exact names locally. Substring matches alone never authorize a client; 20-candidate saturation blocks resolution.

Company, contract and service resolved through live GET. All 79 returned historical rows serialize Edm.Int64 LineNumber as canonical positive digit strings. Add a field-specific OData Int64 decoder (not general coercion), retaining strict integer bounds and rejecting booleans/fractional/signed strings. No financial amount coercion/default guessing is introduced.

## Latest result after live follow-up

Live prepare/refresh PASS on one client: company, contract, item, posted history, VAT/UOM/entity/currency resolve into a one-line proposal and an unchanged refreshed snapshot. Standalone `--live --save-preview` PASS; private formatted review saved to ignored `.local/firstbit/readonly-preview.txt`. Application factory startup/health using actual local ENV returns 200/firstbit_readonly. Local mode switched from mock to firstbit_readonly; write flag remains false; invalid smoke date corrected to today's ISO date. Owner-approved attestation true; password preserved.

339 tests PASS (267 original + 72 FirstBit/security/application), offline application smoke PASS, compileall and whitespace checks PASS. A dedicated two-client test proves FIRSTBIT_SMOKE_CLIENT is only a script input: other clients resolve their own contract/history/amounts and operation identity. Full-name candidate searches still require local exact matches. No production POST/PATCH/DELETE or create/post/PDF; no live Telegram/OpenAI calls. Stop at successful historical preview; draft-write remains a separate stage.
