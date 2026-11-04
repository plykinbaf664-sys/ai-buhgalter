# Inactive company resolution

## Observed

An exact user name reaches `resolve_client()`. The active-only name scan excludes its live FirstBit row because `Catalog_Companies.Inactive=true`, so the bot reports no similar company. This misstates an accounting status as a spelling problem.

## Change

Keep active-only selection. When no active exact match exists, scan a separate fixed, bounded GET page set for nondeleted inactive companies. An exact local name match reports the inactive status and blocks preview/write. Do not turn inactive records into candidates or add aliases. The general no-match response must identify the active-directory scope.

## Verification

- Synthetic exact inactive name/DescriptionFull and punctuation, even with a similar active name.
- Later-page inactive record, live activation on next request, ambiguous active matches and GET-only query safety.
- Live GET confirms the classification; app smoke and full tests run before deployment. No production mutation during verification.
