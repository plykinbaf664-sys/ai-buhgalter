# Invoice native-print discovery and write admission

## Requested result and actual starting point
Owner authorizes production creation/posting after human confirmation, and requests minimal readonly print discovery. Authorization persists; this is not a request for more permissions. Existing adapter still rejects mutation and historical/manual previews lack a proven writable accounting plan. A flag change cannot implement those contracts.

## Work
1. Inspect router, actual write guards, previous private GET evidence and the existing MetadataBridge source. Identify precise missing metadata categories without exporting business data.
2. Prepare a standalone readonly processor based on the existing managed-form/XML layout. Export HTTP service routes/methods, common-module name index, and InventoryExpense command/template names. No publication, business queries, document reads/writes, source execution or print invocation.
3. Build using installed genuine Designer when available; statically audit source/form wiring. Test locally against an empty infobase, separating compilation/import and runtime evidence. Targeted follow-up source exports are required for actual handler signatures and native print semantics; metadata names are not proof.
4. Retain fail-closed write admission until current defaults/correlation/create contract is proved; do not disguise this as missing owner authorization. Update only production-operation source of truth and route to package instructions.

## Verification criteria
Generated package contains no mutation/publication code or production records, has one readonly export command, and reports unsupported metadata fields/collections explicitly. Export is metadata only; printing is never executed for discovery. Fresh OData evidence remains GET only. Report separately actual configuration mechanism, exact invocation, direct PDF availability and need for an endpoint; unproved items stay unknown.

## Status
- [x] Existing bridge excludes HTTPServices/CommonModules; its publication command must not be copied into this standalone processor.
- [x] Generate/audit/build readonly package using genuine local training Designer 8.3.21.1644; import completion and nonempty EPF verified. Binary/build log/base are private under `.local/firstbit/print-discovery/`.
- [ ] Verify local runtime export, then execute live readonly metadata discovery. Hidden local client produced no export; Windows UI diagnostics could not initialize, so runtime/live success is not claimed. Only the tool's own local test processes were stopped; no server restart or deployment.
- [x] Record actual discovery boundary and remaining write blockers in PRODUCTION_OPERATION; operational scope/instructions live with the package.

## Actual verification and results

- `python tools/onec-print-discovery/preflight.py`: PASS; three XML/two BSL files, one readonly export command, action/event wiring and static compatibility/safety checks.
- Genuine Designer source import: completed successfully, producing a real EPF. This does not establish BSL runtime execution, live permissions or native printing.
- `python -m pytest -q tests/test_print_discovery.py tests/test_firstbit_write_schema.py tests/test_operations.py`: **37 passed in 11.95s**. Eight new cases cover unknown capabilities despite matching names/GET, non-exhaustive candidate filtering, partial metadata, self-attestation rejection, unexpected business fields/duplicates/bounds, and package wiring.
- Full `python -m pytest -q`: **617 passed in 46.17s**. compileall and diff whitespace checks passed.
- Fresh production Standard OData discovery: GET only, bound Post declared, no declared print action, write_admitted=false, zero mutations. Evidence refreshed privately in production-operation directory. No guessed HTTP routes called.
- Source ZIP and compiled EPF prepared privately. Live HTTPService/CommonModule export remains needed; exact native print entry point, per-Invoice invocation, direct PDF and necessity of a new HTTP endpoint remain unknown. Names alone cannot settle them.
- Runtime application/write/config guards unchanged; deployment remains readonly. Explicit owner authorization is valid, but actual create/default/correlation contracts are still unproved. No invoice create/post/PDF or Telegram document delivery attempted.
