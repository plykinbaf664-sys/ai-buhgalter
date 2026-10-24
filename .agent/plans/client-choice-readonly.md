# Explicit client selection for read-only previews

## Goal and evidence
An actual human Telegram voice passed STT and reached FirstBit resolution, which correctly stopped on two active records with identical names. Owner requests buttons to choose a record, and explicitly selected option 1 from the private diagnostic. Neither record has posted invoice history; do not manufacture a preview or financial basis.

## Changes and contract
Extend the existing OneC.resolve_client with an optional internal selected_id. FirstBit returns typed bounded candidates through a UserProblem subclass, and rechecks any chosen ID against fresh active search results. Preserve ordinary string callers and fake behavior. Bot holds a per-user expiring token and original typed command, renders numbered candidates and cancel, then resumes existing service.prepare. Raw names, UUIDs and arbitrary callback text cannot authorize a selection. No provider catalogs/candidates go to the LLM. No BillingBasis change.

## Security and failures
Only the existing dedicated reader ENV/SecretStr credentials, verified TLS and GET transport. Same Catalog_Companies consumed fields and metadata guard; bounded substring search, escaped literals, local candidate matching, saturation/pagination fail closed. No new metadata properties or writes/PDF. Existing unknown-state recovery, preview confirmation and edit invalidation remain. New input/cancel/expiry/restart invalidates choices. Forged index/token, cross-user callback and stale/inactive/deleted/moved records stop safely. No automatic alias or first-candidate selection. Store production diagnostics only in ignored .local; log safe stages without business data. Stop the demo process or select mock mode to disable production reads.

## Verification and rollout
Adapter candidate/selection tests, full application webhook tests for choice/resume/cancel/expiry/edit/forgery/delivery retry and client isolation; full pytest and read-only application smoke. Restart the authorized single-process demo only after checks. Rehearse real candidate presentation and the owner's explicit selection 1; report missing historical basis as a blocker. Never enable writes.

## Progress
- [x] Diagnose actual voice and duplicate active records using bounded production GETs.
- [x] Owner selects diagnostic option 1 and requests buttons.
- [x] Implement typed selection through existing adapter/service/bot.
- [x] Verify regression/security and restart demo.
- [x] Apply explicit selection 1 and report actual basis result; update context docs.

## Result
364 pytest checks passed, plus synthetic application smoke and existing live GET preview prepare/refresh. Real application-level selection rehearsal performed 9 GETs, matched the private diagnostic record chosen as option 1 and correctly blocked on missing posted history. Telegram was simulated inside that rehearsal; its result was separately delivered through actual Telegram. Restarted runtime is healthy and secure webhook registered; a signed operator text rehearsal through the running public app delivered real candidate buttons to the confirmed chat. This is not a human click or a complete human voice preview. Private reports: .local/runtime/client-choice-live-check.json and client-choice-public-check.json. No alias was persisted, no secrets/business diagnostics tracked, no FirstBit mutations/PDF. Missing historical basis for the selected client remains an explicit blocker. Service also independently rejects a provider substituting a different ID after explicit selection.
