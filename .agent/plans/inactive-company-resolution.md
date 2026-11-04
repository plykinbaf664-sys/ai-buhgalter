# Inactive company resolution

## Observed

The active-only name scan excludes a live FirstBit row because `Catalog_Companies.Inactive=true`, so the bot reports no similar company. A second live parse of the same request also showed that a model span can include a trailing date after `за`, causing the resolver to receive a company-plus-date string. Both facts misstate an accounting status as a spelling problem.

## Change

Keep active-only selection. When no active exact match exists, scan a separate fixed, bounded GET page set for nondeleted inactive companies. An exact local name match reports the inactive status and blocks preview/write. Do not turn inactive records into candidates or add aliases. The general no-match response must identify the active-directory scope.

Ground an explicit company phrase at a following calendar date regardless of `на`/`за`. If the model-selected span includes that known trailing clause, trim it to the proven literal before resolution. Do not guess a name when the explicit phrase is ambiguous or absent.

## Verification

- Synthetic exact inactive name/DescriptionFull and punctuation, even with a similar active name.
- Later-page inactive record, live activation on next request, ambiguous active matches and GET-only query safety.
- Live GET confirms the classification; app smoke and full tests run before deployment. No production mutation during verification.
- Repeated model parses of the exact request must pass only the company name to `resolve_client()` and report its live inactive status.
