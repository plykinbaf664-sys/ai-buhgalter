# Project Context

## Product

Telegram-бот для подготовки счетов в FirstBit ERP / 1C.

Целевой пользователь — бухгалтер. Основной сценарий:

```text
текст/voice
→ распознать намерение
→ однозначно найти клиента/услуги/основание
→ получить полный invoice preview
→ человек подтверждает / правит / отменяет
→ создать и провести один документ
→ получить штатный PDF из 1C
→ отправить PDF в Telegram
```

## Current repository state

Текущий код — version `0.2.0`, Python `>=3.10`.

В репозитории реально реализованы:
- FastAPI webhook;
- Telegram allowlist + protected webhook;
- text and voice paths;
- OpenAI interpreter/STT behind `AI_MODE`;
- strict Pydantic domain;
- fake 1C adapter;
- preview/edit/confirm/cancel;
- FirstBit duplicate/partial-client candidate buttons, explicit selection and fresh GET revalidation;
- create/post/PDF against fake;
- retry/recovery behavior;
- duplicate webhook protection;
- mock PDF;
- broad pytest suite.

**GET-only real adapter реализован и проверен live prepare/refresh** в `app/firstbit.py`; дополнительный случай с историческим поставщиком, отличным от договора, проверен через явный supplier review и реальную доставку preview в Telegram. Он строит historical proposal, а не готовый payload нового документа. Клиент задаётся Telegram-запросом; smoke ENV не ограничивает приложение. Другие клиенты также требуют своих однозначных договоров и historical basis. Подробности: `firstbit/READONLY_PIPELINE.md`.

`app/config.py` разрешает:

```text
APP_MODE=mock
# либо firstbit_readonly
```

`create_app()` создаёт `FakeOneC` в mock и `FirstBit` из ENV в firstbit_readonly. `ONEC_WRITE_ENABLED=true` запрещён в обоих режимах.

## Runtime shape today

Один Python process:
- FastAPI;
- Uvicorn;
- HTTPX;
- OpenAI SDK when enabled;
- no database;
- no queue;
- no Redis;
- no background worker.

Process-local state:
- webhook receipts;
- pending confirmations;
- draft contexts;
- recovery operations;
- fake 1C documents;
- delivered/delivery-attempted sets.

После process restart эта state не является durable.

## Product actors

### Accountant
Формулирует запрос и подтверждает финальные финансовые значения.

### Telegram
Transport/UI only. Не является financial state store.

### LLM/STT
Помогает понять язык. Не является source of truth.

### Application
Управляет state machine, preview/revision, confirmation, retry/recovery.

### OneC adapter
Контракт определён в `app/domain.py:OneC` и подробно описан в `docs/onec-contract.md`.

### FirstBit ERP / 1C
Будущий production source of truth для:
- companies;
- contracts;
- services/items;
- VAT/tax profiles;
- GL;
- bank/payment data;
- invoice documents;
- standard PDF.

## Existing domain contract

### `InvoiceCommand`
Содержит:
- client text;
- invoice date;
- optional service period;
- service selections;
- tax request;
- previous-invoice intent.

### `ResolvedInvoiceCommand`
Уже содержит stable client/service IDs.

### `BillingBasis`
**Текущая code schema**:

```text
key
client_id
revision
preview
```

Не утверждать, что она уже содержит отдельные company/contract/entity refs. Для real adapter можно расширить модель, но это будет публичное изменение, которое требует поиска всех usages и тестов.

### `InvoicePreview`
Typed full snapshot с:
- invoice/supply date;
- optional service period;
- currency;
- issuer/recipient;
- bank;
- payment terms;
- 1–20 lines;
- totals;
- amount in words;
- reference/previous reference.

Preview arithmetic валидируется моделью.

Для historical proposal добавлен typed `HistoricalProposal` с source/contract/entity provenance. Банковские условия, дата оказания, контакты и сумма прописью могут отсутствовать только у такого явно неисполняемого предложения; обычный preview сохраняет требование полных реквизитов. Неподтверждённые финансовые значения строк блокируют proposal. Неподтверждённые defaults нового документа блокируют write. См. точный список ограничений в FirstBit guide.

### `PreparedInvoice`
Связывает resolved request + basis + display name.

### `Invoice`
Связывает real/fake document с:
- `document_id`;
- posted state;
- client ID;
- basis key;
- revision;
- `preview_digest`.

### `OperationState`
`not_started | draft | posted | unknown`.

## Current user flow guarantees

- Любая команда требует preview confirmation.
- Pending confirmation живёт 5 минут.
- Любая попытка правки отзывает старый token confirmation до нового parsing/resolution.
- При изменении basis/revision перед подтверждением показывается новый preview.
- `/retry` работает только с frozen previous operation.
- Новая команда блокируется, пока operation в recovery.
- Cancel не означает rollback уже начатой financial operation.

## FirstBit production evidence discovered outside current repo

Read-only Standard OData:
- работает Basic Auth для integration user;
- опубликован MVP whitelist из 33 объектов;
- подтверждены Companies, Contracts, Items, registers, Invoice (`Document_InventoryExpense`);
- обычный Invoice = `Document.InventoryExpense`;
- `Accounting and bookkeeping services` — реальный service Item;
- `ItemPrices` для этой услуги не даёт authoritative current price;
- invoice history показывает client-specific recurring price/quantity;
- один invoice может содержать несколько одинаковых accounting service rows;
- у default contract `PriceKind`, `SalesPaymentTerms`, `DeliveryTerms` могут быть ZERO GUID;
- historical `PaymentTermsVersion_Key` нельзя слепо переносить в новый invoice.

Эти факты должны войти в real adapter, но **не выдаются за уже реализованный код**.

## Important fake-vs-production divergence

Fake сейчас моделирует другой pricing assumption:
- previous invoice = hint;
- current price берётся из fake catalog.

Это закреплено тестом текущего fake workflow.

Для исследованной production FirstBit базы этот rule не доказан и для bookkeeping service фактически не поддержан ItemPrices. Real adapter должен иметь собственную безопасную resolution policy.

## Product invariants

Company voice lookup accepts case/spacing/punctuation variants and offers local transliteration/typo candidates. Company names remain local; similarity never supplies an automatic identity. Missing client output from AI can be repaired only by a verbatim explicit invoice phrase, followed by normal resolution. See `firstbit/COMPANY_SEARCH.md`.

- Human confirmation before write.
- 1C is financial source of truth.
- LLM cannot invent financial entities/values.
- Explicit user price/VAT/display-name corrections are supported on existing preview as marked, non-executable proposals; deterministic span decoding, source/line binding and actual tax catalog verification are required. See `firstbit/PREVIEW_REVISIONS.md`.
- Invoice date != service period.
- Stable IDs after read-only resolution.
- Ambiguity stops the workflow.
- Unknown operation state blocks mutation.
- Lost HTTP response != rollback.
- Same billing identity should not create duplicate invoice.
- Production PDF comes from 1C.
