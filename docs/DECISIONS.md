# Engineering Decisions

## Company voice matching is local; similarity only proposes

Whole-phrase server search missed name variants; actual synthetic speech also exposed a missing model client despite correct STT. Read only fresh bounded name fields (200/page, max 5000), match locally without data to AI or disk, recover only verbatim explicit user company phrases, and require choice for approximate/transliterated matches. Only a unique canonical exact name ignoring case/spacing/punctuation may auto-resolve; incomplete discovery cannot justify it. Re-read choices/selection by stable UUID. Live server case probes were insensitive, so do not claim a proven case-sensitive production server. See [company search](firstbit/COMPANY_SEARCH.md).

## Explicit preview revisions remain user proposals

The owner authorized price/VAT/display-name corrections. Keep them separate from historical facts as typed `preview_overrides`, decoded from current-message spans without model-generated amounts/IDs. Bind to existing source/LineNumber locally, verify original history first, verify actual tax profiles and recompute Decimal totals. Preserve service identity and repeated rows; show manual provenance. All manual proposals remain non-executable even in fake; write admission requires a later contract. See [preview revisions](firstbit/PREVIEW_REVISIONS.md) and [ExecPlan](../.agent/plans/preview-price-tax-description.md).

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
Do not document proposed fields as already implemented. If real adapter needs company/contract/source invoice refs, either:
- encode provider-private data outside public domain safely; or
- deliberately extend `BillingBasis` and update all usages/tests.

### Revisit when
During real adapter implementation.

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
Normalize at provider boundary.

### Revisit when
A specific property is documented otherwise.

---

## D11 — Default contract is only a candidate, not unquestioned truth

### Context
`ContractByDefault_Key` exists, but ownership/active state must be checked.

### Decision
Validate default; otherwise fallback to unique active contract by owner.

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

Live owner voice reached resolution and exposed duplicate active Company records with identical names. Do not choose the first record or prefer one by historical price/availability. Return bounded typed candidates, display them only in the authorized chat and accept an expiring per-user token/index callback. Re-read original query candidates and verify the chosen ID remains active/in scope. Keep the selection only in local draft context, never a global alias or LLM context. No posted bookkeeping history remains a preview blocker after client selection. See `.agent/plans/client-choice-readonly.md` and `tests/test_client_choice.py`.

## D21 — Historical issuer conflict needs explicit review, never a silent default

Live GET proved a client whose posted bookkeeping source uses a different legal entity from the current contract, while company/contract/currency and financial arithmetic agree. Targeted metadata proves both Entity references but does not prove that one may override the other for a new document. Resolve both entities and carry current-contract identity/name in typed historical provenance. Bot withholds the historical preview behind an explicit expiring source-review button, refreshing before acceptance. An accepted review is scoped to client+contract+both entity IDs; drift of financial identity blocks, price/revision drift requires renewed review. Display the historical supplier and unresolved new-document supplier clearly; no mutation/PDF is possible even after review/confirmation. Unknown/deleted entity, currency mismatch and inconsistent money still fail closed. No new entity metadata fields were assumed.
