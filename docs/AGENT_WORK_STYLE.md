# Agent Work Style

## Work from the real repository

Before coding:
- inspect the affected module;
- inspect direct callers;
- inspect related tests;
- inspect `docs/onec-contract.md` for adapter work.

Do not build a parallel architecture from conversation memory.

## Preserve existing strengths

This repository already has:
- strict Pydantic boundaries;
- good failure-state distinctions;
- explicit preview confirmation;
- idempotency/recovery thinking;
- safe audit logging;
- testable dependency injection.

Extend these patterns.

## Do not over-abstract the FirstBit adapter

Start with the smallest provider boundary that can:
- send safe GET;
- validate OData responses;
- resolve Company/Contract/Item/history;
- map into current domain types.

Do not introduce DB/queue/event bus solely because production integration is being added.

## Separate current code from target design

When docs or plans mention:
- richer `BillingBasis`;
- metadata baseline;
- durable persistence;
- real write;
- custom 1C HTTP;

label them as proposed/planned until code exists.

## Handle fake and real differences intentionally

Fake is a behavior simulator, not a full FirstBit clone.

If real evidence contradicts fake assumptions:
1. keep existing fake behavior if it still tests application contract;
2. add provider-specific real tests;
3. update shared contract only when the difference is truly domain-level.

Do not mutate fake data just to look like one current production client.

## Integration debugging rule

For OData error:
1. capture safe status/error code;
2. inspect `$metadata` or GET response;
3. confirm exact property/EntitySet;
4. update typed model/query;
5. add regression fixture/test.

Never fix an OData path error by trying guessed field variants in production loops.

## Side-effect discipline

For FirstBit/OData, a read-only task means (Telegram/OpenAI calls are separate external side effects and must be reported):
- GET only;
- no POST/PATCH/DELETE;
- no write flag enablement;
- no hidden "test invoice".

For mutation task:
- use ExecPlan;
- separate draft, post and PDF;
- reconcile after uncertainty.

## Secrets

Never:
- put Basic Auth password in committed config;
- log Authorization header;
- include secrets in fixture snapshots;
- surface raw provider exceptions that may contain URL/body/auth context.

Use `SecretStr` and safe provider error codes.

## Verification

Use focused tests first, then full `pytest -q`, then repo scripts where relevant.

Do not claim:
- real Telegram;
- real OpenAI;
- real 1C;
- production readiness

from mock tests alone.

## Avoid unrelated refactors

Real adapter integration should not simultaneously rewrite:
- bot conversation design;
- LLM stack;
- PDF rendering;
- Telegram delivery;
- model selection;

unless a direct contract requires it.

## Report evidence

At the end:
- list changed paths;
- list actual commands run;
- distinguish unit/mock/live;
- mention side effects explicitly;
- state unresolved FirstBit assumptions.
