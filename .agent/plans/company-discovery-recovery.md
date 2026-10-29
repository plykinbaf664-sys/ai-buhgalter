# Company discovery and clarification recovery

Observed: latest safe audit ends in interpretation clarification before any resolver call; an earlier request returned company-choice buttons. Original user text is not logged, so do not invent its exact cause. Ask for it while reproducing general failing classes.

Plan:
1. Inspect current language guards, draft readiness, company-choice continuation and local retrieval. Reproduce names/clarifications rejected before search, and evaluate typo/voice retrieval against the fresh bounded active directory in memory.
2. Let readonly company discovery happen before invoice date/service completeness. Reuse expiring per-user candidate callbacks; support plain-name refinements and explicit numeric choice without losing the original invoice request. No customer-specific rules.
3. Improve local candidate retrieval for systematic typo/phonetic failures; approximate results always require selection. Keep full-directory scan limits/fresh selected-record verification, all financial fail-closed checks and AI data isolation.
4. Add regressions for these paths, forged/stale/cancelled choices, typo families and pre-parser rejection causes; run full tests, offline smoke, aggregate production GET-only retrieval checks and a real isolated text/voice workflow when available. Reload only owned runtime and check readiness.

Safety: dedicated reader ENV/SecretStr, TLS, existing metadata fields, GET only to FirstBit; no writes/PDF, no raw directory to AI/logs/Git. Private diagnostic evidence only in `.local/firstbit/`. Complete unintelligibility and unavailable/missing provider data remain explicit limits; never claim infallible recognition. Update only COMPANY_SEARCH.md for durable rules.

## Findings and implementation

The owner supplied a repeated-preposition invoice request. An isolated pre-fix retry already reached candidate resolution, so the precise historical HELP response cannot be proved from the safe audit; do not claim the duplicate always fails. The stable defects were independently reproduced: valid whitespace/year wording unnecessarily entered a model-dependent compatibility path; name-only discovery and clarification replies could be interpreted as incomplete invoice commands; short-word transpositions lost candidates after phonetic folding; a free-form month request could be classified as an incomplete invoice date.

Normalized conversational whitespace/preposition stutters and common year qualifiers before the narrow compatibility parser; quote contents are protected. Structured intent still handles other formulations. Mask explicitly delimited company names for command/calendar guards. Added typed readonly discovery drafts to existing expiring choices, no date prerequisite, numeric selection through the same fresh identity checks, and original-command name refinement. Uncertain bare voice can only produce a reviewed company choice. Failed discovery retries remain discovery; unknown invoice interpretation gets useful name-search guidance plus an allowlisted audit code, without logging input.

Added one-edit/transposition word retrieval before phonetic folding and general qu/soft-c handling. No fuzzy auto-selection or customer-specific patterns/aliases. Explicit service month/year is grounded from the current text, preserving any separate invoice day and failing on conflicting periods. No public OneC/domain/storage contract change.

## Verification / rollout

- Full `python -m pytest -q`: **535 passed in 39.05s**, including discovery/refinement/numeric expiry/freshness/cancellation, uncertain bare voice -> selected identity -> later period -> preview, duplicate prepositions/whitespace/year wording, short/phonetic typo tokens, explicit period versus invoice date and all existing security/financial tests.
- `scripts/firstbit_readonly_smoke.py`: PASS, 96 synthetic GETs / four mocked AI calls, no production contact or mutation/PDF. compileall/diff checks passed.
- Fresh production GET scan: 444 active names. Evaluated shortened names with one adjacent transposition for 427 eligible records against the full local directory; all intended records appear in top five, zero retrieval or ranking misses. This is bounded synthetic typo coverage, not universal speech accuracy. No directory persisted; only aggregate reports/limited failure samples in ignored `.local/firstbit/`.
- Isolated application production rehearsal: owner request with repeated preposition and an alternate free-form invoice wording both produced a real one-line historical preview after simulated numeric identity and supplier-review choices; 60 production GETs, no mutation/PDF, Telegram simulated. Separate synthetic OGG/Opus -> actual STT/LLM -> FirstBit preview/date edit/refresh passed with 47 GETs, Telegram/review simulated. No new human voice end-to-end claim.
- Reloaded only the owned app process, preserving ngrok/webhook. Prior process-local buttons invalidated; writes remain false. Only durable context update is COMPANY_SEARCH.md. Private customer/input/preview evidence stays in `.local/firstbit/`.
