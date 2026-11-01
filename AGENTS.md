# AGENTS.md

## Project and discovery

`ai-buhgalteria` — Python/FastAPI Telegram invoice workflow. `mock` implements fake create/post/PDF; `firstbit_readonly` prepares real historical proposals without creating documents. `firstbit_write` adds controlled draft creation and an explicit optional native TaxInvoice/PDF provider; admission and dated rollout evidence → PRODUCTION_OPERATION below. Linux hosting is deployed; local Windows/ngrok is a fallback.

Start with `git status` / `git diff`, then relevant code/tests. This is a router: **do not read all docs for every change**. Local code/tests establish implemented behavior; fresh FirstBit `$metadata`/GET evidence establishes provider facts. Old plans/chat do not override either.

## Routing

| Task | Source of truth |
|---|---|
| Product scope, supported modes, remaining milestones | [PROJECT_CONTEXT](docs/PROJECT_CONTEXT.md) |
| Module ownership, runtime and state | [ARCHITECTURE](docs/ARCHITECTURE.md) |
| End-to-end transitions, confirmation/recovery | [SYSTEM_MAP](docs/SYSTEM_MAP.md) |
| Security, external data and mutation admission | [SECURITY](docs/SECURITY.md) |
| Tests, commands and dated verification evidence | [VERIFICATION](docs/VERIFICATION.md) |
| OneC API and writable-provider requirements | [onec-contract](docs/onec-contract.md), `app/domain.py` |
| FirstBit objects/fields, configuration, schema/transport bounds | [READONLY_PIPELINE](docs/firstbit/READONLY_PIPELINE.md) |
| Company discovery, approximate identity and uncertain speech | [COMPANY_SEARCH](docs/firstbit/COMPANY_SEARCH.md) |
| Initial services/net amounts and per-line historical sources | [INITIAL_REQUESTS](docs/firstbit/INITIAL_REQUESTS.md) |
| Production preparation, durable journal and prospective schema gate | [PRODUCTION_OPERATION](docs/firstbit/PRODUCTION_OPERATION.md) |
| Edits to an existing preview | [PREVIEW_REVISIONS](docs/firstbit/PREVIEW_REVISIONS.md) |
| Integration facts / private metadata coverage | [INTEGRATION_EVIDENCE](docs/firstbit/FIRSTBIT_INTEGRATION_EVIDENCE.md), [METADATA_COVERAGE](docs/firstbit/FIRSTBIT_METADATA_COVERAGE.md) |
| Linux service, HTTPS, protected ENV, readiness/rollback | [SERVER_DEPLOYMENT](docs/SERVER_DEPLOYMENT.md) |
| Local Windows/tunnel fallback | [LIVE_DEMO](docs/firstbit/LIVE_DEMO.md) |
| Durable rationale / working style / execution plans | [DECISIONS](docs/DECISIONS.md), [AGENT_WORK_STYLE](docs/AGENT_WORK_STYLE.md), [.agent/PLANS](.agent/PLANS.md) |

## Cross-cutting guards

- Keep typed Pydantic boundaries and existing OneC/service/bot ownership. Do not add layers or rewrite working flows without a concrete need.
- Production FirstBit: dedicated least-privilege account, ENV/SecretStr, verified TLS. Readonly mode permits GET only; controlled-create admission → PRODUCTION_OPERATION. Successful preview never authorizes writes without explicit confirmation.
- LLM extracts user intent/spans, not provider IDs or financial defaults. Provider records/catalogs/metadata never enter real AI context. Explicit user amounts/tax are locally grounded proposals, not authoritative tariffs.
- Ambiguity, schema mismatch, unsupported arithmetic or unknown financial state fails closed. Approximate identity requires explicit selection; repeated service rows stay separate.
- Any attempted edit revokes confirmation. Readonly confirmation stops after refresh; controlled creation preserves the frozen operation/digest and never retries an uncertain mutation blindly.
- Default drafts/buttons/receipts are process-local: one worker. Optional confirmed-operation journal is described in PRODUCTION_OPERATION; controlled real E2E and restart/read-only replay are proved; exact evidence is in VERIFICATION.
- No customer names, production IDs/TRNs, credentials or raw business/metadata dumps in Git. Private integration evidence stays under ignored `.local/firstbit/`.

## Plans and completion

Use an ExecPlan for real adapter/schema changes, metadata guard changes, persistence/concurrency/deployment changes, or real draft/write/post/PDF admission; see `.agent/PLANS.md`. Completed plans are historical records, not current runtime instructions.

Before completion run relevant checks, report actual commands/results and separate offline, real API, synthetic audio and actual human Telegram evidence. Explicitly state production contact and side effects. Never call real create/post/PDF ready based on readonly tests. Documentation changes follow the ownership map in [README_CONTEXT_ENGINEERING](README_CONTEXT_ENGINEERING.md).
