# Architecture

## Technology actually present

Runtime:
- Python >= 3.10
- FastAPI 0.141.1
- Pydantic 2.13.5
- HTTPX 0.28.1
- OpenAI SDK 3.20.0
- Uvicorn 0.54.0
- ReportLab 5.0.1 only for fake PDF

Test/dev:
- pytest 9.1.1
- PyMuPDF for PDF inspection

No DB, queue, Docker, migrations or CI config were found in current `main`.

## Actual module ownership

### `app/domain.py`
Owns domain contracts and safety types:
- `StrictModel`, `ExternalModel`;
- money/quantity/date bounds;
- `InvoiceCommand`;
- `ResolvedInvoiceCommand`;
- `InvoicePreview`;
- `BillingBasis`;
- `PreparedInvoice`;
- `Invoice`;
- `OperationState`;
- `PdfDocument`;
- exceptions;
- `OneC` Protocol.

### `app/service.py`
Financial orchestration:
- `prepare`;
- `refresh`;
- `_read_state`;
- `execute`;
- write guard;
- reconciliation after uncertain mutation;
- safe audit events.

### `app/bot.py`
Telegram conversational/state-machine layer:
- pending confirmation;
- per-user expiring client-choice buttons, bound to the original typed command and candidate IDs;
- separate expiring supplier review when historical issuer differs from the current contract; the review is scoped to client/contract/entity IDs and refreshed before showing the proposal;
- edit/cancel;
- retry;
- draft context;
- recovery freeze;
- delivery dedupe.

Real provider intent context contains only local field-availability booleans, without provider names/IDs/rows/prices. Raw user corrections still need grounded spans and local merge. Low-confidence STT retains its thresholds and shows the recognized user text only to the same authorized chat for correction, never in audit logs. Demo restart archives the existing safe operational logs under ignored `.local/runtime/archive/` before launching new processes; business/session state remains process-local.

### `app/main.py`
HTTP boundary:
- app creation;
- lifespan;
- HTTPX/OpenAI clients;
- webhook secret check;
- allowlist/private-chat enforcement;
- request body limits;
- webhook receipt dedupe;
- process-wide gate.

### `app/config.py`
Strict ENV configuration.

Important current fact:
```python
mode: Literal["mock", "firstbit_readonly"] = "mock"
```

Both modes reject `ONEC_WRITE_ENABLED=true`. FirstBit credentials/config live in typed `FirstBitSettings`; ENV/SecretStr only.

### `app/firstbit.py`
GET-only real provider and minimal external Pydantic response models. Owns bounded HTTPS I/O, fresh consumed-schema checks, Company/Contract/Item/history/VAT/currency/UOM resolution and non-executable historical proposal mapping. Live prepare/refresh verified on one client; synthetic tests prove separate clients keep their own contract/history/amounts, independently of smoke ENV. Query spaces use RFC3986 `%20`; unsupported tolower and equality on unbounded DescriptionFull are avoided. Double wire values still undergo Decimal/domain validation, and Int64 string decoding is limited to LineNumber. No create/post/PDF transport exists. Exact objects/fields: `firstbit/READONLY_PIPELINE.md`.

### `app/fake_onec.py`
In-memory implementation of `OneC`.

### `app/fake_data.py`
Fake clients/services/tax/bank/etc fixtures.

### `app/ai.py`, `app/language.py`, `app/intent.py`
Controlled language interpretation and draft merge.

### `app/voice.py`
Voice validation + STT.

### `app/telegram.py`, `app/telegram_models.py`
Telegram I/O and typed response models.

### `app/mock_pdf.py`
Fake-only PDF renderer. Never reuse for production accounting PDF.

### Local demo runtime scripts
`scripts/run_local.py` loads private ENV and enforces real read-only / OpenAI / disabled writes before single-worker Uvicorn startup. `start_readonly_demo.py` manages only recorded owned Windows app/tunnel processes with hidden windows; `register_demo_webhook.py` validates local state, public app health and Telegram registration responses. Runtime state/logs stay under ignored `.local/runtime/`. No process architecture change or persistent financial storage is introduced. See `firstbit/LIVE_DEMO.md` for actual live status and billing blocker.

## High-level current runtime

The diagram below describes mock execution. In `firstbit_readonly`, provider reads produce a `HistoricalProposal` inside `InvoicePreview`; confirmation refreshes the proposal and stops with a verification acknowledgement. Execution/PDF are blocked. Real provider draft context is never forwarded to AI. Optional unresolved new-document fields are permitted only on this historical proposal; financial line arithmetic remains fully validated.

```text
POST /telegram/webhook
        |
        v
secret + allowlist + private-chat validation
        |
        v
receipt dedupe + process gate
        |
        v
Bot.prepare()
        |
        +--> voice -> Telegram download -> STT
        |
        +--> CommandInterpreter / strict parser
        |
        v
InvoiceService.prepare()
        |
        +--> OneC.resolve_client()
        +--> OneC.resolve_service()
        +--> OneC.resolve_basis()
        |
        v
PreparedInvoice / InvoicePreview
        |
        v
5-minute confirmation token
        |
        v
InvoiceService.refresh()
        |
        +--> read_operation()
        +--> resolve_basis() again if not_started
        |
        v
InvoiceService.execute()
        |
        +--> read_operation()
        +--> ensure_draft()
        +--> ensure_posted()
        +--> get_pdf()
        |
        v
Telegram sendDocument
```

## Domain validation strategy

`StrictModel`:
- `strict=True`;
- `extra="forbid"`;
- `frozen=True`;
- `hide_input_in_errors=True`;
- `revalidate_instances="always"`;
- `allow_inf_nan=False`.

`ExternalModel` permits extra provider fields but validates consumed fields.

Use same pattern for real OData response models:
- validate external envelope;
- transform to strict internal models;
- never let raw provider dict leak deep into domain logic.

## Preview integrity

`InvoiceLine` recomputes:
- subtotal;
- tax;
- total.

`InvoicePreview` recomputes aggregate totals.

`InvoicePreview.digest` = SHA-256 of model JSON.

`Invoice.preview_digest` must equal confirmed preview digest.

This is a key anti-mismatch guard and must survive real adapter integration.

## Billing identity and operation identity

Current:
```text
operation_id = SHA256("invoice:v1:" + BillingBasis.key)
```

Revision is intentionally excluded.

Meaning:
- changing price/quantity/tax/revision should not silently create a second operation for same business invoice identity;
- `BillingBasis.key` must therefore represent business identity, not snapshot content.

When designing real basis key, keep the semantics from `docs/onec-contract.md`.

## Write flow

`InvoiceService.execute()` does:

```text
read_operation
if unknown -> STOP
if not_started:
    write_guard
    ensure_draft
if draft:
    write_guard
    ensure_posted
get_pdf
```

If exception occurs after calling create/post:
- state becomes unknown;
- service does one `_read_state()` reconciliation;
- it does not automatically re-run mutation in that call;
- raises `WorkflowFailure` with reconciled state.

## Pre-confirm refresh

`InvoiceService.refresh()`:
- calls `read_operation`;
- if `unknown` -> recovery path;
- if operation already started -> freezes existing prepared state;
- if `not_started` -> resolves basis again;
- basis key must stay unchanged;
- changed snapshot leads to new preview and new confirmation.

## Webhook boundary facts

Current code:
- FastAPI OpenAPI/docs disabled.
- Header: `X-Telegram-Bot-Api-Secret-Token`.
- HMAC constant-time comparison.
- Body max 32 KiB.
- Body read timeout 5 s.
- Only numeric allowlisted user IDs.
- Only private chat where `chat.id == sender.id`.
- Bot actors, sender_chat and forwards rejected.
- process-wide `asyncio.Lock`, acquire timeout 0.1 s.
- max 10,000 receipt records, no eviction.
- same `update_id` + changed payload -> HTTP 409.
- max 3 delivery attempts per receipt.

## HTTP client facts

In `main.py`:
- Telegram HTTPX timeout 10s, connect 3s;
- AI HTTPX timeout 20s, connect 3s;
- `follow_redirects=False`;
- `trust_env=False`;
- OpenAI SDK max_retries=0.

## Bot process-local state

`Bot` keeps:
- `pending`;
- `contexts`;
- `last_contexts`;
- `recoveries`;
- `delivered`;
- `delivery_attempted`.

This is currently memory-only.

Implications:
- one-worker design;
- restart loses workflow state;
- production durable idempotency cannot rely on this memory.

## Current config boundary

`Settings` currently contains:
- Telegram token/secret/allowlist;
- `APP_MODE=mock`;
- `ONEC_WRITE_ENABLED`;
- fake fault injection;
- OpenAI mode/key/model config.

FirstBit ENV fields now exist in `FirstBitSettings`; see `firstbit/READONLY_PIPELINE.md`. Credentials are ENV/SecretStr only.

Real adapter work should introduce typed SecretStr-backed settings without weakening existing mock guard.

## Real FirstBit adapter direction

Client lookup now uses `app/company_names.py` over bounded fresh `CompanyName` pages from the existing adapter; `Company` details are read only for actual choices/selection. No persistent index or new service. `LanguageIntent.to_intent` can recover a missing client only from a verbatim explicitly delimited invoice phrase. Similarity/transliteration remains a button suggestion; IDs and provider data stay out of AI. See [company search](firstbit/COMPANY_SEARCH.md).

Explicit user price/VAT/display-name revisions flow through typed `preview_overrides` in the existing draft/command/resolve_basis path. The model supplies spans; `app/numbers.py` supplies deterministic numbers, service binds source/line identity, provider verifies tax and computes totals. See [preview revisions](firstbit/PREVIEW_REVISIONS.md).

Recommended ownership:
```text
app/onec/               # or another small provider boundary consistent with repo
  models.py             # ExternalModel/Pydantic OData payloads
  client.py             # GET-only typed HTTP layer first
  adapter.py            # OneC Protocol implementation
  mapping.py            # reviewed constants/object map if needed
```

Exact paths are not mandated; inspect current style first. Avoid adding unnecessary layers.

Read-only v1 should implement:
- `resolve_client`;
- `resolve_service`;
- `resolve_basis`;
- safe provider errors.

Keep `ensure_draft`, `ensure_posted`, `get_pdf` disabled/not implemented for real adapter until separate approval.

## Confirmed OData resolution rules

### Company
`Catalog_Companies`:
- ignore folder;
- ignore deleted;
- exact normalized Description/DescriptionFull first;
- alias mapping may point to Ref;
- fuzzy only proposes candidates;
- persist Ref.

### Contract
`Catalog_CompanyContracts`:
- prefer valid default ref;
- validate owner;
- validate active;
- fallback to active owner contracts;
- require unique fallback.

### Bookkeeping service
Confirmed production Item:
`Accounting and bookkeeping services`.

Do not treat ItemPrices as authoritative in this specific integration unless later evidence changes.

### Historical invoice
For Company+Contract:
- `Document_InventoryExpense`;
- posted;
- not deleted;
- newest first;
- find first invoice containing bookkeeping Item;
- preserve all matching rows.

Historical values are proposal/preview input, not a forever tariff.

## Important unresolved areas

Before real write:
- exact direct OData create semantics;
- which UI defaults execute through Standard OData;
- atomic uniqueness mechanism in 1C;
- persistence of operation ID;
- posting action semantics;
- standard print form retrieval;
- durable app-side recovery across restart;
- multi-process concurrency.

Do not mark these solved from metadata alone.

## Security boundary

Подробная модель угроз, least-privilege правила, FirstBit/OData exposure, data minimization, TLS/secret requirements и write-admission gate находятся в `docs/SECURITY.md`.

Architecture changes that affect:
- credentials;
- FirstBit permissions;
- OData surface;
- data sent to OpenAI;
- persistence;
- network exposure;
- write/retry/recovery

must be reviewed against that document.
