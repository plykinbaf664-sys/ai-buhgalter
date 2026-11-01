# Verification guide

## Linked TaxInvoice milestone verification

`python -m pytest tests/test_tax_invoice_flow.py -q` checks the existing service/journal/Bot chain with an explicitly synthetic TaxInvoice-capable provider: generation as posted/draft, no duplicate posting, lost generation/post responses before/after commit, returned-reference persistence before read-back, repeat confirm/redelivery/restart, atomic generation claims, native-PDF provenance/version drift, corrupt tax journal and lost Telegram delivery acknowledgement. The source Invoice PDF path is forbidden in these tests. This proves orchestration, not a real FirstBit native adapter or provider-side transaction/financial validation.

The server candidate full suite passed **726 tests**. Additional adapter suites cover analytical carryover/read-back, actual FirstBitProduction with synthetic OData/native UI, duplicate/restart/lost responses, conditional TaxInvoice posting, exact native reference boundaries, TaxInvoice dates and 12-hour schema monitoring. Run tests/test_firstbit_write.py, tests/test_firstbit_tax.py, tests/test_firstbit_production.py, tests/test_firstbit_ui.py and tests/test_schema_monitor.py for focused verification.

Production evidence includes fresh metadata/analytical-reference GETs and genuine native landscape PDF download for an existing TaxInvoice, both directly and under the production service sandbox with fresh OData guards. These browser print operations use native nonfinancial POSTs/temp storage; they are not new Invoice/TaxInvoice create/post proof. One controlled Telegram-confirmed operation completed with recovery: one real Invoice plus one linked TaxInvoice, both Posted=true, exact financial/analytical/registration read-back, native TaxInvoiceLandscapeEN PDF and acknowledged Telegram delivery. After actual service restart, two independent GET-only replays reused the same document references and PDF hash, retained delivered state, made 24 GETs and zero UI actions. A further live prepare-only check admitted a new date with verified supplier TRN, 35 references and zero mutations. Current rollout/evidence: [active plan](../.agent/plans/production-headless-e2e.md). Raw evidence remains private; no customer fixture or captured session is needed for tests.


## Scope and evidence rules

Run from repository root. Local code/tests are implementation truth. Offline success does not prove live API availability, real human voice, production permissions or create/post/PDF. Dated observations below are not a current uptime guarantee. Offline tests do not contact those providers. Live checks and deployment changes must be stated separately in the active milestone evidence.

## Reproducible checks

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts/smoke.py
.\.venv\Scripts\python.exe scripts/demo.py
.\.venv\Scripts\python.exe scripts/firstbit_readonly_smoke.py
.\.venv\Scripts\python.exe -m pip check
git diff --check
```

Linux equivalent: `.venv/bin/python`; install runtime/dev dependencies from `requirements*.txt` as appropriate. Tests do not need production credentials, bundle or external accounts.

| Check | What it proves / does not prove |
|---|---|
| `pytest -q` | Behavior/security regressions with synthetic providers and transports |
| `scripts/smoke.py` | Real loopback HTTP startup, health, secret rejection and malformed-body rejection; no external requests |
| `scripts/demo.py` | Loopback webhook + synthetic voice/STT/LLM -> preview/confirmation -> fake document/PDF; duplicate handling. One fake document, one PDF delivery, one STT/LLM call |
| `scripts/firstbit_readonly_smoke.py` | Offline real-adapter application flow with synthetic FirstBit/Telegram/AI: text/voice, edits, verify/cancel/dedupe. No production contact or PDF |
| `scripts/preview_invoices.py` | Creates mock PDF visual artifacts under ignored `artifacts/`; never a real invoice |
| `scripts/live_ai_check.py` | Paid real OpenAI on fictitious inputs + FakeOneC; no real FirstBit/Telegram write. Requires configured ENV; do not assume its semantic expectations cannot need review |
| `scripts/firstbit_readonly_smoke.py --live` | Actual FirstBit service prepare/refresh, GET only; no OpenAI/Telegram. Requires private smoke client/date and runtime ENV |
| `--live --save-preview` | Same check plus private review text under ignored `.local/firstbit/` |
| `scripts/server_control.py check --deep --public-url <HTTPS-project-base>` | Server health/admission, Telegram webhook info/queue, fresh FirstBit metadata GET and real grounded AI date patch; paid AI, not STT or full invoice E2E |
| `scripts/check_demo_ready.py --deep` | Equivalent readiness for the local tunnel runtime; not the active Linux server checker |

Live smoke does not auto-load `.env.local`; use the explicit loader in [READONLY_PIPELINE](firstbit/READONLY_PIPELINE.md). Server checks require protected EnvironmentFile and working directory: [SERVER_DEPLOYMENT](SERVER_DEPLOYMENT.md). A server `check` can return READY with `webhook_matches=false` or queued updates: inspect these fields, not only `result`. `register`/`restore` mutate Telegram configuration and are separate authorized operational actions. `register --deep` runs its deep checks after registration in current code; use **check --deep first, then register** for safe cutover.

## Flow regression matrix

| Flow | Test modules |
|---|---|
| Domain/basis/revision/execute/reconcile | `test_core.py`, `test_onec_contract.py`, `test_boundaries.py` |
| Language/typed intent/financial grounding/model selection | `test_ai.py`, `test_language.py`, `test_intent.py`, `test_model_selection.py` |
| FirstBit transport/schema/history/arithmetic/isolation | `test_firstbit.py`, `test_firstbit_application.py` |
| VAT-inclusive/exclusive source prices, net edits, exact rounding, legacy digest compatibility and linked Tax Invoice recovery | `test_vat_inclusive.py` |
| Company normalization/partial/fuzzy/paging and expiring selection | `test_company_search.py`, `test_client_choice.py` |
| Initial net amounts, service choice, repeated/multi-source history, quantity approval | `test_initial_lines.py` |
| Existing-preview amount/price/VAT/description edits and source drift | `test_preview_overrides.py` |
| Bot confirmation/recovery/receipt/delivery | `test_invoice_workflow.py`, `test_webhook.py` |
| Voice confidence/download/retry and external failure bounds | `test_voice.py`, `test_failures.py` |
| Windows process/tunnel ownership and Linux control/config guards | `test_demo_runtime.py`, `test_server_runtime.py` |
| Optional confirmed-operation durability, multi-process claims and prospective write-schema pin | `test_operations.py`, `test_firstbit_write_schema.py`; admission/proof limits in [PRODUCTION_OPERATION](firstbit/PRODUCTION_OPERATION.md) |
| Mock renderer/embedded fonts | `test_mock_pdf.py` |

For a focused change run the relevant subset, then the full suite and relevant offline scripts. Expand to live checks only when needed and authorized. Never fuzz production or test a reader's permissions by attempting mutations. Test coverage does not prove FirstBit transactional semantics.

## Dated latest verification

Production-milestone preparation, **2026-10-31**, after the documentation audit: full local suite **609 passed in 67.48s**. Focused Linux core durability/schema/OneC checks: **36 passed**, isolated/no credentials, live runtime unchanged. These are synthetic proofs. Fresh FirstBit GET discovery passed; no production create/post/native PDF/Telegram document E2E occurred. Current checkpoint/remaining contracts: [production plan](../.agent/plans/production-invoice-operation.md).

Documentation audit, **2026-10-31**, local working tree including pre-existing uncommitted server deployment files:

- Full `python -m pytest -q`: **579 passed in 58.28s**.
- Offline smoke/demo/dependency and documentation integrity results are recorded in [audit report](context-audits/_REPO_AUDIT.md).
- No production contact, paid AI or Telegram/SSH side effects during this audit. Source/config/test hashes are checked unchanged from task start; existing dirty changes belong to earlier work.

Last recorded deployment verification, **2026-10-30**, from private deployment evidence and completed deployment plan:

- Linux Python 3.12, dedicated non-root user: 579 tests passed; offline readonly smoke passed with 96 synthetic GETs/four mocked AI calls; pip check passed.
- Actual FirstBit GET-only prepare/refresh reached InvoicePreview, no mutation/PDF.
- Two-service owner-input rehearsal: real AI + FirstBit reached real preview; Telegram/choices were simulated in isolation. It is not an actual human click sequence.
- Synthetic OGG/Opus -> real STT/LLM -> FirstBit -> preview passed on server; not human voice. Complex audio/formulations can still require clarification; financial confidence guards were retained.
- Actual public HTTPS operator requests delivered Telegram responses, including company-choice buttons; this proves real transport/provider progress, not automatic invoice completion for every wording.
- Service enabled, one loopback worker, private ENV/code permissions, own log namespace, other service lifecycles unchanged. Synthetic upstream failure confirmed Telegram-secret redaction. Server readiness matched the webhook and queue was zero then.

Historical execution plans hold earlier scoped results with superseded counts. They must not override this current verification guide or be used as commands to repeat paid/production work. Private raw artifacts remain local; no customer identifiers or full response dumps belong here.

## Before any later real write

Read-only verification is only the first layer. Remaining milestones are owned by [PROJECT_CONTEXT](PROJECT_CONTEXT.md); exact transactional/recovery guarantees by [onec-contract](onec-contract.md); admission checklist by [SECURITY](SECURITY.md). They require fresh evidence and a separate approved plan/target, not changing the current write flag.


Native adapter regressions also cover supplier registration ownership/effective period/schema drift, legacy frozen read-back without new write permission, global linked-record pagination/wrong-party conflicts, dedicated Generate action/one-shot acknowledgement, lifecycle flag normalization and conditional TaxInvoice posting. Recovery tests intentionally leave uncommitted unknown outcomes blocked; no blind retry is a success criterion.
