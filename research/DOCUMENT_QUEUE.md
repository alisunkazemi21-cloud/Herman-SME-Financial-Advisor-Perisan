# Checkpoint 2: durable document extraction — 2026-10-06

PostgreSQL migration 3 adds tenant-scoped extraction jobs and immutable extraction results. Upload a document using the existing API, then submit `POST /businesses/{business}/document-jobs` with an `Idempotency-Key` and body `{"document_id":"UUID","engine":"tesseract"}`. Read status/result with `GET /businesses/{business}/document-jobs/{id}` or list jobs with UUID pagination (`after`, `limit` up to 100).

Run migrations before starting the API/worker. The worker uses the restricted `HERMAN_DATABASE_DSN` and an expiring user credential, not the administrative DSN:

```text
python -m src.backend.cli worker --business BUSINESS_UUID --credential-file data/operator.secret --blob-root data/backend/blobs
```

`worker-once` handles at most one eligible job and exits. Both commands validate membership. A worker is assigned one business; global multi-tenant scheduling is not implemented. The continuous worker polls every two seconds when idle. Credential revocation is checked before claims and before publishing results.

Jobs move from queued to running, then succeeded/failed; transient failures return to queued with 30/60-second backoff, at most three attempts. Claims use row locks with SKIP LOCKED and a fresh lease token. The default parser deadline is 120 seconds and lease is 180 seconds. A replacement worker can recover expired claims; an obsolete token cannot publish or fail a replacement's work. Exhausted crashed jobs are finalized when a worker next polls that business. No worker running means no active retry/recovery.

Each transition writes an append-only audit event. Claim/failure events include attempt number; failure events retain a fixed error code without parser exception text or document content. Source IDs, requested engine and author cannot be updated by the runtime role. Successful extraction is immutable and unique per job. A new job may create another extraction version of the same document; idempotent retries return the original job.

The parser subprocess receives generated temporary paths and a minimal environment without application credentials. It verifies source bytes through the document service and preserves the source SHA-256, parser contract version, package versions, original document ID, row/page locations and review requirement. Temporary filesystem paths are removed from persisted results. CSV, XLSX, PDF and supported images use the existing adapters. Nothing is automatically inserted into the inventory or financial ledger.

Bounds: upload 10 MiB, extraction JSON 20 MiB, XLSX advertised uncompressed size 100 MiB/5,000 entries, PDF 100 pages, input image 20 megapixels. These are safeguards, **not** an OS security sandbox or strict memory limit. Parser timeout terminates the Python subprocess; full descendant-process containment (e.g. OCR executables), malware scanning and hard memory limits still need deployment-level isolation. Normal temporary files are cleaned on return; process/machine crashes may require protected temporary-directory cleanup. Missing/broken parsers return failure, never fabricated extraction.

Validation at the queue checkpoint: **93 tests passed, one pre-existing real OCR test skipped**. Seven real-PostgreSQL queue tests cover actual Persian CSV subprocess extraction, invalid input, exclusive concurrent claim, obsolete-worker fencing, backoff, lease/attempt exhaustion, role/tenant isolation, environment filtering, tampered evidence and audit history. Ruff and [GitHub CI](https://github.com/alisunkazemi21-cloud/Herman-SME-Financial-Advisor-Perisan/actions/runs/37479582726) passed. OCR/model quality, queue throughput across 1,000 businesses and backup/restore are not established by these tests. Subsequent explicit row mapping is documented in [checkpoint 3](TABULAR_IMPORTS.md).

References used before implementation: [PostgreSQL locking clauses](https://www.postgresql.org/docs/17/sql-select.html#SQL-FOR-UPDATE-SHARE), [Python subprocess timeouts](https://docs.python.org/3/library/subprocess.html). The former supports queue consumers using SKIP LOCKED; the latter documents timeout behavior of the child process.
