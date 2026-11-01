# Контракт интеграции 1С

## Optional linked TaxInvoice capability

`app/domain.py:TaxInvoiceOneC` extends OneC without changing the existing fake/readonly requirements. These are adapter obligations, **not discovered HTTP endpoints**. A provider advertising `requires_tax_invoice=True` must implement authoritative `read_tax_operation`, one-shot `ensure_tax_invoice`, conditional `ensure_tax_posted`, and native `get_tax_invoice_pdf`, with a durable journal available before any source mutation. Missing capability fails before source creation.

`TaxInvoiceReference` is an unverified returned hint. `TaxInvoice` binds the actual linked document to the source/client/basis/confirmed digest and its current posted state/revision. The adapter must verify the actual financial contents, issuer and relation against the confirmed preview; merely returning matching IDs/digest is insufficient. Duplicate/ambiguous linkage is unknown/conflict, never permission to select one. Read-back after generation decides whether posting is needed. Lost outcomes must reconcile before further mutation; an absent result after durable intent does not authorize resending generation.

`TaxInvoicePdf` carries exact source/tax references, tax revision, fixed print manager/template provenance; service rechecks both documents before caching. The provider must obtain native bytes from the proved print pipeline, never use the source Invoice print form or mock rendering. Concrete FirstBit implementation, admission and rollout evidence live in [PRODUCTION_OPERATION](firstbit/PRODUCTION_OPERATION.md).

Это требования к адаптеру `app/domain.py:OneC`, **не описание существующих endpoints**.
Реализован GET-only `app/firstbit.py` (`APP_MODE=firstbit_readonly`); controlled-create расширение `app/firstbit_write.py` описано в [PRODUCTION_OPERATION](firstbit/PRODUCTION_OPERATION.md). Опциональный native provider app/firstbit_production.py довёл контрольную операцию до проведения, связанного TaxInvoice и штатного PDF с восстановлением; результаты принадлежат VERIFICATION. Область live prepare/refresh и multi-service/voice/Telegram проверок — [VERIFICATION](VERIFICATION.md). Smoke ENV не ограничивает клиентов приложения.
`ONEC_WRITE_ENABLED=true` невалиден в mock/readonly. Сам reader не становится writable от флага; режим controlled-create требует отдельного допуска.

Сервис требует durable journal для любой non-fake mutation. `InvoiceResult.pdf=None` допускается только как явный результат остановки на проверенном черновике либо отсутствия штатного PDF; это не утверждение о проведении/доставке. Политика допуска и ограничения не дублируются здесь: [PRODUCTION_OPERATION](firstbit/PRODUCTION_OPERATION.md).

| Метод | Вход → выход (Pydantic) | Обязательная гарантия |
|---|---|---|
| `resolve_client` | имя/описание пользователя, optional internal `selected_id` → `ResolvedClient` | Только чтение; единственная проверенная identity (exact/reviewed alias) или `ClientChoiceRequired(ClientCandidates)`. Явный выбор повторно проверяется по свежим активным кандидатам исходного запроса |
| `resolve_service` | `client_id`, название услуги, optional internal `selected_id` → `ResolvedService` | Только чтение; один допустимый стабильный ID услуги или typed ServiceChoiceRequired; выбранный ID проверяется по исходному запросу |
| `resolve_basis` | `ResolvedInvoiceCommand` → `BillingBasis` с `InvoicePreview` | Только чтение; стабильные ID, revision и полный типизированный snapshot дат/реквизитов/строк/цен/налогов/итогов |
| `read_operation` | `BillingBasis`, operation ID → `OperationState` | Авторитетное чтение перед записью; `unknown` нельзя трактовать как `not_started` |
| `ensure_draft` | `BillingBasis`, operation ID → `Invoice` | Атомарно найти/создать один документ для основания; проверить актуальность revision перед записью |
| `ensure_posted` | `BillingBasis`, `Invoice`, operation ID → `Invoice` | Повторно проверить revision и провести именно этот документ; уже проведённый вернуть без эффектов |
| `get_pdf` | `Invoice` → `PdfDocument` | Только штатная печатная форма 1С для существующего проведённого документа |

InvoiceLine.price is the document's native unit price; price_includes_tax=false means net and true means gross. Subtotal always remains net, tax_amount is separate and total is gross. A preview requires one common document pricing mode. User override inputs retain their documented net meaning ([PREVIEW_REVISIONS](firstbit/PREVIEW_REVISIONS.md)); an unrepresentable conversion fails closed. The new false default is omitted from serialized lines to preserve the exact JSON/digests of existing confirmed exclusive operations; true is serialized and bound to the confirmed digest. FirstBit wire mapping is owned by [READONLY_PIPELINE](firstbit/READONLY_PIPELINE.md).

Пользовательские названия используются только в read-only поиске клиента/услуг.
Transport/schema bounds and actual consumed mapping: [READONLY_PIPELINE](firstbit/READONLY_PIPELINE.md). Company discovery/choice: [COMPANY_SEARCH](firstbit/COMPANY_SEARCH.md); generic Service choice and per-line historical composition: [INITIAL_REQUESTS](firstbit/INITIAL_REQUESTS.md). The Protocol supports typed ClientChoiceRequired/ServiceChoiceRequired; selection authorizes only continuing reads. Returned IDs must match the explicit internal selection.

После успешного поиска `PreparedInvoice.request` содержит стабильные ID и количества,
`BillingBasis` — ключ, revision и проверенный preview. Изменяющие методы получают
только это основание и operation ID; поиск по свободному тексту при recovery запрещён.
Обязательная `Invoice.preview_digest` связывает возвращённый документ с точным
подтверждённым snapshot (`InvoicePreview.digest`, SHA-256 канонической сериализации модели).
Адаптер возвращает этот digest только после проверки соответствия документа snapshot;
не может присваивать его произвольному найденному документу. При несовпадении запись/
доставка останавливаются для проверки оператором. Если точное соответствие не доказано,
результат нельзя считать подтверждённым.

`invoice_date` — дата документа; `service_period` — отдельный необязательный период услуг.
Preview включает также `supply_date`, валюту, реквизиты сторон, банк/условия, 1–20 строк
со стабильными ID услуг, количеством, UOM, ценой, типизированным налоговым профилем и
готовыми итогами, а также общие итоги и сумму прописью. Налоговый профиль — ID, название,
режим (`standard`, `zero_rated`, `exempt`, `outside_scope`) и ставка. Число явно запрошенной ставки декодируется из пользовательских слов локально; существование/тип профиля проверяются по provider данным, не выдумываются моделью.
Предыдущий счёт может дать ID/количества/структуру и налоговую подсказку, но цены и
допустимость профиля проверяются заново. Неоднозначность требует уточнения, до записи.

Это правило текущих цен относится к fake; для FirstBit bookkeeping authoritative `ItemPrices` не доказан. Production read-only возвращает явно маркированное historical proposal: цены, отдельные строки и VAT предыдущего posted invoice проверяются арифметически и требуют проверки человеком. Они не объявляются текущим тарифом. Неподдерживаемая арифметика/неизвестные суммы блокируются. `HistoricalProposal` хранит source/contract/entity provenance внутри preview; `BillingBasis` не расширен. Поля supply date/bank/terms/contacts/amount in words могут быть `None` только в таком неисполняемом proposal: defaults нового документа не угадываются. `InvoiceService.execute()` блокирует historical proposals независимо от write permission. Подробный mapping и ограничения: `firstbit/READONLY_PIPELINE.md`.
Без явного списка услуг FirstBit использует только проверенную историческую структуру по правилам INITIAL_REQUESTS; произвольные настройки/defaults не угадываются.
Исторический supplier review и readonly confirmation/retry описаны в [SYSTEM_MAP](SYSTEM_MAP.md). Это UI-проверка proposal, не часть будущего mutation API и не подтверждение new-document defaults.


При получении штатного PDF адаптер проверяет актуальную идентичность и revision документа
и соответствие подтверждённому snapshot. Изменённый после подтверждения документ
нельзя молча печатать как ранее подтверждённый. Локальный mock generator здесь не используется.

`BillingBasis.key` — устойчивый непрозрачный идентификатор основания из 1С:
информационная база/организация, `client_id`, договор и бизнес-идентичность счёта.
Ключ и `client_id` не должны меняться из-за другого написания имени или смены пользователя Telegram.
Правки цены, количества, услуги, налогового режима или revision не должны открывать
новую операцию для того же счёта. В fake для сценария с периодом сохраняется прежняя
месячная идентичность независимо от формы команды; дата документа остаётся отдельным
полем snapshot. Если период не нужен, основание определяется датой. Старый запрос
периода и новый запрос даты с тем же периодом не должны создавать разные документы.
Как именно он получается, определяет исследование конкретной конфигурации.
Python разрешает эти значения только по проверенным provider данным/явным grounded предложениям пользователя, не из предположений модели.

Operation ID вычисляется из версии сценария и ключа основания. Это средство корреляции,
само по себе оно не обеспечивает идемпотентность. Уникальность и её транзакционная
проверка должны быть реализованы в 1С, включая конкурирующих клиентов интеграции.
Одного предварительного поиска и последующего POST недостаточно.

Перед каждой изменяющей операцией адаптер проверяет, что контрагент, договор,
строки, цены, организация и прочие данные всё ещё соответствуют возвращённой
revision. Проверка и запись должны быть атомарными в 1С либо защищены её
эквивалентным механизмом блокировки/версии. Простое чтение перед POST недостаточно.
После пользовательского подтверждения приложение также перечитывает состояние и
основание: при изменении revision/snapshot, если операция достоверно не началась,
показывает новый preview и требует подтверждения заново. Это дополнительная UX-проверка,
она не заменяет атомарную проверку в адаптере. Начатая/неопределённая операция остаётся frozen.

Потеря ответа или отмена HTTP-запроса не доказывают откат в 1С. Сервис сначала
вызывает `read_operation` в режиме только чтения. Если состояние `draft` или
`posted`, он продолжает тот же документ; если `unknown`, запись останавливается.
Новый `ensure_draft` вслепую не вызывается.
Адаптер без подтверждённой гарантии такого восстановления включать нельзя.
Нужно определить поведение для документов, созданных вручную, удалённых, отменённых,
изменённых после создания и для намеренного второго счёта за тот же период.
Приложение сейчас поддерживает только один счёт на основание.

Все ответы внешнего API адаптер немедленно валидирует Pydantic-моделями конкретного
API, затем преобразует во внутренние модели. Сервис дополнительно проверяет внутренние
результаты. Ошибки API не передаются пользователю или в лог как сырые сообщения.
Ожидаемые уточнения — только фиксированные безопасные сообщения приложения;
инфраструктурные ошибки — `BackendFailure`, таймауты и безопасные технические коды.

## Что нужно от владельца 1С

### Read-only пользовательские предложения

`InvoiceCommand.initial_overrides` indexes explicitly requested services; `preview_overrides` addresses an existing preview. `PreviewLineOverride` carries `line_number`, mutually exclusive net `price`/net line `amount`, optional currency/description/tax, without provider IDs. Service obtains a valid baseline and adds source ID/LineNumber locally in ResolvedPreviewLineOverride. Multi-source provenance is checked per line. Exact grounding/source/tax/rounding behavior: [INITIAL_REQUESTS](firstbit/INITIAL_REQUESTS.md), [PREVIEW_REVISIONS](firstbit/PREVIEW_REVISIONS.md).

Historical/manual proposals require a real writer and a fresh complete ExecutionReview before execution. GET-only and manual fake proposals remain non-executable even with caller permission. Readonly confirmation refreshes basis and stops without authoritative operation reconciliation; the GET-only reader's read_operation returns unknown. BillingBasis schema remains key/client_id/revision/preview. Price/date/quantity edits do not by themselves change business identity; source/issuer/contract/period identity drift can block the old operation. This extension is not a writable-provider contract.

### Будущий write contract

1. Название/версия конфигурации, тип документа и поддержка его проведения.
2. Документация опубликованных HTTP services/API, адрес тестовой базы и способ авторизации.
3. Тестовый контрагент; правила выбора организации, договора, строк и периода.
4. Возможности постоянной записи operation ID, атомарной уникальности, revision/версии и сверки результата.
5. Штатная PDF-форма, способ получения и ограничения времени/размера.
6. Пользователь интеграции с чтением необходимых справочников, созданием/чтением/проведением
   только нужного документа и доступом к его печатной форме. Без административных прав,
   удаления, произвольного SQL/запросов/выполнения кода и доступа к лишним организациям.

Секреты передаются через ENV/хранилище секретов, не в документации или репозитории.

## Последовательность допуска

1. Проверить авторизацию и поиск клиента в тестовой базе, включая 0/2 совпадения.
2. Проверить связанные данные, договоры, услуги и неоднозначности без записи.
3. Создать тестовый документ; проверить содержимое средствами 1С.
4. Проверить проведение отдельно и повторное проведение того же документа.
5. Получить и визуально проверить стандартный PDF отдельно.
6. Проверить потерю ответа после фактического создания/проведения и конкурентный запрос.
7. Искусственно изменить данные между подготовкой и записью; убедиться, что revision блокирует запись.
8. Перезапустить приложение между попытками; убедиться, что второй документ не появился.
9. Только после этого провести текстовый и голосовой E2E с настоящим Telegram.

Локальная проверка поведения fake: `python -m pytest tests/test_onec_contract.py tests/test_core.py -q`.
Она не подтверждает транзакции, права или работоспособность настоящей 1С.
