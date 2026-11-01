# Restore live read-only demo and tolerate transient read failures

> Historical execution record, closed for current rollout. Statements, counts and pending observations below describe that checkpoint, not current availability or present requirements. Current behavior: [docs/firstbit/READONLY_PIPELINE.md](../../docs/firstbit/READONLY_PIPELINE.md); current verification: [VERIFICATION](../../docs/VERIFICATION.md).

## Goal and observed evidence
Owner requests recovery of the server and latest failing Telegram flow, then completion of the working preview stage. Existing app was healthy while its expired temporary Cloudflare tunnel reported Tunnel not found. Subsequent network DNS failures stopped tunnel creation. A stale tunnel PID was reused by an unrelated process; it was not stopped, and the stale state was archived only after verifying no owned process/server remained. Latest human voice passed STT and candidate selection, then FirstBit read and Telegram delivery timed out.

Read-only targeted probes also reproduced Cyrillic short-brand lookup failure inside a long legal company name. Real OpenAI parsing reproduced duplicate tax requests and a display rename emitted as a catalog addition; these are normalized only when explicit source text and identical values prove the intended patch.

## Changes and safety
- Existing launcher accepts URLs only after a successful quick-tunnel announcement; API error URLs cannot become webhook roots. DNS creation failure stops safely. Ownership/PID protections and secure webhook remain.
- Extend local similarity for spoken short brands inside longer names; all such results require explicit candidate choice, never financial/identity defaults.
- Preserve prepared context for grounded field patches mislabelled create only when no new client/invoice scope is requested. Normalize explicit display renames and identical tax duplicates; conflicting values remain blocked.
- FirstBit transport still exposes GET only. Retry an identical GET at most once after transient timeout/http transport failure, with 0.2s backoff and existing per-request/service deadlines. Never retry HTTP status/auth errors, oversized responses, malformed schema/data, cancellation or any mutation. TLS and ENV/SecretStr dedicated reader guards remain. No new metadata fields, raw provider data to AI, production dumps or financial write.
- Keep current OneC/BillingBasis/storage architecture. No new worker/watchdog/persistence. Telegram's existing receipt/delivery recovery remains authoritative.

## Verification and rollout
Focused regressions → full suite → offline application smoke → real GET/AI rehearsals using synthetic audio and isolated Telegram callbacks → restart existing single-worker demo → validate public health, secure webhook/queue and actual delivery to confirmed owner. Do not simulate owner choices in the running app. Stop at preview; accounting defaults, durable atomic idempotency/write/post/PDF remain separate gates.

## Progress
- [x] Inspect actual runtime/audits and recover network/process state safely.
- [x] Reproduce and fix local name/grounded patch issues with regressions.
- [x] Verify bounded GET retries and full/live checks.
- [x] Deploy, verify actual Telegram delivery and update runtime/context docs.

## Result

### Owner-requested ngrok switch
Verified an existing user-owned ngrok account config, obtained the official signed Windows agent (3.39.13, Authenticode Valid) under ignored .local/tools. Started a parallel endpoint with token ENV/SecretStr only, inspection/logging disabled, loopback API 4047. Verified public readonly health, registered and confirmed the secure Telegram webhook without dropping updates, then stopped only the owned old Cloudflare tunnel. App PID/drafts were retained. Added provider-aware process ownership/restart dispatch, a dedicated reproducible ngrok launcher and shared whitelisted HTTPS URL validation/readiness. No unrelated process, global ngrok configuration, FirstBit state or write permission was modified.

Focused runtime regressions: 18 passed. Deep readiness on ngrok: READY for all five checks. Actual public transport check: unauthorized request 403, signed operator /start 200 with real Telegram delivery to the owner; no financial command or FirstBit call in that rehearsal. Direct FirstBit/OpenAI egress and local network/host availability remain separate from this tunnel replacement.

### Network recurrence follow-up

Voice-latency follow-up: audited actual voice lookup timeout followed by delivery failure and delayed Telegram retry; healthy next text completed in 10.5s. Implemented bounded single retries only for idempotent getFile/validated voice download, plus HTTPX connection-establishment-only retry for Telegram. No uncertain delivery or PDF read/write retry. Added parsed audit marker for timing, without transcripts. Focused tests 113 passed, full suite 488 passed. Actual synthetic voice upload/getFile/download succeeded in 0.28s; 83,030 bytes, no FirstBit contact. Deep readiness after secure restart is READY. One restart attempt encountered transient Cloudflare DNS failure and the next succeeded; this remains a local network/temporary-hosting dependency, not a permanent uptime guarantee.
Actual later voice requests reached STT but timed out in OpenAI parsing at 20s; QUIC tunnel logs simultaneously showed UDP/network reconnect failures. Changed the existing tunnel transport to TCP HTTP/2 (no TLS relaxation/new workers). Official SDK parsing now has at most two identical attempts only for connection/timeout or 5xx errors, 25s per request, 40s total. Auth/quota, refusal, validation and cancellation do not trigger that retry. SDK-wide retries remain disabled, STT and provider/document execution are not repeated by this helper. Recognized user text is shown only back to the same private chat if parsing remains unavailable, never audit/disk.

Added `scripts/check_demo_ready.py --deep`: private typed readiness check for local/public health, actual secure webhook/empty queue, FirstBit consumed metadata via GET and one actual grounded AI patch (no business data). At that checkpoint the full regression passed 486 cases (28.99s); actual synthetic voice/LLM/FirstBit preview/date/refresh passed again, 47 GETs, simulated Telegram/review only in the isolated rehearsal. Before redeployment, readiness passed all five checks. At that earlier checkpoint permanent hosting had not been supplied; later Linux deployment is documented in SERVER_DEPLOYMENT.

Final follow-up deployment: restarted actual app/tunnel with HTTP/2 and latest private-feedback behavior. `check_demo_ready.py --deep` again returned READY for all five checks after restart. Signed public operator request resolved actual FirstBit and delivered the fresh historical-source review prompt to the confirmed owner's real Telegram; owner choice was not simulated. Audit request completed successfully. No production mutation; current runtime remains local/temporary until the owner supplies a permanent hosting target.
Full regression **479 passed** (28.26s); focused preview suite 46 passed; offline application smoke passed (96 GETs, 4 mocked AI requests). Actual configured-client GET-only prepare/refresh passed. Existing synthetic voice through actual STT/LLM/FirstBit passed preview/date/refresh (47 GETs). Second owner-named company through actual OpenAI text/FirstBit passed candidate selection, historical-source review, preview, combined price/VAT/full-title edits and refreshed verification (63 GETs); isolated Telegram and choices were simulated only in the rehearsal. A separate new TTS request timed out and is not claimed as success.

Deployed via `scripts/start_readonly_demo.py --restart`: READY, pending updates retained. Private `.local/runtime/check_recovery_public.py`: PASS, local/public health 200, actual OpenAI/FirstBit read resolution and actual Telegram delivery to confirmed owner through a signed operator text. Real owner review was left pending, not simulated. `getWebhookInfo` confirms the current URL and pending_update_count=0; writes false. Docs/router/index updated; no new metadata consumption or production dumps. Read-only stage is operational under the current network connection; temporary local tunnel uptime is not a permanent-hosting guarantee. Create/post/PDF and durable/accounting write gates remain separate.


### Follow-up: uncertain speech and FirstBit read recovery

Plan: inspect latest safe stage logs and current direct/public connectivity; preserve ngrok unless actual ingress evidence warrants switching; route uncertain speech only to a new readonly proposal with mandatory existing company-choice callbacks; keep uncertain edits/fake writes blocked; recover a failed typed draft with /retry without repeating STT/LLM; expose only allowlisted provider failure codes to safe audit; run focused/full regressions and GET-only application smoke, then deploy and verify readiness. No metadata/schema/storage/write changes.

Evidence: latest available user logs contain low-confidence STT clarifications, followed by successfully parsed text and generic FirstBit read failures with separate Telegram delivery failures. Historical failures were recorded before the ngrok switch; their exact underlying status was lost by generic error wrapping and cannot be reconstructed. Readiness at that checkpoint passed all five checks with ngrok. New audits distinguish bounded timeout/transport/HTTP-status/schema categories without recording URLs, text, records or secrets.


Follow-up implementation/verification complete: mandatory company-choice gate for uncertain new readonly speech, explicit rejection of uncertain edits, three/four-letter single-error acronym suggestions, readonly typed draft retry, and bounded safe provider failure classifications. Full regression 507 passed (31.00s); offline application smoke 96 GETs/four mocked AI calls passed; actual one-line GET-only prepare/refresh passed. Reloaded owned app only, preserving ngrok/webhook; deep readiness all five checks READY. No new metadata fields/storage or write permissions; previous process-local buttons require a fresh request after reload.
