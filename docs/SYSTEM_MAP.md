# System Map

## Flow 1 — Telegram webhook admission

### Trigger
`POST /telegram/webhook`.

### Path
```text
FastAPI
→ secret token HMAC check
→ bounded body read
→ Update Pydantic validation
→ actor/chat allowlist checks
→ process gate
→ receipt dedupe
→ Bot.handle
```

### Code
- `app/main.py`
- `app/telegram_models.py`
- `app/validation.py`

### Invariants
- private chat only;
- numeric allowlist;
- no forwarded/sender_chat inputs;
- max 32 KiB;
- changed payload under same update ID = conflict;
- failed delivery is not acknowledged as success.

---

## Flow 2 — Text/voice to invoice intent

### Trigger
Telegram message.

### Path
```text
Bot.prepare
→ text OR voice
→ voice download + STT when needed
→ CommandInterpreter
→ controlled intent / draft merge
→ InvoiceCommand
→ FirstBit client resolution
→ when ambiguous/partial: typed candidates → user selection button → fresh GET revalidation
→ existing InvoiceService.prepare → historical basis → preview
```

### Code
- `app/bot.py`
- `app/ai.py`
- `app/voice.py`
- `app/language.py`
- `app/intent.py`
- `app/parser.py`

### Invariants
- attempted edit revokes old confirmation before parsing;
- LLM cannot supply unapproved financial fields;
- external AI output is validated;
- voice uncertainty can reject input;
- recovery state blocks new command/STT.
- client-choice callbacks carry a token/index, never a caller-provided client ID; candidates are not sent to AI;
- client selection authorizes only continuing resolution; missing history/price still blocks preview.

---

## Flow 3 — Prepare / resolve

### Trigger
Valid `InvoiceCommand`.

### Path
```text
InvoiceService.prepare
→ resolve_client
→ resolve_service(s)
→ build ResolvedInvoiceCommand
→ resolve_basis
→ validate provider preview against request
→ PreparedInvoice
```

### Code
- `app/service.py`
- `app/domain.py`
- OneC adapter (`app/fake_onec.py` or GET-only `app/firstbit.py`)

### Invariants
- provider must return full preview;
- provider cannot silently change requested period/service/quantity/tax intent;
- failures become safe `WorkflowFailure("resolve")`;
- UserProblem remains controlled clarification.

### Real FirstBit extension
`APP_MODE=firstbit_readonly` selects FirstBit reads for client/service/basis. A historical proposal is explicitly non-executable; live GET prepare/refresh now passes. Client selection uses the Telegram request independently of the smoke script's client. See `firstbit/READONLY_PIPELINE.md`.

---

## Flow 4 — Preview / confirmation / edit

### Trigger
Prepared invoice.

### Path
```text
Bot.show_preview
→ store DraftContext
→ if historical/current issuer mismatch: per-user source-review token → fresh GET → explicit review
→ create Pending token (5 min)
→ Telegram preview + buttons
→ confirm / edit / cancel
```

### Code
- `app/bot.py`
- `app/presentation.py`

### Invariants
- no financial mutation before final confirm;
- token tied to user;
- expired/wrong token rejected;
- edit removes pending confirmation;
- new preview = new token.

---

## Flow 5 — Pre-write refresh

Read-only variant: `Bot.confirm -> InvoiceService.refresh -> fresh resolve_basis -> compare revision/preview -> new preview or verify-only acknowledgement`. It never calls execute. The provider's operation lookup remains unknown; preview verification makes no financial-operation state assertion. The path below remains the fake/future writable-provider path.

### Trigger
Confirm.

### Path
```text
Bot.confirm
→ InvoiceService.refresh
→ read_operation
→ if unknown: freeze into recovery
→ if already started: keep frozen prepared
→ if not_started: resolve_basis again
→ compare basis key/snapshot
→ maybe show updated preview
```

### Code
- `app/bot.py`
- `app/service.py`

### Invariants
- unknown blocks write;
- changed basis snapshot requires re-confirmation;
- started operation is never reinterpreted from new free text.

---

## Flow 6 — Execute

### Trigger
Confirmed/frozen `PreparedInvoice`.

### Path
```text
InvoiceService.execute
→ read_operation
→ ensure_draft if not_started
→ ensure_posted if draft
→ get_pdf if posted
```

### Code
- `app/service.py`
- OneC adapter

### Invariants
- write guard before real mutation;
- document identity checked;
- preview digest checked;
- posting must return same document;
- no blind mutation retry.

---

## Flow 7 — Mutation uncertainty / recovery

### Trigger
Exception after create/post call.

### Path
```text
catch
→ mark state unknown
→ one read-only reconciliation
→ classify not_started/draft/posted/unknown
→ WorkflowFailure
→ Bot stores recoveries
→ /retry resumes frozen PreparedInvoice
```

### Code
- `app/service.py`
- `app/bot.py`

### Invariants
- lost response != rollback;
- `/retry` does not resolve client again;
- new commands blocked while recovery exists;
- same operation ID retained.

---

## Flow 8 — PDF delivery

### Trigger
Posted invoice + valid `PdfDocument`.

### Current fake path
```text
FakeOneC.get_pdf
→ app/mock_pdf.py
→ PdfDocument validation
→ Telegram sendDocument
```

### Production target
```text
real OneC standard print form
→ PdfDocument validation
→ Telegram sendDocument
```

### Invariants
- fake PDF only for mock;
- PDF bytes must begin `%PDF-` and end `%%EOF`;
- max 10 MB;
- Telegram delivery uncertainty must not cause blind duplicate file sends.

---

## Flow 9 — Production FirstBit read-only resolution

Company lookup: original text/STT → company span (verbatim explicit-phrase fallback if model omits it) → fresh bounded name-only GET pages → local canonical identity / approximate ranking → unique exact match or user choice → fresh active Company GET → contract/history/basis. Case/spacing/punctuation are ignored; approximate/spoken/transliterated matches require buttons. No company search text or name directory enters AI/OData syntax. [Rules](firstbit/COMPANY_SEARCH.md).

Preview corrections reuse this flow: text/voice → grounded spans (price/tax/name/explicit row) → local draft → command overrides → source/LineNumber binding → validated history + VAT GET → Decimal recomputation → marked preview/new token. Refresh repeats reads; execute rejects manual proposals. [Details](firstbit/PREVIEW_REVISIONS.md).

### Trigger
Real OneC adapter `resolve_*`.

### Company
```text
spoken/text name
→ normalized exact lookup in Catalog_Companies
→ exclude folder/deleted
→ aliases if reviewed
→ ambiguous => clarification
→ stable Ref_Key
```

### Contract
```text
Company.ContractByDefault_Key
→ fetch contract
→ owner/active validation
→ fallback by Owner_Key
→ exactly one active candidate required
```

### Bookkeeping basis
```text
Company + Contract
→ newest posted non-deleted Document_InventoryExpense
→ find invoice containing bookkeeping Item
→ preserve all matching rows
→ create current proposal/preview
```

### Integration-specific invariant
Current fake pricing logic and real FirstBit pricing logic are not assumed identical.

---

## Flow 10 — Metadata/OData consumed-field guard

### Trigger
FirstBit resolve_client / resolve_service / resolve_basis (fresh GET `$metadata`).

### Path
```text
fresh metadata
→ validate used EntitySets/property types and Inventory collection
→ pass OR block
```

### Invariants
- no guessed property names;
- no automatic baseline acceptance;
- schema drift blocks write paths.

Implemented minimal read-only guard: `app/firstbit.py`. A full reviewed write baseline and live validation remain later gates; synthetic metadata proves only application guard behavior.
