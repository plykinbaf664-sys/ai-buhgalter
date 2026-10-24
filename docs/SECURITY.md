# Security Model

## Why this document exists

Этот проект работает рядом с production FirstBit ERP / 1C крупной компании. Ошибка здесь может затронуть реальные бухгалтерские документы, клиентов, договоры, реквизиты и финансовые данные.

Security model строится по принципам:

- least privilege;
- deny by default;
- read-only before write;
- human confirmation before financial side effect;
- fail closed;
- no trust in external input;
- minimal data exposure;
- explicit recovery after uncertain side effect;
- auditable actions without secret leakage.

## 1. Trust boundaries

### Untrusted inputs
Считать недоверенными:
- Telegram update;
- user text;
- voice/audio;
- LLM output;
- Telegram API response;
- OpenAI response;
- FirstBit/OData response;
- ENV values;
- HTTP status/body;
- metadata exports.

Все структурированные данные проходят Pydantic validation before use.

### Trusted only after validation
- stable 1C Ref_Key resolved deterministically;
- validated BillingBasis;
- confirmed InvoicePreview revision/digest;
- reconciled operation state.

## 2. Current repository protections already implemented

### Telegram admission
`app/main.py`:
- webhook secret in `X-Telegram-Bot-Api-Secret-Token`;
- constant-time `hmac.compare_digest`;
- numeric user allowlist;
- only private chat;
- requires `chat.id == sender.id`;
- bot actors rejected;
- forwarded messages / `sender_chat` rejected;
- body max 32 KiB;
- body read timeout 5 s;
- changed payload under same `update_id` returns conflict;
- max three delivery attempts;
- process-wide gate limits concurrent handling.

### Secrets/config
`app/config.py`:
- tokens/API keys use `SecretStr`;
- strict token/webhook-secret validation;
- `ONEC_WRITE_ENABLED` must parse exactly `true|false`;
- `ONEC_WRITE_ENABLED=true` is invalid while `APP_MODE=mock`.

Current read-only implementation also rejects true under `APP_MODE=firstbit_readonly`. `FirstBitSettings` requires a dedicated account attestation and rejects admin-like usernames, empty credentials, zero Item IDs and non-HTTPS/credential-bearing/non-root URLs. Attestation does not prove server privileges: owner must verify permissions. `.local/` is ignored in full.

`app/firstbit.py` exposes only bounded GET over verified TLS, with redirects, retries and ambient proxies disabled. Fresh metadata verifies consumed fields/types before resolution. OData text is a quoted literal; reference filters use UUIDs; no nextLink or arbitrary URL execution. Mutation/PDF protocol methods unconditionally reject calls. The service independently rejects preview-only providers and historical proposal execution even when a caller enables writes. Verify-only confirmation does not claim operation reconciliation; provider read_operation remains unknown.

FirstBit proposal bank/payment/supply/tax-registration defaults are not inferred. Missing line financial values block the proposal; missing new-document defaults remain explicit write blockers. The real-mode interpreter receives an empty draft instead of provider-derived context; user text and voice continue through existing AI boundaries. See `firstbit/READONLY_PIPELINE.md` for exact limits and live GET evidence. Live query encoding uses RFC3986 spaces and local exact name validation, so server candidate searches cannot silently select a partial match.

`.gitignore` excludes:
- `.env`;
- `.env.*`;
while retaining `.env.example`.

### External HTTP
`app/main.py`:
- bounded timeouts;
- redirects disabled;
- `trust_env=False`;
- OpenAI SDK automatic retries disabled.

### LLM containment
The application does not give the LLM tools or direct 1C access.
LLM output is parsed/validated and cannot directly invoke a financial side effect.

Production rule:
**do not send raw FirstBit records, contracts, bank details, TRNs, GL data, or invoice history to the LLM unless a separately reviewed use case explicitly requires it.**
For current invoice creation flow, LLM should receive only the minimum user-language context needed for intent parsing.

### Voice handling
`app/voice.py`:
- audio max 4 MB;
- max 120 seconds;
- OGG/Opus header validation;
- bounded transcript;
- confidence heuristic;
- SDK temporary audio file is deleted in `finally`;
- cleanup failure is surfaced.

### Financial write safety
`app/service.py`:
- real provider write is blocked unless `allow_real_writes=True`;
- read state before mutation;
- `unknown` blocks mutation;
- basis is refreshed before confirmation;
- changed snapshot requires a new confirmation;
- create/post results are runtime-validated;
- document/client/basis identity is checked;
- `preview_digest` must match confirmed preview;
- after mutation exception, service does read-only reconciliation instead of blind retry.

### Audit logging
`app/service.py` logs an explicit `AuditEvent`.
It intentionally does not log:
- command text;
- exception messages;
- HTTP URLs;
- HTTP bodies;
- credentials.

It may log:
- Telegram user ID;
- request ID;
- operation ID;
- document ID;
- stage/status/safe error type.

Production deployment must define retention/access rules for these identifiers.

## 3. FirstBit / 1C security rules

### Dedicated integration identity
Use a dedicated service account, never a personal/admin account.

Current integration identity must have the minimum necessary permissions.

During read-only phase:
- no document creation;
- no posting;
- no deletion;
- no arbitrary code execution;
- no configuration changes;
- no admin rights.

Before write phase, grant only the exact permissions needed for:
- reading required catalogs/registers;
- creating/reading the target invoice type;
- posting that exact type if approved;
- obtaining its standard print form.

Do not grant deletion rights unless a separately approved business flow requires them.

### OData surface
The Standard OData whitelist is an exposure boundary.

Rules:
- publish only objects required by the workflow;
- additions require justification;
- never auto-publish newly discovered metadata;
- review the 33-object MVP whitelist again before production rollout and remove objects not required by the actual adapter.

### Query minimization
Real adapter must:
- use explicit `$select`;
- use restrictive `$filter`;
- use bounded `$top`;
- paginate deliberately;
- avoid full-table dumps;
- never interpolate raw user text into OData URL syntax;
- never expose arbitrary OData query construction to Telegram/LLM input.

### Transport
- HTTPS only;
- certificate verification must remain enabled;
- no `verify=False`;
- no plaintext Basic Auth;
- no credential in URL;
- no password in repository/logs/test fixtures.

Preferred production network posture when available:
- IP allowlist and/or VPN/private network;
- outbound-only application access to FirstBit;
- restrict FirstBit endpoint exposure at firewall/reverse-proxy level.

## 4. Data minimization / confidentiality

### Principle
Read only the fields needed to resolve the current invoice.

For example:
- company resolution: name/ref/default contract, not entire company record;
- contract resolution: owner/entity/currency/relevant refs;
- historical invoice resolution: only fields needed for proposed preview;
- do not pull unrelated employees, HR, payroll or other business data.

### LLM boundary
Do not send:
- full 1C customer directory;
- bank account directory;
- GL chart;
- tax registrations;
- historical invoice corpus;
- credentials;
- internal operation IDs unless necessary.

Current intent parsing should remain independent of bulk 1C data.

## 5. Fail-closed rules

The following must stop the workflow:
- ambiguous company;
- ambiguous contract;
- no safe billing basis;
- unexpected OData schema;
- auth error;
- timeout where outcome is uncertain;
- metadata drift;
- stale revision;
- preview/document digest mismatch;
- unexpected currency/exchange-rate requirement;
- unrecognized VAT/GL/payment-term state.

No "best guess" fallback for financial fields.

## 6. Metadata drift protection

Before enabling production write:

```text
fresh FirstBit metadata
→ compare reviewed baseline
→ verify required EntitySets/properties
→ verify whitelist
→ pass OR block write
```

Rules:
- no automatic baseline acceptance;
- no guessed renamed fields;
- schema mismatch is a security event because it can redirect writes to incorrect semantics.

## 7. Idempotency and recovery

`operation_id` is correlation, not sufficient by itself for durable production idempotency.

Before real write, FirstBit-side or equivalently durable uniqueness must prove:
- same business basis cannot create two documents concurrently;
- application restart does not lose operation identity;
- lost response can be reconciled;
- manual/externally created conflicting documents are handled explicitly.

Process-memory dedupe in the current app is not enough for production.

## 8. Production deployment requirements not yet implemented in repository

These are mandatory before write-enabled production:

- explicit real FirstBit mode in typed settings;
- `ONEC_BASE_URL`, username, password/secret provider via `SecretStr`;
- dedicated real adapter with GET-only mode first;
- durable operation/recovery storage;
- at-rest protection and access policy for that storage;
- reverse proxy rate limiting;
- TLS termination policy;
- network ACL/VPN/IP allowlist where available;
- log retention/access/redaction policy;
- secret rotation procedure;
- backup/restore and incident response procedure;
- security review of the actual 1C service account permissions;
- controlled rollout with a test company/document.

## 9. Forbidden shortcuts

Never:
- use admin/Nastya credentials in runtime;
- hardcode FirstBit credentials;
- paste credentials into source/docs/tests;
- log `Authorization`;
- disable TLS verification;
- enable write just to "see if it works";
- retry POST/PATCH automatically after timeout;
- accept ambiguous customer match;
- let LLM construct arbitrary OData filters;
- use production database as a fuzzing target;
- generate a fake/local PDF as official production accounting output;
- auto-accept metadata drift;
- deploy multiple workers while dedupe/recovery is memory-only.

## 10. Security verification before write

Minimum gate:

1. real adapter is read-only and tested;
2. all existing tests pass;
3. new OData validation/security tests pass;
4. service account permissions reviewed;
5. OData whitelist reviewed for minimum exposure;
6. no secret in repo/logs/artifacts;
7. TLS verification proven;
8. raw user input cannot form arbitrary OData syntax;
9. metadata guard passes;
10. durable idempotency exists;
11. lost-response recovery tested;
12. restart recovery tested;
13. draft-only test explicitly approved;
14. posting remains disabled until draft inspection succeeds;
15. PDF retrieval tested separately.

## 11. Incident stop conditions

Immediately disable write and investigate if:
- unexpected document appears;
- duplicate invoice appears;
- metadata/schema changes;
- integration account permissions change unexpectedly;
- repeated auth failures occur;
- response indicates unexpected company/entity;
- reconciliation returns `unknown`;
- document digest does not match confirmed preview;
- FirstBit returns fields/types outside validated contract.

Security posture is fail-closed: inability to prove safety means no financial mutation.

Explicit owner-requested price/tax/description revisions are allowed only on existing previews. The model returns current-message spans, not numeric prices/rates/provider IDs; deterministic parsing and local row/source binding enforce grounding. FirstBit verifies the original source before applying user proposals and resolves actual VAT records with fixed bounded GET templates. Currency mismatch, unsupported included VAT, ambiguous tax/row and source/line drift fail closed. Every manual preview is non-executable, even with a fake provider or a caller write flag; its digest includes the overrides. This does not establish legal tax applicability or write defaults. See [preview revisions](firstbit/PREVIEW_REVISIONS.md).

Client-choice callbacks are scoped to an authorized private-chat user, random token, original typed command, candidate list and five-minute expiry. Only a stored candidate index can supply the internal selected_id; no raw text/LLM ID or arbitrary UUID callback is accepted. New input/cancel/restart invalidates choices. Adapter re-reads active candidates for the original query before continuing. Candidate names/IDs/TRN remain local or in that authorized Telegram chat, never model context or audit text. Choosing a client does not authorize financial defaults, create/post/PDF or substitution of another client's history.

Spelling-tolerant client search uses fresh name-only in-memory pages, 200 rows/page, bounded at 5000, fixed select/filter/skip/order and duplicate-page/nextLink/schema guards. No company query text enters OData and no name directory is cached, logged, persisted or sent to AI. Fuzzy/transliterated/spoken acronym matches only suggest up to five choices; exact normalized duplicates still require explicit selection. Auto-resolution requires complete discovery and one exact identity ignoring case/spacing/punctuation, followed by a fresh record check. A missing model client may be recovered from a clearly delimited verbatim user request, not an invented name/ID. See [company search](firstbit/COMPANY_SEARCH.md).

Historical supplier mismatch is a separate review gate: both source and contract entities must exist and pass GET validation. The callback accepts only viewing that historical source, after refresh, scoped to the same client/contract/entities. It does not approve a new-document supplier, accounting defaults or write permission. Financial identity drift blocks and changed values require renewed review. Real model context carries field-availability booleans only. Low-confidence speech thresholds are unchanged; the recognized user text may be shown in that same private chat for correction and must not enter audit logs. No transcript persistence was added; private voice rehearsal files contain synthetic speech.
