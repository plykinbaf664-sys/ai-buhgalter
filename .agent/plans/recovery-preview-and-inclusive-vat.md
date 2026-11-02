# ExecPlan: separate safe preview from recovery lock

## Observed behavior

An explicitly selected historical invoice line with `AmountVATIn=true` is rejected in `_resolve_selected_lines_basis`, even though the normal multi-line path supports inclusive VAT. In the same user dialog, an unresolved confirmed operation blocks all later text/voice requests before interpretation, so a harmless new preview cannot be built.

## Layers to inspect

1. FirstBit selected-line re-read, currency and document/line arithmetic validation.
2. `InvoiceLine` inclusive-VAT recalculation and preview invariants.
3. Bot recovery, pending preview, selection callbacks, confirmation guard and `/retry` completion.
4. Regression tests proving preview can proceed while writes remain blocked until reconciliation.

## Verification criteria

- Valid inclusive-VAT selected rows round-trip to the same net/VAT/gross amounts; mismatched currency, malformed arithmetic, or mixed document VAT modes still fail closed.
- An unresolved confirmed operation does not prevent a new preview or safe read-only selection/edit/cancel actions.
- Confirmation remains blocked, the recovery snapshot is unchanged, `/retry` remains the only recovery path, and completing recovery invalidates any newer pending preview.
- Focused tests and full test suite pass; no FirstBit write is performed during verification.
