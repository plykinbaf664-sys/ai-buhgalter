# ExecPlans

## Use an ExecPlan when

Required for:
- real FirstBit adapter spanning multiple modules;
- public domain model changes such as `BillingBasis`;
- adding any new real write-capable mode/provider admission;
- persistent operation/recovery storage;
- first real draft;
- posting;
- standard PDF retrieval;
- metadata drift guard;
- multi-worker deployment;
- a new deployment topology or ownership/cutover boundary.

Not required for a small isolated validator/test/doc correction.

## Plan template

```markdown
# [Title]

## Goal
Observable result.

## Current repository evidence
Exact modules/tests/config involved.

## External evidence
FirstBit metadata/runtime facts used.
Clearly separate from code truth.

## Scope
Included and excluded work.

## Invariants
Human confirmation, preview digest, operation identity, unknown blocking, secrets, etc.

## Proposed changes by module
Concrete existing paths first.

## Domain/schema impact
Especially BillingBasis / InvoicePreview / OperationState.

## Provider/API contract
GET/write endpoints, Pydantic external models, timeouts.

## Side effects
Which calls mutate what.

## Failure/recovery matrix
Before request / after server commit / lost response / stale revision / duplicate.

## Verification matrix
Focused tests
→ full pytest
→ demo/smoke
→ production GET-only
→ later controlled mutation.

## Rollout
Feature flags/config, safe target, stop conditions.

## Risks/unknowns
Only unresolved facts.

## Progress
Living checklist.

## Result
Actual implementation and verification.
```

## Current and completed work

The real readonly adapter and single-worker Linux deployment are implemented. Completed records in `.agent/plans/` are historical execution evidence, not current rules or a request to rerun old rollout steps. Use their linked source-of-truth docs for present behavior. Case-only parser/discovery investigation notes have been archived privately rather than kept as permanent context.

Next possible plan: controlled real draft admission, only with separate explicit authorization and an approved target. Prove current supplier/financial/default semantics, exact create behavior, dedicated rights, reviewed write schema, atomic uniqueness, durable operation/receipt/recovery storage, stale-basis handling and lost-response/restart/concurrency recovery first. Posting and standard PDF remain later separate plans. See [remaining milestones](../docs/PROJECT_CONTEXT.md).

## Mandatory security section for real-1C plans

Every real-1C ExecPlan must explicitly state:

- integration account and required permissions;
- network/TLS assumptions;
- secrets source/rotation;
- exact OData EntitySets and fields accessed;
- data sent to external AI providers;
- mutation methods enabled;
- rollback/recovery/idempotency;
- metadata-drift stop condition;
- logging/redaction;
- production stop/disable procedure.
