# AGENTS.md

## Purpose

`ai-buhgalter` — Python/FastAPI Telegram workflow для подготовки и подтверждения счетов с будущей интеграцией FirstBit ERP / 1C.

Текущий репозиторий уже реализует полный безопасный workflow поверх `FakeOneC`: текст/голос → типизированная команда → read-only resolution → `InvoicePreview` → подтверждение → create/post → PDF → Telegram, включая recovery, идемпотентность внутри fake-процесса и защиту от повторов.

Реальный GET-only адаптер `app/firstbit.py` подключён через `APP_MODE=firstbit_readonly`: `resolve_client` / `resolve_service` / `resolve_basis` возвращают typed historical proposal в `InvoicePreview`. Live GET prepare/refresh и отдельный supplier-review case с реальной доставкой preview проверены; write/post/PDF не реализованы. `FIRSTBIT_SMOKE_CLIENT` используется только проверочным скриптом и не ограничивает клиентов приложения. Настройка, точный mapping и blockers → `docs/firstbit/READONLY_PIPELINE.md`.

Этот файл — короткий router. Не читай все docs перед каждой правкой.

## Context discovery

1. Определи затронутый flow.
2. Прочитай только релевантный контекст.
3. Сверь его с текущим кодом, тестами и конфигом.
4. Для 1C/OData точные EntitySet/property names сверяй с `$metadata` и реальными GET, а не с догадками.
5. Если prose расходится с кодом — код/tests/runtime evidence выше.

## Documentation routing

- Продукт, текущий rollout, различие fake/real → `docs/PROJECT_CONTEXT.md`
- Реальная структура репозитория и архитектура → `docs/ARCHITECTURE.md`
- Security model / 1C production safety → `docs/SECURITY.md`
- End-to-end flows и ownership → `docs/SYSTEM_MAP.md`
- Точные команды и regression matrix → `docs/VERIFICATION.md`
- Долговечные решения и найденные противоречия → `docs/DECISIONS.md`
- Рабочий стиль → `docs/AGENT_WORK_STYLE.md`
- Сложные/high-risk изменения → `.agent/PLANS.md`
- Контракт OneC adapter, уже существующий в репозитории → `docs/onec-contract.md`
- FirstBit read-only реализация, ENV, smoke и blockers → `docs/firstbit/READONLY_PIPELINE.md`
- Живой Telegram demo, restart, STT/LLM status → `docs/firstbit/LIVE_DEMO.md`
- Выбор клиента кнопками и безопасность callback → `.agent/plans/client-choice-readonly.md`, `tests/test_client_choice.py`
- Голосовые варианты названия/регистр/опечатки → `docs/firstbit/COMPANY_SEARCH.md`, `.agent/plans/voice-company-search.md`, `app/company_names.py`, `tests/test_company_search.py`
- Голос → исторический образец, конфликт поставщика и компактный preview → `.agent/plans/voice-history-preview.md`, `docs/firstbit/LIVE_DEMO.md`
- Ручные правки цены/НДС/названия в preview → `docs/firstbit/PREVIEW_REVISIONS.md`, `.agent/plans/preview-price-tax-description.md`, `tests/test_preview_overrides.py`
- FirstBit исследование → `docs/firstbit/FIRSTBIT_INTEGRATION_EVIDENCE.md`
- Покрытие private metadata → `docs/firstbit/FIRSTBIT_METADATA_COVERAGE.md`

## Repository orientation

Высокосигнальные файлы:

- `app/domain.py` — Pydantic domain models, `OneC` Protocol, operation state, digests.
- `app/service.py` — `InvoiceService.prepare/refresh/execute`, write guard, reconcile after uncertain mutation.
- `app/bot.py` — Telegram workflow, pending confirmation, edit/cancel/retry, delivery dedupe.
- `app/main.py` — FastAPI app, webhook security, allowlist, request dedupe, process-local receipts.
- `app/config.py` — strict ENV settings; `APP_MODE=mock|firstbit_readonly`, write flag запрещён в обоих.
- `app/firstbit.py` — typed settings, fresh consumed-schema guard, bounded GET-only adapter; никогда не создаёт документы.
- `app/company_names.py` — локальные exact keys и approximate ranking имён; транслитерация/похожие имена только предлагают выбор, не выбирают ID.
- `app/fake_onec.py` / `app/fake_data.py` — fake provider and fixtures.
- `app/ai.py`, `app/language.py`, `app/intent.py`, `app/voice.py` — LLM/STT and controlled language-to-domain conversion.
- `app/telegram.py` / `app/telegram_models.py` — Telegram transport and response validation.
- `app/mock_pdf.py` — только TEST/MOCK PDF path.
- `docs/onec-contract.md` — уже существующий adapter contract.
- `tests/` — behavior/regression suite.
- `scripts/demo.py`, `scripts/smoke.py`, `scripts/preview_invoices.py`, `scripts/live_ai_check.py` — reproducible checks.
- `scripts/start_readonly_demo.py` / `run_local.py` / `register_demo_webhook.py` — локальный Windows demo runtime, скрытые процессы, typed ENV, защищённый Telegram webhook, архивация safe audit при restart. Реальные STT/LLM + FirstBit проверены на синтетическом OGG/Opus, затем настоящий Telegram supplier-review callback завершился доставкой реального preview. Не выдавать синтетическое аудио за человеческий voice. Запись/PDF выключены.

## Cross-cutting invariants

- Pydantic на внешних и критических внутренних границах; не заменяй typed models сырыми dict.
- LLM не создаёт 1C IDs, цену, VAT, GL, договор или итоговые суммы.
- Явную цену/ставку пользователя разрешено применить только как правку существующего preview: LLM выбирает spans, число декодируется детерминированно, налог подтверждается справочником. Ручные правки не допускаются к execute даже в fake; переименование сохраняет ID услуги. Исторический source/LineNumber привязываются локально, не моделью.
- Свободный текст используется только для parsing/read-only resolution.
- До явного подтверждения документ не создаётся.
- Любая attempted edit отзывает старое подтверждение.
- Перед write `InvoiceService.refresh()` перечитывает состояние операции и basis.
- `operation_id = sha256("invoice:v1:" + BillingBasis.key)`; revision намеренно не входит в ID.
- `read_operation=unknown` блокирует дальнейшие записи.
- После исключения во время create/post сервис делает один read-only reconcile и не повторяет mutation вслепую.
- `preview_digest` связывает документ с точным подтверждённым `InvoicePreview`.
- `InvoiceService._write_guard()` запрещает real write без явного разрешения.
- `ONEC_WRITE_ENABLED=true` невалиден в обоих режимах. Historical proposal и preview-only provider блокируются также в `InvoiceService.execute()` независимо от caller permission.
- Mock PDF не должен использоваться в real adapter: production PDF только штатный из 1C.
- Секреты не логировать и не переносить в docs/fixtures.
- Production POST/PATCH/DELETE не выполнять без отдельного явного разрешения владельца.
- Runtime 1C identity — только dedicated least-privilege account; admin credentials запрещены.
- Raw user/LLM text не может формировать произвольный OData query/filter.
- FirstBit data не отправлять в LLM сверх минимально необходимого intent-context.
- В real AI context передаются только boolean-признаки наличия полей локального draft; имена/ID/строки/цены FirstBit остаются локально.
- Различие Entity текущего договора и posted source не исправляется автоматически. Исторический поставщик и организация договора проверяются GET; bot требует явного выбора образца перед preview. Это не подтверждает поставщика нового документа и не снимает write guard.
- TLS verification не отключать; credentials не хранить в URL/source/logs.

## Current integration guard

`create_app()` по умолчанию создаёт `FakeOneC`; при `APP_MODE=firstbit_readonly` создаёт `FirstBit` из ENV с lifecycle cleanup. Не подменять fake production-данными. Read-only confirmation только проверяет proposal, без execute и без ложного `read_operation=not_started`; реальный lookup пока возвращает `unknown`.

Production Standard OData проверен текущим адаптером через live GET: metadata → клиент → договор → service → historical basis → preview → refresh. Живые особенности: Edm.Double, Int64 LineNumber-строка, query spaces `%20`; tolower и DescriptionFull equality не поддерживаются. Client search теперь локален: свежие name-only страницы по 200, максимум 5000; регистр/пробелы/пунктуация незначимы для единственного exact match. Транслитерация/голосовые буквы/опечатки/частичные совпадения только предлагают кнопки (до 5); выбранный ID перечитывается и проверяется по исходному запросу. Неполный список/неоднозначность блокируют автоматический выбор. Ни слова поиска, ни каталог не передаются в OData syntax/LLM. Не считать исторические данные defaults нового документа. Private metadata/preview только под ignored `.local/`.

## Important integration mismatch to preserve explicitly

Текущий fake/`docs/onec-contract.md` предполагает: предыдущий счёт даёт структуру/количество, а цена заново берётся из текущего каталога.

В исследованной production FirstBit базе для `Accounting and bookkeeping services` authoritative `ItemPrices` не найден, а реальная цена/quantity повторяются по клиенту в исторических invoice lines и иногда меняются.

Следствие: **не копируй fake pricing rule в real adapter автоматически**. Для production v1 historical line может быть proposal, который показывается в preview и требует human confirmation. Этот integration-specific rule должен быть покрыт отдельными тестами.

## Complex work

ExecPlan обязателен для:
- нового real OneC/OData adapter;
- изменения `BillingBasis` schema;
- перехода read-only → write;
- create/post/PDF против реальной 1C;
- metadata drift guard;
- production idempotency/persistence;
- замены process-local state постоянным storage;
- multi-worker/multi-process deployment.

## Completion

Перед завершением:
- выполни релевантные tests/scripts;
- укажи, какие команды реально запускались;
- отдельно скажи, был ли контакт с production;
- отдельно скажи, были ли только GET или были side effects;
- не называй real 1C flow готовым, пока write/post/PDF не проверены.
