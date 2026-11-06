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

Possible continuations in Bot: company choice, service choice/refinement, initial-quantity clarification, or missing business facts. Tokens are user-scoped/expiring; chosen IDs are locally stored candidates and freshly checked. Choosing identity never confirms amounts/defaults or write permission.

Actual FirstBit reads: fresh schema -> active company -> validated default/unique active contract -> active Service items -> posted client/contract-scoped history -> tax/UOM/currency/entities -> typed historical proposal. Exact sets/limits: [READONLY_PIPELINE](firstbit/READONLY_PIPELINE.md). Multiple services may use different validated historical sources under the constraints in [INITIAL_REQUESTS](firstbit/INITIAL_REQUESTS.md).

## 4. Preview and editing

`Bot.show_preview` stores canonical local DraftContext and presents the preview immediately. If historical issuer differs from current contract issuer, both organizations are shown before the ordinary confirmation. Refresh rechecks the live source and rotates the preview when financial values change; changed identity invalidates the old confirmation.

Then Telegram receives the preview and five-minute confirmation/edit/cancel token. Price/amount/VAT/display-name/date/quantity changes reuse the local draft. Monetary edits bind to each original source/LineNumber; changing source identity cannot silently transfer them. Other services/rows are not dropped or merged. New validated preview means a new token. Details: [PREVIEW_REVISIONS](firstbit/PREVIEW_REVISIONS.md).

An expired or superseded preview button reopens the latest local preview with a fresh token; it never reuses an expired token or executes an older confirmed snapshot after a newer preview appears. A failed preconfirmation read keeps the current preview confirmable and creates no durable recovery entry. Recovery begins only for an actually reserved/started confirmed operation.

## 5. Confirmation and provider capabilities

| Branch | Refresh | Result when unchanged |
|---|---|---|
| FirstBit preview-only, or an unadmitted manual proposal | Re-read resolve_basis; no authoritative read_operation claim | Verify-only acknowledgement; no execute/PDF |
| Ordinary fake preview | Read operation, reject unknown, freeze already started; re-read basis if not started | Pass PreparedInvoice to fake execute |

An admitted real writable proposal refreshes its reviewed basis/schema and authoritative operation state, then executes through the same service/journal. Native capability continues through linked TaxInvoice; the base writer stops at verified draft.

Any changed refreshed snapshot causes a new preview/confirmation. Failed real refresh revokes confirmation but does not manufacture a financial recovery state. Real `read_operation=unknown` remains truthful and cannot be treated as `not_started`.

## 6. Execution and writable-provider contract

`execute` -> reject preview-only or unadmitted historical/manual proposals -> read_operation -> if unknown stop -> guarded ensure_draft -> guarded ensure_posted -> validated PDF -> Telegram.

Document identity and confirmed digest are checked throughout; posting must keep the same document. After an exception during create/post, reconcile once read-only and raise a classified failure; never retry mutation blindly in the same call. Fake supports this in memory; the real adapters use durable claims and authoritative OData read-back. Current admission and native interfaces: [PRODUCTION_OPERATION](firstbit/PRODUCTION_OPERATION.md). Exact contract: [onec-contract](onec-contract.md).

## 7. Retry and cancellation

| State | `/retry` | New input / cancel |
|---|---|---|
| Readonly draft after discovery/read failure | Reuses typed draft/selection; discovery if incomplete or prepare new proposal, no new STT/LLM | Can replace/cancel draft |
| Frozen confirmed operation recovery | Continues the selected PreparedInvoice/operation ID after authoritative provider state read; with several unfinished operations, presents a user-scoped choice | A new FirstBit request receives a separate operation ID even for the same client/date. Cancel clears only the current preview and never rolls back a confirmed operation |
| No retained context/recovery | Reports nothing to recover | New request required |

The bot can retain a read-only draft even after a preview; retry is not restricted to mutation recovery. Restart loses unconfirmed conversation state. With the optional durable journal, all unfinished confirmed operations are restored for reconciliation; this includes linked TaxInvoice work when a capable provider is supplied. A retry of one operation does not clear a separate current preview.

For production `/retry`, the current confirmed operation is preferred. If several old operations remain after restart, the bot checks their live source state, ignores deletion-marked ones for the automatic choice and shows one labeled choice only when several remain possible. A repeat confirmation of the same token reuses that frozen operation; an old edit/confirm button points to the current preview, rotating an expired token. Telegram buttons are cleared after a callback where supported. Once a known draft/posted state is recovered, the bot makes one bounded GET-first continuation of the same operation; unknown financial outcomes still require reconciliation. Delivery remains one-shot. The native file is sent as `Tax Invoice.pdf`.

Recovery choices are revalidated against the durable user-owned operation and live 1C state when clicked. Deleted, already delivered or genuinely unknown operations are not offered as actionable choices; they do not block a new independent preview. Transient failures get one delayed GET-first automatic continuation of the same frozen operation, while duplicate financial mutations remain prohibited by journal claims and read-back. An unresolved outcome is reported plainly rather than cycled through the same selection buttons.

If 1C returns a document with the operation marker but with fields differing from the confirmed snapshot, this is a read-back mismatch: the bot neither posts that document nor recreates it. The old operation is excluded from actionable retry choices, while a separate new request remains available. Provider-specific field evidence belongs in private `.local/firstbit/` until a safe correction path is proved.

In the production deployment, a confirmed operation is reserved durably before the webhook acknowledges it. A background task continues that frozen operation through Invoice, TaxInvoice, native PDF and one-shot Telegram delivery; the webhook does not wait for FirstBit printing. While printing runs, the bot sends periodic progress. A failed native print gets one delayed automatic retry of the same TaxInvoice without a new financial mutation. On restart, confirmed undelivered operations with readable live state are resumed automatically. Unknown financial or Telegram delivery outcomes remain subject to reconciliation rather than blind repetition.

A new FirstBit request always prepares a new preview and independent operation; a prior request with the same client/date or historical sample does not seize it. `/retry` lists only unfinished confirmed operations and continues the selected frozen snapshot, including a posted Invoice awaiting its TaxInvoice/PDF. A source marked for deletion affects its own operation, never a newly confirmed one. Legacy mock/v1 deterministic bases retain their existing duplicate behavior. Editing a preview cannot modify an Invoice already written in 1C; that correction needs a separate verified document-amendment workflow.

## 8. PDF and uncertain delivery

FakeOneC -> mock renderer -> validated PdfDocument -> sendDocument remains the mock flow. An optional TaxInvoice-capable provider continues a verified posted source through linked-document reconciliation/generation, actual-state-dependent posting, native TaxInvoice PDF and both-document read-back before the same delivery transport. The optional native FirstBitProduction subclass provides this capability; implementation is not evidence that a new production E2E has completed. Exact contract/admission: [PRODUCTION_OPERATION](firstbit/PRODUCTION_OPERATION.md).

Default delivery dedupe is process-local. With the journal, PDF provenance/cache and per-user delivery attempts survive restart. A lost delivery acknowledgement freezes automatic resend; it does not regenerate either accounting document. Text/preview receipt delivery can retry within its bounded attempts. `/cancel` is never a rollback of a financial side effect.

## 9. Metadata and hosting

FirstBit resolve_client/resolve_service/resolve_basis fetch fresh consumed schema before business reads. A missing/wrong field/type blocks resolution today, not merely a future write. This is not a full write-baseline or permissions audit. Mapping details: [READONLY_PIPELINE](firstbit/READONLY_PIPELINE.md).

Server ingress: existing HTTPS -> project Caddy routes -> loopback single-worker service. Local fallback uses Windows app/tunnel launchers and can change the bot's webhook, so it must not be started as if independent of the server deployment. Operations: [SERVER_DEPLOYMENT](SERVER_DEPLOYMENT.md), [LIVE_DEMO](firstbit/LIVE_DEMO.md).
