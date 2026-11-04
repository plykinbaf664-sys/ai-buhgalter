# Delayed Tax Invoice recovery and deleted source

## Observed state

One confirmed operation for a future dated invoice is durable as posted. Fresh GET now finds the same FirstBit InventoryExpense with `DeletionMark=true`, `Posted=false`; no linked TaxInvoice was generated. The bot stores one recovery per user and blocks confirmation of every later preview, while its generic error hides the deleted source.

## Goal

Allow a still valid posted Invoice to resume linked TaxInvoice/PDF work later. Let a user confirm a distinct invoice while an unrelated operation needs attention. Keep the frozen original operation and duplicate protection across restart. Show a precise, safe state when its source is marked for deletion.

## Boundaries

- No automatic recreation, reposting or undeleting a marked Invoice. No journal reset or reuse of its operation ID.
- A deleted/changed source cannot authorize GenerateTaxInvoice.
- Recovery selection must be durable and user scoped; multiple unfinished operations cannot be chosen silently.
- Live FirstBit checks during development are GET only. No production financial mutation for verification.

## Verification

- Synthetic journal/application tests: multiple unfinished operations for one user, distinct invoice confirmation, later targeted retry, restart, repeat delivery, same-basis conflict.
- Adapter tests: deleted source is detected by GET and classified without a new POST/UI action.
- Production GET-only state check and postdeploy readiness.

## Progress

- [x] Inspect code, journal, and fresh live GET evidence.
- [x] Implement durable per-operation recovery and precise deleted-source response.
- [ ] Run tests and deploy.
