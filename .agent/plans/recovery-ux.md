# Recovery UX and Tax Invoice delivery

Observed: multiple durable recoveries are offered in hash order, including deleted old documents; repeated preview callbacks show stale errors; a known posted result can still require a manual `/retry`; Telegram labels the Tax Invoice PDF as a generic Invoice.

Change only Bot/Telegram presentation and bounded continuation. Prefer the current confirmed operation, reconcile ambiguous old choices with GET, omit deletion-marked entries from automatic choices, remove consumed inline buttons, and show the current preview without rotating its token. Retry the same frozen operation once when read-back already proves draft/posted state; journal claims continue to prevent duplicate mutations.

Verify synthetic lost-response continuation, repeat callback/delivery, old deleted choice, preview edit token, native PDF filename and server readiness. New financial production writes still require a user's confirmation.
