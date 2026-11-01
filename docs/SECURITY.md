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

`app/firstbit.py` exposes only bounded GET over verified TLS, with redirects and ambient proxies disabled; one extra identical GET is allowed only after transport error/timeout. Fresh metadata verifies consumed fields/types before resolution. OData text is a quoted literal; reference filters use UUIDs; no nextLink or arbitrary URL execution. Its mutation/PDF methods reject calls. The service rejects unadmitted historical/manual proposals independently of caller permission. Readonly confirmation stops after refresh; its operation state remains unknown. The separate controlled-create subclass and mandatory journal/schema/accounting-review admission are owned by [PRODUCTION_OPERATION](firstbit/PRODUCTION_OPERATION.md); this does not enable automatic posting or PDF.

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
- Non-fake mutation now requires both explicit permission and a durable operation journal; this alone cannot unlock the current FirstBit reader. Exact mechanisms/admission limits: [PRODUCTION_OPERATION](firstbit/PRODUCTION_OPERATION.md).
- preview-only and unadmitted historical/manual proposals are blocked from execution; explicitly reviewed native proposals use PRODUCTION_OPERATION admission; `allow_real_writes=True` alone cannot admit the GET-only FirstBit adapter;
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

Server retention/access/redaction is configured for the project namespace; exact operational settings live in [SERVER_DEPLOYMENT](SERVER_DEPLOYMENT.md). This is not persistent operation storage.

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
- review the actually published surface against the adapter before expanding rollout; the historical 33-object MVP snapshot is not proof of current publication.

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

## 8. Implemented deployment versus remaining admission gaps

Typed real readonly mode, `FIRSTBIT_BASE_URL`/credentials through SecretStr, the GET-only adapter, consumed-field metadata guard and Linux service/HTTPS/private ENV/log retention are implemented. Operational details belong to [SERVER_DEPLOYMENT](SERVER_DEPLOYMENT.md), not a second configuration recipe here. TLS and owner attestation do not independently audit server permissions or network ACLs.

Before write-enabled production, still prove durable operation/receipt/recovery storage and its protection, atomic business uniqueness, restart/concurrency/lost-response recovery, current accounting/default/tax applicability and reviewed payload semantics. Review OData publication and actual least-privilege account rights, network ACL/VPN/IP restrictions, secret rotation/backup/incident procedures and ingress abuse controls. Body bounds/process gate are implemented; proxy rate limiting is not established by the current deployment files. A full reviewed write schema/permissions baseline remains separate from today's consumed-field guard. Exact milestone sequence: [PROJECT_CONTEXT](PROJECT_CONTEXT.md).

## 9. Forbidden shortcuts

Never:
- use administrator or personal employee credentials in runtime;
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

Draft admission requires items 1–13 below; items 14–15 are the subsequent separate posting/PDF gates, not prerequisites to the first controlled draft. All require explicit approved targets.

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

Telegram voice retrieval can repeat getFile or the validated file GET once on transport failure/timeout, under explicit lookup/download bounds. It cannot repeat sendMessage/sendDocument. The default Telegram HTTP transport may retry a failure establishing a connection before HTTP bytes are sent, but never a read/write response failure; uncertain PDF delivery remains frozen. Timing audits add only a parsed-stage marker, never source text/audio/provider bodies.

OpenAI retry is confined to schema-constrained command parsing: at most two same-input calls on connection/timeout or 5xx, 25s per attempt/40s overall; SDK-wide automatic retries remain disabled. No auth/quota, invalid output, refusal or cancellation retry; no repeat of STT/OneC execution. Exhausted voice parsing may show the recognized user text only to its originating authorized private chat, without audit/transcript persistence or provider-data context. Private pre-demo readiness checks use GET for FirstBit; optional deep AI parsing contains synthetic user input only.

Runtime transport recovery permits only one additional identical FirstBit GET after a transport error/timeout, with 0.2s backoff and existing deadlines. HTTP status/auth, oversized bodies, schema/financial validation and cancellation do not retry. This never applies to create/post/delete or operation reconciliation and does not relax TLS/identity/write guards. Local patch repair may deduplicate identical grounded values, recover a verbatim service title and normalize an unambiguous existing-preview action; conflicting values, new client/invoice scope or wrong-row bindings remain blocked.

## 12. Feature boundaries and their owning contracts

Explicit user initial money/services and subsequent preview corrections are non-executable proposals grounded in original message spans and a validated historical baseline. Numeric money/rates are decoded locally; actual tax catalog existence is not proof of legal applicability to a new document. Financial/source/rounding/currency failures stop rather than silently repair. Detailed policy lives in [INITIAL_REQUESTS](firstbit/INITIAL_REQUESTS.md) and [PREVIEW_REVISIONS](firstbit/PREVIEW_REVISIONS.md).

Company/service selection uses locally stored candidate IDs, expiring user tokens and indices, never an LLM-provided or arbitrary callback UUID. Approximate identity requires review; fresh GET checks original-query scope and active state. Selection does not admit a financial mutation. Company search/speech rules live in [COMPANY_SEARCH](firstbit/COMPANY_SEARCH.md); service choices in [INITIAL_REQUESTS](firstbit/INITIAL_REQUESTS.md).

Historical/current-contract supplier mismatch requires explicit review of the historical sample and fresh scope checks; it does not establish a new-document default. Confirmation/recovery state transitions live in [SYSTEM_MAP](SYSTEM_MAP.md). FirstBit method/byte/paging/schema constraints are owned by [READONLY_PIPELINE](firstbit/READONLY_PIPELINE.md).

Raw user audio/text is sent to OpenAI only for enabled STT/language work. No FirstBit records/metadata/catalogs are sent; real intent context is empty draft plus boolean availability. Responses uses store=false; this is not a provider-retention guarantee. Uncertain recognition and failed parsing may show recognized user text only in the originating authorized private chat, not audit logs. SDK temporary audio is removed; in-memory receipts may retain a private pending response until delivery/restart. Private diagnostic captures require minimization and stay outside Git.


## Native browser financial boundary

The optional native FirstBit UI runtime runs on the VPS under the dedicated unprivileged service user, never a personal browser profile. Credentials remain ENV/SecretStr; browser profile, cookies, downloads and diagnostic responses are private ignored accounting state. Browser storage is confined to project .local/firstbit; downloaded files use generated local names rather than untrusted suggested paths. Verify the publication origin before credential entry and the exact native object reference before actions.

Chromium keeps its user-namespace sandbox. A project-binary AppArmor userns profile and a scoped namespace allowlist replace the old blanket namespace denial; do not disable host-wide userns protection or use a no-sandbox/root browser. The service needs a larger task limit for Chromium; writable paths are only its own profile/cache/temp/operation storage. Other projects remain outside this deployment.

The native UI flag is valid only in explicitly enabled firstbit_write mode. Financial clicks follow fresh reviewed schema/expected-document checks and durable one-shot provider claims. Login/navigation/printing retries cannot cover posting or generation clicks. Metadata health checks and safe operator events contain no response bodies; fresh write guards still fail closed independently of the scheduled check. Domain recovery rules and delivery uncertainty are owned by [PRODUCTION_OPERATION](firstbit/PRODUCTION_OPERATION.md).
