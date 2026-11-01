# Production operation: preparation and admission

## Actual status

A controlled production operation completed through the real Telegram request/confirmation and recovery path: one Invoice, one linked TaxInvoice, verified posted states, native landscape PDF and acknowledged Telegram delivery. This was a recovered operation, not an uninterrupted first attempt. Dated verification and limits are owned by [VERIFICATION](../VERIFICATION.md) and the [ExecPlan](../../.agent/plans/production-headless-e2e.md).

Firstbit_readonly remains GET-only. Firstbit_write defaults to controlled-draft FirstBitWrite; explicit FIRSTBIT_NATIVE_UI_ENABLED=true selects FirstBitProduction and the full native flow. The same OneC/service/journal/Bot layers are reused.


Write admission still requires an explicitly confirmed reviewed snapshot, dedicated writer attestation, preprovisioned durable journal and approved full schema pin. Preview/discovery never invokes native financial actions.

## Controlled-create admission

This candidate offers historical accounting **as an explicit proposal**, not current defaults. The adapter reads the posted source and live bank/payment/GL references, shows carryover in `ExecutionReview`, and binds exact payload/evidence/schema hashes into the preview digest. Sources must agree on customer, contract, issuer and accounting headers. The currently modeled scope is SaleToCustomer/TaxableByVAT, one common document/accounting/national currency with unit exchange rates, no delivery/custom terms/sets/discount sections and one 100% zero-day PaymentOnDelivery stage. The proposed payment date is explicitly the invoice date; PriceDate retains the source timestamp. Missing/deleted/closed/wrong-owner bank, unsupported schedules/FX or changed tax identity leaves a readonly preview with an explicit blocker. A historical/current-contract issuer mismatch requires explicit supplier review and a final preview showing the historical issuer; both references remain in reviewed evidence. Nonempty unmodeled row dimensions/linkage/deferral/retention fields also block admission and read-back; they must not disappear through extra="ignore". The reviewed metadata detail types `OffsetAdvancesDebtsAutomatically` as `Yes / no` (`Enum.YesNo` in the full index); OData exposes `Edm.String` without enum members. Posted-source GET evidence confirms the wire literals `Yes` and `No`. Only those exact literals are admitted, shown as automatic-offset enabled/disabled in preview, carried into the frozen payload and compared on read-back. Missing or unknown values fail closed with a field-specific blocker; no user value or default is substituted. Repeated service lines remain separate. Price/content changes get a fresh review; manual edits never inherit old confirmation.

Source VAT pricing mode is preserved in the reviewed Invoice header and row payload and verified on read-back, following [READONLY_PIPELINE](READONLY_PIPELINE.md). Different historical modes cannot be silently mixed into one document; financial edits must round-trip exactly. The existing same-currency/unit-FX, discount and accounting-reference guards are unchanged. Inventory.ConnectionKey is a signed Edm.Int64 row-linkage value; zero and negative keys are preserved losslessly within the full signed range, without absolute-value or floating-point conversion. Posted sources confirm repeated zero keys: these are unset links, not row identities; separate source rows remain separate. Duplicate nonzero links still block.

Only an admitted, explicitly confirmed snapshot can reserve/claim creation. The adapter rereads source/reference/schema evidence, then commits a separate provider-request claim before its single POST to Document_InventoryExpense. Payload uses a fixed allowlist; no arbitrary properties, URLs, query text, data-load bypass or Posted=true. Typed values and exact decimal roundtrips form the body. Read-back verifies marker, client/contract/issuer/date, all selected accounting fields, schedule, separate lines and amounts. Unknown results reconcile; absence after a persisted intent never permits another POST.

Reconciliation scopes GET by typed client/contract/issuer UUIDs and invoice day, pages minimal document headers in fixed Ref_Key order (200/page, cap 1000), compares the operation marker locally, then fetches the matching document by UUID. Duplicate markers/IDs, incomplete pages, foreign scope, limit or read-back mismatch fail closed. It never filters by arbitrary user/LLM text or executes nextLink. The schema/current business records are live; metadata snapshots are not runtime catalogs.

`InvoiceResult.pdf=None` explicitly represents a verified draft stopped before posting, or verified posted state without native PDF. The bot reports the actual state and document number/ID; it sends no mock PDF. An unresolved draft stays in recovery and `/retry` rereads that same operation. It does not unlock another invoice for that user's unfinished operation. Posting remains disabled in the base controlled-draft provider. The native production subclass admits the full linked-document flow only with all native capabilities and the durable journal.

### Configuration and provisioning

`APP_MODE=firstbit_write`, `ONEC_WRITE_ENABLED=true`, `FIRSTBIT_INTEGRATION_ACCOUNT=true`, `FIRSTBIT_READONLY_ACCOUNT=false`, absolute `INVOICE_OPERATION_DB`, and `FIRSTBIT_WRITE_SCHEMA_SHA256` are required alongside existing secrets. These attest a dedicated least-privilege integration identity, never admin. Readonly and mock modes still reject the write flag. With reviewed ENV explicitly loaded, provision a missing new store once using `python scripts/init_operation_journal.py`; existing stores are refused, never reset. Server private writable path is `/srv/ai-buhgalteria/operations/` (owner service user, directory 0700/file 0600), exposed only to this service by systemd ReadWritePaths. Secrets remain in the protected EnvironmentFile; no webhook or other-project changes are needed.

Full native operation also requires FIRSTBIT_NATIVE_UI_ENABLED=true, pinned Playwright/Chromium and PDF-validation dependencies, and project-private browser storage. Security and hosting are owned by [SECURITY](../SECURITY.md) / [SERVER_DEPLOYMENT](../SERVER_DEPLOYMENT.md). Use full_execution_schema from app/firstbit_production.py for the approved pin, not the narrower controlled-create pin. Never auto-approve a new fingerprint at startup.


## Frozen confirmed-operation journal

`INVOICE_OPERATION_DB` is optional in existing mock/readonly modes and mandatory in controlled-create mode. Namespace binds the store to app mode/provider scope. Unknown versions, corrupt snapshots, conflicting identities or PDF hashes fail closed. Linux requires parent 0700/file 0600. Snapshots/PDF bytes are private accounting data, never Git/AI/log content. Journal schema v3 adds linked TaxInvoice identities/intents/PDF provenance after v2 provider-send claims, using append-only migration from v1/v2; it does not reset operation intents or silently rewrite changed domain snapshot digests.

Initialization is explicit (`OperationJournal(..., create=True)`); normal open defaults to create=False. Existing empty/unknown databases are not reset. The mock factory may initialize a test store; non-mock requires prior provisioning. Never replace a missing production store to get a passing run. Backup/restore requires external reconciliation; idempotency records must not be pruned casually.

Execution freezes the exact confirmed PreparedInvoice. SQLite FULL synchronous transactions commit an atomic mutation intent **before** external create/post. Another process cannot claim that same mutation. Conflicting snapshots cannot inherit confirmation; operation_id remains independent of revision.

Phases: reserved -> create_started -> verified draft -> post_started -> verified posted -> cached PDF. Only provider read-back is accounting authority. An absent remote result after a persisted intent never resets it: the request may still be in flight. A draft observation cannot clear uncertain posting. A lost committed response can reconcile to the same document; an uncertain noncommitted attempt stays blocked for stronger evidence/operator resolution.

PDF bytes/hash bind to the verified invoice. Per-user delivery phases ready/sending/delivered are durable; sending is committed before sendDocument, delivered only after acknowledgement. Lost acknowledgement stays unknown after restart and prevents automatic resend; delivery may require manual reconciliation. `finalized` separately denotes verified posted operation completion without PDF, never a PDF-delivered claim.

Bot restores already-confirmed recoveries. Unconfirmed drafts/tokens and webhook receipts remain process-local; old tokens do not become write permission. FakeOneC documents themselves remain ephemeral. Cross-process claims are tested, but deployment stays single-worker until other conversation/receipt concurrency concerns are addressed.

## Write-schema safety

Fresh GET metadata proves the InventoryExpense entity and a bound side-effecting Post action with posting-mode parameter. A semantic fingerprint covers critical header/line attributes, Inventory collection and Post signature. Missing/wrong schema or changed approved pin blocks. Extra unused fields are not automatically critical. Observed FactorAccCur is Int64, not an assumed financial Double.

`FirstBit.verify_write_schema(expected_sha256)` remains a prospective core check and does not unlock the reader. `FirstBitWrite.execution_schema` additionally pins every consumed reference property and payment-stage/header field, including entity-set bindings. The controlled writer refetches this full contract while building/rechecking admission before mutation. Missing/changed pin blocks. Schema matching is not proof of native filling or financial success. The native fingerprint additionally covers consumed TaxInvoice dates, headers, basis/row schemas, entity binding and supplier VAT-registration interfaces. A 12-hour background check writes private health and emits a safe operator event on failure; every financial action independently checks fresh schema.

GET-only discovery, with private ENV explicitly loaded:

```text
python scripts/firstbit_write_preflight.py --save-private
python scripts/firstbit_write_preflight.py --expected-schema-sha256 <reviewed-private-pin>
python scripts/firstbit_write_preflight.py --execution-schema --save-private
```

DISCOVERY_ONLY/SCHEMA_PIN_MATCH both report write_admitted=false. Private evidence stays under `.local/firstbit/production-operation/`. Never auto-approve a newly observed hash immediately before mutation. [Platform OData reference](https://1cfresh.com/articles/data_odata) is supporting documentation, not proof of FirstBit-specific defaults/printing.

## Native production interfaces and admission

Invoice creation uses one allowlisted Standard OData POST and exact typed read-back. Posting uses the native document UI command, not an unproved conditional OData Post request. Before a financial click the adapter verifies the active native document link, refreshes the approved schema and expected OData record/version, then commits a one-shot provider-request claim. Financial UI clicks have no retry loop. Read-only login/navigation may reconnect; printing may retry because it cannot create/post accounting documents.

App/firstbit_tax.py reads Document_TaxInvoice. It pages only minimal global relation keys, checks DocumentBasis and its actual polymorphic type, refuses duplicate/deleted/ambiguous links, then verifies separate rows, parties/TRNs, currency, net/VAT/gross, dates and UOM against the confirmed source. Absence after generation intent remains unknown. Actual Posted is authoritative; generation is not assumed to post universally.

App/firstbit_ui.py uses the dedicated Generate Tax Invoice action and Print -> Tax Invoice (EN, landscape) -> Save Printable Document -> local PDF download. Only PDF is selected; archive, document attachment and Chrome/HTML/Python replacement are excluded. Standard navigation links derive from runtime object references, never captured session/module/temp identifiers. Provider facts: [INTEGRATION_EVIDENCE](FIRSTBIT_INTEGRATION_EVIDENCE.md).

Generation finishes all OData guards before opening a fresh native session. Read-only CheckBasisBeforeFilling may reconnect after a proved platform session rejection. The browser intercepts the actual GenerateTaxInvoice request and commits the unique provider-send claim immediately before allowing that request out; duplicate requests are aborted. The context is closed with its gate still installed before recovery/read-back. A generation intent without any send claim may resume only for this dispatch-gated provider, without resetting journal state. Any existing send claim keeps an absent result unknown. Printing also performs live validation before opening its native session. Each launch uses a new project-private temporary browser profile, cleaned after the context closes; saved session identifiers are never reused across stages. Native session loss is a provider condition, not evidence that an accounting mutation failed.

Native PDF checks cover signature/size, landscape layout and exact TaxInvoice number. Fresh schema/version/posted-state checks run again before caching. A private manifest binds operation/source/tax/version/path/hash; the durable journal caches PDF and governs Telegram acknowledgement uncertainty.

Production E2E requires one specifically confirmed target completing every stage and real Telegram delivery. Unknown state reconciles rather than retries or deletes. No automatic accounting cleanup is implemented.

## Minimal native-print discovery

The existing MetadataBridge source enumerates business metadata kinds and has a separate OData publication command; it does not export HTTPServices/CommonModules. The standalone [readonly discovery package](../../tools/onec-print-discovery/README.md) reuses its managed-form/XML approach without copying publication or business access. It exports declared HTTP routes/methods/handlers when available, a names-only CommonModule/CommonCommand index, and both InventoryExpense/TaxInvoice command/template names. Missing/unsupported metadata is an explicit gap, not evidence of absence.

`scripts/firstbit_print_discovery.py` validates bounded private exports and suggests source-inspection candidates. It never invokes a route, and cannot establish API publication, handler safety, direct PDF support or the absence of an existing mechanism. Runtime metadata cannot supply module bodies. If an additional native handler becomes necessary, targeted evidence can be a Designer/EDT export of the document's print entry points, candidate HTTP handler and directly called common-module routines, plus sanitized publication status. Package instructions own exact operational steps and export scope.

Native UI generation and PDF are now proved by HAR; facts are owned by [INTEGRATION_EVIDENCE](FIRSTBIT_INTEGRATION_EVIDENCE.md#native-tax-invoice-generation-and-pdf-captured-flow). Supported external invocation and the need for a new HTTP endpoint remain **unknown**. An existing native print command can be callable internally without a supported external API. Do not decide a new endpoint is necessary merely because OData declares no printing. The native UI adapter avoids depending on a separate published handler; the discovery package is an optional research tool, not a production prerequisite.

## Linked-operation implementation boundary

The existing service/domain/journal now support an optional `TaxInvoiceOneC` capability: source create/read-back/final state -> reconcile/generate one linked TaxInvoice -> read its actual state -> post only if needed -> fetch the fixed native TaxInvoice PDF -> check both documents again -> cache/deliver using the existing Bot. The native production subclass implements this capability with the interfaces above. Readonly and base controlled-draft providers do not advertise it. Implementation and production financial proof are separate.

Generation/posting intent and provider-send claims are committed before their respective calls. A returned TaxInvoice reference is persisted as an unverified hint before authoritative read-back. Source relationship, client, confirmed digest and document identity must agree; changed identities or ambiguous/unknown states stop. A lost committed result can reconcile the same document; absence after intent cannot unlock generation again. The journal uniquely binds source and tax identities. A native-PDF result binds source ID, tax ID, tax revision, print manager and fixed template. A changed document version invalidates cached provenance. Source-invoice PDF cannot stand in for the TaxInvoice form. Synthetic contract/provider tests prove orchestration and durable recovery only; actual native adapter validation must additionally verify financial content and relevant schema.

The TaxInvoice path requires a durable journal and complete generation/read-back/post/PDF capabilities before source creation. Native API admission must preserve fresh reviewed schema checks, expected-revision finalization and authoritative relation/content reconciliation. The current real accounting proposal still blocks unsupported dimensions. Captured historical references are not authorization to regenerate TaxInvoice or perform a new financial test.

## Verification boundary

`tests/test_operations.py`: persistent identity, multi-process claims, lost committed responses, absent/unknown outcomes, journal/new-app recovery, PDF delivery uncertainty, corruption/namespace/private permissions and unconfirmed tokens. `tests/test_firstbit_write_schema.py`: independent synthetic schema drift/pin/freshness and continued readonly guard. `tests/test_onec_contract.py`: mandatory journal for a writable non-fake test adapter and provider PDF pass-through without mock rendering.

`tests/test_firstbit_write.py`: independent synthetic write schema/server, admitted create/read-back/restart/redelivery, lost committed/uncommitted response, accounting/schema/evidence drift, source-row preservation, price revision, application button/accurate draft status, bounded multi-page correlation and duplicate-marker blocking. No production records are fixtures.

All are synthetic proofs, not production mutations. Dated outcomes: [ExecPlan](../../.agent/plans/production-invoice-operation.md). Broader milestones/admission: [PROJECT_CONTEXT](../PROJECT_CONTEXT.md), [SECURITY](../SECURITY.md), [onec-contract](../onec-contract.md).

Linked TaxInvoice milestone verification and current blockers: [ExecPlan](../../.agent/plans/production-tax-invoice-pdf.md), `tests/test_tax_invoice_flow.py`.


## Supplier VAT registration and compatible read-back

Native preparation fills the supplier TRN from the effective live registration and binds its catalog/version/period evidence into the existing ExecutionReview. No new domain snapshot fields were added. An absent supplier number in an old historical preview means unresolved, not an authoritative empty TRN. TaxInvoice read-back independently checks its TRN against the registration owned by the approved supplier as of issuing time; buyer TRN and all other financial/identity checks remain strict. Exact provider facts and fields belong to [INTEGRATION_EVIDENCE](FIRSTBIT_INTEGRATION_EVIDENCE.md).

An expanded approved schema can reconcile already-created documents from a compatible older frozen snapshot only when the fresh older consumed contract still matches and its payload hash is intact. The snapshot/digest is never rewritten. Legacy reviews cannot authorize create/post/generate; current review/schema approval is mandatory for those methods. This allows read-back/cached PDF recovery without weakening the new write guard.
