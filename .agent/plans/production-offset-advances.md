# ExecPlan: support the verified historical debt-offset state

## Observed blocker
A live GET-only reproduction of a historical multi-service preview reached the correct four historical service rows but could not create `ExecutionReview`. `WriteDocument.OffsetAdvancesDebtsAutomatically` accepts only `Literal["No"]`; live OData exposes this property as `Edm.String`, and the source uses another value. The broad fallback hides the validation field behind a generic write blocker.

## Layers to inspect
1. Fresh `$metadata` type/facets and the exact selected source field, kept private.
2. FirstBit UI/evidence for the field’s allowed values and semantics; no inferred defaults.
3. Typed source model, payload carryover, read-back comparison, safe blocker reporting.
4. Regression tests for supported and unknown values.

## Verification criteria
- Accept/carry forward only values whose meaning and OData representation are proven for this configuration; unknown values remain fail-closed with a useful blocker.
- No mutation during discovery/verification; add synthetic regression coverage.
- Existing suite remains green, service restarts healthy, live prepare remains GET-only.
- No invoice create/post/PDF until a separately confirmed preview.

## Findings

- Reviewed detail: document attribute type is Yes / no; full index identifies Enum.YesNo. Fresh OData publishes Edm.String, not an enum list. Runtime posted-source evidence confirms Yes and prior reviewed evidence confirms No.
- Admit only exact Yes/No, preserve source value in the existing frozen review/payload/read-back, and display the behavior before confirmation. Unknown values remain blocked.
- Remove misleading global read-only/draft-only wording in writer responses; report the individual preflight blocker.

## Completed verification

- Focused writer/bot/readonly/tax regressions: 134 passed.
- Full offline suite: 734 passed.
- Fresh production application prepare: four source lines preserved, ExecutionReview admitted, readonly_preview=false; 39 GET requests, zero mutations and zero native UI actions. Exact customer data and rendered preview remain private.
- Service restarted successfully; local/public health reports firstbit_write; webhook matches, pending updates zero, unsigned requests denied. No accounting document created during this fix. A fresh user confirmation is required after restart.
