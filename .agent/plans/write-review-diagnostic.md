# ExecPlan: precise write-admission failure for a historical preview

## Observed behavior

A valid historical preview is read-only because accounting review returns the generic “historical accounting data failed write validation” message. No document was created.

## Trace

Reproduce the exact preview with GET-only FirstBit reads. Identify the failing field or validation boundary in `FirstBitWrite._plan` / `FirstBitProduction._plan` and compare it with fresh source and metadata evidence. Preserve raw evidence only under ignored `.local/firstbit/`; do not put customer data or refs in fixtures/docs.

The exact one-line quantity/total and historical source were reproduced. `WriteDocument.DocumentBasis` rejects the source's nonempty UUID. Fresh `$metadata` exposes the field and polymorphic type as strings; the live type is an unavailable entity. The private full metadata index lists several possible basis-document kinds but does not identify that live subtype. A GET-only diagnostic that relaxed only the local parse guard found no further write-review blocker; it performed no reserve/execute/mutation. Omitting this linkage from a new Invoice without understanding it would change the proposal, so admission remains blocked.

## Verification

Fix a general adapter defect only if evidence proves it. Otherwise expose an actionable, field-specific blocker while retaining fail-closed write admission. Add synthetic regression tests, run targeted/full suites, and perform application-level GET-only preview smoke. Production writes require a separate explicit confirmation in Telegram.

The fix is a field-specific user blocker for nonempty `DocumentBasis` and `GoodsOrder`; synthetic tests assert preview and confirmation show it and issue only GET. Targeted suites: 76 passed locally. Linux full suite and live application-level smoke remain deployment gates.
