# Repository audit snapshot

Repository reviewed:
`plykinbaf664-sys/ai-buhgalter`, default branch `main`.

Observed root:
- `.env.example`
- `AGENTS.md`
- `README.md`
- `app/`
- `docs/onec-contract.md`
- `pyproject.toml`
- `requirements*.txt`
- `scripts/`
- `tests/`

Important findings applied to context docs:
- version 0.2.0, Python >=3.10;
- real OneC adapter not present;
- `APP_MODE` currently mock-only;
- current `BillingBasis` is only key/client_id/revision/preview;
- process-local receipt/pending/recovery state;
- exact repo test/demo/smoke commands;
- module ownership;
- current service refresh/execute/reconcile semantics;
- existing OneC contract;
- fake pricing assumption differs from discovered FirstBit production behavior.

No GitHub repository files were modified by this audit.
