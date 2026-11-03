# Preview editor reliability

## Goal

An existing preview accepts natural text or voice edits to services, quantity, price and VAT; a successful message returns one recalculated preview with a fresh confirmation.

## Current evidence

The current LLM emits a broad `LanguageIntent` with separate legacy and batch fields. Local grounding and `apply_draft_mutations` can reject or partially apply what the user meant. Add/replace currently reject an explicit price or tax in the same message. Prior mocked tests did not prove how the production model fills the schema.

## Investigation

Trace real model output using synthetic preview context and varied phrasing. Compare the extracted actions with deterministic target, value and financial validation. Check Telegram context/version boundaries and FirstBit historical-line requirements for adding a service.

## Implementation constraints

Keep the current Bot, InvoiceService, OneC and FirstBit flow. No provider data goes to OpenAI. Mutations use source-grounded typed operations; ambiguous targets and financial values fail closed. Do not write to FirstBit during verification.

## Verification

Prove quantity, price, rename, add, delete, replace, retain and multiple actions in one utterance through Telegram-level synthetic tests; check ambiguous and stale-state behavior. Run targeted and full Linux suites, then safe readiness before and after deployment. Verify real LLM interpretation with synthetic inputs separately from mocked application tests.

## Progress

- [x] Diagnose production model behavior and deterministic grounding gaps using synthetic real-model probes.
- [x] Implement a focused preview edit path and complete safe application of its operations.
- [ ] Verify and deploy.
