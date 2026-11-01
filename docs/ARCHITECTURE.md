# Architecture

## Actual runtime

Python >=3.10, FastAPI/Pydantic, HTTPX, official OpenAI SDK and Uvicorn; ReportLab/Pillow and embedded fonts implement mock PDF only. Exact versions are in `requirements*.txt`. One worker, one process-wide admission lock; default state is in-memory. An optional local SQLite confirmed-operation journal is implemented; no external DB/queue/Redis/background financial worker/Docker or CI pipeline is implemented.

`create_app()` defaults to FakeOneC. `APP_MODE=firstbit_readonly` constructs and closes a real reader; `firstbit_write` constructs its controlled-create subclass with a mandatory preprovisioned journal. Admission/limits are owned by [PRODUCTION_OPERATION](firstbit/PRODUCTION_OPERATION.md). Server/local launchers validate settings before starting. Host/service layout: [SERVER_DEPLOYMENT](SERVER_DEPLOYMENT.md); local fallback: [LIVE_DEMO](firstbit/LIVE_DEMO.md).

Native production extends this same provider through app/firstbit_production.py. App/firstbit_tax.py owns typed OData TaxInvoice reconciliation; app/firstbit_ui.py owns serialized native browser navigation/actions/downloads under a dedicated Linux identity. App/schema_monitor.py is a periodic read-only health task, never a financial worker. Enablement and evidence boundaries are owned by [PRODUCTION_OPERATION](firstbit/PRODUCTION_OPERATION.md).

## Module ownership

| Area | Files and responsibility |
|---|---|
| HTTP boundary | `app/main.py`: factory/lifespan, private-chat allowlist, webhook secret, body/read bounds, gate and receipts |
| Domain/API | `app/domain.py`: frozen strict models, totals/digest, commands/basis/provenance/operation state and OneC Protocol |
| Financial orchestration | `app/service.py`: prepare, source-bound overrides, request/provider consistency, refresh, fake execution/reconcile and safe audit |
| Durable confirmed operations | `app/operations.py`: optional transactional journal consumed by service/Bot; admission/limits in [PRODUCTION_OPERATION](firstbit/PRODUCTION_OPERATION.md) |
| Conversation | `app/bot.py`: local drafts, company/service/quantity/supplier choices, confirmation/edit/cancel/retry, receipt-based delivery |
| Language | `app/ai.py`, `app/language.py`, `app/intent.py`, `app/numbers.py`, `app/parser.py`: schema-constrained parsing, source spans, deterministic numbers/dates and draft merge |
| Voice/model choice | `app/voice.py`, `app/model_selection.py`: bounded transcription, confidence classification, supported model selection cached per process |
| Real provider | `app/firstbit.py`: typed settings, fixed GET transport, fresh consumed-schema checks, identities/contracts/services/history/tax/currency/UOM and historical proposal |
| Name matching | `app/company_names.py`: local canonical keys and approximate ranking; similarity is a suggestion, not identity authority |
| Fake provider | `app/fake_onec.py`, `app/fake_data.py`: synthetic catalog, in-memory operations/faults; `app/mock_pdf.py` renders TEST/MOCK PDF |
| Presentation/transport | `app/presentation.py`, `app/telegram.py`, `app/telegram_models.py`: preview text, validated Telegram delivery/file download; `app/http.py`, `app/validation.py`: bounded HTTP/JSON boundaries |
| Configuration | `app/config.py`: supported modes, Telegram/OpenAI ENV and write/fault guards; FirstBitSettings lives in provider |
| Operations | `scripts/run_server.py`, `scripts/server_control.py`, `deploy/`; Windows counterparts `scripts/run_local.py`, `start_readonly_demo.py`, `start_ngrok_demo.py`, `register_demo_webhook.py` |

## Dependency and data direction

```text
Telegram webhook -> Bot -> parser/interpreter + local draft
                           -> InvoiceService -> OneC Protocol
                                                  +-> FakeOneC
                                                  +-> FirstBit GET
                           <- validated PreparedInvoice / clarification
                 <- presentation + validated Telegram transport
```

The LLM cannot invoke provider methods. Real AI receives only original user input, empty provider-derived draft and boolean field availability; provider resolution and number/source binding are local. Monetary initial requests use `InitialInvoiceRequest`, other natural requests/edits `LanguageIntent`, narrow legacy period extraction `Extraction`; strict `parse_command` remains available without AI. Model output is grounded before it becomes `InvoiceCommand`. Mechanisms and transitions: [SYSTEM_MAP](SYSTEM_MAP.md).

Initial money requires a validated baseline, then locally bound source/LineNumber overrides and a second basis read. Multi-service history uses per-line provenance rather than a new engine or a larger BillingBasis schema. Preview changes are part of digest/revision. Exact financial behavior is owned by the two feature guides, not this architecture summary.

## State and identity

`main.py` holds bounded webhook receipts and the process gate. Bot owns `pending`, `client_choices`, `service_choices`, `initial_quantities`, `supplier_reviews`, `contexts`, `last_contexts`, `recoveries`, `delivered` and `delivery_attempted`. FakeOneC holds fake documents. Unconfirmed state is in-memory; an optional confirmed-operation journal can restore frozen recoveries/delivery as described in PRODUCTION_OPERATION. SDK voice uses a temporary file removed in finally, not durable audio storage. Audit logs and deployment state files are operational evidence, not persistence for business operations.

`BillingBasis.key` represents provider-defined business identity. `PreparedInvoice.operation_id = sha256("invoice:v1:" + key)` intentionally excludes revision. Revision and preview digest detect snapshot changes, not duplicate operations across restarts. A returned Invoice must match client/basis and the confirmed preview digest. API/recovery obligations: [onec-contract](onec-contract.md).

Readonly proposal refresh re-reads basis and compares it. Writable/fake refresh reads operation state first, freezes already started operations, and re-resolves only a not-started basis. Execute rejects historical/manual/preview-only proposals unless the real candidate supplies an admitted ExecutionReview and explicit write capability/permission. Candidate admission and rollout are owned by PRODUCTION_OPERATION; production native PDF is not connected.

`TaxInvoiceOneC` is an optional extension to the existing OneC protocol, not a second provider architecture. `InvoiceService` orchestrates linked generation/read-back/finalization and `OperationJournal` persists the relation and one-shot intents; Bot retains its existing delivery path. `TaxInvoiceReference` is a returned hint, `TaxInvoice` a verified provider result, and `TaxInvoicePdf` includes exact document/version/form provenance. The actual FirstBit native capability is not implemented or advertised; only synthetic providers currently exercise it. Contract and reliability obligations: [onec-contract](onec-contract.md), [PRODUCTION_OPERATION](firstbit/PRODUCTION_OPERATION.md).

## Concurrency and operational limits

Webhook receipts have a hard capacity without eviction; gate contention returns 503. A receipt binds update ID to payload fingerprint, holds pending response/prepared state for delivery retry, and clears temporary payload fields after acknowledged handling. Default duplicate/delivery tracking is process-local; an enabled journal persists confirmed-operation delivery uncertainty as described in PRODUCTION_OPERATION. Exact bounds and verification: [SECURITY](SECURITY.md), [VERIFICATION](VERIFICATION.md).

Do not add workers, provider-side transactional uniqueness claims or a new invoice engine based only on old proposed architecture notes. Local confirmed-operation persistence exists; provider-side guarantees and actual real write/PDF verification remain milestones in [PROJECT_CONTEXT](PROJECT_CONTEXT.md).
