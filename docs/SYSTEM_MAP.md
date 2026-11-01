# Invoice system map

This document owns state transitions. Financial source rules, field mapping, security controls and test commands live in the linked specialist guides.

## 1. Admission and delivery receipt

`POST /telegram/webhook` -> secret -> bounded body/typed Update -> allowlisted private actor -> process gate -> receipt fingerprint/deduplication -> `Bot.handle`.

Unauthorized chat/actor is acknowledged without business processing; invalid secret/body or identity-conflicting update is rejected. Busy/capacity/delivery failures return non-success. An existing receipt reuses prepared response rather than repeating STT/LLM. Admission implementation: `app/main.py`; transport/delivery: `app/telegram.py`, bot `Receipt`.

## 2. Language -> local draft

Text, or validated Telegram OGG/Opus download -> STT -> `CommandInterpreter` -> strict command or grounded intent -> `merge_intent` -> `InvoiceDraft.command()`.

The narrow parser/legacy extraction handles explicit month/year compatibility. Natural requests/edits use LanguageIntent; new requests with line money use InitialInvoiceRequest. Model word spans are checked against original user input; numeric money/rates are decoded locally. Date and service period are distinct; incomplete dates require clarification. No FirstBit record enters real AI draft context.

New input revokes previous choice tokens; an attempted edit/voice revokes prior confirmation before interpretation. Low-confidence fake speech is rejected. Real low-confidence new speech may only continue with mandatory company selection, including a sole exact candidate; uncertain edits/financial initial overrides remain blocked. Details: [COMPANY_SEARCH](firstbit/COMPANY_SEARCH.md), [INITIAL_REQUESTS](firstbit/INITIAL_REQUESTS.md).

Readonly company-only requests can call discovery before a complete invoice/date exists, without LLM. Choices retain the original command or partial draft; numeric replies and callbacks use the same scoped selection checks. No match or ambiguous identity is a clarification, not permission to guess.

## 3. Identity/services/basis -> preview

```text
InvoiceService.prepare
  -> resolve_client (or explicit verified choice / existing scoped identity)
  -> resolve_service for each requested slot
  -> ResolvedInvoiceCommand
  -> resolve_basis -> validated BillingBasis.preview
  -> initial monetary overrides, if any:
       bind to baseline source ID + LineNumber -> second resolve_basis
  -> validate requested period/services/quantity/tax and overrides
  -> canonical PreparedInvoice
```

Possible continuations in Bot: company choice, service choice/refinement, initial-quantity clarification, missing business facts, or supplier review. Tokens are user-scoped/expiring; chosen IDs are locally stored candidates and freshly checked. Choosing identity never confirms amounts/defaults or write permission.

Actual FirstBit reads: fresh schema -> active company -> validated default/unique active contract -> active Service items -> posted client/contract-scoped history -> tax/UOM/currency/entities -> typed historical proposal. Exact sets/limits: [READONLY_PIPELINE](firstbit/READONLY_PIPELINE.md). Multiple services may use different validated historical sources under the constraints in [INITIAL_REQUESTS](firstbit/INITIAL_REQUESTS.md).

## 4. Supplier review and editing

`Bot.show_preview` stores canonical local DraftContext. If historical issuer differs from current contract issuer, Bot first requires an explicit expiring historical-source review and re-reads the proposal before accepting it. Scope covers client/contract/both entities; changed identity blocks and changed snapshot requires renewed review. This reviews an historical sample, not the supplier of a new real invoice.

Then Telegram receives the preview and five-minute confirmation/edit/cancel token. Price/amount/VAT/display-name/date/quantity changes reuse the local draft. Monetary edits bind to each original source/LineNumber; changing source identity cannot silently transfer them. Other services/rows are not dropped or merged. New validated preview means a new token. Details: [PREVIEW_REVISIONS](firstbit/PREVIEW_REVISIONS.md).

## 5. Confirmation and provider capabilities

| Branch | Refresh | Result when unchanged |
|---|---|---|
| FirstBit preview-only, or an unadmitted manual proposal | Re-read resolve_basis; no authoritative read_operation claim | Verify-only acknowledgement; no execute/PDF |
| Ordinary fake preview | Read operation, reject unknown, freeze already started; re-read basis if not started | Pass PreparedInvoice to fake execute |

An admitted real writable proposal refreshes its reviewed basis/schema and authoritative operation state, then executes through the same service/journal. Native capability continues through linked TaxInvoice; the base writer stops at verified draft.

Any changed refreshed snapshot causes a new preview/confirmation. Relevant supplier review is re-evaluated. Failed real refresh revokes confirmation but does not manufacture a financial recovery state. Real `read_operation=unknown` remains truthful and cannot be treated as `not_started`.

## 6. Execution and writable-provider contract

`execute` -> reject preview-only or unadmitted historical/manual proposals -> read_operation -> if unknown stop -> guarded ensure_draft -> guarded ensure_posted -> validated PDF -> Telegram.

Document identity and confirmed digest are checked throughout; posting must keep the same document. After an exception during create/post, reconcile once read-only and raise a classified failure; never retry mutation blindly in the same call. Fake supports this in memory; the real adapters use durable claims and authoritative OData read-back. Current admission and native interfaces: [PRODUCTION_OPERATION](firstbit/PRODUCTION_OPERATION.md). Exact contract: [onec-contract](onec-contract.md).

## 7. Retry and cancellation

| State | `/retry` | New input / cancel |
|---|---|---|
| Readonly draft after discovery/read failure | Reuses typed draft/selection; discovery if incomplete or prepare new proposal, no new STT/LLM | Can replace/cancel draft |
| Frozen confirmed operation recovery | Continues the same PreparedInvoice/operation ID after authoritative provider state read | New invoice/voice blocked; cancel does not roll back document |
| No retained context/recovery | Reports nothing to recover | New request required |

The bot can retain a read-only draft even after a preview; retry is not restricted to mutation recovery. Restart loses unconfirmed conversation state. With the optional durable journal, frozen confirmed operations are restored for reconciliation; this includes linked TaxInvoice work when a capable provider is supplied.

## 8. PDF and uncertain delivery

FakeOneC -> mock renderer -> validated PdfDocument -> sendDocument remains the mock flow. An optional TaxInvoice-capable provider continues a verified posted source through linked-document reconciliation/generation, actual-state-dependent posting, native TaxInvoice PDF and both-document read-back before the same delivery transport. The optional native FirstBitProduction subclass provides this capability; implementation is not evidence that a new production E2E has completed. Exact contract/admission: [PRODUCTION_OPERATION](firstbit/PRODUCTION_OPERATION.md).

Default delivery dedupe is process-local. With the journal, PDF provenance/cache and per-user delivery attempts survive restart. A lost delivery acknowledgement freezes automatic resend; it does not regenerate either accounting document. Text/preview receipt delivery can retry within its bounded attempts. `/cancel` is never a rollback of a financial side effect.

## 9. Metadata and hosting

FirstBit resolve_client/resolve_service/resolve_basis fetch fresh consumed schema before business reads. A missing/wrong field/type blocks resolution today, not merely a future write. This is not a full write-baseline or permissions audit. Mapping details: [READONLY_PIPELINE](firstbit/READONLY_PIPELINE.md).

Server ingress: existing HTTPS -> project Caddy routes -> loopback single-worker service. Local fallback uses Windows app/tunnel launchers and can change the bot's webhook, so it must not be started as if independent of the server deployment. Operations: [SERVER_DEPLOYMENT](SERVER_DEPLOYMENT.md), [LIVE_DEMO](firstbit/LIVE_DEMO.md).
