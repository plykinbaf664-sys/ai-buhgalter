# Context Engineering for `ai-buhgalter`

Этот слой документации дополняет существующий `README.md`, `AGENTS.md` и `docs/onec-contract.md`, но не заменяет код и тесты как implementation truth.

## Structure

```text
AGENTS.md
README_CONTEXT_ENGINEERING.md

docs/
├── PROJECT_CONTEXT.md
├── ARCHITECTURE.md
├── SYSTEM_MAP.md
├── VERIFICATION.md
├── DECISIONS.md
├── SECURITY.md
├── AGENT_WORK_STYLE.md
├── onec-contract.md          # adapter contract
└── firstbit/
    ├── FIRSTBIT_INTEGRATION_EVIDENCE.md
    ├── FIRSTBIT_METADATA_COVERAGE.md
    ├── READONLY_PIPELINE.md  # implemented mapping, ENV, smoke, blockers
    ├── LIVE_DEMO.md          # running Telegram demo, restart, live STT/LLM status
    ├── PREVIEW_REVISIONS.md  # explicit price/VAT/name edits, source binding, no writes
    ├── INITIAL_REQUESTS.md   # initial net amounts, service choices, per-line historical sources
    └── COMPANY_SEARCH.md     # local voice/transliteration/typo matching and user choices

.agent/
├── PLANS.md
└── plans/
    ├── real-firstbit-readonly.md
    ├── live-telegram-readonly-demo.md
    ├── client-choice-readonly.md   # explicit candidate buttons, no automatic duplicate selection
    ├── voice-history-preview.md   # source-supplier review, compact preview, real voice rehearsal
    ├── preview-price-tax-description.md # typed grounded manual revisions
    ├── voice-company-search.md # spelling-tolerant company lookup and verbatim fallback
    └── runtime-recovery.md     # tunnel/DNS recovery, bounded GET retry, grounded patch repair
```

## Why this exists

В репозитории уже есть сильные cross-cutting engineering rules, но `AGENTS.md` исторически стал длинным. Этот context system разделяет:

- always-on routing;
- product/domain facts;
- actual repository architecture;
- flow maps;
- verification;
- dedicated security model for production 1C;
- durable decisions;
- soft work style;
- high-risk execution plans.

Будущему coding agent не нужно перечитывать весь проект перед каждой правкой.

## Source-of-truth order

Для точного поведения:

1. код, Pydantic models, tests, runtime config;
2. свежий FirstBit `$metadata` / read-only runtime evidence;
3. `docs/onec-contract.md` и context docs;
4. старые сообщения/заметки.

## Maintenance

Active ngrok demo launcher: `scripts/start_ngrok_demo.py`; `start_readonly_demo.py` delegates according to stored provider. URL validation and secure registration are shared in `register_demo_webhook.py`; deep readiness supports both whitelisted HTTPS tunnel providers. Operational evidence → `docs/firstbit/LIVE_DEMO.md`.

Customer-demo connectivity/readiness: `scripts/check_demo_ready.py --deep`, `scripts/start_readonly_demo.py` (TCP HTTP/2), `app/ai.py` (bounded parsing-only network retry), `.agent/plans/runtime-recovery.md`. Diagnostics are CLI-only; no new public probe endpoint or persistent queue/worker was added.

Voice company search and local name-only discovery: [COMPANY_SEARCH.md](docs/firstbit/COMPANY_SEARCH.md), `app/company_names.py`, `tests/test_company_search.py`. Approximate matching only suggests candidates; unique exact identities ignore case/spacing/punctuation. No directory data to AI/disk.

Price/tax/display-name preview revisions: [PREVIEW_REVISIONS.md](docs/firstbit/PREVIEW_REVISIONS.md), [ExecPlan](.agent/plans/preview-price-tax-description.md), `app/numbers.py`, `tests/test_preview_overrides.py`. Explicit user values are grounded spans and non-executable proposals, distinct from model-invented financial data.

Read-only FirstBit implementation starts at `docs/firstbit/READONLY_PIPELINE.md` and `app/firstbit.py`. Private targeted metadata lives under ignored `.local/firstbit/metadata/`; it is not a runtime dependency or a Git fixture. Live GET prepare/refresh now passes; current findings and private review artifact location are recorded in the FirstBit guide and verification report.

Обновляй context docs при изменении:
- ownership/module boundaries;
- adapter contract;
- persistent state model;
- write safety;
- verification commands;
- real FirstBit mapping;
- durable business rule.

Не обновляй их ради косметической переформулировки.

## Hard guards vs prose

Критические правила должны по возможности иметь механическую защиту.

В репозитории уже есть хорошие примеры:
- strict/frozen Pydantic models;
- `extra="forbid"`;
- `SecretStr`;
- explicit write guard;
- `preview_digest`;
- stable operation ID;
- unknown-state blocking;
- HMAC compare for webhook/callback token comparisons;
- max payload/line/PDF limits;
- no automatic mutation retry after uncertain outcome.

При внедрении real 1C продолжай этот подход вместо наращивания только текстовых правил.


Speech/read incident routing: `docs/firstbit/COMPANY_SEARCH.md` covers uncertain-STT company choice, short acronym suggestions and readonly `/retry`; `docs/firstbit/LIVE_DEMO.md` distinguishes inbound tunnel health from direct FirstBit/OpenAI egress. Regressions live in `tests/test_voice.py`, `tests/test_client_choice.py`, `tests/test_company_search.py`, and `tests/test_firstbit.py`.
