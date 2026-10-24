# Live Telegram voice demonstration, FirstBit read-only

## Goal and authorization
Owner requested application restart and real Telegram/OpenAI verification: accountant voice -> STT/LLM -> FirstBit -> invoice preview in chat. Production create/post/PDF remain forbidden; future posting requires a separate plan and controlled write admission.

## Initial evidence
No app/tunnel process was running; configured Telegram bot authenticates, but previous trycloudflare webhook is unreachable. FirstBit live prepare/refresh already passes. OpenAI model discovery works through the app's explicit official base URL; gpt-4o-mini and gpt-4o-mini-transcribe are available. Real response generation returned 429 credit_balance_exhausted. Owner asked asynchronously to restore API credit/key while runtime preparation continues.

## Work
Add a minimal local entrypoint loading ignored ENV and enforcing firstbit_readonly/AI_MODE=openai/write=false; run one localhost Uvicorn process and a Cloudflare demo tunnel. Keep PID/log/URL state under ignored .local/runtime. Register webhook with existing secret and allowlist, retaining pending updates. Use existing application paths for a real Telegram text preview and verification; test actual STT/LLM/voice after credit is restored. Never send real provider catalogs/history/bank/GL records to AI. Test commands may contain only the user-supplied client query and dates. Third-party messages only to the configured authorized private chat as requested for this demo.

## Safety and validation
TLS verification stays on; no secrets in commands/logs/Git. Cloudflared downloaded from official Cloudflare release and checked against release SHA256. FirstBit transport remains GET-only. Keep the user informed of actual live versus synthetic evidence. Preserve existing tests, check current health/public webhook and Telegram acknowledgments. No fabricated claim of voice success if billing remains blocked.

## Progress
- [x] Identify absent runtime and expired tunnel.
- [x] Verify Telegram auth and OpenAI credit blocker.
- [x] Start application and replacement tunnel, register secure webhook.
- [x] Verify actual Telegram preview delivery; control semantics remain covered by existing app tests and live FirstBit refresh, not a claimed human button click.
- [x] Record the initial OpenAI billing failure, then verify real LLM and STT succeed after the owner restores API credit.
- [x] Update runtime instructions/evidence and leave a working demo process.
- [x] Verify natural-language input through real OpenAI -> FirstBit -> Telegram preview after funding.
- [ ] Observe an actual incoming human Telegram voice update through STT -> resolution -> preview delivery.

## Initial result before API funding

Owner retained GPT API after considering Qwen; no provider migration performed. An actual incoming `/start` was received; owner confirmed that chat for testing. Signed public webhook rehearsals delivered real FirstBit previews to that chat, including a fresh preview after restarting through the new helper. No production FirstBit writes or PDFs. No human voice success is claimed. Official API model list succeeds, but real LLM and synthetic-WAV transcription requests both fail billing with credit_balance_exhausted. Credentials remain private; user must restore credit or replace the local key before final live voice testing.

Added scripts/run_local.py (typed ENV/read-only startup), scripts/start_readonly_demo.py (owned hidden processes and tunnel), scripts/register_demo_webhook.py (typed secure registration). No PowerShell execution policy change. Cloudflare release binary is private and digest-verified. Launcher --restart verified, /healthz 200 firstbit_readonly, Telegram webhook READY, pending updates retained. Docs/firstbit/LIVE_DEMO.md records the runbook and limits.

Final regression: 342 tests passed, including 3 process-ownership safety tests; compileall and whitespace checks passed. Local and public health 200/firstbit_readonly; current Telegram pending update count zero. Text demo is live; the requested human voice demonstration remains blocked on actual OpenAI API credit. No financial write capability was enabled.

## Follow-up after the owner funded the API account

Actual gpt-4o-mini structured intent extraction now passes client/date/service grounding. Actual gpt-4o-mini-transcribe on the existing synthesized WAV passes Transcript and confidence validation (22 confidence tokens). An explicit signed natural-language request through the existing public webhook then passed real OpenAI -> FirstBit -> Telegram preview delivery. Same running app and key; no restart, no provider change, no FirstBit writes. Private summaries: .local/runtime/openai-funded-check.json and funded-natural-language-check.json.

Owner was asked to send a real Telegram voice update. Human voice success is not inferred from synthetic WAV or signed text rehearsals; observe actual stt/resolve/update success in safe app audits before claiming that part complete.

## Actual human voice and client-choice follow-up
An actual owner Telegram voice subsequently passed download/STT and reached client resolution. GET diagnostics found two active records with identical names and no posted history for either client. Owner selected private diagnostic option 1 and requested candidate buttons. Implemented and deployed explicit per-user candidate selection; 364 tests pass. Application-level real GET selection correctly blocks on absent history; public runtime candidate buttons were delivered through real Telegram. See client-choice-readonly.md. Full human voice -> successful preview remains incomplete for that financial basis; no create/post/PDF enabled.
