# Independent confirmed operations

## Observed failure

The current operation ID is derived from a FirstBit billing key scoped to issuer, client, contract and date/period. A later request with the same business coordinates reuses that ID. Bot history selection and the journal then bind the new preview to an older confirmed operation, including one whose created Invoice was later marked for deletion.

## Check and change

- Trace `resolve_basis` → `PreparedInvoice.operation_id` → bot history prompt → journal reservation → FirstBit marker/read-back → linked TaxInvoice.
- Give each new FirstBit preview an independent operation nonce. Preserve it through preview refresh; use its ID only after confirmation. Keep legacy confirmed snapshots readable and recoverable.
- Allow multiple reservations for one business key while retaining unique operation/source/tax references. Keep `/retry` scoped to the chosen frozen operation; new requests do not inherit its outcome.
- Do not change historical source selection, accounting review, preview editing or financial write guards.

## Verification

- Same client/date and sample can form independent confirmations with distinct markers and journal rows; edits/refresh preserve the current nonce.
- Old v1 rows remain readable. A deleted Invoice affects only its own operation; another operation can reach create.
- Repeat confirm and lost response of one operation cannot create a second Invoice or TaxInvoice.
- Targeted tests, server read-only smoke and deployment readiness; live financial creation only after a user's current preview confirmation.
