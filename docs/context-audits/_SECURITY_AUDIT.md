# Security Audit — current repository vs required production posture

## Already implemented in code

- Telegram webhook secret with constant-time comparison.
- Numeric Telegram allowlist.
- Private-chat-only checks.
- Forwarded/sender-chat rejection.
- Bounded webhook body and read timeout.
- Strict Pydantic models.
- SecretStr for Telegram/OpenAI secrets.
- `.env*` ignored except `.env.example`.
- `APP_MODE` currently mock-only.
- `ONEC_WRITE_ENABLED=true` rejected in mock.
- Write guard in `InvoiceService`.
- Read-before-write state reconciliation.
- `unknown` blocks mutation.
- No blind retry after uncertain create/post.
- `preview_digest` binds returned document to confirmed snapshot.
- Audit log intentionally avoids free text, raw exception, URL and HTTP body.
- HTTP clients use timeouts, no redirects, `trust_env=False`.
- OpenAI SDK retries disabled.
- Voice input size/type/duration controls and temporary-file deletion.
- Mock PDF is clearly separated from real 1C PDF contract.

## Documented in project contract, but not yet implemented for real FirstBit

- dedicated low-privilege integration account;
- real OData adapter;
- typed FirstBit credentials/settings;
- atomic FirstBit-side uniqueness/idempotency;
- durable recovery across application restart;
- standard 1C PDF retrieval;
- real posting;
- metadata-drift guard.

## Additional protections added to context engineering

- dedicated `docs/SECURITY.md`;
- no admin runtime credentials;
- query minimization (`$select/$filter/$top`);
- raw user/LLM text cannot construct arbitrary OData;
- no bulk FirstBit data sent to LLM;
- HTTPS/certificate verification must never be disabled;
- review/trim OData whitelist before write rollout;
- network ACL/VPN/IP allowlist recommendation;
- log retention/access policy requirement;
- secret rotation requirement;
- incident stop conditions;
- explicit security gate before first write.

## Current highest risks

1. No real FirstBit adapter exists yet, so its HTTP/query/credential behavior is not code-reviewed.
2. Runtime process state is memory-only; restart-safe production idempotency is not solved.
3. OData whitelist exposes 33 objects; it should be re-reviewed for minimum necessary production surface.
4. Real 1C service-account permissions have not been proven from repository code.
5. Write/post/PDF behavior through FirstBit is not yet verified.
6. Network-level restrictions around the FirstBit OData endpoint are not represented in this repo.
7. Audit-log retention/access controls are operational, not implemented in code.

## Security conclusion

The application architecture is already conservative and has several strong safety controls, but it is **not yet safe to enable production writes** merely because read-only OData works.

The correct current posture is:
**production read-only only → build and audit typed adapter → permissions/network review → durable idempotency → controlled draft test → separate posting test → separate PDF test.**
