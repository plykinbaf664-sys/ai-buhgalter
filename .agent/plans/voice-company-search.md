# Voice company resolution without exact spelling requirements

## Goal and evidence
Latest actual voice audit passed STT, then stopped at resolve/client. Transcripts and old Telegram replies are intentionally not persisted; their exact wording cannot be recovered from this audit. Existing adapter uses a whole-name server substring search before local casefold; a case-sensitive server, punctuation differences or Cyrillic speech for Latin company names can therefore hide valid candidates. The current fake server's case-insensitive matching does not reproduce that boundary.

Live follow-up showed equal results for upper/lower/title variants: server case sensitivity itself was not reproduced. A real synthetic voice also reproduced omitted client output despite STT correctly returning the user-spoken name. Both whole-phrase lookup and that missing-output case are now covered.

## Scope and invariants
Improve existing FirstBit read-only client resolution and reuse expiring per-user client-choice buttons. Case/spacing/punctuation equivalence may resolve only a unique verified exact identity. Transliteration, acronym speech and fuzzy similarities are candidate suggestions only, requiring explicit user choice. No financial inference, arbitrary OData, raw directory to AI, persisted business dump, write or new architecture. Fresh GET verifies selection, active status and original query scope. Bound catalog discovery and candidates; incomplete discovery cannot justify automatic identity selection. Preserve unknown operation/write guards.

## Work
- Inspect code/tests and actual bounded GET behavior, including case sensitivity and metadata-verified names/IDs.
- Choose minimal reliable bounded name retrieval/local matching, not guessed OData functions.
- Add tests for server case sensitivity, voice spellings, duplicates, no matches, limits, stale choices and security.
- Full regression and read-only application/live checks, then restart bot and update docs/index with actual results.

## Security and rollout
Dedicated reader ENV/SecretStr, verified HTTPS, GET only, ONEC_WRITE_ENABLED=false. Reuse existing Catalog_Companies consumed properties; no metadata bundle dump. Local normalized/fuzzy keys never become query syntax or IDs. Any name directory stays bounded in memory only and never reaches AI/logs/Git. No production callback choice is simulated for the owner. Disable by stopping the local runtime; no rollback of financial records is needed because no mutation occurs.

## Progress
- [x] Inspect latest safe audit and current client resolver.
- [x] Implement bounded retrieval and deterministic matching.
- [x] Focused/full tests and live read-only verification.
- [x] Restart and document final behavior/limits.

## Result

465 tests passed (422 baseline + 43 new); final focused suite 43 passed. Offline application smoke passed with 96 GETs / 4 mocked AI calls and zero mutations/PDF; configured live prepare/refresh passed. Actual spelling cases: 36 GETs / zero mutations, including exact canonical variants, phonetic/typo choices and duplicate personal-name choices. Actual OpenAI STT/LLM + FirstBit synthetic voice rehearsal passed: preview → date edit → refreshed verification, 47 GETs, simulated Telegram/supplier choice only within the isolated check. Confidence thresholds were preserved. Fresh active-name discovery was 443 rows in three pages; no name records persisted or sent to AI.

Bot restarted with writes false and secure webhook ready, pending updates retained. Local/public health 200. Signed operator Cyrillic-spelling text reached real OpenAI/FirstBit and delivered actual client-choice buttons to the confirmed owner's Telegram; the script did not choose for the owner. Private report `.local/runtime/company-search-public-check.json`. Index/docs/security/OneC contract updated. No full bundle load, guessed metadata, production create/post/update/delete or PDF. Existing accounting/write-admission blockers remain.
