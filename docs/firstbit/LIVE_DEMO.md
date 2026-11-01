# Local Windows read-only fallback

The deployed bot uses the Linux server. Operational source of truth: [SERVER_DEPLOYMENT](../SERVER_DEPLOYMENT.md); verification scope: [VERIFICATION](../VERIFICATION.md). This guide describes only the optional local fallback. A local tunnel is not required while the server is active.

## Local prerequisites and side effects

`scripts/run_local.py` explicitly loads ignored `.env.local`, validates real readonly/OpenAI settings and binds one worker to `127.0.0.1:8000`. ENV format is literal unquoted `KEY=value`, not arbitrary shell code. Ordinary `create_app` does not load that file itself.

`scripts/start_readonly_demo.py` manages recorded owned Windows processes; `scripts/start_ngrok_demo.py` manages the ngrok path. These launchers can **register the bot's webhook**, replacing its server endpoint. Do not run against the working bot casually: use an isolated bot or an authorized fallback operation, with the previous webhook saved.

## Commands

```powershell
.\.venv\Scripts\python.exe scripts/run_local.py --check
.\.venv\Scripts\python.exe scripts/start_ngrok_demo.py
# Explicitly reload app/config when needed:
.\.venv\Scripts\python.exe scripts/start_readonly_demo.py --restart
.\.venv\Scripts\python.exe scripts/check_demo_ready.py --deep
```

The common launcher delegates according to stored tunnel provider. It supports cloudflared and ngrok, verifies ownership/liveness before stopping recorded PIDs, and rejects unrelated/reused processes. Hidden processes, no PowerShell execution-policy changes. Restart loses local drafts/buttons/receipts; use a fresh request.

ngrok prerequisites: reviewed official signed Windows agent at ignored `.local/tools/ngrok.exe`, private ENV/SecretStr `NGROK_AUTHTOKEN` or existing approved user config. Inspection and CLI payload logging are disabled; local inspection API is loopback-only. The alternative cloudflared binary belongs at `.local/tools/cloudflared.exe`; its tunnel uses TCP HTTP/2. Binaries/configs are not repository dependencies.

Launchers validate app/public health before webhook registration, retain queued Telegram updates and use the existing secret, message/callback_query updates and one connection. `scripts/register_demo_webhook.py` intentionally validates supported tunnel roots, not the server's path-prefixed URL. Use `scripts/server_control.py` for server operations instead.

## State and readiness

Ignored `.local/runtime/demo-processes.json` contains owned PIDs/provider/public URL. Operational audit/tunnel logs and previous-webhook information remain private there; logs are archived during restart. These files are not durable invoice/session storage. Do not copy runtime artifacts into fixtures/docs or mistake saved state for current ownership of Telegram's webhook.

Deep readiness contacts Telegram and FirstBit with reads and makes a paid synthetic OpenAI parsing check. Inspect individual checks, webhook match and queue. It does not test STT, actual human voice, all clients/services, or create/post/PDF. Do not run repeated live checks to manufacture confidence.

If fallback is used, local computer/network/tunnel must stay available. Restore the server webhook explicitly after recovery. Neither a healthy tunnel nor a healthy app implies FirstBit/OpenAI egress is available. Network retry, speech recovery and financial boundaries are covered in [SECURITY](../SECURITY.md), [COMPANY_SEARCH](COMPANY_SEARCH.md) and [INITIAL_REQUESTS](INITIAL_REQUESTS.md), without retaining individual incident narratives here.
