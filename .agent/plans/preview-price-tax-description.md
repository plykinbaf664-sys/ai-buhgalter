# Explicit user price, tax and line-description revisions

> Historical execution record, closed for current rollout. Statements, counts and pending observations below describe that checkpoint, not current availability or present requirements. Current behavior: [docs/firstbit/PREVIEW_REVISIONS.md](../../docs/firstbit/PREVIEW_REVISIONS.md); current verification: [VERIFICATION](../../docs/VERIFICATION.md).

## Goal and authorization
Owner explicitly requests price/tax/service-name corrections in the existing read-only preview. This supersedes the prior prohibition on user price changes only for explicit grounded preview edits. Model-invented prices/rates/IDs remain forbidden. FirstBit remains dedicated-reader ENV/SecretStr, TLS verified, GET only, writes false; no create/post/PDF.

## Architecture and contract
Reuse intent -> local draft -> InvoiceCommand -> service.prepare/refresh -> OneC.resolve_basis -> preview/confirmation. Add typed user line overrides (net unit price, display description, requested tax), kept distinct from historical values and shown in provenance. Language model selects source spans only for new financial fields; deterministic bounded digit/Russian-number parsing supplies values. No provider data enters AI context. No BillingBasis schema change.

InvoiceCommand has user overrides without provider IDs. Service binds them to an existing prepared client's historical source and source line numbers in ResolvedInvoiceCommand. FirstBit validates the original posted lines before applying overrides, verifies source/line binding, resolves tax against actual VAT records, then recalculates exact Decimal totals. Renaming preserves service ID; repeated same-service rows stay distinct. Requests before a preview, unknown/ambiguous tax, ambiguous target, source/row drift and unsupported included-VAT amounts fail closed. Ordinary date/quantity edits retain overrides; changing client/service/history clears them rather than copying manual money to another scope.

Refresh re-reads source and tax records and reapplies explicit overrides, preserving operation ID but changing revision/digest. Source changes cannot silently rebind edits. Any attempted edit revokes old confirmation. All manually overridden previews are non-executable independently of provider/caller flags, including fake. Existing non-overridden fake behavior remains intact.

## Metadata and security
Use existing Catalog_VATRates fields and fresh metadata/GET; never assume rate IDs, exemption semantics or tax applicability defaults. Exact current matching profile can be retained; otherwise accept exactly one verified profile. UI states tax/price/description are user proposals. Raw user text is only escaped data in fixed bounded queries; model cannot emit provider IDs, executable filters or computed totals. No production records/secrets/audio dumps in Git; diagnostics remain .local. State stays single-process; restart invalidates buttons.

## Verification
Grounding/number parsing, typed schema bounds, line targeting and preservation, catalog-backed tax, historical-before-edit validation, source/row drift, stale confirmation, refresh/deduplication and blocked writes -> full existing suite -> offline smoke -> actual GET/AI/Telegram preview checks when credentials available. Update context routing/contract/docs. Stop before all writes/PDF.

## Progress
- [x] Inspect current command/draft/provider/confirmation/tests.
- [x] Implement typed grounded overrides and deterministic recomputation.
- [x] Verify focused/full tests, application and live GET-only checks.
- [x] Deploy read-only bot, update docs/index and report results.

## Result

After restart, local/public health passed and a signed operator text request reached actual OpenAI/FirstBit and real Telegram delivery to the confirmed owner. Fresh historical-supplier review is awaiting the owner; no production-app user callback was simulated. Private report: `.local/runtime/preview-edits-public-check.json`.

422 tests passed (382 previous + 40 revision cases). Expanded offline application smoke passed: 92 GETs / 4 mocked AI requests / zero writes/PDF. Live configured-client FirstBit prepare/refresh passed. Isolated real OpenAI text + synthetic OGG/Opus voice + FirstBit application rehearsal passed (72 GETs, synthetic Telegram/supplier choice), including combined price/rate/description and distinct exempt treatment, followed by fresh verification. Actual LLM findings led to local duplicate-rename removal and literal percentage normalization; no weakened confidence or financial guards. Existing metadata properties suffice; no full metadata bundle read or new financial defaults. Compileall, diff check and ignored production artifacts verified. Read-only runtime restarted and webhook ready without dropping updates. Real write/post/PDF remain outside scope; tax applicability, issuer/defaults and durable atomic operation identity/reconciliation are unresolved write-admission gates.
