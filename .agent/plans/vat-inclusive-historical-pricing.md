# ExecPlan: historical VAT-inclusive pricing

## Observed behavior
Resolution rejects a posted historical source when AmountVATIn=true, before producing a confirmable preview. The current line domain, source mapper and write payload assume VAT-exclusive prices.

## Work
1. Verify live source row/header arithmetic and corresponding native Tax Invoice representation with bounded GET; keep raw evidence private.
2. Choose a typed pricing representation that preserves source unit prices, quantity, net/VAT/gross and existing confirmed-operation digests.
3. Implement shared arithmetic and explicit editing semantics, adapter mapping, payload/read-back and Tax Invoice verification. Do not silently normalize away rounding differences.
4. Add synthetic tests for exclusive/inclusive prices, quantity, edits, mixed taxes, rounding, malformed values, compatibility and write/recovery boundaries.
5. Run regression suite and GET-only application prepare/refresh smoke, then deploy. Do not create production invoices for discovery.

## Acceptance
Exact historical financial facts remain verifiable; preview labels pricing clearly; VAT is never added twice. Unknown or inconsistent arithmetic fails closed. Existing operations/digests/recovery remain usable. No production customer fixtures or raw data in Git.

## Evidence and implementation
- Bounded fresh GET confirms inclusive source row Amount=AmountTotal=rounded quantity*price and VAT extracted from that amount. A linked native Tax Invoice keeps the inclusive flag and source-currency *Cur financial fields; existing unit-FX policy is retained.
- Preserve native unit price plus a strict typed pricing flag instead of rounding a derived net unit price. Shared Decimal arithmetic verifies each line. Old false-mode line JSON is byte-compatible; new true-mode snapshots include the flag.
- Explicit user price/amount stay net and require exact representability in the native mode. Uniform mode, discounts, tax identity and FX checks remain fail-closed.
- Real Invoice payload/read-back and linked Tax Invoice validation now compare the actual pricing mode. NLP and company resolution are unchanged.

## Verification
- Existing focused suite: 269 passed. Added synthetic pricing/adapter/native/restart regressions; initial full suite: 756 passed; final full suite after linkage regressions: 769 passed.
- Live GET-only discovery and application prepare/refresh reached an inclusive preview with a complete ExecutionReview, no write blocker and unchanged refresh: 73 GET, zero mutations, zero UI actions. Sample chosen by posted/active/default-contract/unit-FX evidence; no production identity in Git.
- Two earlier confirmed production snapshots load with their original digests. No new production invoice, Tax Invoice or PDF was created during this fix.

## Exact-request follow-up
The supplied original text parsed to the correct company query and explicit date without changing NLP. Its inclusive preview was valid but exposed a separate source-validation bug: row ConnectionKey was restricted to positive values despite the published signed Edm.Int64 type. Live posted rows also prove repeated zero keys are valid; zero is not treated as row identity. Restore the full signed range and preserve the original values and separate rows; malformed/overflow keys still block with a field-specific reason. Repeated nonzero links remain blocked. Synthetic inclusive source/native tests now exercise negative keys; production customer text stays private.

## Final verification
- Exact supplied request: real language parsing preserves company/date; unique live resolution, inclusive preview and complete write review. Final application refresh: 30 GET, unchanged preview, zero mutations and zero browser actions (browser warm-up intentionally replaced by a no-op for GET-only verification).
- Synthetic full native-flow/restart coverage includes repeated zero keys and signed keys, keeping two separate lines and exactly one document pair. Existing two confirmed production operations were replayed read-only after pricing changes: 24 GET, no UI/mutations and unchanged document/PDF/delivery identity.

- Deployed to the existing isolated VPS workspace. Own systemd service restarted in firstbit_write; public health and protected webhook readiness pass, pending updates zero. No new financial objects or Telegram messages were emitted by verification.
