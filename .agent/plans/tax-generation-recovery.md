# ExecPlan: recover native Tax Invoice generation safely

## Observed behavior
A confirmed operation has one posted source Invoice; generation intent/provider claim is durable, but the linked Tax Invoice/PDF is not verified. The bot stops in recovery.

## Steps
1. Fresh GET-only source and linked Tax Invoice reconciliation.
2. Inspect private native runtime error evidence and identify the failed boundary.
3. Correct the general adapter/recovery behavior with synthetic regression tests; never clear an uncertain claim.
4. Continue the already-confirmed operation, using an existing linked document whenever present. If absent, generation requires proof that the prior action failed without a created/in-flight result.
5. Verify native PDF and deliver through the existing durable Telegram flow.

## Verification criteria
At most one source and one linked Tax Invoice; unknown outcomes reconcile before mutation. Read-back validates financial fields and identities. Restart/repeat do not create duplicates. No raw evidence or production identities in Git.

## Findings and implementation
- The source was posted. A source-bound CheckBasisBeforeFilling request was rejected by the platform with SeanceContextException; the native generation method was never dispatched. Raw proof remains private.
- Split live validation from the final send claim. Reopen the native session after OData guards; gate the actual GenerateTaxInvoice request, abort duplicates, and close the context before read-back.
- Durable generation intent without a provider-send claim can resume only for a dispatch-gated provider. An existing claim remains unknown. No journal migration/reset.
- The legacy already-claimed operation requires an exclusive one-time operator continuation after checking the private preflight-rejection proof and fresh global relation absence; no blind retry.

## Production result
The legacy confirmed operation completed through an exclusive, proof-bound single dispatch after the rejected read-only preflight. OData verified the same posted source and exactly one linked posted Tax Invoice with all four lines. The native TaxInvoiceLandscapeEN PDF passed identity/layout/amount checks and was delivered with a Telegram acknowledgement. The original invoice was not created or posted again. The accounting transport in recovery allowed only GET; native UI performed the one approved Tax Invoice generation and native printing. Exact identities, payloads, receipts and PDF remain private.

Native contexts now use fresh temporary profiles per stage and clean only their owned profile. Recovery probes must retain the production no-keepalive OData transport policy when validating native-session behavior.

## Final verification
- Full regression suite: 739 passed. Coverage includes duplicate native requests, platform-only preflight rejection recognition, lost committed/uncommitted responses, restart before provider dispatch, single generation after safe resume, native-print guard ordering, and fresh-profile ownership/cleanup.
- Post-restart completed-operation replay: same source, same Tax Invoice and same PDF hash; 12 GET requests, zero accounting mutations, delivered state retained.
- A separate native read-only navigation opened the same Tax Invoice in a new temporary profile and cleaned that profile on close.
- Service/public health is firstbit_write; webhook matches, queue is empty, unsigned webhook denied.
