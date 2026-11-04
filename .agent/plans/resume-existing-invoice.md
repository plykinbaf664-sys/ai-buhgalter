# ExecPlan: resume an existing confirmed Invoice

## Observed behavior

A repeated request can produce a new preview while an earlier confirmed operation already owns the same billing basis. Confirmation then blocks as a duplicate and only mentions `/retry`; the user is not offered the linked TaxInvoice continuation in context.

## Investigation and implementation

Trace the bot's preview, confirmation, recovery and journal ownership paths; verify how the FirstBit basis key is formed and how live Invoice/TaxInvoice state is reconciled. Add a scoped choice to continue the frozen confirmed operation from a repeated request. Do not treat a new preview as permission to change an Invoice already written in 1C. Keep distinct billing bases independent and ambiguous/unknown state closed.

The observed root cause is the bot's `show_preview`/`confirm` duplicate branch: it hid confirmation for a known operation but offered only a textual `/retry` instruction. The existing service already reconciles the frozen Invoice and linked TaxInvoice on retry. The FirstBit basis key is stable for issuer, client, contract and invoice date or service period; newly selected historical rows change the snapshot revision, not that key.

## Verification

Regression tests: repeated request with a verified existing Invoice offers continuation; accepting uses the original operation and creates no second Invoice; stale/foreign choices fail; a distinct basis follows normal confirmation; restart restores continuation. Run relevant and full suites, then a GET-only production state check. Deploy only after tests and report production side effects separately.

Local targeted synthetic suite: `tests/test_operations.py tests/test_tax_invoice_flow.py` — 47 passed. The full Windows run had two environment-only failures (Playwright absent in that venv; POSIX chmod assertion on Windows), plus one test expecting the old re-confirmation button; that expectation was updated. Linux release suite remains the deployment gate.
