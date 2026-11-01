# Focused production create and native backend interface proof

## Scope
Prove one controlled InventoryExpense create/read-back with all required accounting dimensions, and investigate already available production interfaces for GenerateTaxInvoice and native TaxInvoiceLandscapeEN PDF. Preserve working preview/NLP/recovery. Existing owner authorization permits one controlled production test; it does not permit guessing accounting values or bypassing schema/admission guards.

## Steps and verification
1. Inspect current adapter/admission, scoped private metadata/index/HAR and latest runtime evidence. Identify the exact accounting fields blocking create and their live publication/read-back semantics.
2. Inspect discoverable service roots, metadata/service descriptions and HAR-established backend surfaces with bounded requests. Do not assume source/support is needed just because Standard OData omits a function. Never replay captured sessions/ephemeral URLs or call guessed mutations.
3. If a complete supported payload and concrete confirmed test operation can be established, use the existing durable journal/schema guard for one create and exact read-back. Unknown outcome reconciles without resending. No unrelated records, changes or cleanup.
4. Invoke only proved native generation/print interfaces with required identity/reconciliation guarantees. Otherwise report exactly what is unavailable, what evidence establishes the limit, and the smallest missing callable method. Keep evidence private under .local/firstbit/.

## Completion criteria
Separate actual production calls, verified accounting read-back, native backend generation/PDF and full E2E. No synthetic result or HAR download counts as a new production operation. Update only the relevant FirstBit source of truth if durable knowledge changes.

## Findings and actual execution (2026-10-31)

- [x] Current dirty worktree/router, adapter, schema/admission, scoped private full index/HAR and relevant safety context inspected. Full bundle was not loaded; only its index section was streamed and selected objects saved privately.
- [x] Available interfaces investigated beyond OData: live service document/metadata, publication root and its freshly advertised bootstrap, standard SOAP/HTTP roots and HAR-established module metadata path without captured identifiers/session. No guessed named service/mutation routes or captured cookies used. Detailed provider facts are owned only by `docs/firstbit/FIRSTBIT_INTEGRATION_EVIDENCE.md`.
- [x] Fresh posted/non-deleted source read-back, exact BaseUnit/IncomeItem/additional-GL reads succeed. Required BusinessActivity/ExpenseItem exact reads return 404 and their catalogs remain unpublished. Row metadata provides no navigation fallback. Existing admission still returns PROPOSAL_BLOCKED after 17 GETs; payload must not omit nonempty analytics or row connections.
- [ ] Controlled create: not sent, because a complete admitted/verified accounting payload could not be established. There is no new Invoice read-back or financial test operation to report.
- [ ] Native backend integration: no supported callable generation/relation/read-back/PDF contract discovered. Sessionless native module metadata returns 403; SOAP/HTTP roots do not list services. Root responses are not proof that all named services are absent. New endpoint/source delivery is not proved necessary: the smallest next input is an existing service address/descriptor or scoped publication inventory, plus a supported way to validate the missing analytics.

Private evidence and bounded probe scripts: `.local/firstbit/backend-interface-proof/` and `.local/firstbit/tax-invoice-flow/probe_backend_interfaces.py`; existing GET-only admission script `.local/firstbit/production-operation/check_write_proposal.py` was rerun. Browser discovery was attempted with the declared chrome skill after API/tool discovery, but its runtime failed before browser connection; no cookies/profile/session were read and no UI action occurred. This tool failure is not evidence of a FirstBit limitation.

Verification: `.venv/Scripts/python.exe -m pytest tests/test_firstbit_write.py tests/test_firstbit_write_schema.py tests/test_tax_invoice_flow.py -q` -> **59 passed in 12.80s**. No application behavior was changed; preview/NLP/recovery and active server are untouched. Contact with real FirstBit was GET only; zero create/post/generate/update/delete, zero new PDFs or Telegram sends. Full production E2E remains open. No new API scaffolding or weaker guard was added to disguise missing production evidence.
