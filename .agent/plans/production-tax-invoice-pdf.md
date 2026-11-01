# Confirmed preview to Invoice, Tax Invoice and native landscape PDF

## Goal and starting state
Owner authorizes the full production milestone: confirmed preview -> one InventoryExpense -> verified required final state -> native GenerateTaxInvoice -> one linked TaxInvoice -> verified final state -> native TaxInvoiceLandscapeEN PDF -> Telegram. Existing readonly/parser/edit flows stay intact. Current local candidate only implements controlled draft creation and refuses incomplete accounting; production remains readonly. Preserve all existing uncommitted work.

## Evidence and implementation steps
1. Locate and inspect only relevant HAR requests/responses, native function names, bindings and PDF provenance; keep sessions/cookies/UUIDs/download URLs private. Treat the owner's HAR summary as evidence of a captured case, not a callable service contract or universal automatic-posting rule. Recheck live metadata/publication and the current adapter/OneC/service/journal/Bot tests.
2. Establish stable supported native entry points for filling/creating/finalizing InventoryExpense, GenerateTaxInvoice and TaxInvoiceLandscapeEN printing. Never replay HAR sessions or assume internal functions are public OData actions. If a 1C-side endpoint is required, prepare a concrete minimal contract/source package using proved configuration symbols; do not invent filling/printing routines.
3. Extend the existing operation domain/journal/recovery to persist both document identities and the source relationship, plus one-shot tax-generation intent. Unknown outcomes reconcile the same operation before any further mutation. Read-back Posted=true skips posting; Posted=false needs a proved native finalization path, never Posted=true field assignment.
4. Integrate verified native PDF into the current service/Bot transport. Validate the exact TaxInvoice/issuer/confirmed amounts/form identity, PDF bytes and durable delivery uncertainty. No alternate invoice engine, mock production renderer or FirstBit data sent to AI.
5. Verify synthetic real-adapter/security/restart/lost-response cases and existing full suite, then a minimum concrete human-confirmed production operation in sequence. Before writes, fresh reviewed schema guard and proved accounting plan must hold. Report separately each actual mutation, both read-backs, native PDF and Telegram delivery.

## Verification criteria
At most one Invoice and one linked TaxInvoice per frozen confirmed operation across repeat confirm, redelivery, lost responses and restart. No blind mutation retries, no duplicate posting of already-posted documents, no unrelated financial cleanup. Exact native form TaxInvoiceLandscapeEN, real PDF and same-document provenance must be proved. Source data stays live; raw evidence stays ignored under .local/firstbit/. Existing production bot/other server projects remain untouched until reviewed activation.

## Progress
- [x] Router/relevant context/current implementation and dirty worktree inspected.
- [x] Locate raw HAR, correlate generation/source/tax references with native export and real downloaded PDF; keep capture private and ignored.
- [x] Fresh GET metadata/source read-back establishes the available external surface; no financial mutations or captured-session replay.
- [x] Implement optional linked-document domain/service/journal recovery and existing Telegram delivery integration, proved with synthetic providers.
- [x] Extend metadata-only discovery to both document managers/templates; compile EPF using genuine local 1C Designer. Runtime discovery remains unverified.
- [ ] Establish supported native external invocation/read-back/finalization/printing contracts and connect the real FirstBit adapter.
- [ ] Controlled production E2E and scoped activation.

## Evidence, results and blockers (2026-10-31)

HAR is stored under ignored `.local/firstbit/tax-invoice-flow/`; generation takes one source reference and returns a distinct linked reference. Matching native manager/template/export/download and PDF signature/EOF/landscape are verified offline. Exact provider facts live only in `docs/firstbit/FIRSTBIT_INTEGRATION_EVIDENCE.md`; no customer/Ref/session data is in this plan. Captured automatic posting is not established as a universal rule.

Production contact: fresh metadata and captured source-document read-back, GET only; zero financial mutations. The current published surface cannot independently read back TaxInvoice or invoke generation/printing. Internal web-client RPC cannot be treated as a public API. Owner write permission is already explicit; the missing dependency is technical source/publication access. A targeted request and metadata-only tool are ready in `tools/onec-print-discovery/README.md`. Configuration module ownership/signatures, authoritative relation lookup, transaction/uniqueness/finalization and native print entry points must be proved before a native handler/adapter can be implemented. The separate InventoryExpense accounting-dimension/default-filling blocker from the preceding candidate also remains.

Changes reuse existing OneC/service/Bot/journal: optional TaxInvoiceOneC, linked returned-reference versus verified-document models, schema-v3 append-only migration, generation/posting one-shot claims, authoritative reconciliation, fixed-form/version PDF provenance and existing durable Telegram delivery. No full-native capability is advertised by the real adapter; active server remains readonly. Synthetic provider fixtures contain no production data and never count as native FirstBit E2E.

Verification: `.venv/Scripts/python.exe -m pytest -q` passed **668 tests in 56.99s** after final capability-admission checks. Isolated Linux focused execution passed **97 tests in 45.19s** before those last local admission checks; source archive contained no credentials/business evidence, runtime ENV was not loaded, working service PID/start state stayed unchanged, and the temporary source/archive were removed within this project's verification folder. Private server log/summary remain under `/srv/ai-buhgalteria/state/controlled-create-offline-*`. Genuine 1C 8.3.21 Designer compiled the v2 discovery EPF via `tools/onec-print-discovery/BUILD.ps1`; build success is not an in-FirstBit runtime check. `git diff --check` passed (only repository line-ending notices). Raw HAR and compiled EPF are confirmed ignored.

Definition of Done remains unmet: no new production Invoice/TaxInvoice was created, no new native PDF delivered to Telegram, and no actual provider-side lost-response/restart proof was performed. Do not activate or claim production completion from these synthetic proofs.
