# Native posting recovery

## Observed incident

The latest confirmed operation has one verified Invoice, still `Posted=false` and unchanged in live OData. The durable journal is `post_started` with a provider post claim, so repeat confirmation and history choice report `unknown`. Private native traces show browser session loss around posting. The user receives no Tax Invoice/PDF.

## Checks

Trace the native FormPost request, browser-session boundary, provider claim, journal reconciliation, and Telegram recovery. Verify the same Invoice by GET before any action; inspect only project-private evidence. Distinguish a pre-dispatch failure from an unknown dispatched mutation.

## Implementation and verification

Move OData preflight before a fresh browser session, gate the actual posting request, and record whether dispatch happened. Permit recovery only for a proved unsent post intent or a verified unchanged draft of the same Invoice under an explicit bounded policy. Keep Invoice creation and Tax Invoice generation at most once. Add synthetic session-loss/restart/retry tests and run the full suite. Stage/deploy only after health checks; reconcile the existing operation and continue it to the native Tax Invoice/PDF through the same journal. Preserve private evidence outside Git.
