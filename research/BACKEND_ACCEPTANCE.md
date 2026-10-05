# Backend milestone 1 — 2026-10-05

## Implemented boundary

The approved architecture now has a working PostgreSQL/FastAPI vertical slice:

1. Authenticate an operator-provisioned, expiring bearer credential (only SHA-256 stored in PostgreSQL).
2. Create a business and owner membership; list only businesses belonging to that user.
3. Create warehouse/items; upload immutable evidence, scoped by business UUID and content hash.
4. Propose inventory counts, movements, fulfilled orders and versioned recipes with document/locator references.
5. A reviewer/owner approves or rejects a proposal; an editor cannot approve, including via direct SQL under RLS.
6. Reconcile a period using persisted records, reviewed completeness assertions and materiality thresholds.
7. Save the exact input snapshot, input hash, metric version, result and actor in one database transaction.
8. Retrieve source records, decisions, audit events and analyses through tenant-scoped endpoints.

Quick inventory uses the same deterministic calculator with only the current request. It authenticates the user but does not retrieve business history, save a conversation or write an analysis. This is the initial Quick calculation tool, **not a finished conversational Quick Advisor**.

No interface changes were made for this milestone.

## Runtime and setup

Install `python -m pip install -e '.[dev,ocr,backend]'`. Use PostgreSQL 17 or newer. The local checkpoint uses official EDB PostgreSQL 17.11 Windows binaries, downloaded from the binary distribution linked by [PostgreSQL](https://www.postgresql.org/download/windows/), with a project-local cluster on `127.0.0.1:55432`. No Windows service was installed. `.runtime/`, `.env`, `*.secret` and `data/` are ignored by Git.

Set `HERMAN_ADMIN_DSN` in the process environment to a dedicated database's administrative connection string. For this initial migration the administrator is a superuser: narrowly scoped SECURITY DEFINER functions are owned by the migration administrator and use a fixed search path. Run:

```text
python -m src.backend.cli migrate
```

Create a separate PostgreSQL LOGIN role, with a strong password, that is a member of `herman_app`. Give it no other memberships, ownership or elevated privileges. The application rejects an administrative/owner DSN. Set `HERMAN_DATABASE_DSN` to this runtime login. Never use the migration connection string to serve requests.

Provision a local user with:

```text
python -m src.backend.cli provision-user --name "مدیر" --credential-file data/operator.secret
python -m src.backend.cli serve --port 8000 --blob-root data/backend/blobs
```

Create the `data` directory first. Restrict the credential file to the operator; credentials expire after 30 days and can be revoked administratively in `herman.api_credentials`. The server binds to loopback and disables access logs by default. It is not a public production deployment, signup service, or full identity provider.

The runtime DB credential and application process are trusted. RLS protects tenant queries under the actor selected by server authentication; it does not protect against an attacker who controls that trusted runtime credential and can issue arbitrary SQL/set session variables. Clients must never receive database credentials.

## API contract

Requests use `Authorization: Bearer <credential>`. Writes require `Idempotency-Key` (1–200 characters). Reusing a key with changed content returns a conflict; successful retries return the existing identity. Business creation keys are scoped to the actor; other write keys are scoped to the business. Quick calculation has no side effects and does not need a key.

| Route | Purpose |
|---|---|
| `GET/POST /businesses` | List memberships/create business |
| `POST /businesses/{business}/documents` | Raw file bytes, `X-Filename` metadata, max 10 MiB |
| `GET /businesses/{business}/documents/{id}` | Authorized download; hash rechecked; attachment/no-store |
| `POST /businesses/{business}/warehouses`, `/items`, `/conversions` | Warehouse/catalog/explicit pack conversion; conversions require reviewer |
| `POST /businesses/{business}/counts`, `/movements`, `/recipes`, `/fulfillments` | Typed proposals, `status=proposed` only |
| `POST /businesses/{business}/records/{id}/decision` | Reviewer decision with reason |
| `GET /businesses/{business}/records/{id}` | Source, typed details and separate decision |
| `GET /businesses/{business}/resources/{resource}` | UUID-keyset pages, `after`, `limit` 1–100 |
| `POST /businesses/{business}/inventory-analyses` | Persisted reconciliation using explicit count IDs |
| `GET /businesses/{business}/inventory-analyses/{id}` | Reproducible input and result |
| `POST /quick/inventory` | Request-only calculation without history |

Resource listing accepts `items`, `warehouses`, `documents`, `records`, `audit_events`, `analysis_runs`; pages sort by UUID, not chronology. Analysis listing returns metadata; retrieve one analysis for its full snapshot. API schema is generated at `/openapi.json`. Numeric quantities should be JSON strings, never floating-point JSON numbers. Timestamps require UTC offset. Business IDs in payloads must match the route. Client filenames never determine storage paths.

Inventory counts are boundary measurements: opening at `start`, closing at `end`; movements/fulfillments are in `[start,end)`. Unreviewed in-period records make analysis incomplete; rejected records are excluded. Coverage assertions and thresholds need local evidence and a reviewer. Evidence bytes are verified before saving analysis. Files are atomically published before metadata commits; a failed transaction can leave an unreferenced blob, never a referenced partial file. Blob garbage collection is not yet implemented.

## Acceptance evidence

- 22 deterministic inventory tests: restaurant's 7 kg unexplained shortage, direct retail, pack units, recipe batches/yield/nesting/version boundaries, invalid inputs, zero denominator, strict materiality boundary and incomplete evidence.
- Real PostgreSQL tests: separate runtime role; no-context RLS; malicious cross-business foreign keys; viewer/editor restrictions; authorship checks; append-only updates; revoked credentials; rollback; 8 concurrent identical writes; idempotent business creation; persisted analysis and Quick isolation.
- Full suite at this checkpoint: **86 passed, 1 skipped**. The skipped test is the pre-existing real OCR fixture/engine checkpoint. Ruff passed. Later additions are recorded below when run.
- CI now runs the backend tests against a PostgreSQL 17 service, not SQLite.
- Synthetic capacity output is recorded separately under `research/benchmarks/`; its scope excludes OCR, agents, document ingestion and full reconciliation latency.

### Capacity checkpoint

On the local Windows 11 / PostgreSQL 17.11 instance (4 logical CPUs, 128 MiB shared buffers), the fixture contained 1,000 businesses and 1,000,000 inventory movements: 10 businesses with 50,000 each, one with 5,500, and 989 with 500 each. Each request opened a new authenticated-context database connection, aggregated one tenant's movements and checked visible tenant IDs without a tenant predicate. There were 25 concurrent workers, 1,000 successful requests and zero incorrect aggregates or unauthorized accesses; a further 25 mismatched actor/business attempts were rejected.

| Measurement | Schema 1 baseline | Schema 2, reused fixture |
|---|---:|---:|
| p50 | 776.34 ms | 549.98 ms |
| p95 | 3,267.39 ms | 1,946.38 ms |
| p99 | 4,378.39 ms | 2,786.36 ms |
| Maximum | 6,486.08 ms | 3,558.09 ms |
| Total read phase | 47.17 s | 31.46 s |

The baseline EXPLAIN exposed a per-row membership lookup. Migration 2 preserves the row-level business equality check and evaluates membership through a statement-level subquery. The fixtures/cache states differ between runs, so the latency difference cannot be attributed entirely to that change. Both raw reports and plans are committed:

- [Baseline](benchmarks/backend-2026-10-05.json)
- [After migration 2](benchmarks/backend-2026-10-05-optimized.json)

This establishes that the tested schema can hold and correctly scope the stated synthetic dataset. It does **not** establish a production SLA or capacity for 1,000 simultaneously active businesses. Connection pooling, mixed read/write workloads and full period-analysis performance remain unmeasured. To reproduce, migrate a fresh disposable database, set `HERMAN_ADMIN_DSN` and `HERMAN_DATABASE_DSN`, then run `python -m scripts.benchmark_backend --output research/benchmarks/local.json`. The script refuses initial seeding into a nonempty database. `--reuse-fixture` validates the existing fixture profile before measuring again.

After the paginated reading, source-byte validation and migration changes, all 28 backend/domain tests passed again. The FastAPI test transport emitted a deprecation warning about its current httpx adapter; it did not fail. No OCR validation claim was added.

## Remaining work and explicit limits

This is the first backend milestone, not completion of the approved whole application:

- Durable ingestion queue, extraction versions/retry/recovery, mapping extracted candidates to typed business proposals.
- General financial journal migration into tenant-scoped PostgreSQL and further financial KPI tools.
- Full agent orchestration, verified business knowledge/retrieval, conversation memory and conversational Quick Advisor.
- Correction/supersession of previously approved records and unit/catalog definitions; records currently remain immutable. Recipe overlap is detected by the calculator and produces incomplete results; preventing concurrent overlapping approvals at database level is still outstanding. Plan bounded recipe intervals when recording future versions.
- Production/intermediate-goods stock ledger: this calculator supports base ingredients/direct resale; it rejects intermediate recipe products as reconciliation targets. Do not mix production and service consumption.
- Branches, item lots, valuation/costing, reservation/returns workflows, rate limits, upload scanning and pooled connections.
- Membership administration UI/API, refresh/session management, credential rotation workflow and deployment hardening.
- Backup/restore rehearsal for both database and evidence blobs, storage retention, outbox and late-document invalidation jobs.
- Full 1,000-business **application** load test with ingestion, concurrent changes, reconciliation, OCR and realistic document sizes. A database read benchmark alone cannot certify this.

The existing local Ollama and OCR adapters remain separate; their real-engine accuracy has not been established. No claim of Iranian accounting-standard compliance is added here.
