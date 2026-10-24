# ExecPlans

## Use an ExecPlan when

Required for:
- real FirstBit adapter spanning multiple modules;
- public domain model changes such as `BillingBasis`;
- adding `APP_MODE=real`;
- persistent operation/recovery storage;
- first real draft;
- posting;
- standard PDF retrieval;
- metadata drift guard;
- multi-worker deployment.

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

## Suggested first plan: `real-firstbit-readonly.md`

Scope:
- typed FirstBit settings;
- typed GET-only OData client;
- real adapter for resolve_client/service/basis;
- historical bookkeeping proposal;
- no writes;
- no PDF;
- no new process architecture.

Acceptance:
- all existing tests green;
- new OData fixture tests green;
- application-level MNSA-style read-only smoke works;
- logs contain no secrets;
- no write method exists/is reachable in the real adapter for this phase.

## Suggested later plan: `real-firstbit-draft.md`

Must not begin until read-only is accepted.

Separately prove:
- basis freshness;
- atomic uniqueness;
- operation ID persistence;
- create payload/defaults;
- lost-response reconciliation;
- restart behavior.

Posting and PDF remain later milestones.

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
