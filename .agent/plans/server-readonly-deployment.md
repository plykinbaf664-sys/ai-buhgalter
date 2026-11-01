# Isolated server deployment of ai-buhgalteria

> Historical execution record, closed for current rollout. Statements, counts and pending observations below describe that checkpoint, not current availability or present requirements. Current behavior: [docs/SERVER_DEPLOYMENT.md](../../docs/SERVER_DEPLOYMENT.md); current verification: [VERIFICATION](../../docs/VERIFICATION.md).

## Goal
Move the current verified readonly Telegram application to the owner's Balance Pro server without touching other applications or their credentials. Deliver a supervised single-worker service, private configuration, HTTPS webhook, reproducible checks and rollback.

## Evidence and scope
Repository is clean at the starting revision. Current app is FastAPI, Python >=3.10, pinned requirements; no persistence and no Linux deployment packaging. Server is Ubuntu 24.04/Python 3.12 with existing Caddy HTTPS and other live services. Port 8000 belongs to another service and must not be reused. Existing local Windows/ngrok deployment stays available until successful cutover.

## Invariants
- FirstBit dedicated reader, TLS, GET-only adapter, APP_MODE=firstbit_readonly, ONEC_WRITE_ENABLED=false; no financial mutations or production PDF.
- One worker/process; no new persistence or claim of write-grade idempotency. Restart invalidates process-local choices.
- Only this project's directory, user, unit and explicitly scoped HTTPS route may be added. Never restart/stop unrelated services, replace shared configuration, change firewall globally or upgrade shared dependencies.
- Secrets transferred via verified SSH only, separate from source bundle; ENV/SecretStr at runtime. No raw ENV, credentials, production records or diagnostic dumps in source bundle, command arguments, logs or Git.
- LLM receives only existing user-input/span context. Schema drift/business uncertainty still fail closed.

## Plan
1. Inspect tracked files, config/runtime, host resources/services and existing HTTPS routing; write an explicit source allowlist and exclude .git/.local/.env.local/venv/caches/artifacts. Check for embedded secrets and package integrity.
2. Add the smallest Linux runner, single-worker hardened systemd unit and safe health/webhook deployment tooling. Isolate dependencies and a non-login user under /srv/ai-buhgalteria; bind to an unused loopback port. Determine HTTPS routing from actual server evidence, preserving all existing routes.
3. Build a reviewed source archive with hashes; transfer it and only necessary settings separately with restrictive permissions. Verify source hash, typed settings and dependencies on Linux; run full regression and offline application smoke there.
4. Start only the project service; verify localhost admission controls and production GET-only FirstBit/real AI readiness. Establish project HTTPS endpoint without displacing existing traffic. Save prior webhook locally/private, switch Telegram without dropping queued updates, verify public admission and actual authorized delivery.
5. Recheck unrelated service/config health and project restart behavior; document operations, rollback, retention, security limits and actual evidence. Stop only owned local demo runtime after successful cutover if necessary to prevent duplicate ownership.

## Failure/recovery
Do not switch webhook while health/config/metadata/AI checks fail. On failed cutover restore previous webhook without dropping updates and stop only the new project unit. Keep previous release/config private; do not delete shared files. Service restart loses draft/callback state, so request fresh input. No automatic replay of financial mutations exists.

## Verification criteria
Clean source archive, no local/private dumps; private ENV access; non-root service with bounded resources and loopback bind; one worker; full tests and offline smoke green on target Python; production GET-only metadata/resolution smoke; public HTTPS and unsigned webhook denial; Telegram configured to new endpoint with zero discarded updates; actual authorized Telegram delivery; other services stay running and unchanged. Exact deployment details and unresolved blockers must be reported without secrets.

## Progress
- [x] Initial repository and host inventory; existing services identified, no remote mutation yet.
- [x] Prepare package and Linux runtime.
- [x] Install isolated release/config and verify on server.
- [x] Cut over webhook after readiness checks, preserving queued updates.
- [x] Final isolation/cleanup/documentation verification.

## Implementation and observed verification

Source release uses explicit path allowlist, secret scan, archive SHA-256 and per-file source manifest. No Git/ENV/local metadata/business dumps/venv/caches/artifacts were transferred in the source archive. Necessary runtime secrets travelled separately over verified SSH, then moved into root-only config; they are never shell sourced. No shared Python/system packages were changed. Existing pinned requirements installed in the project venv on Python 3.12, with resolved dependencies recorded privately and pip check passing.

Added `scripts/run_server.py`, `scripts/server_control.py`, project-only systemd unit, Caddy route and secret-header log filter, namespaced log retention, runtime security tests and `docs/SERVER_DEPLOYMENT.md` as the deployment source of truth. Router/index links updated. Windows launcher path separators normalized consistently: the first Linux regression run exposed one simulated Windows path mismatch; the final Linux run passes all tests. No accounting business rule or schema changed during deployment.

Actual commands/checks:
- Local full `python -m pytest -q`: **579 passed**, 45.29s. After the path-normalization fix, focused runtime tests: **29 passed**.
- Target Python 3.12, dedicated non-root user: `python -m pytest -q -p no:cacheprovider`: **579 passed**, 32.57s, after the fix. Offline `scripts/firstbit_readonly_smoke.py`: PASS, 96 synthetic GETs/four mocked AI calls, no production contact. `pip check`: no broken requirements.
- Target `scripts/firstbit_readonly_smoke.py --live`: PASS through real FirstBit prepare/refresh to InvoicePreview; GET only, zero mutations/PDF, no AI/Telegram.
- Private isolated target application rehearsal of the owner's two-service request: real AI + **75 production FirstBit GETs**, two-line preview with net 2800 + verified VAT 140 = 2940 AED. Telegram and choices were simulated, not actual owner actions.
- Private target synthetic-voice rehearsal: actual OpenAI TTS/STT/LLM + **30 production FirstBit GETs**, real historical InvoicePreview, simulated Telegram/choices. This is synthetic OGG/Opus, not a human recording. A separate complex audio rehearsal needed service clarification or was blocked by financial speech confidence; those guards were retained. Do not claim every voice succeeds without clarification.
- `scripts/server_control.py check --deep`: local/public readonly health, unsigned webhook 403, actual fresh production metadata GET and grounded OpenAI date check PASS. Registration subsequently confirmed the new webhook and zero pending updates; none were dropped.
- Signed operator text through actual public server HTTPS endpoint: HTTP 200 and actual Telegram response. The first two-service public rehearsal asked for language clarification; a compact company/period request then passed actual AI/company resolution and delivered company-choice buttons. The two-service complete preview is separately proven in the isolated target rehearsal above; do not conflate it with live owner clicks. Actual owner's subsequent choices were left to the owner. Private local report `.local/deploy/public-result.json`.
- Caddy adapted configuration compared before reload: existing application routes/listeners preserved; only the project route and Telegram-secret log redaction imports added. Caddy's automatic config-file hiding list gains the imported files (additional denial); its order is immaterial. Caddy was gracefully reloaded, not restarted.
- Deliberate stop of **only** the project unit and a synthetic secret request produced 502. The initial check exposed default proxy error-header logging; the final filter removed the sentinel from Caddy error logs. Unit restarted and deep readiness passed. No real secret was used in that failure test.

Readiness/registration invoke temporary project-owned check units with protected EnvironmentFile; no credentials enter argv. Service is enabled for boot and constrained to one worker, loopback bind, dedicated uid, readonly code, protected home/system, no capabilities, resource limits, private temporary files and project journal namespace. State remains process-local. Previous webhook and Caddy evidence stay private for rollback; the local runtime is retained as fallback but receives no active webhook traffic.

Side effects were limited to project files/user/unit, project HTTPS/log imports, authorized OpenAI calls, Telegram configuration and two owner test responses. All production FirstBit calls were GET, with ONEC_WRITE_ENABLED=false. Other project code, ENV, units, dependencies and firewall were not modified. Server-wide reboot was deliberately not used as an autostart test. Create/post/PDF, durable write idempotency and accounting defaults remain out of scope.

Final isolation audit PASS: existing service PIDs and start timestamps, including Caddy, match the pre-deployment snapshot. Runtime UID is dedicated/non-root; service cannot read the root-only ENV file directly or write its code; boot enablement and loopback-only listener confirmed. Public private-file paths return 404. Namespaced audit confirms actual server AI parse, company-choice response and completed Telegram delivery. Actual runtime secrets were absent from project/Caddy journals. Private temporary smoke configuration, generated audio and rehearsal code were removed; safe result summaries and rollback evidence retained. The actual public tests delivered two operator responses (one clarification and one company choice), without simulating owner decisions.
