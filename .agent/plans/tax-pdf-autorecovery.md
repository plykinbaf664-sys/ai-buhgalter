# Tax Invoice PDF completion after confirmation

Observed: one confirmed production operation has a posted source Invoice and linked posted Tax Invoice, but no PDF/delivery. The webhook sent a progress message, then held the request through a native print failure and a second lengthy retry. Native UI evidence shows dropped sessions and rejected login attempts; the journal remains recoverable.

Trace: production journal and namespaced service log -> live OData read-back -> native UI print/login -> service timeout/retry -> Telegram delivery/receipt.

Implement the smallest reliable continuation that gives bounded attempts, automatic recovery of read-only/print stages, truthful user feedback, and durable operation identity. Never repeat create/GenerateTaxInvoice without reconciliation. Verify focused code tests, then continue the existing operation in production through native PDF and acknowledged Telegram delivery; record any externally proven blocker precisely.
