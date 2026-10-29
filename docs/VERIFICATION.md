# Verification Guide


## Uncertain speech and failed-read recovery

- Full `.venv/Scripts/python.exe -m pytest -q`: **507 passed in 31.00s**. Focused voice/client-choice/FirstBit regression passed 151 cases before the additional acronym/edit/audit cases; the final full run includes all additions. Tests cover uncertain readonly exact/duplicate company choice before history, explicit selection, short misheard acronym suggestions, uncertain edit revocation without financial reads, readonly `/retry` without STT/LLM, cancellation and redacted HTTP/transport audit codes. Existing fake uncertainty checks remain green.
- `scripts/firstbit_readonly_smoke.py`: **PASS**, 96 synthetic GETs / four mocked AI calls, no production contact/mutations/PDF. `live_smoke()` with private ENV loaded: **PASS**, actual existing one-line preview and unchanged refresh; production GET only, no Telegram/OpenAI in that check.
- Reloaded only the owned app process; retained the ngrok endpoint/webhook. Old process-local buttons are invalidated. `scripts/check_demo_ready.py --deep`: **READY** for all five checks after reload, including actual grounded OpenAI patch and production FirstBit metadata GET; writes false.
- `compileall` and `git diff --check`: **PASS**. No new metadata properties or production records added to Git. Historical generic FirstBit failures cannot be retroactively assigned a specific HTTP/network cause.
- Actual signed operator text through the updated public ngrok webhook: **PASS**; real OpenAI interpretation, real FirstBit GET resolution, actual Telegram historical-source review delivered to the confirmed owner. Review was left for the owner; no production click was simulated. This verifies text transport/provider resolution, not a new human voice E2E. Private report: `.local/runtime/runtime-recovery-public-check.json`.

## Ngrok migration

- `scripts/start_readonly_demo.py`: READY using ngrok; existing app and its process-local draft retained. Old owned Cloudflare tunnel stopped only after public health and Telegram registration succeeded.
- `scripts/check_demo_ready.py --deep`: READY for local/public health, matching Telegram webhook and empty queue, production FirstBit metadata GET, and grounded OpenAI parsing. FirstBit writes remain disabled.
- Public ngrok webhook rehearsal: unsigned request rejected with 403; signed operator `/start` accepted with 200 and delivered to the owner's Telegram. This is a transport check, not a human voice invoice test. No FirstBit contact in `/start`.
- Focused `tests/test_demo_runtime.py`: 18 passed. Agent inspection/logging disabled; token supplied through ENV/SecretStr; local binary/config/state ignored under `.local/`. Explicit ngrok `--restart` was not exercised against the live draft.
- Full regression `python -m pytest -q`: **499 passed in 30.38s**. Updated launchers pass `compileall` and `git diff --check`.


## Voice latency: Telegram redelivery wait

Actual slow update evidence: voice download started at 18:02:29 UTC, failed at 18:02:40, response delivery failed at 18:02:43, and Telegram retried delivery at 18:04:45. The next text update completed in 10.5 seconds. The long observed wait was network failure plus webhook redelivery backoff, not a minute of successful accounting computation.

- Voice file lookup and download now each tolerate one transient read failure. Lookup is bounded at 5s/attempt (4s HTTP timeout); download at 12s/attempt (8s HTTP timeout). Status/auth, invalid paths, sizes or data do not retry. Only getFile and validated file GET use this helper; never sendMessage/sendDocument.
- The real Telegram HTTP transport retries one connection-establishment failure only, with TLS and trust_env=False. Read/write uncertainty is not retried by delivery, preserving PDF safeguards. A safe `interpret/parsed` audit marker separates language parsing from FirstBit resolution; no source text is logged.
- Focused voice/webhook/client-choice regression: **113 passed**. Full regression: **488 passed**. Tests inject a single lookup/download timeout and prove recovery without Telegram update redelivery, extra STT or document creation.
- Actual Telegram upload/getFile/download rehearsal passed with an existing synthetic 83,030-byte OGG/Opus file: **0.28s** lookup+download. Technical voice was delivered only to the confirmed owner; no FirstBit contact or business-data input in this rehearsal. This is download timing, not full voice-to-preview latency. Private safe report `.local/runtime/telegram-voice-latency.json`.
- Restart with secure webhook **READY** after retrying a transient Cloudflare DNS creation failure. `scripts/check_demo_ready.py --deep` again **READY** for all five checks, writes false. Metadata/business-write guards unchanged; no new metadata fields or production dumps.

## Network recurrence: customer-demo hardening

Final redeployment verification: secure webhook READY without dropping updates; tunnel log `protocol=http2`; `check_demo_ready.py --deep` READY again after restart. Signed public-webhook operator text completed actual OpenAI/FirstBit resolution and actual Telegram delivery to the confirmed owner. A fresh historical-source review is left to the owner, not simulated in production. Private report remains `.local/runtime/runtime-recovery-public-check.json`; no new human voice success is claimed from that text rehearsal.

- `.venv/Scripts/python.exe -m pytest -q`: **486 passed** (28.99s). New cases prove a same-input SDK parsing retry, no retry of invalid/refused output or auth/quota failures, bounded recovery from 503, explicit TCP HTTP/2 tunnel launch, private recognized-text feedback and no repeated STT on a duplicate update.
- `.venv/Scripts/python.exe scripts/check_demo_ready.py --deep`: **READY** across local/public health, matching Telegram webhook with zero queued updates, actual FirstBit metadata GET and an actual grounded OpenAI date patch. Deep mode makes one paid AI parsing check (at most one network retry); no FirstBit mutation. Catalog-only mode does not assert API billing/inference availability.
- `.venv/Scripts/python.exe .local/runtime/check_company_voice.py`: **PASS**, actual STT/LLM/FirstBit with existing synthetic OGG/Opus: preview, date edit, read-only refresh; 47 GETs, zero mutations, isolated simulated Telegram/supplier review. No new human voice success is inferred from this rehearsal.
- `compileall`, `git diff --check`: **PASS**.

Observed cause was actual `openai_timeout` after successful STT and renewed QUIC/DNS transport failures, with three Telegram updates waiting. The tunnel is now configured for TCP HTTP/2; logs confirm `protocol=http2`. Interpretation alone may retry a transient SDK call once under a 40s total budget (25s attempt timeout); STT, schema validation and document execution are not replayed. This is resilience to transient failures, not a guarantee against loss of Internet/VPN/host power. A permanent server/domain remains an owner-supplied deployment prerequisite; no unapproved remote hosting or secret transfer occurred.

## 2026-10-27: runtime recovery and complete read-only preview check

Final deployment: `scripts/start_readonly_demo.py --restart` **READY**. `.local/runtime/check_recovery_public.py` **PASS**: local/public health 200, signed operator text → actual OpenAI → actual FirstBit read resolution → actual Telegram delivery to the confirmed owner. The fresh supplier-review callback was not simulated in the running app; owner retains that choice. `getWebhookInfo` confirms the active tunnel URL and **0 pending updates**; writes remain false. Private report `.local/runtime/runtime-recovery-public-check.json`. This public delivery test used text; voice evidence below is synthetic audio. No permanent hosting/VPN-independent uptime claim follows.

- `.venv/Scripts/python.exe -m pytest -q`: **479 passed** (28.26s). Added regressions for tunnel API-error URL rejection, transient identical GET recovery, short spoken brands within long legal names, model create-label repair restricted to an existing preview, identical tax deduplication vs conflicting values, legacy display rename conversion, complete verbatim title and wrong-row blocking. Existing write/recovery/security guards remain green.
- `.venv/Scripts/python.exe -m pytest -q tests/test_demo_runtime.py`: **6 passed**; focused preview suite **46 passed** after final row-scope correction. Before the final caption cases, combined preview/workflow check passed 83 cases; final full suite above covers all changes.
- `scripts/firstbit_readonly_smoke.py`: **PASS**, synthetic application flow, 96 GETs / 4 mocked AI requests, zero mutations/PDF.
- Private `.local/runtime/check_company_voice.py`: **PASS**, actual OpenAI STT/LLM + FirstBit, existing synthetic OGG/Opus → real preview → date edit → read-only refresh; 47 GETs / zero mutations. Telegram/review in the isolated rehearsal were simulated. This is not a new human voice E2E.
- Private `.local/runtime/check_carville_recovery.py` with `CARVILLE_CHECK_TEXT=1`: **PASS**, actual OpenAI/FirstBit short-name lookup → three candidates → isolated explicit target and historical-source choices → one-line real preview → combined price/VAT/complete-description edit → read-only refresh. 63 GETs, zero mutations/PDF. Only synthetic operator text and simulated Telegram callbacks; names, IDs and financial snapshots are not Git fixtures. A separate fresh TTS generation timed out; no successful new-company synthetic voice is claimed. The existing synthetic voice check above independently verifies actual STT/LLM.
- Targeted real GET reproduced Latin short-name suggestions but no Cyrillic short-brand candidate before the fix. After local phonetic/token matching, the correct already owner-named company is among three suggestions, never automatically chosen. No new metadata property or full bundle load was needed.
- `compileall`, `git diff --check`: **PASS**. Runtime state/logs/reports stay ignored under `.local`; no production records added to Git.

Incident evidence: expired temporary tunnel, transient DNS/network failures, and later FirstBit/Telegram timeouts after an actual human candidate selection. The application had already passed voice recognition. A stale tunnel PID was reused by an unrelated process; no foreign process was stopped. The stale state was archived only after checking workspace ownership, absent local health and no owned live process. The launcher now accepts a URL only after a successful tunnel announcement, so api.trycloudflare.com in an error is not mistaken for a public webhook. GET-only retry is limited to one additional identical request after transport error/timeout; status/auth/schema/money/cancellation do not retry.

FirstBit contact was GET-only. Authorized external side effects were paid AI rehearsals and Telegram tunnel/webhook/message operations. Create/post/PDF and current accounting/write-admission gates remain outside scope. [Recovery ExecPlan](../.agent/plans/runtime-recovery.md).

## Latest: voice company search without exact spelling

Deployment/public check: `scripts/start_readonly_demo.py --restart` **READY**, secure webhook refreshed, pending updates retained, writes false. `.local/runtime/check_company_search_public.py` **PASS**: local/public health 200, signed operator Cyrillic spoken-name text → real OpenAI/FirstBit → actual Telegram candidate buttons in the confirmed owner's chat. No production-app user choice was simulated; it awaits the actual owner's callback. This delivery check used text, not human audio. Private status only, no company record dump.

- `.venv/Scripts/python.exe -m pytest -q`: **465 passed** (28.94s), including the previous 422 cases and 43 new lookup/phrase-extraction cases. `.venv/Scripts/python.exe -m pytest -q tests/test_company_search.py`: **43 passed** after the final missing-prefix guard. Fixtures are synthetic names/records, not production exports. The older injection regression now verifies that no company text enters OData at all; the two-client fixture lists both names while preserving distinct scoped history/contracts.
- `scripts/firstbit_readonly_smoke.py`: **PASS**, synthetic application flow including text/voice/manual revisions/verify/cancel/dedupe, 96 GETs / 4 mocked AI calls, zero mutations/PDF.
- `scripts/firstbit_readonly_smoke.py --live`, with private ENV loaded: **PASS**, actual FirstBit prepare/refresh, GET only, no Telegram/OpenAI in this check.
- Private `.local/runtime/check_company_names.py`: **PASS**, 36 actual FirstBit GETs, zero mutations. Case/spacing/punctuation variants resolved to the same verified identity; spoken Cyrillic/transliteration/typo variants offered buttons; the previously owner-named duplicate personal name returned two choices. No company records/IDs/prices in the report.
- Private `.local/runtime/check_company_voice.py`: **PASS**, actual OpenAI STT/LLM + FirstBit, synthetic OGG/Opus pronounced company name → real preview → actual LLM date edit → read-only refreshed verification, 47 GETs / zero mutations. Telegram transport and supplier-review choice were simulated only in this isolated test. Initial real model calls reproduced an omitted client despite correct STT; verbatim phrase recovery fixes that case. A separate attempt stopped at unchanged STT confidence guards. No new human voice E2E is claimed.
- Live discovery verified the existing metadata fields, fixed `$skip` and `Ref_Key asc`; three name-only pages covered 443 active records in 2.34s during the probe, with no record persistence. Upper/lower/title server probes each returned one record: current server case sensitivity itself was not the demonstrated cause. The latest human voice audit only proves successful STT followed by client-resolution clarification; original text/audio cannot be recovered from retained audit.
- `compileall`, `git diff --check`, ignored `.local` and empty `git ls-files .local`: **PASS**. No full metadata bundle load or new metadata field/EntitySet was required.

FirstBit traffic was GET only; paid AI rehearsal and authorized Telegram runtime/webhook delivery are external side effects. Company names are ephemeral local data, never AI context, logs or committed business dumps. Controlled write gates remain unchanged. [Contract, limits and local matching](firstbit/COMPANY_SEARCH.md).

## Latest: explicit price/VAT/description revisions

- `.venv/Scripts/python.exe -m pytest -q`: **422 passed** (26.12s), including 40 new revision cases and all 382 previous cases. The expanded smoke assertion now expects its fourth mocked AI request. Grounding/role/row validation, cumulative edits, actual-profile zero vs exempt semantics, duplicate model rename/addition, quantity/date preservation, source/row/money/tax drift, stale tokens and fake/real execute guards are covered.
- `.venv/Scripts/python.exe scripts/firstbit_readonly_smoke.py`: **PASS**, actual application with synthetic transports, 92 GETs / 4 mock AI calls, now including price/VAT/description edits, unchanged second row, stable operation identity, changed digest and verify-only acknowledgement. Zero mutations/PDFs.
- `.venv/Scripts/python.exe scripts/firstbit_readonly_smoke.py --live`, with private ENV loaded: **PASS**, real FirstBit one-line prepare/refresh, GET only; no Telegram/OpenAI in this check.
- Private `.local/runtime/check_preview_edits.py`: **PASS** against real OpenAI and real FirstBit, 72 GETs / zero mutations. Baseline historical proposal → combined text edit → combined synthetic OGG/Opus voice edit → exempt tax edit distinct from 0% → fresh read-only verification. Telegram transport and supplier-review click were simulated only in the isolated rehearsal, not in the owner's running session. Audio contains test instructions only, no FirstBit data. Model duplicate catalog additions and wrong labels for spoken zero percent were found during this check and corrected with deterministic grounding/normalization regressions.
- `.venv/Scripts/python.exe scripts/start_readonly_demo.py --restart`: **READY**, validated config, safe logs archived, secure webhook refreshed without dropping pending updates, `writes_enabled=false`. State is still process-local; old buttons are invalid after restart.
- Private `.local/runtime/check_updated_bot.py`: **PASS**, local/public health 200, signed public-webhook operator text → actual OpenAI/FirstBit resolution success → actual Telegram delivery to the confirmed owner. A fresh historical-supplier review prompt was sent; the real owner's choice was not simulated or approved by this script. This public check is text, not a human voice.
- `.venv/Scripts/python.exe -m compileall -q app scripts tests`, `git diff --check`: **PASS**. `.local` and `.env.local` are ignored; `git ls-files .local` is empty.

Metadata/evidence: existing integration/coverage documents and runtime fresh `$metadata` guard; the same `Catalog_VATRates` fields and historical `Inventory.LineNumber` already consumed by the adapter. No additional metadata object or full bundle read was necessary for these revisions. No ItemPrices or accounting defaults were introduced. See [revision contract and examples](firstbit/PREVIEW_REVISIONS.md). FirstBit was contacted only with GET; paid AI rehearsals and authorized Telegram runtime/webhook operations were external side effects. Create/post/update/delete/PDF remain disabled. Controlled draft-write still needs tax applicability/current accounting defaults, resolved issuer, atomic idempotency and durable reconciliation in a separately approved stage.

## Actual repository commands

From current `README.md`:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe scripts/demo.py
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts/smoke.py
.\.venv\Scripts\python.exe scripts/firstbit_readonly_smoke.py
```

Dependency consistency:

```powershell
.\.venv\Scripts\python.exe -m pip check
```

Focused OneC contract behavior:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_onec_contract.py tests/test_core.py -q
```

Mock invoice visual artifacts:

```powershell
.\.venv\Scripts\python.exe scripts/preview_invoices.py
```

Live OpenAI check (paid API, still no Telegram/1C write):

```powershell
.\.venv\Scripts\python.exe scripts/live_ai_check.py
```

Do not run paid/live checks unless required and configured.

## What existing checks mean

### `scripts/demo.py`
Real local HTTP server, but outgoing services are substituted.
Exercises voice → STT → LLM → confirmation → fake 1C → PDF and duplicate behavior.

Expected README outcome:
- 1 fake document;
- 1 PDF delivery;
- 1 STT call;
- 1 LLM call.

### `scripts/smoke.py`
Repository-provided smoke path. Inspect current script before relying on exact assertions.

### pytest suite
Current test modules:

- `test_ai.py`
- `test_boundaries.py`
- `test_core.py`
- `test_failures.py`
- `test_intent.py`
- `test_invoice_workflow.py`
- `test_language.py`
- `test_mock_pdf.py`
- `test_model_selection.py`
- `test_onec_contract.py`
- `test_voice.py`
- `test_webhook.py`
- `test_firstbit.py`
- `test_firstbit_application.py`
- `test_demo_runtime.py`

Do not state an exact total passed count without running the suite.

## Verification ladder

### L1 — domain/model
- strict validation;
- money/quantity/date bounds;
- totals/digest;
- operation-state consistency.

### L2 — service
- provider result validation;
- refresh behavior;
- write guard;
- reconciliation;
- stale/conflict semantics.

### L3 — bot/webhook
- confirmation expiry;
- edit invalidation;
- allowlist;
- duplicate update;
- failed delivery;
- recovery freeze.

### L4 — offline HTTP smoke
- demo/smoke scripts.

### L5 — production read-only FirstBit
Only GET:
- company lookup;
- contract lookup;
- item/service lookup;
- historical invoice lookup;
- application-level `resolve_basis` smoke.

### L6 — production mutation
Separate explicit phase; not part of current read-only task.

## Mandatory new tests for real FirstBit read-only adapter

At minimum:

1. exact company match;
2. folder ignored;
3. deleted ignored;
4. ambiguous company => controlled clarification;
5. valid default contract;
6. default contract wrong owner => reject;
7. inactive default => reject;
8. exactly-one active fallback;
9. multiple active contracts => clarification;
10. zero GUID => missing;
11. historical invoice selection by Company+Contract;
12. only posted/non-deleted accepted;
13. newest matching invoice chosen;
14. invoice without bookkeeping Item skipped;
15. multiple same-Item rows preserved;
16. no historical bookkeeping invoice => clarification;
17. production bookkeeping price is not sourced from empty ItemPrices;
18. malformed OData => safe failure;
19. timeout => unknown/safe failure;
20. 401/403 => safe provider failure;
21. no POST/PATCH/DELETE performed;
22. existing `InvoiceService.prepare()` contract remains valid;
23. no secret/auth header appears in exception/log serialization.

## Regression checks that must stay green

Existing repo behavior includes:
- untrusted provider payload cannot bypass runtime validation;
- LLM cannot invent amount/tax/client/service fields;
- old confirmation becomes invalid after edit;
- changed revision refreshes preview and keeps same operation ID;
- race after refresh is still blocked atomically by adapter contract;
- unknown state blocks edit/new request;
- lost fake create/post response recovers same snapshot;
- repeated request does not duplicate document;
- voice path does not run while recovery is unresolved;
- preview can contain up to 20 lines and Telegram message chunks remain bounded.

## Production read-only smoke discipline

- credentials only via ENV/SecretStr;
- no password in command history;
- GET only;
- fail closed on unexpected schema;
- do not turn a successful curl into a claim that write works.

## Write admission checklist

Before first real draft:
- real adapter read-only tests green;
- source of all mandatory financial fields understood;
- current revision/fingerprint design implemented;
- durable operation correlation strategy established;
- atomic uniqueness in 1C established;
- metadata drift guard passes;
- test target explicitly approved;
- `ONEC_WRITE_ENABLED` path implemented for real mode;
- first test creates draft only;
- posting is a later separate test;
- PDF is a later separate test.

## Reporting

Every completion note must include:
- changed files;
- commands actually executed;
- pass/fail;
- whether real FirstBit was contacted;
- whether calls were GET-only;
- unresolved assumptions.

## Security-specific verification

Before any real FirstBit write, add/execute tests proving:

- Basic Auth secret is never present in logs/exceptions;
- TLS verification is enabled;
- user-controlled company/service strings cannot inject OData query syntax;
- GET client uses structured query params;
- pagination/result size is bounded;
- only expected EntitySets are callable by adapter code;
- no POST/PATCH/DELETE path is reachable in read-only mode;
- `ONEC_WRITE_ENABLED=false` is the default;
- metadata mismatch blocks write;
- admin credentials are not accepted as normal runtime configuration;
- FirstBit record payloads are not forwarded to OpenAI by the invoice-resolution flow;
- duplicate/timeout/restart scenarios cannot produce blind second writes.

Also perform a manual permissions audit of the dedicated 1C integration account before enabling write.

## Implemented FirstBit read-only checks

`scripts/firstbit_readonly_smoke.py` exercises the actual factory with `APP_MODE=firstbit_readonly`: webhook text/voice, STT/LLM responses, synthetic FirstBit GET, two independent rows, quantity edits, old-token rejection, changed-source refresh, verify-only confirmation, failed GET refresh without false financial recovery, cancellation and duplicate webhook. Every FirstBit request is asserted GET. OpenAI requests are checked for absence of provider-derived draft context. This is offline application evidence, not live compatibility.

Focused suite:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_firstbit.py tests/test_firstbit_application.py -q
```

After credentials are filled/imported from ignored `.env.local`, the live script invokes service prepare/refresh against FirstBit only, without OpenAI or Telegram:

```powershell
.\.venv\Scripts\python.exe scripts/firstbit_readonly_smoke.py --live
```

Required ENV, sources and unsupported cases: [FirstBit guide](firstbit/READONLY_PIPELINE.md). Initial verification below lacked credentials; the subsequent live follow-up supplied them and passed GET prepare/refresh. Do not treat a passing synthetic fixture alone as proof of live compatibility. Full future write-baseline drift, durable operation reconciliation, create/post/PDF remain separate work.

## Initial verification recorded 2026-10-24 (before credentials)

All commands below ran from repository root using `.venv/Scripts/python.exe` (system Python has no pytest installed).

| Command after Python executable | Actual result |
|---|---|
| `-m pytest -q` | **330 passed**; original 267 tests preserved, 63 new FirstBit/security/application checks |
| `-m pytest tests/test_firstbit.py tests/test_firstbit_application.py -q` | **63 passed** during focused verification; final full suite includes them |
| `scripts/firstbit_readonly_smoke.py` | **PASS**, 61 synthetic FirstBit GETs including failed-refresh scenario, 3 mocked AI requests, 0 mutations, 0 PDFs |
| `scripts/firstbit_readonly_smoke.py --live` | **BLOCKED** before network: missing configured credentials/client/date; owner will fill ENV later |
| `scripts/demo.py` | **PASS**, existing offline voice/STT/LLM/fake-create/post/PDF and dedupe |
| `scripts/smoke.py` | **PASS**, local HTTP startup/health/webhook authentication/malformed input |
| `-m pip check` | **PASS**, no broken requirements |
| `-m compileall -q app scripts tests` | **PASS** |

`git diff --check` passed. `git check-ignore` confirms the private metadata bundle and `.env.local` are ignored; `git ls-files .local` is empty. No production FirstBit, real Telegram or real OpenAI contact occurred during these checks. No production side effects; demo's document/PDF operations are fake only. Read-only implementation is ready for configuration/live validation, not an assertion of production write/post/PDF readiness.

## Live follow-up after owner supplied credentials

Owner explicitly confirmed dedicated read-only permissions. Corrected login edge whitespace, enabled the existing read-only attestation, set local APP_MODE=firstbit_readonly with writes false, and used today's valid ISO date for smoke after detecting an invalid date value. No secrets are recorded here.

`scripts/firstbit_readonly_smoke.py --live --save-preview` passed against real FirstBit: one-line typed preview and unchanged prepare/refresh snapshot. Successful instrumented verification performed 20 GETs; preceding targeted diagnostic GETs identified authentication/query/schema differences. All production HTTP requests were GET. No create/post/update/delete, no PDF, no real Telegram/OpenAI contact. Formatted preview is available only in ignored `.local/firstbit/readonly-preview.txt`; raw current schema/diagnostics are likewise private.

Live corrections are covered by regressions for Double/Decimal validation, canonical Int64 strings, RFC3986 filter spaces, unsupported function/unbounded-field avoidance, exact candidate selection and two clients with distinct contracts/history/totals independent of smoke ENV. Current full suite result is recorded in the execution plan; previous 330-pass result above is the pre-live baseline.

Final follow-up commands/results:
- `.venv/Scripts/python.exe -m pytest -q`: **339 passed** (267 original + 72 FirstBit/security/application checks).
- `.venv/Scripts/python.exe scripts/firstbit_readonly_smoke.py --live --save-preview`, with local ENV explicitly loaded: **PASS**, real FirstBit historical preview with one line, unchanged snapshot on refresh, zero mutations/PDFs.
- `.venv/Scripts/python.exe scripts/firstbit_readonly_smoke.py`: **PASS**, synthetic text/voice/application flow.
- Application factory using current local ENV: `/healthz` **200**, mode `firstbit_readonly`; Telegram/OpenAI network transports replaced for this startup-only check.
- `.venv/Scripts/python.exe -m compileall -q app scripts tests` and `git diff --check`: **PASS**.
- `git check-ignore` confirms `.env.local`, live schema and formatted preview are ignored; `git ls-files .local` remains empty.

Production FirstBit was contacted only with GET; no create/post/update/delete/PDF side effects. Live preview success applies to the checked client/basis; arbitrary clients still need their own visible active records, unambiguous contract and supported historical bookkeeping lines. Actual Telegram delivery/STT/OpenAI interaction was not run against live external services in this follow-up.

## Subsequent real Telegram/OpenAI runtime verification

See [LIVE_DEMO.md](firstbit/LIVE_DEMO.md). Actual Telegram getMe/webhook registration succeeded; owner's incoming /start was received. A signed public webhook rehearsal read real FirstBit and delivered its preview to the owner's explicitly confirmed private chat. The new launcher was tested with --restart, re-registered the secure webhook without dropping updates, and delivered a fresh preview afterward. This is real Telegram delivery, but rehearsal invoice input was injected deliberately and was not human speech.

Actual official OpenAI models GET succeeded and selected supported gpt-4o-mini / gpt-4o-mini-transcribe. Real LLM generation and real transcription of locally synthesized WAV both returned **429 credit_balance_exhausted**. No successful live STT/LLM/human voice result is claimed. Owner decided to keep GPT API; Qwen was not added. Remaining external blocker: funded API project/key and then an actual voice message.

Operational commands tested: `scripts/run_local.py --check`, `scripts/start_readonly_demo.py`, `scripts/start_readonly_demo.py --restart`, `scripts/register_demo_webhook.py` (through launcher). Typed process ownership safeguards have regressions in `tests/test_demo_runtime.py`; no global Windows script policy change. Production FirstBit calls remained GET-only. Telegram setWebhook/sendMessage were intentional authorized side effects; OpenAI requests used synthetic text/audio. No production create/post/PDF.

Final runtime follow-up verification: **342 tests passed** via `.venv/Scripts/python.exe -m pytest -q`; `compileall` and `git diff --check` pass. Local and public health both return 200/firstbit_readonly after restart. Current webhook matches the active tunnel, pending updates are zero. Private runtime state/tools/instructions remain ignored and untracked. API billing and a subsequent human voice test remain outstanding; do not mark the live voice objective achieved.

## Funded API recheck

After owner reported funding, actual gpt-4o-mini structured intent extraction passed with a synthetic grounded client/date/service request. Actual gpt-4o-mini-transcribe on local synthesized WAV passed the app's Transcript/confidence check with 22 confidence entries. Both used the existing official SDK/base URL and retries disabled; API credit blocker is resolved.

The same running application then passed a signed public-webhook natural-language rehearsal: actual OpenAI intent -> actual FirstBit GET resolution -> validated preview -> real Telegram delivery to the owner's previously confirmed private chat. App audits show interpret started, resolve success, interpret success, update handled. Input was a signed text rehearsal, not a human voice. No restart was required for refilling the same key.

Local/public health remain 200/firstbit_readonly. Private reports are .local/runtime/openai-funded-check.json and funded-natural-language-check.json. No code changed in this recheck, so the existing 342-pass code regression remains the baseline rather than a newly rerun suite. Production FirstBit requests were GET only; Telegram preview delivery and paid OpenAI test requests were the authorized side effects. No create/post/PDF. Await an actual Telegram voice update before claiming complete human voice E2E.

## Actual voice diagnostics and explicit client buttons

Owner's actual incoming voice passed download/STT and reached client resolution. Targeted fresh GETs proved duplicate active Company names and absent posted invoices for both records, including other contracts. Names, IDs and diagnostics remain private; owner selected diagnostic record 1. New candidate buttons do not override missing financial evidence.

Commands/checks actually run for this change:
- `.venv/Scripts/python.exe -m pytest -q tests/test_client_choice.py tests/test_firstbit.py`: **92 passed** before the final missing-history wording change.
- `.venv/Scripts/python.exe -m pytest -q`: **364 passed** after the final code change (22.91s), including independent service rejection if a provider substitutes a different selected client ID.
- `.venv/Scripts/python.exe scripts/firstbit_readonly_smoke.py`: **PASS**, synthetic application text/voice/edit/refresh/verify/cancel/dedupe, no financial mutation/PDF.
- `.venv/Scripts/python.exe scripts/firstbit_readonly_smoke.py --live`, with local ENV loaded: **PASS**, actual existing one-line historical preview and unchanged refresh, GET only.
- Private application-level real FirstBit selection rehearsal: **PASS**, 9 GETs, original diagnostic option 1 selected and correctly blocked on missing posted history; Telegram transport synthetic inside this check, no AI calls. Separate real Telegram notification acknowledged.
- `.venv/Scripts/python.exe scripts/start_readonly_demo.py --restart`: **READY**, read-only config, secure webhook, pending updates retained. Signed operator text through the running public webhook delivered actual candidate buttons with real FirstBit/Telegram; not a human voice/click. Public health 200.
- `.venv/Scripts/python.exe -m compileall -q app scripts tests`: **PASS**.

New tests cover candidate selection and original command/client/history scope, partial single-candidate confirmation, inactive/renamed/out-of-scope selections, forgery/cross-user callbacks, expiry, cancellation/new-input revocation, missing basis, safe audits and receipt-based delivery retry. State remains process-local; restart invalidates choice/confirmation buttons. Production FirstBit traffic was only GET; real Telegram notifications/buttons were the authorized external side effects. No create/post/PDF.

## Voice/history preview and supplier review

- `.venv/Scripts/python.exe -m pytest -q`: **382 passed** (21.07s), including all prior cases. New checks cover verified historical/current supplier mismatch, explicit review before any preview button, user scope/forgery/cancel/expiry/new-input revocation, fresh snapshot checks, supplier identity drift blocking, renewed review on changed financial values, receipt retry, unchanged unknown/deleted-entity/currency/money guards, concise provenance rendering and distinct historical rows.
- Additional regressions cover local draft clarification without repeating the known client, controlled bookkeeping synonyms, low-confidence transcript shown only to its user without LLM/mutation/log leakage, and preserving existing safe logs at restart.
- `.venv/Scripts/python.exe scripts/firstbit_readonly_smoke.py`: **PASS**, synthetic application flow, 61 GETs/3 mocked AI calls, zero mutations/PDF.
- `.venv/Scripts/python.exe scripts/firstbit_readonly_smoke.py --live` with private ENV loaded: **PASS**, existing real one-line prepare/refresh, GET only, no Telegram/OpenAI in this check.
- `.venv/Scripts/python.exe .local/runtime/check_bmt_voice.py`: **PASS** on actual OpenAI STT/LLM and actual FirstBit, synthetic OGG/Opus input, simulated Telegram transport and supplier-review click. Real preview -> actual LLM text date edit -> read-only refreshed verification; 42 GETs, zero mutations. One earlier audio attempt was blocked by the original STT confidence guard, which was retained.
- `.venv/Scripts/python.exe scripts/start_readonly_demo.py --restart`: **READY**, config validated, existing audits archived, secure webhook updated without dropping pending updates. The running public app delivered an actual Telegram supplier-review prompt after a signed natural-language operator rehearsal through real OpenAI/FirstBit. A subsequent actual incoming owner callback accepted the review and completed validated real preview delivery after fresh GET. Initial voice was synthetic and public invoice text was an operator rehearsal; this does not establish a full new human voice E2E.
- `.venv/Scripts/python.exe -m compileall -q app scripts tests`: **PASS**.

Metadata evidence used: reviewed integration/coverage docs, targeted bundle members for Catalog.CompanyContracts.Entity/AccountsCurrency and Document.InventoryExpense.Entity/DocumentCurrency, fresh GET `$metadata`, and bounded Company/Contract/invoice/Entity/Item reads. No new provider field was guessed; the new pair of provenance fields is application-domain data. Production diagnostics, synthetic audio and reports remain ignored under `.local/`. FirstBit traffic was GET only. Authorized external side effects were paid OpenAI voice/intent rehearsals and Telegram prompt delivery; no create/post/update/delete or PDF.
