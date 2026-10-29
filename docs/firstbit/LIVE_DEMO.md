# Live Telegram read-only demonstration

## Active tunnel: ngrok

The owner requested replacing the repeatedly disconnecting Cloudflare tunnel. ngrok is now active; public health and the secure Telegram webhook were verified before the old Cloudflare process was stopped. The application itself was not restarted during the switch, preserving current process-local drafts/buttons. Payload inspection is disabled (`--inspect=false`), CLI logging is disabled, and agent API port 4047 is loopback-only. ngrok credentials pass via ENV/SecretStr, never CLI arguments/project config/logs. The existing external user config may be read for its token without modifying it.

Start/verify the existing app and ngrok: `.venv/Scripts/python.exe scripts/start_ngrok_demo.py`. `scripts/start_readonly_demo.py` detects the recorded ngrok provider and delegates to this launcher, including `--restart` when explicitly needed to reload the app. The owned PID guard recognizes both providers and never stops unrelated processes. For a switch from a running Cloudflare demo, do not use `--restart`: the old app/tunnel stays until the new public health and Telegram registration succeed. On a new machine obtain the signed official ngrok Windows agent and place it under ignored `.local/tools/ngrok.exe`, then privately configure `NGROK_AUTHTOKEN`.

Verified on the switched runtime: all five deep readiness checks READY, public unsigned webhook rejected with 403, signed operator `/start` accepted with 200 and delivered to the confirmed owner's Telegram. No invoice was requested in that transport rehearsal; it is not human-voice evidence. FirstBit remains GET-only. Agent downloaded from the official ngrok Windows download link, Authenticode `Valid`, signer ngrok Inc., version 3.39.13. Existing account credentials were reused; no new account, paid upgrade or remote deployment was assumed. Direct FirstBit/OpenAI connections and local-PC/network dependencies remain distinct from the selected incoming tunnel.

## Voice download / redelivery latency follow-up

A later slow voice failed Telegram file retrieval and then response delivery; Telegram redelivery added about two minutes. Healthy text processing in that sample was 10.5s. Voice lookup/download now have one bounded network retry, while the Telegram transport retries only connection establishment; uncertain send/PDF results still follow existing recovery. Actual synthetic Telegram file lookup/download measured 0.28s (83,030 bytes), distinct from total STT/LLM/FirstBit processing time. Full regression 488 passed; deep readiness returned READY after restart. The technical voice in the owner's chat belongs to this diagnostic, not an invoice or a new human-input test.

## Pre-customer demo check

Latest restart and final verification completed: TCP HTTP/2 is active, all five deep-readiness checks are READY after restart, and an actual Telegram prompt was delivered after real OpenAI/FirstBit resolution via a signed operator text. Fresh owner source review remains a real user action. Do not use old pre-restart buttons. The missing permanent server/domain was requested separately; no hosting or remote secret transfer has been assumed.

The temporary tunnel now uses TCP HTTP/2 rather than QUIC/UDP. Command parsing tolerates one transient OpenAI timeout/connection/5xx failure, with 25s per attempt and a 40s total limit, without repeating transcription or executing an invoice. Auth/quota/validation errors remain closed. A recognized transcript can be returned only to its own private chat on an exhausted parsing failure; it is not logged or persisted.

Run `.venv/Scripts/python.exe scripts/check_demo_ready.py --deep` before a presentation. It must report READY for local/public app, actual webhook/empty queue, FirstBit schema GET and one real grounded OpenAI patch. Deep mode uses the paid API and contains no production business data. The local computer/network and temporary tunnel remain deployment dependencies; permanent hosting needs an actual owner-provided server/domain. Current full regression **486 passed**, and actual synthetic voice/FirstBit preview/date/verify passed again (47 GETs, isolated simulated Telegram callbacks).

## 2026-10-27 recovery

Final restarted runtime: local and public health **200**, secure webhook matches the active tunnel, Telegram pending updates **0**. An authorized signed operator text reached actual OpenAI/FirstBit and delivered a fresh historical-source review prompt to the confirmed owner; the script did not click it. Private evidence `.local/runtime/runtime-recovery-public-check.json`. The demo is running locally with the existing temporary tunnel and current network connection, not a permanent-hosting availability guarantee.

Recovered an expired quick tunnel and intermittent DNS/network failure; no unrelated process was stopped when its PID matched stale runtime state. The stale state was archived after ownership/liveness checks. The launcher now rejects an API URL from a failed tunnel-creation log instead of registering it as the public webhook. FirstBit can retry an identical GET once for transient transport errors/timeouts; status/validation failures stay closed.

Current full regression: **479 passed**. Actual OpenAI STT/LLM with existing synthetic speech and FirstBit passed preview/date/refresh (47 GETs, isolated Telegram/review). A second owner-named company passed actual OpenAI text + FirstBit lookup/choice/preview/price/VAT/complete-title revision/refresh (63 GETs, isolated callbacks). An independent new TTS generation timed out, so no new-company voice success is asserted. Production FirstBit remains GET-only; no create/post/PDF. Details and actual commands: [VERIFICATION.md](../VERIFICATION.md).

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


## Speech/read recovery follow-up

Ngrok remains the active inbound tunnel: local/public health, Telegram webhook/queue, direct FirstBit metadata GET and OpenAI catalog checks passed. The latest available incident audits precede the ngrok migration: two uncertain-STT rejections, then parsed text requests failing in FirstBit resolution and separate Telegram delivery failures. The former generic BackendFailure erased the exact historical network/status cause; changing tunnel cannot prove or repair that direct egress failure. New safe audit codes distinguish timeout, transport, HTTP status and schema failure without URLs, raw text or provider payloads.

Uncertain new voice now produces mandatory company choices in readonly mode, including one exact candidate; [search rules](COMPANY_SEARCH.md). Uncertain financial edits still require clarification. After a failed read, use `/retry` without recording again. There is no unconditional recognition guarantee for unintelligible audio or missing provider data.
