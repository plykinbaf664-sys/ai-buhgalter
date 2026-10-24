# Reliable voice -> historical invoice preview

## Goal
One natural spoken invoice request -> grounded intent -> unique/explicitly selected client -> verified contract and posted bookkeeping history -> understandable read-only preview, with concise actionable clarifications only when necessary. No production writes, posting or PDF.

## Current evidence and investigation
Existing Telegram/STT/LLM pipeline and GET-only FirstBit adapter are deployed. Owner reports confusing output for a new named client. Runtime is healthy, webhook has no pending updates/errors. Audit retains stages only, not transcripts/replies; do not claim old message contents were retrieved. Reproduce the owner's named client's resolution and inspect only bounded Company/Contract/history reads. Fresh metadata and typed response checks outrank prior assumptions.

## Approach
Find the concrete failure before selecting changes. Reuse OneC/service/draft/candidate/confirmation/recovery flow. Fix deterministic matching or history mapping only on proven evidence, and simplify user-facing diagnostics/preview without hiding financial unknowns. Any unresolved or ambiguous identity/value/schema stops safely. Keep same-service historical rows distinct. No global client hardcoding or automatic fallback to another client's history.

Targeted GETs now prove: unique company, valid default contract, 18 posted invoices in the bounded window, two containing the configured bookkeeping item. All history uses one legal entity, different from the current contract Entity; currency agrees. Both entities independently resolve through Catalog_Entities. Targeted bundle members confirm Entity/AccountsCurrency/DocumentCurrency references, but do not establish that contract Entity may be silently overridden. Preserve that uncertainty: carry both proven entity identities in historical provenance, require an explicit per-user expiring supplier-review button before displaying a historical proposal under the source issuer, and keep future new-document issuer/defaults unresolved. Currency mismatch/unknown entity/financial inconsistency still block. No automatic promotion of historical issuer to a current accounting default. Refresh before accepting the review, and bind it to client+contract+source entity+contract entity; new input invalidates unaccepted buttons, supplier/scope drift requires a new review. Simplify only the real historical presentation, leaving fake rendering intact. Send only boolean local-draft availability to AI so short follow-ups do not repeatedly request fields already held locally.

## Security
Dedicated readonly ENV/SecretStr credentials; verified TLS; GET only against known reviewed sets/fields. User/LLM text enters escaped literals in fixed bounded query templates only. No raw provider data or candidates sent to OpenAI. Production diagnostics remain ignored under .local, synthetic tests only in Git. No write flag change, no create/post/PDF. Same single-worker receipts and expiry semantics; restart invalidates old buttons. Disable by stopping local demo or selecting mock.

## Verification
Focused regression for observed failure and language/UI/security boundaries -> full suite -> offline application smoke -> targeted production GET prepare/refresh -> real Telegram delivery. Clearly distinguish synthetic/injected input from incoming human voice. Update existing guide, runtime evidence and context index. Stop after usable real preview or a proven external blocker.

## Progress
- [x] Inspect existing architecture, contract, evidence and runtime health.
- [x] Establish actual client/contract/history and reproduced provider failure; old reply contents unavailable.
- [x] Implement smallest evidence-backed correction and clearer interaction.
- [x] Run tests/smokes, deploy, verify real preview in an isolated voice rehearsal and real Telegram delivery after actual owner review.
- [x] Update context/evidence and report remaining financial/write blockers.

## Result
382 tests pass; offline application smoke and regular live GET prepare/refresh pass. Actual STT/LLM + FirstBit on synthetic OGG/Opus produced a real one-line preview after a simulated supplier review, then text date edit and read-only confirmation passed (42 GETs, no mutation). A preceding low-confidence attempt stopped safely; thresholds remain unchanged and recognized text is now shown privately for correction. Public runtime restarted with safe logs archived and delivered an actual supplier-review prompt through real OpenAI/FirstBit/Telegram using signed operator text. An actual incoming owner Telegram callback then accepted the review and completed real preview delivery after refresh, recorded in the safe public audit/private check summary. Initial audio remains synthetic, and new-document supplier/default conflict still blocks any future write admission. No create/post/PDF enabled. Context routing, guide, contract, security and verification updated. Same consumed metadata fields; targeted bundle members and fresh GET verified references, no schema guessing.
