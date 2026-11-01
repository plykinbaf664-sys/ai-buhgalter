# Project context index

`AGENTS.md` is the short entry router. Read only the flow affected by a task; current code/tests and fresh provider evidence outrank prose. This index describes ownership, rather than repeating implementation rules.

| Document | Owns |
|---|---|
| [README](README.md) | Getting started, mode distinction and user-facing examples |
| [PROJECT_CONTEXT](docs/PROJECT_CONTEXT.md) | Product scope and remaining milestones |
| [ARCHITECTURE](docs/ARCHITECTURE.md) | Module ownership, runtime, process-local state |
| [SYSTEM_MAP](docs/SYSTEM_MAP.md) | End-to-end transitions and recovery branches |
| [SECURITY](docs/SECURITY.md) | Normative trust boundaries and write-admission requirements |
| [VERIFICATION](docs/VERIFICATION.md) | Actual commands, regression matrix, dated results and evidence limits |
| [DECISIONS](docs/DECISIONS.md) | Durable rationale; mechanics link to their owner |
| [AGENT_WORK_STYLE](docs/AGENT_WORK_STYLE.md) | Working guidance |
| [onec-contract](docs/onec-contract.md) | Adapter API, including future writable-provider guarantees |
| [SERVER_DEPLOYMENT](docs/SERVER_DEPLOYMENT.md) | Linux deployment, protected ENV, HTTPS, operations/rollback |
| [READONLY_PIPELINE](docs/firstbit/READONLY_PIPELINE.md) | Implemented FirstBit mapping, settings, transport/schema bounds |
| [COMPANY_SEARCH](docs/firstbit/COMPANY_SEARCH.md) | Company discovery, matching/selection, uncertain voice and readonly retry |
| [INITIAL_REQUESTS](docs/firstbit/INITIAL_REQUESTS.md) | Initial money/services, service discovery and historical source composition |
| [PRODUCTION_OPERATION](docs/firstbit/PRODUCTION_OPERATION.md) | Optional confirmed-operation journal, prospective write-schema pin and unclosed production admission |
| [PREVIEW_REVISIONS](docs/firstbit/PREVIEW_REVISIONS.md) | Subsequent price/amount/VAT/description edits and source binding |
| [INTEGRATION_EVIDENCE](docs/firstbit/FIRSTBIT_INTEGRATION_EVIDENCE.md) | Repository-safe provider findings, distinguished from consumed runtime fields |
| [METADATA_COVERAGE](docs/firstbit/FIRSTBIT_METADATA_COVERAGE.md) | Private snapshot coverage and evidence gaps |
| [LIVE_DEMO](docs/firstbit/LIVE_DEMO.md) | Local Windows/tunnel fallback only |
| [.agent/PLANS](.agent/PLANS.md) | When/how to write a plan; completed records in `.agent/plans/` |
| [Documentation audit](docs/context-audits/_REPO_AUDIT.md) | Dated audit scope, corrections and verification |
| [Font README](app/assets/README.md) | Mock-PDF font source/license |

## Maintenance

Update the owning document when module boundaries, adapter behavior, financial proposals, storage, security, deployment or verification change. Link to it elsewhere; do not copy the same policy into every file. No automatic requirement to update every document for a small code change.

Keep facts about the current implementation separate from future requirements and dated observations. A healthy deployment yesterday is not a present availability guarantee. Exact test counts belong only in dated verification records, not in every feature guide.

Completed plans explain scope/results at their execution time; they are not operational checklists or an invitation to repeat paid/live tests. Incident-only notes and superseded audit copies are private under `.local/firstbit/documentation-audit/`. Private metadata is a discovery aid, not a runtime or test dependency; inspect targeted members rather than loading the whole bundle.

Critical rules are enforced by models, guards and tests where implemented. Prose does not implement missing persistence, transactional uniqueness, write/post/PDF or a network availability guarantee.
