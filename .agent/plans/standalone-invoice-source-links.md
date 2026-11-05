# ExecPlan: standalone Invoice from a linked historical sample

## Problem

Historical posted Invoice may contain a nonempty `DocumentBasis` or `GoodsOrder`. Current writer blocks because its new-document payload omits these links. The user requests a new standalone Invoice using historical financial rows, then linked TaxInvoice/PDF.

## Evidence and change

Verify fresh FirstBit metadata and GET values, plus native creation/read-back evidence, to establish whether a new standalone Invoice may intentionally have an empty source-document link. Separate historical provenance from the new document's legal/operational basis. If proven, show this omission in the reviewed preview, bind it to the frozen digest and read-back, and retain all other accounting, schema, idempotency and confirmation guards. Unknown link types or business semantics fail closed.

Fresh `$metadata` types `DocumentBasis`, `DocumentBasis_Type` and `GoodsOrder` as nullable strings. The private metadata index describes `DocumentBasis` as a polymorphic document basis; the exact source subtype is unavailable through published OData. Two previously completed native operations exist in the journal; GET of one confirmed its new Invoice had empty basis/order while its TaxInvoice was posted and native PDF cached. The exact target preview's other accounting checks passed in a private GET-only diagnostic. The implementation treats the historical links as source provenance and explicitly reviews omission for a new standalone Invoice, with empty-link read-back.

## Verification

Synthetic linked-source and negative tests; full Linux suite; exact application GET-only preview/confirmability smoke. Controlled production write only after a human confirms the new preview in Telegram. Verify source Invoice, TaxInvoice and PDF by read-back; never create a test Invoice without that confirmation.
