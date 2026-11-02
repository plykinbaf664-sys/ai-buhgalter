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
