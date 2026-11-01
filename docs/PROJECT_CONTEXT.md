# Project context

## Scope and current milestone

Telegram assistant for an accountant preparing invoices in FirstBit ERP / 1C. Version `0.2.0`, Python >=3.10. Historical read-only InvoicePreview remains supported. Controlled-create and optional native TaxInvoice/PDF adapters are implemented; a controlled production E2E completed with recovery, native PDF and Telegram delivery. The current write source of truth is [PRODUCTION_OPERATION](firstbit/PRODUCTION_OPERATION.md).

| Mode | Provider | Current outcome |
|---|---|---|
| `mock` (factory default) | `FakeOneC` with fictitious data | Preview -> confirmation -> fake create/post -> TEST/MOCK PDF |
| `firstbit_readonly` | Real GET-only `FirstBit` | Verified client/contract/services/history -> historical preview -> fresh verification; stop |
| `firstbit_write` | `FirstBitWrite` extends the reader | Reviewed accounting proposal -> explicit confirmation -> controlled draft; optional native provider continues through linked TaxInvoice/PDF. Admission/proof: PRODUCTION_OPERATION |

Mock/readonly modes reject `ONEC_WRITE_ENABLED=true`; fake mutations remain in-memory simulation. Real modes require their separately attested dedicated identity and never substitute fake records on failure. Deployment is a supervised single-worker Linux service; local Windows/ngrok remains a fallback. Operations: [SERVER_DEPLOYMENT](SERVER_DEPLOYMENT.md); dated write rollout evidence: [ExecPlan](../.agent/plans/production-headless-e2e.md).

## User scenario

Text or voice -> controlled intent -> local typed draft -> company/service resolution and clarifications -> historical proposal -> preview/edit/cancel/verify. Company-only discovery can happen before date/service completion. Multiple active catalog services are supported when the selected client's contract and verified per-service history support them; this is not a guarantee for every service/client or unintelligible speech.

Explicit initial amounts/prices/tax are applied as user proposals after a verified historical baseline; omitted fields come from that service's source for the same client/contract. Net line amount is distinct from net unit price. Later edits do not silently reset other fields. The detailed financial policy lives in [INITIAL_REQUESTS](firstbit/INITIAL_REQUESTS.md) and [PREVIEW_REVISIONS](firstbit/PREVIEW_REVISIONS.md).

Company spelling/case/legal-form variations and fuzzy suggestions use [COMPANY_SEARCH](firstbit/COMPANY_SEARCH.md). A company selection only confirms identity. Service selection, quantity clarification and historical-source supplier review may still be needed. Missing history is a blocker, not permission to borrow another client's parameters.

## Domain and actors

Telegram is transport/UI; LLM/STT interprets user language; application controls state and validation; the OneC provider resolves verified accounting facts. AI is not an accounting authority.

- `InvoiceIntent` / `InvoiceDraft`: grounded changes and local incomplete conversational state.
- `InvoiceCommand`: client text, document date, optional service period, services, tax/history requests, initial or existing-preview overrides.
- `ResolvedInvoiceCommand`: stable client/service IDs and locally bound override provenance.
- `BillingBasis`: exactly `key`, `client_id`, `revision`, `preview`. No separate contract/entity columns were added.
- `InvoicePreview`: validated dates/parties/currency/lines/totals and optional typed historical provenance. Ordinary fake document previews require full requisites; historical proposals explicitly allow unresolved new-document defaults.
- `HistoricalProposal.sources` / line `source_id` and `source_line_number`: per-line sources for multi-service proposals; primary source retained.
- `PreparedInvoice`: resolved request + basis + display name. `Invoice`: returned document identity plus confirmed preview digest.
- `OperationState`: `not_started | draft | posted | unknown`; real reader returns `unknown` and does not claim authoritative document reconciliation.

Exact API/types: [onec-contract](onec-contract.md), `app/domain.py`. Runtime/state ownership: [ARCHITECTURE](ARCHITECTURE.md). Flow transitions: [SYSTEM_MAP](SYSTEM_MAP.md).

## Current boundaries

Real FirstBit supplies present read-only identities/history/tax/currency/UOM facts. Defaults are not inferred: supported native admission validates historical accounting carryover and live references, including effective supplier VAT registration. Unsupported cases remain explicit blockers. Historical posted prices are proposals, not permanent current tariffs. Fake instead uses current fake-catalog prices; this difference must be preserved. Provider facts and exact consumed mapping: [integration evidence](firstbit/FIRSTBIT_INTEGRATION_EVIDENCE.md), [read-only pipeline](firstbit/READONLY_PIPELINE.md).

Readonly confirmation only refreshes the proposal. An admitted native confirmation executes the guarded source/linked-document/PDF flow. `/retry` has separate readonly draft and frozen operation branches. A cancellation does not roll back an already started financial operation. Default state is process-local; restart invalidates choices/confirmation/receipts. An optional confirmed-operation journal is implemented, but production write idempotency/E2E remains unproved; see PRODUCTION_OPERATION. No external database or queue is required.

## Remaining milestones

1. Preserve the supported read-only rollout; extend financial variants only with proven metadata/business semantics and tests. Unknown values, included VAT/discounts and missing history currently block.
2. Before controlled real draft-write: prove current supplier/defaults, pricing approval and tax applicability, exact create behavior, least-privilege write permissions, atomic business uniqueness, durable operation/receipt/recovery state, stale-basis protection and authoritative lost-response reconciliation. A reviewed metadata/permission baseline and restart/concurrency tests are required. This is not enabled by flipping an existing flag.
3. Separately admit and inspect a controlled real draft in an explicitly approved target.
4. Separately implement/verify posting, then standard FirstBit PDF; never use mock PDF as an official invoice.
5. Only then demonstrate real writable text/voice E2E, including failure/restart/delivery scenarios. Multi-worker deployment requires durable coordination first.

Write admission/security checklist is owned by [SECURITY](SECURITY.md); transactional adapter obligations by [onec-contract](onec-contract.md). Read-only success does not prove any later milestone.

Confirmed-operation persistence preparation now exists as an optional journal, with remaining production admission/proof limits in [PRODUCTION_OPERATION](firstbit/PRODUCTION_OPERATION.md). This is not real FirstBit write/PDF completion; unconfirmed drafts and receipts remain process-local.
