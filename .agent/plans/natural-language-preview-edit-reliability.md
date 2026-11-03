# Reliable natural-language preview edits

## Observable bug

Existing preview edits sometimes fall into new-invoice parsing, reject mixed item edits, or fail quantity grounding even when the requested values are explicit. “Keep these items and remove the rest” has no typed operation.

## Layers to inspect

- `AIInterpreter._intent`: chooses initial-invoice versus existing-draft schema.
- `LanguageIntent.to_intent` / `ground_intent`: converts model spans and local numeric evidence.
- `Bot.handle` and `apply_draft_mutations`: preserve preview context, resolve targets, recalculate and replace confirmation.
- Telegram regression coverage in `tests/test_preview_overrides.py`.

## Verification criteria

- Existing preview corrections stay on the edit path unless a distinct new invoice is explicit.
- Multi-field and multi-item edits, keep-only selection, English service labels, and quantity plus unchanged price produce one recalculated preview.
- Ambiguous targets fail closed without dropping the existing draft; old confirmation is invalidated only after a successful mutation.
- Focused and full test suites pass; no FirstBit write is used for verification.

## Scope

Reuse the current typed intent, bot, and preview pipeline. Do not change FirstBit accounting/write behavior or persist customer data.

## Result

- Existing draft with explicit line items no longer selects the initial-invoice schema just because the message also says “invoice/price”.
- Clear edit-language model output mislabeled as `initial_lines` is converted to typed line updates/deletions only when a current draft exists and no separate invoice is explicit.
- Added atomic `retain` intent for keep-selected/remove-rest requests; ambiguous retain targets fail closed.
- Local target resolution prefers exact labels, then bounded approximate matching; ties remain clarification.
- Quantity grounding can recover the one explicit quantity next to a unit marker when a model span also captured adjacent money, and still verifies against the model's typed quantity.
- Verification: focused Telegram preview-edit suite and full repository suite; production business writes are not part of verification.
- Follow-up from live dialog reproduction: quantity-unit matching strips punctuation and deduplicates the same literal found through both a unit and a “quantity” label. Regressions cover two item quantities separated by commas and a service-name quantity followed by deletions.
