# Documentation audit — 2026-10-31

## Scope and authority

Audited **34 original project Markdown documents/instructions**: root AGENTS/README/context index, all docs/firstbit/context-audits, all .agent plans and the assets README. The private metadata README was also checked and only obsolete document paths corrected; the metadata bundle itself was not loaded in full or modified. Generated/third-party venv/Git/cache content is outside project documentation scope.

Started with git status -> git diff -> relevant current code and tests. Initial working tree already contained earlier deployment changes, including non-document files; they were neither reverted nor altered. Current local behavior is established by source/tests; integration compatibility was checked offline against the saved private consumed-schema XML, not claimed as a fresh live GET. No external API/SSH/server/webhook/deployment changes were made during this audit.

## Corrections and ownership

- Removed mock-only/no-real-adapter/no-hosting claims from current guides. Default fake mode, deployed FirstBit GET-only mode and future writable targets are now distinct.
- Replaced the old single-bookkeeping/current-catalog-tariff narrative with links to generic Service discovery, per-service historical sources and explicit initial net money. Kept the fake current-price rule distinct from FirstBit historical proposals.
- Distinguished initial baseline/overrides from existing-preview edits, net amount from unit price, per-line source ID/LineNumber binding, supplier review, catalog-backed VAT and unresolved new-document defaults.
- Separated real verify-only confirmation/typed readonly retry from fake mutation/reconciliation/recovery/PDF. Real read_operation remains unknown; no write admission follows from a preview.
- Corrected contract fallback (invalid/missing/deleted/wrong-owner default blocks), bounded 30-invoice history versus exhaustive search, guarded name paging versus a transactional snapshot, allowed GET retry versus 'no retries', and read-schema guard versus future write baseline.
- Removed obsolete alternate module-layout proposals and deployment prerequisites already implemented. Documented remaining persistence/uniqueness/accounting/default/write/post/PDF work without implying it exists.
- Kept AGENTS a short router; the context index assigns each policy to one owner. Feature guides own mechanics, SYSTEM_MAP transitions, SECURITY admission, SERVER_DEPLOYMENT operations and VERIFICATION commands/results. Summaries elsewhere link instead of duplicating full policies.
- Replaced incident chronology and repeated 'latest' counts in live/verification guides with current commands and dated proof scope. Completed plans are explicitly historical, not active rollout instructions. Retained useful rationale and observed metadata field inventories separately from runtime consumption.
- Documented actual operational limits: server READY alone does not require matching webhook/empty queue; check --deep must precede register; deployment templates are not a full installer; existing backup can block another cutover; rate limiting and current account/network permissions are not proven by code. No changes were made to implement those missing controls.

## Removed or consolidated

The redundant old `_SECURITY_AUDIT.md` snapshot claimed mock-only/no adapter; relevant current risks are consolidated in SECURITY and milestone docs. Two completed case-only parser/discovery plans were removed from permanent context; their general lessons already belong to COMPANY_SEARCH/architecture. Originals of all reviewed documents are preserved only under ignored `.local/firstbit/documentation-audit/original/`. No raw customer case or identifiers were copied into replacement documentation.

## Verification actually run

- `python -m pytest -q`: **579 passed in 58.28s**.
- `python scripts/smoke.py`: PASS, real loopback startup/health/webhook admission; no external calls.
- `python scripts/demo.py`: PASS, synthetic voice/STT/LLM and fake create/post/PDF, one document/one PDF; no live calls.
- `python scripts/firstbit_readonly_smoke.py`: PASS, 96 synthetic GETs/four mocked AI calls, zero production contact/mutations/PDF.
- `python -m pip check`: no broken requirements.
- `git diff --check`: passed; only pre-existing line-ending normalization warnings.
- Private audit validator: local Markdown links/fences/path routing, exact runtime/test/deploy file hashes against task-start baseline, no new/deleted non-doc source files, secret/customer-case/nonzero UUID scan. Consumed fields/types pass against saved private metadata XML via mocked transport; no full bundle or live schema request.

Audit output/evidence stays under ignored `.local/firstbit/documentation-audit/`; it is not a runtime dependency or a new production dump. Final link/hash pass completed: 31 remaining project Markdown files, 162 local links, zero broken links; all 64 files in the runtime/test/deploy/assets baseline are unchanged. Private-data scan passed. Current suite result belongs to VERIFICATION, not every feature guide. Historical live/synthetic/human observations are labeled by scope, not promoted to universal recognition/availability claims.

## Reviewed inventory

| Original document | Audit outcome |
|---|---|
| `.agent/plans/client-choice-readonly.md` | Updated |
| `.agent/plans/company-discovery-recovery.md` | Removed / archived privately |
| `.agent/plans/company-resolution-short-name.md` | Removed / archived privately |
| `.agent/plans/initial-request-financial-lines.md` | Updated |
| `.agent/plans/live-telegram-readonly-demo.md` | Updated |
| `.agent/plans/preview-price-tax-description.md` | Updated |
| `.agent/plans/real-firstbit-readonly.md` | Updated |
| `.agent/plans/runtime-recovery.md` | Updated |
| `.agent/plans/server-readonly-deployment.md` | Updated |
| `.agent/plans/voice-company-search.md` | Updated |
| `.agent/plans/voice-history-preview.md` | Updated |
| `.agent/PLANS.md` | Updated |
| `AGENTS.md` | Updated |
| `app/assets/README.md` | Checked; retained |
| `docs/AGENT_WORK_STYLE.md` | Updated |
| `docs/ARCHITECTURE.md` | Updated |
| `docs/context-audits/_REPO_AUDIT.md` | Updated |
| `docs/context-audits/_SECURITY_AUDIT.md` | Removed / archived privately |
| `docs/DECISIONS.md` | Updated |
| `docs/firstbit/COMPANY_SEARCH.md` | Updated |
| `docs/firstbit/FIRSTBIT_INTEGRATION_EVIDENCE.md` | Updated |
| `docs/firstbit/FIRSTBIT_METADATA_COVERAGE.md` | Updated |
| `docs/firstbit/INITIAL_REQUESTS.md` | Checked; retained |
| `docs/firstbit/LIVE_DEMO.md` | Updated |
| `docs/firstbit/PREVIEW_REVISIONS.md` | Updated |
| `docs/firstbit/READONLY_PIPELINE.md` | Updated |
| `docs/onec-contract.md` | Updated |
| `docs/PROJECT_CONTEXT.md` | Updated |
| `docs/SECURITY.md` | Updated |
| `docs/SERVER_DEPLOYMENT.md` | Updated |
| `docs/SYSTEM_MAP.md` | Updated |
| `docs/VERIFICATION.md` | Updated |
| `README.md` | Updated |
| `README_CONTEXT_ENGINEERING.md` | Updated |

## Result and remaining limits

Current local docs describe implemented readonly and fake behavior consistently; the removed snapshots no longer compete with the router. Code/business logic/config/test/deploy sources remain unchanged by this task. This documentation-only audit was not deployed to the server and does not re-prove present production availability or completed real create/post/PDF. Unsupported financial cases, missing history, current accounting/default approval, durable state/atomic uniqueness/reconciliation and separately controlled draft/post/PDF milestones remain explicit blockers rather than undocumented assumptions.
