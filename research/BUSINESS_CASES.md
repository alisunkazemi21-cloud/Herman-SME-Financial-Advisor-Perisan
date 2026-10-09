# Persistent business cases

Business cases preserve a financial question and its ordered conversation under one business. Migration 008 adds append-only cases and turns with forced tenant RLS, composite tenant references and immutable author metadata. Quick remains request-only and has no case/history endpoints.

## API contract

All routes require a bearer credential. Successful responses use `Cache-Control: no-store`. Owners, editors and reviewers can create cases and turns; viewers can read them. Both creation routes require an `Idempotency-Key` of 1–200 characters.

| Method | Route under `/businesses/{business}/advisor/cases` | Result |
|---|---|---|
| POST | base | Create a case from `title_fa` (1–200 characters); return its ID |
| GET | base | Case metadata and latest turn, UUID `after` cursor |
| POST | `/{case}/turns` | Append and return an immutable turn receipt |
| GET | `/{case}/turns` | Turn metadata, numeric `after` cursor |
| GET | `/{case}/turns/{identity}` | Full stored request, context and answer receipt |

Pages default to 20 records and allow 1–50. Case order is UUID order, not chronological order. Turn pages are chronological and omit full receipts; clients fetch an individual receipt when needed.

A turn accepts `context` using the existing BusinessContextInput contract, `expected_turn` (0 for an empty case), and `generate_draft` (default true). Set `generate_draft` to false to save deterministic context without an installed model. Select `include_financial: true` inside context to include reviewed financial portfolio values. The server builds context; clients cannot inject retrieved facts or choose a model endpoint.

## History and evidence

Each continuation includes at most three previous questions and replies, oldest first. Previous questions retain their input bound of 2,000 characters; replies are limited to 1,500 characters with an explicit truncation flag. `history_truncated` reports omitted older turns. Historical replies are marked `authoritative: false` under `conversation_history_unverified`. They never become knowledge claims, approved financial inputs or calculation operands.

Structured context is rebuilt from reviewed records for each request. A stored receipt preserves the exact context sent to inference, its canonical JSON SHA-256, and the returned draft. Both context and the final receipt are bounded to 64 KiB; oversized requests fail without a partial turn. The database also enforces a 128 KiB JSON-text ceiling to accommodate its serialization overhead. Context-only receipts have status `context_only` and no draft. Model receipts remain unverified drafts; saving a reply does not approve its financial assertions.

## Ordering, retries and authorization

The expected turn is checked before inference and again during publication. A unique business/case/turn number prevents simultaneous continuations from creating two answers at the same position. A stale continuation returns conflict; the client should fetch the latest turn and explicitly resubmit with a new idempotency key.

Idempotency covers the typed request and case ID. A completed retry returns its original receipt without inference. Concurrent requests can both infer before one publishes, especially across server processes; exactly-once inference is not promised. Failed inference, a revoked credential detected after inference, loss of membership, or a sequence conflict publishes no turn. Publication uses the existing atomic audit/idempotency write transaction. Model calls run outside database transactions. API credentials are rechecked after generation; membership and write role are rechecked at publication. These checks are not a claim that credential revocation and publication are one atomic operation.

## Validation and limits

Nine PostgreSQL acceptance tests cover immutable receipts, bounded history, metadata pagination, retry reuse, role and tenant isolation, stale requests, failed inference, simultaneous continuations, membership loss, API behavior and credential revocation during inference. Stubbed model text tests orchestration only; live Persian model quality is unverified.

There is no case rename, archive, delete, answer approval, automatic knowledge promotion or financial posting operation. Historical financial context records what was retrieved then; it does not update when evidence or reviewed records later change. This checkpoint adds backend persistence only. The visible case/portfolio screens remain deferred.
