# Поиск компании после голоса или текста

Регистр, пробелы и пунктуация не должны требовать точного произношения. Компания ищется по исходным словам пользователя, без списка компаний в OpenAI и без угаданного ID.

## Поведение

- Единственное точное название после Unicode/case/space/punctuation normalization разрешается автоматически. Сопоставляются краткое и полное названия; совпадение с одним из них достаточно.
- Русское произношение английских букв, транслитерация, пропущенная правовая форма, частичное имя, иной порядок слов и небольшие опечатки дают предложения кнопками. Даже единственный приблизительный кандидат требует выбора пользователя.
- Показаны до пяти наиболее похожих кандидатов. Дубликаты точного имени показываются отдельно (максимум 19); сходство не выбирает между ними. Нет нужной записи — пользователь может уточнить другую часть имени.
- Если LLM пропустил компанию в явной новой просьбе «Сформируй счёт для … на дату / за период / за услугу», резервное извлечение сохраняет дословный фрагмент. Оно не придумывает латинское написание, не применяется к обычной правке цены/даты и останавливается при неоднозначном `для`.
- Переносы/табуляции и повторы служебных слов нормализуются до parsing; текст внутри кавычек сохраняется. Ясная просьба за месяц принимает обычные окончания года (`год`, `года`, `г.`) детерминированно. Остальные формулировки остаются в structured intent flow; слова внутри явно выделенного названия компании не считаются командами или датой.
- В readonly режиме достаточно названия либо «найди компанию …»: справочник проверяется до полноты даты/услуг, без вызова LLM. После выбора компании можно уточнить дату/период. Это поиск, а не разрешение создать документ.
- Пока показаны кандидаты, новое название уточняет исходный поиск и сохраняет период/услуги запроса. Ответ номером выбирает вариант того же пользователя в пределах существующего срока действия; callback и номер проходят одинаковую свежую проверку identity. Отмена/новая команда/истечение срока отзывают прежний выбор.
- Явное «за месяц YEAR» подтверждает период услуг даже если модель пропустила его или ошибочно вернула неполную дату без дня. Существующая явно указанная дата счёта сохраняется; противоречащие периоды требуют уточнения. Даты внутри кавычек названия не извлекаются как период. Поиск компании и выбор identity не подтверждают договор/цену/налог.
- Выбор хранит исходный запрос и expiring user token, не UUID из callback. При выборе свежие GET повторяют поиск и проверяют активную запись/соответствие запросу. Следующие финансовые проверки договора, истории и supplier review сохранены.

## Реализация

`app/company_names.py` — чистое локальное сопоставление: `exact_key` для строгого совпадения без регистра/пунктуации; отдельная транслитерация/английские названия букв/нормализация юридических форм/SequenceMatcher только для предложений. Fuzzy score никогда не становится financial authority или автоматическим выбором.

Для простой просьбы «счёт за месяц и год», не принятой строгим parser, SDK- и HTTP-ветки используют одинаковый компактный `Extraction(action, client, year, month)`, затем общий `ground()` строит `InvoiceCommand`. Полная доменная команда с полями услуг/налогов/preview overrides не является схемой извлечения для этой ветки: её рост увеличивает сложность ответа модели и может исчерпать лимит до получения имени. При расследовании проверяйте фактический вызов `resolve_client()`; ошибка интерпретации до него не доказывает отсутствие компании. Побуквенно записанные аббревиатуры, дополнительные слова и юридическая форма в полном названии могут давать корректный кандидат вместо автоматического exact match; это штатный выбор пользователем, а не отказ поиска.

Короткая произнесённая торговая марка теперь сравнивается и с отдельными словами длинного юридического названия. Ограниченные фонетические варианты (например, к/c и немая конечная e) используются только для кандидатов; каждое слово запроса должно иметь сильное сопоставление. Исходный exact key не ослаблен. Synthetic long-name/short-brand regressions и actual GET подтверждают выбор кнопками, не автоматическую подстановку.

Одну вставку/удаление/замену или перестановку соседних букв в слове сравниваем до фонетического folding; это предотвращает потерю кандидата после удаления повторной/немой буквы. Для предложений учитываются мягкая латинская c и qu/кв. Ни опечатка, ни фонетическое сходство не изменяют правила автоматического exact match. Полная неразборчивость, отсутствие записи или финансовой истории остаются явными ограничениями; невозможно безопасно гарантировать восстановление любого произнесённого имени.

`app/firstbit.py` читает свежий список активных имён в память, с фиксированными `$filter`, `$select`, `$top=200`, `$skip` и `$orderby=Ref_Key asc`, максимум 5000 записей. Нужны только существующие `Catalog_Companies.Ref_Key,DeletionMark,IsFolder,Inactive,Description,DescriptionFull`. Контракт/TRN перечитываются обычным адресным GET только для реально показываемых/выбранных записей. Не используются неподдерживаемый `tolower`, guessed search endpoints, arbitrary nextLink, disk cache или полная business record выгрузка. В случае неполного списка, повторяющихся page IDs, malformed schema/envelope или превышения лимита автоматический выбор запрещён.

Запрос/транслитерация пользователя вообще не попадают в OData клиента: поиск выполняется локально. Список не сохраняется на диск, в audit или Git и не передаётся AI. Весь provider transport — GET, account/read-only ENV и TLS guards сохранены. Write flag остаётся false; приближённое совпадение не разрешает create/post/PDF.

## Фактическая проверка

Последний человеческий voice прошёл STT и остановился на client resolution. Его исходная запись/текст не сохраняются, поэтому конкретное произнесённое название нельзя восстановить из audit. Последующие live GET с разным регистром вернули одинаковую запись: доказательств регистрозависимости текущей базы нет. Слабым местом был поиск всей фразы на сервере; реальный синтетический voice также воспроизвёл отдельный пропуск названия в LLM при корректном STT.

Проверены `$skip`/stable order и ограниченное чтение 443 активных имён (три страницы, без сохранения записей). Отдельная actual GET проверка вариантов case/spacing/punctuation, spoken Cyrillic/typo и неоднозначного личного имени прошла: 36 GET, ноль mutations. Application rehearsal с настоящими OpenAI STT/LLM и FirstBit прошёл: синтетическое OGG/Opus → найденная компания → supplier review → real preview → date edit → read-only refresh, 47 GET. Telegram transport и supplier-review click в этом изолированном rehearsal имитировались; это не новый человеческий voice E2E. Confidence guard не ослаблялся.

Проверки: `tests/test_company_search.py`, существующие `tests/test_client_choice.py`, `tests/test_firstbit.py`, `scripts/firstbit_readonly_smoke.py`. Итоговые команды и runtime deployment → [VERIFICATION.md](../VERIFICATION.md). [ExecPlan](../../.agent/plans/voice-company-search.md).


## Uncertain voice: readonly proposal only

Low-confidence STT is no longer discarded in the real readonly new-invoice flow. The typed untrusted transcript is interpreted as a new request only; it must pass the existing company-choice callbacks even if the name resolves exactly to one record. The recognized text is shown privately with the buttons so the user can check it. Fuzzy matches always remain suggestions. One mistaken letter in a three/four-letter acronym can produce up to five ranked candidates; two-letter approximate queries remain blocked. Selection is revalidated with fresh GET before history/preview. Uncertain edits or explicit financial preview overrides are blocked and the old confirmation is revoked. Fake/write workflow retains its original conservative STT rejection. Audio/transcript are not newly logged or persisted; the existing private response receipt can contain the text shown to its user.

After a FirstBit read failure, `/retry` reuses the local typed draft and selected identity, without new STT/LLM. It only prepares a new readonly preview/review; cancellation clears that draft. It does not replay production mutations. Preview and historical-source checks are unchanged.
