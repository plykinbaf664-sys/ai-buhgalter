# ExecPlan: natural-language InvoicePreview mutations

## Observed failure

After an invoice preview, ordinary requests to update and remove several lines fell through to the generic request prompt. A generic delete-word safety check also confused line deletion with deleting an external document. The bot could invalidate confirmation before it knew whether a proposed edit was valid.

## Checks

1. Trace parsing, typed intent, draft context, FirstBit history resolution, recalculation and confirmation callbacks.
2. Add typed multi-action draft mutations; resolve line references against the current preview and retain stable row/source identity.
3. Apply validated mutations deterministically, re-resolve changed services, refresh the full preview and totals, and replace confirmation only after successful preparation.
4. Verify text/voice, ambiguity, stale confirmation, repeated edits, GET-only application smoke, and the existing production write/recovery suite.

## Acceptance

The request «Строка 2 исправить на 4 штуки. Строка 3, строка 4 удалить.» updates the intended row and removes the other two in one mutation. Remaining lines and accounting context are preserved; totals recalculate; only the new preview can be confirmed. Rejected or ambiguous edits preserve the current preview and confirmation. Editing itself performs no write.

## Production follow-up: multiple item edits

### Observed failure

A live edit combining deletion of two numbered items with a quantity change to another item received `Уточните количество и одну изменяемую строку.` That exact response is raised by `LanguageIntent.to_intent()` when multiple legacy quantity changes are returned. The prompt also contains older, conflicting instructions to use the legacy shape, despite the newer batch `draft_changes` contract.

### Checks and implementation

1. Make the prompt consistent: edits to an existing preview use `draft_changes`; retain safe compatibility for explicit legacy quantity spans mixed with a valid batch.
2. Ground item numbers locally, including “пункт” references, and apply operations against current stable line identities before renumbering.
3. Label preview positions as “Пункт N”.
4. Preserve separate source rows when service descriptions match; never merge accounting lines implicitly.

### Verification criteria

For “Удали второй пункт и третий пункт, а в пятом пункте поменяй количество на 5”, remove exactly original items 2 and 3, update original item 5, preserve other line identities, recalculate net/VAT/gross totals, and return a fresh preview with current item numbers. The old confirmation is stale; no financial write occurs. Repeated service descriptions remain separate positions.
