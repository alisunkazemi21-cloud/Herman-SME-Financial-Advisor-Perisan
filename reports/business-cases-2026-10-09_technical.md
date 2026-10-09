# Business cases technical report

Migration 008 introduces advisor cases and numbered turns with forced tenant RLS, composite references, immutable-record triggers and author checks. The HTTP API exposes creation, cursor-paginated metadata and individual receipt retrieval. Request authentication, write-role enforcement, audit publication and idempotency reuse the existing backend boundaries.

Turn generation includes fresh reviewed context plus three prior turns. Replies are capped at 1,500 characters; whole context/receipt payloads are capped at 64 KiB. Sequence is checked before and after inference. API credentials are checked again after inference and membership is checked at publication. A failure leaves no partial turn. Concurrent inference is possible; a unique constraint prevents duplicate sequence publication.

Nine focused PostgreSQL tests passed. See [validation](../research/VALIDATION.md) for the full-suite result and [API contract](../research/BUSINESS_CASES.md) for limits. Tests use model stubs; live model quality and full application capacity remain unverified. No UI expansion, cloud adapter or automatic posting was introduced.
