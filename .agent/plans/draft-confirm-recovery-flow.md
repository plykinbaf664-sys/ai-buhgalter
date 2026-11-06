# Draft, confirmation and recovery flow

Observed: edited previews can leave older confirmation callbacks visible; an old confirmed operation can appear to own a new draft; `/retry` can select an unrelated or unrecoverable operation and return to a choice instead of progressing. Recent production delivery succeeded only after a long retry with no clear user state.

Trace the canonical draft and callback token through edit, refreshed confirmation, durable reservation, recovery selection, provider reconciliation and Telegram delivery. Distinguish a new draft from an already confirmed operation; do not weaken duplicate protection for the same operation.

Verify: an edit rotates confirmation and an old button cannot execute; new previews are independent of old journal rows; `/retry` selects or labels only actionable operations and progresses the same identity; deleted/failed old rows do not trap the user; source/tax/PDF/delivery stay at most once. Run focused tests and a read-only production state check before deployment.

Production GET-only verification also found a newly created draft identified by its operation marker whose read-back differs from the confirmed fields. The mismatch is classified separately and excluded from automatic posting/retry; no financial repair is inferred from this single case. Provider response details stay in ignored local evidence. Completion of this particular accounting operation requires a separately proved correction path.
