# Изолированное серверное размещение ai-buhgalteria

## Размещение и границы

Ubuntu/Python 3.12, отдельный каталог `/srv/ai-buhgalteria`, непривилегированный non-login пользователь `ai-buhgalteria`, собственный venv и unit `ai-buhgalteria.service`. Исходники/зависимости принадлежат root, приложение читает их без права изменения. `config/runtime.env` — root:root 0600 в каталоге 0700; systemd передаёт секреты через ENV, приложение валидирует typed settings/SecretStr. Другие пользователи приложения не получают ключи.

Один worker слушает `127.0.0.1:8107`. Снаружи доступны только `GET /ai-buhgalteria/healthz` и `POST /ai-buhgalteria/telegram/webhook` существующего HTTPS-сайта. Caddy импортирует `/srv/ai-buhgalteria/deploy/Caddy.routes`; остальные маршруты сохраняются. Другие project paths возвращают 404, файлы не раздаются. Webhook secret передаётся заголовком, не URL. Дополнительный import `deploy/Caddy.log-filter` в `log default / format filter / fields` удаляет только `X-Telegram-Bot-Api-Secret-Token` из журналов, включая ошибки proxy. Проверять это искусственным секретом при недоступном собственном upstream: одной манипуляции request headers недостаточно. Остальные существующие фильтры сохраняются. Proxy ограничивает body; приложение независимо проверяет размер, секрет, allowlist, private chat и дубликаты.

Активный сервис переведён на APP_MODE=firstbit_write с явными ONEC_WRITE_ENABLED=true и FIRSTBIT_NATIVE_UI_ENABLED=true. Dedicated integration account подтверждён владельцем; approved full schema pin и private journal обязательны. Health и fresh schema проверены. Это статус включения, а не доказательство нового финансового E2E; результаты — [ExecPlan](../.agent/plans/production-headless-e2e.md), границы — [PRODUCTION_OPERATION](firstbit/PRODUCTION_OPERATION.md). В OpenAI не передаются записи FirstBit.

Текущая серверная рабочая копия находится в workspace/, current указывает на неё. Предыдущий release сохранён. Browser binaries/venv/cache/profile/temp расположены внутри проекта; private runtime и журнал имеют отдельные writable paths. Конфигурация до переключения сохранена как private ENV, исходный unit/target — в ignored local deployment backup. Журнал финансовых операций при rollback не удалять и не переинициализировать.


## Структура

```text
/srv/ai-buhgalteria/
  releases/<UTC-release>/   # исходники/tests/docs, SOURCE_MANIFEST.json, .venv
  workspace/               # текущая серверная рабочая копия и project-local runtime
  current -> workspace/    # активная версия
  operations/              # private durable journal/PDF artifacts, service-owned
  config/runtime.env       # необходимые runtime ENV; без ngrok и smoke client
  state/                   # private проверки/backup webhook, не БД
  backups/                 # root-only контроль конфигурации и resolved dependencies
  incoming/                # root-only staging; ENV переносится отсюда
  deploy/Caddy.routes      # project-specific HTTPS routing
  deploy/Caddy.log-filter  # remove Telegram secret header from proxy logs
```

Source archive проверяется SHA-256 для архива и каждого файла, secrets scan и явным списком разрешённых путей. `.git`, `.env.local`, `.local`, venv, caches, logs, artifacts и metadata/business dumps исключены. Secrets передаются отдельно через verified SSH, не через Git/argv/журналы. Временный smoke ENV удаляется после проверки и не ограничивает клиентов приложения.

## Управление и журналы

```sh
systemctl status ai-buhgalteria --no-pager
systemctl restart ai-buhgalteria
journalctl --namespace=ai-buhgalteria -u ai-buhgalteria --since '15 minutes ago' --no-pager
curl -fsS http://127.0.0.1:8107/healthz
```

После restart старые callbacks/drafts недействительны: нужен новый запрос. Unit включён при загрузке, crash restart ограничен по частоте. Нельзя запускать несколько workers или перезагружать весь сервер для проверки, пока там работают другие проекты. Финансовые mutations не повторяются.

Unit ограничивает CPU/память/процессы/capabilities, включает NoNewPrivileges, readonly filesystem, ProtectHome и private tmp/devices. Запись только в собственные state/operations/browser paths; Chromium sandbox сохраняется. Точные ограничения native browser принадлежат [SECURITY](SECURITY.md). Отдельный journal namespace ограничен 64 MiB/семью днями, доступен административным пользователям; глобальная retention чужих журналов не меняется. Audit содержит безопасные стадии/коды/идентификаторы без сообщений/audio/raw responses. Private диагностические отчёты оператор удаляет после проверки; backup webhook хранится до принятия переноса. Исходные deployment-check файлы были одноразовыми private инструментами, а не установленной системой continuous monitoring.

Текущее размещение проверено 30.10.2026: service и стабильный HTTPS endpoint активны, Telegram направлен на сервер, локальный Windows/ngrok оставлен резервом. Сервер работает независимо от включённого рабочего компьютера и локального туннеля; внешние API остаются сетевыми зависимостями.

## Readiness и webhook

Операторские команды получают секреты через временный systemd unit, без shell `source`:

```sh
systemd-run --quiet --wait --pipe --collect --unit=ai-buhgalteria-check \
  --uid=ai-buhgalteria --gid=ai-buhgalteria \
  --property=EnvironmentFile=/srv/ai-buhgalteria/config/runtime.env \
  --working-directory=/srv/ai-buhgalteria/current \
  /srv/ai-buhgalteria/current/.venv/bin/python scripts/server_control.py check \
  --public-url https://agent.balancepro.ae/ai-buhgalteria --deep
```

`check --deep` проверяет local/public readonly health, отказ unsigned webhook, читает Telegram registration/queue, делает production `$metadata` GET и реальный grounded AI-разбор синтетической даты. В текущем коде READY не требует webhook_matches=true или нулевой очереди: эти поля нужно проверить отдельно. Это не full invoice/STT E2E. Сначала выполняется check --deep, затем только после успеха отдельный `register` с тем же URL переключает Telegram и сохраняет прежний webhook в private `state/previous-webhook.json`. Queued updates не удаляются, max_connections=1, allowed_updates=message/callback_query. Caddy сначала адаптируется/валидируется; неизменность чужих маршрутов проверяется до graceful reload, без restart.

## Обновление и rollback

Новый release проверяется отдельным venv, full tests, offline smoke и GET-only readiness, затем меняются только project current и project unit. Предыдущая цель symlink сохраняется; при сбое вернуть её и перезапустить только этот unit. Не обновлять чужие venv/ENV/unit/firewall и не удалять предыдущую версию до принятия rollback.

`scripts/server_control.py restore --public-url ...` с тем же защищённым ENV проверяет доступность прежнего endpoint и возвращает Telegram, используя неизменённый secret. Старый runtime должен оставаться доступен, иначе сначала восстановить его. После rollback можно остановить только project unit. Для удаления размещения убрать только два project imports (route и log-filter) из свежего shared config, проверить Caddy и graceful reload; не удалять файл, пока на него ссылается import. Нельзя безусловно возвращать полный backup поверх чужих новых изменений.

## Ограничения

Сам по себе supervised deployment не доказывает финансовый E2E; текущий controlled native E2E и границы подтверждены в VERIFICATION. Dedupe/confirmation/drafts остаются process-local и теряются после restart. Отсутствие validated history/контракта/финансовых значений блокирует preview. Доступность зависит от FirstBit/OpenAI/Telegram/сервера; durable idempotency/create/post/PDF требуют отдельного этапа. Датированная верификация — [VERIFICATION](VERIFICATION.md); исходный deployment plan остаётся историческим execution record. Аудит локальной документации сам по себе не обновляет release на сервере и не подтверждает его текущую доступность.

## Пределы существующих deployment tools

`deploy/` содержит unit, маршруты, log-filter и retention config; это не автоматический installer/CI/CD. Build/transfer/extraction/hash checks первоначального переноса выполнялись отдельными private инструментами. Для нового release оператору требуется явный reviewed manifest/package procedure; не считать наличие этих проверок в прошлом гарантией каждого будущего переноса.

`server_control.py register` сохраняет original webhook backup с exclusive create и не перезаписывает его. Existing backup плюс другая текущая регистрация могут заблокировать повторный cutover; сначала приватно проверить сохранённую цель, не удалять backup вслепую. Restore предполагает прежние secret/allowed_updates/max_connections и проверяет доступность прошлого endpoint. Проверки register --deep в текущем коде идут после setWebhook, поэтому безопасная последовательность — check --deep, затем отдельный register.
