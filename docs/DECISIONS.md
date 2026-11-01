# Engineering decisions

Rationale only. Current mechanics live in the owning guides; completed incident plans are historical, not rules.

## D25 — Native UI actions with OData accounting authority

Use the existing OneC provider/service/journal for the requested full production path. Native Generate and print commands can be automated by a dedicated VPS Playwright browser when no supported external method has been established. This uses standard navigation and observed form controls, not copied web-session RPC/module/version/temp URLs. OData remains authoritative for document existence, relationships, content and Posted state; an observed auto-posted TaxInvoice is not a universal rule.

Separate retries by side effect: bounded read-only navigation or printing can reconnect; financial clicks stay one-shot behind durable claims. Actual rollout/admission belongs to [PRODUCTION_OPERATION](firstbit/PRODUCTION_OPERATION.md), not this rationale.

## D24 — Native print evidence is not an external API contract

Keep the requested linked TaxInvoice flow in the existing OneC/service/journal/Bot architecture. Persist the second document's identity and uncertainty before adding a real native transport; require same-document/form provenance for its PDF. HAR can prove native behavior without proving a supported callable API, universal posting or transaction guarantees. Do not turn captured web-session RPC into the production integration or invent module owners/signatures. Obtain targeted configuration/publication evidence and use a narrow native handler only if needed. Actual provider facts: [INTEGRATION_EVIDENCE](firstbit/FIRSTBIT_INTEGRATION_EVIDENCE.md); admission: [PRODUCTION_OPERATION](firstbit/PRODUCTION_OPERATION.md).

## D1 — Preserve the existing `OneC` Protocol boundary

### Context
`app/domain.py` already defines a narrow adapter interface used by `InvoiceService`.

### Decision
Implement real FirstBit/OData behind `OneC`; do not let OData/HTTP logic leak into bot/service layers.

### Revisit when
Only if a real integration cannot satisfy the contract without a deliberate domain change.

---

## D2 — Current code truth: `BillingBasis` is small

### Context
Production integration discovery suggested a richer basis object, but current code defines only `key`, `client_id`, `revision`, `preview`.

### Decision
Do not document proposed fields as already implemented. Current source/contract/entity provenance lives in typed HistoricalProposal and per-line source fields in the preview; BillingBasis itself was not expanded. Future schema changes must update all usages/tests.

### Revisit when
When a future provider/storage contract actually needs different public fields.

---

## D3 — Keep operation identity independent of revision

### Context
Current code hashes `invoice:v1:` + basis key. Revision changes should trigger new confirmation, not a second business operation.

### Decision
Preserve this semantic.

### Revisit when
Only if business identity definition changes.

---

## D4 — `preview_digest` is a hard document/snapshot guard

### Context
A returned/found document must correspond to the exact human-confirmed preview.

### Decision
Real adapter must only set/validate `preview_digest` after proving document/snapshot correspondence.

### Revisit when
If 1C supplies a stronger native immutable snapshot/version mechanism.

---

## D5 — Unknown outcome is frozen, not retried blindly

### Context
Current `InvoiceService.execute()` already reconciles once after uncertain create/post failure.

### Decision
Real adapter must support authoritative `read_operation`; `unknown` blocks new mutation.

### Revisit when
Never relax by adding blind retries.

---

## D6 — Current app remains single-process until state becomes durable

### Context
Receipts, pending confirmations, recovery and delivery dedupe are in memory. README explicitly documents loss on restart.

### Decision
Do not scale to multiple workers/processes as if current idempotency were durable.

### Revisit when
Persistent operation/receipt/recovery storage exists and concurrency tests pass.

---

## D7 — Mock PDF and production PDF are separate systems

### Context
`app/mock_pdf.py` is a TEST/MOCK renderer.

### Decision
Real adapter returns standard 1C print form. Never reuse local renderer for production invoice PDF.

### Revisit when
Only if accounting/legal requirements explicitly define a different official source.

---

## D8 — Fake pricing rule must not be copied into FirstBit adapter

### Context
Current fake/tests use previous invoice as hint but refresh price from fake service catalog.

Production FirstBit discovery for `Accounting and bookkeeping services` found no authoritative ItemPrices record and showed client-specific recurring historical prices/quantities.

### Decision
Treat this as an integration-specific divergence:
- fake can keep current behavior;
- real adapter may use latest matching historical invoice rows as **proposal**;
- human preview confirmation remains mandatory.

### Revisit when
A verified authoritative current-tariff source is found in FirstBit.

---

## D9 — Historical same-service rows remain distinct

### Context
A production invoice can contain multiple accounting-service rows with different price/quantity/discount.

### Decision
Never collapse them during real resolution.

### Revisit when
Business supplies an explicit aggregation rule.

---

## D10 — ZERO GUID normalizes to missing

### Context
FirstBit OData uses all-zero GUID for empty references.

### Decision
Treat ZERO as an empty reference only according to the consumed field semantics. Empty default contract can trigger fallback; required linked references fail in _record. Do not turn arbitrary missing accounting refs into guessed defaults.

### Revisit when
A specific property is documented otherwise.

---

## D11 — Default contract is only a candidate, not unquestioned truth

### Context
`ContractByDefault_Key` exists, but ownership/active state must be checked.

### Decision
Validate the default record and its owner/active state. Empty default or an inactive valid record permits unique active-owner fallback. Missing/deleted default or wrong owner blocks rather than silently replacing it.

### Revisit when
FirstBit exposes a stronger official resolver.

---

## D12 — `PaymentTermsVersion_Key` from historical invoice is reference-only

### Context
Version is time/document-specific.

### Decision
Do not copy into a new invoice until official selection semantics are implemented.

### Revisit when
Write/post behavior is proven.

---

## D13 — Standard OData first, custom HTTP only if necessary

### Context
Standard OData read path works. Write/post/PDF behavior is not yet proven.

### Decision
Prefer the existing supported Standard OData surface while deterministic. Add a custom 1C HTTP service only for guarantees Standard OData cannot safely provide.

### Revisit when
Controlled draft/post/PDF tests reveal limitations.

---

## D14 — Metadata/runtime evidence outranks guessed naming

### Context
A FirstBit register exposed nested `RecordSet`, while flat searchable rows were in `*_RecordType`.

### Decision
Use actual `$metadata` and response shape for OData model/query construction.

### Revisit when
Never replace with guessed metadata conventions.

---

## D15 — Real mode requires an explicit config change

### Context
`Settings.mode` supports `mock` and explicit `firstbit_readonly`.

### Decision
Select real reads with `APP_MODE=firstbit_readonly` and typed `FirstBitSettings`. Both modes reject the write flag. Default startup remains fake; no automatic fallback from failed FirstBit startup to fake data.

### Revisit when
Any future write-mode admission requires a separate plan and permission.

## D16 — Production 1C is treated as a high-impact trust boundary

### Context
The integration reaches a real accounting database of a large company.

### Decision
Security defaults to least privilege, read-only rollout, explicit write admission, TLS verification, query/data minimization, no raw FirstBit data to LLM, no admin runtime identity, and fail-closed behavior on ambiguity/schema drift/unknown state.

### Revisit when
Individual controls may evolve, but the fail-closed/least-privilege posture is not relaxed without an explicit reviewed risk decision.

## D17 — Historical proposal is typed and non-executable

`InvoicePreview.historical_proposal` carries source/contract/entity provenance. Financial lines retain exact validation. Optional bank/terms/supply date/contact/words fields represent unresolved new-document defaults; they are not invented or reused from historical defaults. Such proposals are rejected by service execution independently of write permission. Fake full previews remain complete. Included VAT/discount arithmetic is blocked until separately verified. See `firstbit/READONLY_PIPELINE.md`.

## D18 — Verification is separate from operation reconciliation

The real reader cannot prove that an operation has not started, so `read_operation` returns unknown. The read-only preview button refreshes only basis/proposal and acknowledges verification without execution or recovery entry. Existing fake/future mutation recovery paths retain their unknown-state protections. Production-derived draft context is not sent to AI.

## D19 — Live compatibility remains an explicit gate

Private configuration metadata supports mapping discovery. Credentials were subsequently supplied and live GET prepare/refresh passed after verifying actual numeric types, Int64 serialization and query encoding/function support. This proves one supported historical preview, not every client's financial variant or production writes. Synthetic tests separately prove client isolation independent of smoke ENV. No create/post/PDF readiness follows from a read-only preview.

## D20 — Duplicate and partial client names require explicit choice

Live owner voice reached resolution and exposed duplicate active Company records with identical names. Do not choose the first record or prefer one by historical price/availability. Return bounded typed candidates, display them only in the authorized chat and accept an expiring per-user token/index callback. Re-read original query candidates and verify the chosen ID remains active/in scope. Keep the selection only in local draft context, never a global alias or LLM context. Missing the requested service history remains a preview blocker after client selection. Current behavior: [company search](firstbit/COMPANY_SEARCH.md), `tests/test_client_choice.py`.

## D21 — Historical issuer conflict needs explicit review, never a silent default

Live GET proved a client whose posted bookkeeping source uses a different legal entity from the current contract, while company/contract/currency and financial arithmetic agree. Targeted metadata proves both Entity references but does not prove that one may override the other for a new document. Resolve both entities and carry current-contract identity/name in typed historical provenance. Bot withholds the historical preview behind an explicit expiring source-review button, refreshing before acceptance. An accepted review is scoped to client+contract+both entity IDs; drift of financial identity blocks, price/revision drift requires renewed review. Display the historical supplier and unresolved new-document supplier clearly; no mutation/PDF is possible even after review/confirmation. Unknown/deleted entity, currency mismatch and inconsistent money still fail closed. No new entity metadata fields were assumed.

## D22 — Explicit user financial values require a verified baseline

Initial net amounts/services and later corrections are typed user proposals, not model-generated accounting defaults. Reuse prepare/resolve_basis and per-line source provenance rather than a second invoice engine. Multi-service sources may differ but must satisfy the verified client/contract/issuer/currency constraints. Detailed policy: [INITIAL_REQUESTS](firstbit/INITIAL_REQUESTS.md), [PREVIEW_REVISIONS](firstbit/PREVIEW_REVISIONS.md). Revisit only through a separately reviewed write contract.

## D23 — Supervised hosting does not imply durable financial state

Deploy a dedicated non-root, single-worker readonly service with independent dependencies and protected ENV/HTTPS/logs. Do not scale workers or claim restart-safe idempotency from systemd restarts. Keep rollback scoped to this project and preserve shared routes/services. Operations: [SERVER_DEPLOYMENT](SERVER_DEPLOYMENT.md). Revisit concurrency only after durable coordination and recovery exist.
