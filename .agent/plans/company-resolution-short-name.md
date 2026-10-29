# Short company-name resolution investigation

## Observed bug / goal
An owner-supplied invoice request with a shortened company name and an explicit service month does not resolve. Reproduce that exact private request without assuming whether parsing, local matching, paging, provider data or downstream business rules are responsible. Keep customer-specific evidence only under ignored `.local/firstbit/`.

## Investigation layers
1. Follow AGENTS routing: company-search rules, language/intent flow, readonly provider contract and relevant verification commands; inspect corresponding code/tests.
2. Run the actual interpreter on the exact request. Capture locally the interpretation, merged draft/command and the literal query entering `resolve_client()`.
3. With existing dedicated-reader ENV/SecretStr credentials and writes disabled, use only bounded GETs through the adapter. Verify consumed metadata and actual Description/DescriptionFull; count/order all name pages and inspect completion/limit behavior. Never pass provider records to AI.
4. Compare exact/short/full/legal-form/partial matching against proven data. Fix the general failing mechanism only; no customer-specific regex, aliases or fixtures. Preserve human choice for partial/fuzzy ambiguity and fresh selected-ID validation.

## Verification criteria
- Synthetic regressions for shortened/full names, punctuation/case/whitespace, legal suffixes, ambiguity and later pages; incomplete/unstable scans fail closed.
- Existing focused tests and full pytest remain green; readonly application smoke passes.
- Repeat the exact request through real parsing and production GET-only resolution. Continue to historical InvoicePreview when supported, recording any separate contract/history/currency blocker without bypassing it. Explicitly distinguish diagnostic candidate selection from a real user click.
- No production names/IDs/TRNs/raw responses in tracked files, no mutations, no global aliases, TLS/metadata/confirmation guards unchanged. No domain/storage changes. Any durable new rule goes only in COMPANY_SEARCH.md; no duplicated context updates.

## Production safety / rollout
Use existing approved least-privilege reader, valid TLS and local ENV secrets. Read Catalog_Companies name fields and only existing provider dependencies when continuing to preview. OData syntax stays fixed, UUIDs typed; user text stays local to matching. Metadata mismatch, incomplete directory, ambiguity, unknown financial values or unsupported state stop the flow. No write method or flag is enabled; stopping diagnostics/reloading the single app process is sufficient rollback.

## Progress
- [x] Reproduce and prove root cause.
- [x] Implement general correction and regressions.
- [x] Verify focused/full/offline/live results and record outcome.

## Result
The exact private request failed before `resolve_client()`: a trailing year qualifier took it beyond the narrow parser into SDK legacy extraction. The SDK requested the entire growing InvoiceCommand domain schema; repeated real responses were incomplete at max_output_tokens and failed typed JSON decoding. Direct production name search already returned the intended reviewed candidate. Thus there was no evidence for changing or bypassing matching, aliases, pagination or business rules.

The SDK legacy path now uses the existing four-field Extraction and common ground(), matching its HTTP counterpart. No OneC/domain schema or matching rules changed. Updated SDK test seams preserve typed-command/voice/retry/model-selection assertions. Added synthetic multiword-shortening/legal-form/full-name normalization/ambiguity/later-page regressions plus actual official-SDK mock -> draft -> real-adapter fixture -> historical preview coverage. No owner-specific record or name was added to these tests.

Verification: focused `python -m pytest -q tests/test_ai.py tests/test_model_selection.py tests/test_company_search.py`: 122 passed. Full `python -m pytest -q`: 519 passed in 34.48s after updating the voice mock to the compact extraction contract. `scripts/firstbit_readonly_smoke.py`: PASS, 96 synthetic GETs/four mocked AI calls, no production contact. compileall/diff checks pass.

Exact production request after correction: actual AI returned the literal short name, year and month; instrumented service passed it unchanged to resolve_client. Production returned one candidate. An isolated diagnostic selection of that candidate continued through fresh GETs to a one-line historical InvoicePreview. This was not a human Telegram callback. Supplier review remains required before bot presentation/verification; no contract/history/currency blocker was encountered. No financial write/PDF/Telegram delivery was attempted in this diagnostic.

Pagination evidence: complete 444-name scan, three fixed 200-row pages at skips 0/200/400, unique IDs, intended record on page one, below the existing 5000-row cap. Private request/response/selection/preview evidence and reports remain only under ignored `.local/firstbit/`. Only durable context update: COMPANY_SEARCH.md explains the compact extraction boundary and distinguishing pre-resolver failures from a legitimate candidate choice.

Reloaded the existing owned app process while preserving ngrok/webhook; prior process-local buttons invalidated. Writes remain false. No new metadata fields, full metadata-bundle ingestion, storage layers or aliases were required.
