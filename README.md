# Счета через Telegram и FirstBit / 1C

Текст или голос -> типизированный запрос -> проверенные данные -> InvoicePreview -> правка, отмена или подтверждение.

| Режим | Что выполняется |
|---|---|
| `APP_MODE=mock` — default | Вымышленные данные, fake create/post и TEST/MOCK PDF после подтверждения |
| `APP_MODE=firstbit_readonly` | Настоящий FirstBit через GET, историческое предложение, повторная проверка; **без create/post/PDF** |
| `APP_MODE=firstbit_write` | Controlled draft либо явно включённый native Invoice → TaxInvoice → штатный PDF. Финансовый E2E проверяется отдельно. [Допуск и статус](docs/firstbit/PRODUCTION_OPERATION.md) |

`ONEC_WRITE_ENABLED=false` обязателен для mock/readonly. Допуск controlled-create и фактические проверки записи описаны в [PRODUCTION_OPERATION](docs/firstbit/PRODUCTION_OPERATION.md); native adapter реализован, но включение режима не заменяет controlled production E2E. Рабочий бот размещён на Linux-сервере; локальный компьютер/ngrok ему не нужны. Серверные команды и rollback: [SERVER_DEPLOYMENT](docs/SERVER_DEPLOYMENT.md). Карта проекта для следующего агента: [AGENTS](AGENTS.md), [context index](README_CONTEXT_ENGINEERING.md).

## Возможности и границы

- Natural language и voice при `AI_MODE=openai`; узкая команда месяца/года работает без AI.
- Дата счёта отдельно от периода услуг. Короткие правки используют локальный draft.
- Поиск компании по краткому/полному имени, без требования дословного регистра/пунктуации; неточные варианты требуют выбора кнопками. [Поиск и voice](docs/firstbit/COMPANY_SEARCH.md).
- Активные услуги каталога, в том числе несколько разных/повторных услуг. Нужны проверенные договор и исторический источник каждой услуги этого клиента; отсутствующие значения не угадываются.
- Первоначальные суммы, цена единицы, количество и НДС из запроса применяются после проверки исторического baseline. **«На сумму 1800 с НДС» означает net-сумму строки 1800, НДС сверху**, ставка проверяется в 1С. [Первоначальные параметры](docs/firstbit/INITIAL_REQUESTS.md).
- В preview можно исправить цену/net-сумму, налог, название, дату/количество. Для нескольких строк укажите номер. Переименование сохраняет ID услуги. [Правки](docs/firstbit/PREVIEW_REVISIONS.md).
- Неоднозначность, неподдержанная арифметика, неизвестные финансовые значения или schema mismatch требуют уточнения/блокируют preview. Историческая цена не вечный тариф. Выбор исторического поставщика не подтверждает поставщика нового документа.

Пример формы запроса (имя ниже вымышленное, реальные услуги должны существовать в каталоге):

```text
Сформируй счёт для ООО Ромашка на 29 октября 2026 года
Бухгалтерское обслуживание на сумму 1800 с НДС
Подготовка декларации на сумму 1000 с НДС
```

Пример последующей правки: «Во второй строке сумма 1200, НДС 5%». Новая попытка правки отзывает старое подтверждение. Нет гарантии понимания любого аудио/формулировки: распознанное нужно проверить, при необходимости уточнить.

## Быстрый offline-запуск без ключей

Python >=3.10; Windows/Python 3.10 и Linux/Python 3.12 проверялись. Из корня:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts/smoke.py
.\.venv\Scripts\python.exe scripts/demo.py
.\.venv\Scripts\python.exe scripts/firstbit_readonly_smoke.py
```

На Linux эквивалентный интерпретатор — `.venv/bin/python`. Эти smoke/demo используют loopback/синтетические исходящие HTTP, не production. Demo покрывает fake voice -> STT/LLM -> preview -> confirm -> fake invoice/PDF; FirstBit smoke отдельно проверяет real-adapter workflow с synthetic transports. Точные значения проверок: [VERIFICATION](docs/VERIFICATION.md).

## ENV и запуск

Шаблон без секретов — [.env.example](.env.example). Установить Telegram token, независимый webhook secret и числовой allowlist; для natural language/voice — `AI_MODE=openai`, OpenAI API key и модели (`auto` по умолчанию). Обычная factory читает ENV и **не загружает `.env` автоматически**. Локальный `run_local.py` явно загружает ignored `.env.local`, сервер получает EnvironmentFile через systemd.

FirstBit settings, источник каждого значения, фактические объекты/поля и live GET smoke: [READONLY_PIPELINE](docs/firstbit/READONLY_PIPELINE.md). `FIRSTBIT_SMOKE_CLIENT` относится только к проверочному скрипту, не ограничивает клиентов бота. Для mock нужен только `requirements.txt` и общие Telegram settings; для тестов — dev requirements.

Один процесс/worker; общий запуск после настройки ENV:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000 --workers 1 --no-access-log
```

Нужен HTTPS webhook с тем же secret. Не переключайте рабочий серверный бот на локальный туннель случайным запуском demo launcher: у бота один webhook. Изолированный тестовый бот или согласованный fallback описаны в [LIVE_DEMO](docs/firstbit/LIVE_DEMO.md); основной сервер — в [SERVER_DEPLOYMENT](docs/SERVER_DEPLOYMENT.md).

## Подтверждение, retry и состояние

`/start`, `/help`, `/cancel`, `/retry`; подтверждение/правка/отмена доступны кнопками. В реальном режиме «Проверить preview» только перечитывает и проверяет предложение. Изменение snapshot требует нового preview/подтверждения. В mock обычное подтверждение может создать/провести fake-документ; ручные денежные предложения неисполняемы и там.

Readonly `/retry` повторяет подготовку из сохранённого typed draft без нового STT/LLM. Recovery продолжает frozen operation после чтения состояния; потерянный ответ не доказывает rollback. Cancel не отменяет уже начатую финансовую операцию. Полные переходы: [SYSTEM_MAP](docs/SYSTEM_MAP.md).

По умолчанию drafts, choices, receipts, fake-документы и delivery dedupe process-local; после restart нужны новые запросы/кнопки. Добавлен опциональный журнал подтверждённых операций и доставки, контрольный real Invoice/TaxInvoice/PDF E2E пройден с восстановлением: [PRODUCTION_OPERATION](docs/firstbit/PRODUCTION_OPERATION.md). Внешней БД/очереди и нескольких workers нет. Безопасность и будущий допуск записи: [SECURITY](docs/SECURITY.md). Оставшиеся milestones: [PROJECT_CONTEXT](docs/PROJECT_CONTEXT.md).
