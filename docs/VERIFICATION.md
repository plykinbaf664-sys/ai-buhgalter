# Verification Guide

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
