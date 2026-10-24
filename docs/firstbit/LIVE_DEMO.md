# Live Telegram read-only demonstration

## Latest company-name correction

The updated bot was restarted and its secure webhook is ready, both local/public health 200. An authorized signed operator text using the Cyrillic spoken company name reached actual OpenAI/FirstBit and delivered actual company-choice buttons to the owner; the script left selection to the owner. Private evidence `.local/runtime/company-search-public-check.json`. Old buttons are invalid after restart; continue with the fresh choices or a new request.

Company lookup accepts case/spacing/punctuation and suggests local spoken-acronym/transliteration/typo matches via existing candidate buttons. Explicit «счёт для …» source text repairs a missing model client; quoted names/date-like words inside names are preserved conservatively. See [COMPANY_SEARCH.md](COMPANY_SEARCH.md). Current regression: **465 passed**; actual GET spelling checks passed (36 GETs), and synthetic voice through real STT/LLM/FirstBit reached real preview, date edit and refreshed verification (47 GETs, isolated simulated Telegram/supplier choice). Speech confidence safeguards remain unchanged. No production write/PDF is enabled.

## What is running

Local Windows app with `APP_MODE=firstbit_readonly`, `AI_MODE=openai`, `ONEC_WRITE_ENABLED=false`, one Uvicorn worker on 127.0.0.1:8000, a temporary Cloudflare HTTPS tunnel and the registered Telegram webhook. Bot: `https://t.me/buhgalter32_bot`.

The owner requested restart and real Telegram/OpenAI tests. They chose to keep GPT API after considering Qwen; no Qwen provider/config was added. Production FirstBit remains GET-only. Real create/post/PDF is a later explicitly controlled stage.

## Verified live

- Bot API getMe succeeded. Owner's actual `/start` reached the app through Telegram/webhook.
- Replaced the expired tunnel and registered the new webhook using the existing secret, `message`/`callback_query`, one connection and no dropped pending updates.
- Public `/healthz` returned 200 / firstbit_readonly.
- A signed rehearsal request through the public webhook resolved real FirstBit data and delivered a preview to the owner's confirmed private chat. The app recorded resolve success and successful update handling, which includes validated Telegram delivery acknowledgment. This rehearsal was injected explicitly; it was not a human voice message.
- Restart helper was exercised with `--restart`; application/tunnel restarted and secure webhook registration succeeded. A fresh preview was then delivered to the same confirmed chat.
- OpenAI initially returned **429 credit_balance_exhausted**. After the owner funded the account, actual `gpt-4o-mini` structured intent extraction passed with grounded client/date/service, and actual `gpt-4o-mini-transcribe` transcription of locally synthesized WAV passed the application's confidence check (22 token confidence entries).
- The existing running app then accepted a signed natural-language rehearsal through the public webhook, called real OpenAI, resolved real FirstBit and delivered a new preview to the owner's confirmed Telegram chat. No app restart or provider change was needed after refilling the same key.

Live STT and LLM now pass. An actual incoming owner Telegram voice subsequently passed download/STT and reached client resolution, which safely stopped on two active records with identical short/full names. Bounded GET diagnostics confirmed both records and distinct default contracts; no posted invoice history was found for either company, including other contracts. Owner explicitly selected diagnostic option 1. No production names/IDs are recorded here. A complete human voice -> successful preview is still unproven for this client because the financial basis is absent. OpenAI serves speech transcription and structured language intent extraction; FirstBit resolution/calculation stays deterministic and outside the model.

Duplicate/partial names now produce numbered candidate buttons using typed adapter results. The chosen ID comes only from stored per-user candidates and is rechecked with fresh GETs; new input/cancel/five-minute expiry invalidates the buttons. Choosing a company does not authorize writing or manufacture its historical basis. Plan: `.agent/plans/client-choice-readonly.md`.

Deployment recheck: 364 tests pass, including independent service enforcement of the chosen client ID. Actual FirstBit application-level selection rehearsal used the owner's chosen diagnostic record 1, performed 9 GETs and correctly stopped on missing posted history. Telegram transport was synthetic inside that selection rehearsal; its result was separately delivered to the confirmed owner chat through real Telegram. The restarted public app then delivered actual candidate buttons using real FirstBit and real Telegram; input was explicitly signed operator text, not a new human voice/click. Regular live GET preview prepare/refresh still passes on the configured smoke client. No global alias was added and no FirstBit write occurred.

## API access restored; next human test

### Voice/history preview follow-up

Price/VAT/display-name revisions are now supported on existing preview; [rules and examples](PREVIEW_REVISIONS.md). Latest regression: **422 passed**. Actual OpenAI text and synthetic OGG/Opus voice edits against actual FirstBit passed in an isolated application rehearsal (72 GETs, simulated Telegram/review, zero writes). Explicit zero percent is decoded from the user's literal words, distinct from exempt even if the model mislabels it; duplicate model rename/addition is reduced to the requested display rename. Bot was restarted in read-only mode; old buttons require a new request. This adds no create/post/PDF readiness.

Reproduced another owner-named client through fresh GET. The concrete blocker was source-versus-current-contract issuer mismatch; no claim is made about unavailable old Telegram reply text. The new flow requires an explicit historical-supplier review, refreshes before acceptance, and then displays a compact financial preview with unresolved new-document supplier/defaults still visible. A supplier choice is not write approval. Preview no longer prints raw source/contract UUIDs or repeated empty-default paragraphs.

**382 tests pass.** A real synthetic OGG/Opus recording was transcribed through actual OpenAI STT, interpreted by actual OpenAI, and resolved against actual FirstBit through the application webhook. In that isolated rehearsal, Telegram transport and supplier-review click were synthetic. It produced a one-line real preview, then an actual LLM text date edit retained the client/review, and read-only refresh confirmation passed (42 FirstBit GETs, zero mutations/PDFs). A preceding voice attempt failed the existing confidence threshold, correctly before LLM/FirstBit; thresholds were not relaxed. The user now sees the recognized transcript privately when that happens. Synthetic audio was generated only from the owner-provided request; no FirstBit payload was sent to AI.

The updated running public app then accepted an explicitly signed natural-language operator request, used real OpenAI and FirstBit, and delivered the supplier-review prompt to the confirmed owner's real Telegram chat. An actual incoming owner callback subsequently accepted that source review; after fresh GET the app completed validated real Telegram preview delivery. That is real human review/delivery, while the initial invoice text was an operator rehearsal and the earlier voice was synthetic. Private evidence: `.local/runtime/bmt-voice-check.json`, `.local/runtime/bmt-public-check.json`, `.local/firstbit/bmt-voice-preview.txt`; private filenames are not Git fixtures. The normal live preview prepare/refresh still passes for the configured smoke client. No complete new-document/write/post/PDF readiness is claimed.

The owner restored the API project's credit balance; real paid checks now succeed. GPT API is retained. Never paste keys into chat/docs/Git. Changing `.env.local` requires restart to load a different key; refilling the same key did not require restart.

Then, in the bot's private chat:
1. `/start`.
2. Speak one client name, the invoice date, and bookkeeping service. Choose a record with the candidate buttons if names are duplicate/partial; verify its full name, TRN and record ID. There is no fixed-client restriction: `FIRSTBIT_SMOKE_CLIENT` belongs only to smoke helpers.
3. Check the full proposal, historical source, separate rows, quantities/prices/VAT/totals. Missing/ambiguous basis or unsupported arithmetic blocks resolution.
4. Speak a quantity/date edit or [price/VAT/description correction](PREVIEW_REVISIONS.md) and verify the previous button is invalidated. Price is net per unit in the preview currency; multiple rows require a target row for price/name.
5. Press “Проверить preview” or cancel. This stage must never create/post a document or send a production PDF.

Private ready-to-copy text and voice examples using the owner's configured demo client are saved in `.local/runtime/demo-instructions.txt`. The strict legacy text example avoids a paid LLM request; natural-language input also now passes the real OpenAI -> FirstBit -> Telegram path. The next check is the owner's actual Telegram voice. Do not send real customer names or these private files to public repositories.

## Start/restart on this machine

```powershell
.\.venv\Scripts\python.exe scripts/start_readonly_demo.py
# After updating ENV, or to replace a stopped tunnel:
.\.venv\Scripts\python.exe scripts/start_readonly_demo.py --restart
```

The launcher checks typed private ENV before stopping anything, manages only this workspace's recorded process IDs, runs the app/tunnel hidden, waits for health and registers the webhook without exposing credentials or dropping pending updates. Existing foreign processes/PIDs are rejected. Windows PowerShell script execution policy remains unchanged; the entrypoint is Python.

An already-running tracked app reports that it is running; use `--restart` to reload ENV or recover a lost tunnel. Receipts/confirmation state are process-local: restart invalidates old preview buttons; issue a fresh request afterward. Background processes continue after the command exits, but the computer and network must stay available for the demo.

Before launching new processes the helper preserves the existing four operational logs under ignored `.local/runtime/archive/`, so restart no longer destroys safe stage evidence. No transcript/business-response logging or persistent financial/session storage was added.

On this machine `.local/tools/cloudflared.exe` was downloaded from the official Cloudflare release and its SHA256 was checked against the release digest. It is an ignored local prerequisite, not a Git dependency. On a fresh machine obtain the Windows amd64 binary from [Cloudflare downloads](https://developers.cloudflare.com/tunnel/downloads/) and place it at that private path. The tunnel is temporary and its hostname changes on restart, as described by [Cloudflare Quick Tunnels](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/).

## Private runtime state

- `.local/runtime/demo-processes.json`: owned app/tunnel PIDs and current public URL, no credentials.
- `.local/runtime/app.stderr.log`: explicit safe audit events, never command text or provider bodies.
- `.local/runtime/tunnel.stderr.log`: tunnel operational log.
- `.local/runtime/real-telegram-check.json`: signed rehearsal result.
- `.local/firstbit/readonly-preview.txt`: private formatted FirstBit preview.

All remain ignored. Future write admission still requires durable identity/uniqueness, current accounting/default rules, reconciliation and a separately approved draft-only test; posting and standard PDF follow separately.
