# Explicit initial invoice parameters over historical proposals

> Historical execution record, closed for current rollout. Statements, counts and pending observations below describe that checkpoint, not current availability or present requirements. Current behavior: [docs/firstbit/INITIAL_REQUESTS.md](../../docs/firstbit/INITIAL_REQUESTS.md); current verification: [VERIFICATION](../../docs/VERIFICATION.md).

## Goal
Initial text/voice may specify client/date and multiple service lines with amounts/tax. Explicit grounded user values take precedence; omitted values come only from verified client-specific posted history. Preview remains editable, cancelable and non-executable.

## Evidence / unknowns
At investigation start, preview edits supported net unit price, catalog-backed VAT and display wording only after a prepared preview. The real adapter was restricted to one configured bookkeeping item; a different requested service must resolve to an actual active Service item and have proven client/contract history, not be implemented as a cosmetic rename. The owner subsequently confirmed NET line amounts, with VAT added separately. Generic 'with VAT' does not invent a rate.

## Plan / verification
1. Inspect existing language spans, numbers, draft/command merge, service prepare, source/line-bound overrides and preview validation. Use targeted existing metadata and bounded production GETs to establish service/history feasibility; save evidence only in ignored `.local/firstbit/`.
2. Extend existing typed initial intent and line overrides rather than add a separate invoice engine. Decode money from source spans locally; distinguish unit price, net line amount and gross line amount. Require explicit basis/clarification; validate tax via the existing catalog/history path and exact Decimal arithmetic. Preserve separate repeated service lines.
3. Resolve real service IDs locally, choose a verified historical source for the requested client/contract/services, bind overrides to that source/LineNumber, and revalidate before preview. Missing service/history/currency/tax or impossible rounding blocks; no silent dropping of requested lines.
4. Cover initial precedence/fallback, multiple distinct/repeated services, VAT semantics/ambiguity, source drift, later edits, injection/data isolation and independent write guards. Run focused/full tests, offline application smoke and exact production GET-only rehearsal when the required financial meaning is established. Deploy only verified behavior.

## Safety / scope
No BillingBasis/storage/write architecture change is planned. OneC protocol methods remain; any new command/override fields must be typed and verified at the service/provider boundaries. Existing dedicated reader ENV/SecretStr, TLS, metadata guards, GET-only transport, supplier review, confirmation/cancellation/recovery remain. FirstBit names/IDs/money are never sent to the LLM; it selects spans from user input only. No production dumps/fixtures in Git, no mutations/PDF. Current accounting/tax applicability and controlled draft-write remain separate gates.

## Scope change established during investigation

A combined request needed independently verified per-service historical sources rather than renaming/duplicating a bookkeeping row. The owner confirmed NET line amounts with VAT added separately. Private case data remains outside Git; the resulting generalized source/LineNumber binding and financial semantics are documented in INITIAL_REQUESTS.

## Approved interpretation and implementation design
Owner clarified that explicit line amounts are NET, with VAT added separately. Initial per-service overrides will use the existing typed override mechanism with a distinct net line amount (never interpreted as unit price); source spans are decoded locally. Gross-inclusive instructions remain a clarification, not silently reinterpreted.

Expand active service discovery over bounded fresh item-name pages with exact/fuzzy selection and per-user expiring service-choice callbacks, mirroring company choice. Initial overrides survive client/service choice. For distinct services, choose each service's latest matching posted invoice under the same client/contract/date scope; preserve repeated rows and reject ambiguous grouping. Extend historical preview line/source provenance with explicit source IDs and a checked list of source documents. All selected sources must agree on issuer/currency; fail closed on conflicts. Bind edits to per-line source ID plus LineNumber and guard the complete source-set revision. This extends preview/command provenance, not BillingBasis or mutation APIs. Missing required history/financial data remains a user-visible blocker rather than fabricated defaults. Add focused multi-service/amount/source-drift tests, then full/offline/live checks and context routing updates.

## Completion evidence

Implemented the typed initial-line path, locally grounded net amounts and VAT requests, fresh catalog-wide Service discovery, expiring service choices/refinement, per-service posted-history sources and source-bound later edits. Nonrepresentable amount/quantity combinations require explicit quantity approval rather than changing totals silently. Command/preview provenance was extended as described above; BillingBasis and operation IDs were preserved. Missing history, inconsistent suppliers/currencies and unknown financial facts remain blocking or explicit review steps. Durable behavior is documented once in `docs/firstbit/INITIAL_REQUESTS.md`, with router/index links.

Commands actually run:
- `.venv/Scripts/python.exe -m pytest -q`: **568 passed**, 66.55 seconds, including the existing regression suite and new initial-line/security/workflow tests.
- `.venv/Scripts/python.exe scripts/firstbit_readonly_smoke.py`: PASS, 96 synthetic GET requests and four mocked AI calls; no production contact in this offline smoke.
- `.venv/Scripts/python.exe .local/firstbit/check_initial_lines.py`: exact owner request reached a real InvoicePreview using real AI and production FirstBit, **75 GETs, zero mutations**. Telegram and company/service/quantity/supplier selections were simulated in an isolated application. Net 2800, verified VAT 140, total 2940 AED. Final rerun passed after the last parser changes.
- `.venv/Scripts/python.exe .local/firstbit/check_initial_voice.py`: PASS, **91 production GETs, zero mutations**, actual STT/LLM and real preview. Audio was generated synthetic OGG/Opus, not a human recording; Telegram and choices were simulated in isolation.
- `.venv/Scripts/python.exe .local/firstbit/check_initial_public.py`: PASS through the actual public webhook; a real company-choice response was delivered to the owner's authorized Telegram chat. No owner choices were simulated in the live bot. Full selected-preview delivery for this exact request still requires the owner's clicks.
- `.venv/Scripts/python.exe -m compileall -q app scripts`, `git diff --check`, and ignored-private-artifact check: passed (Git reports only line-ending normalization warnings).
- `.venv/Scripts/python.exe scripts/check_demo_ready.py --deep` after the final app reload: **READY** for local/public health, Telegram webhook queue, production metadata GET and grounded OpenAI patch; writes disabled.

Private diagnostics remain under ignored `.local/firstbit/`. The owned app process was reloaded after final code changes, retaining the ngrok tunnel and `firstbit_readonly` mode. Old process-local buttons expire across restart; use a fresh request. There were real external OpenAI and Telegram calls as explicitly described, but every FirstBit call was GET and `ONEC_WRITE_ENABLED=false` remained enforced. Controlled draft-write, posting, production PDF, durable idempotency and unresolved accounting applicability remain separate work.

## Completed implementation

The typed initial-line, generic Service lookup/choice and multi-source historical-preview path is implemented. No real write/post/PDF was enabled. Later source/financial corrections and exact current verification scope belong to the linked feature/verification guides rather than this original implementation outline.
