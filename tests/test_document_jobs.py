"""Queue lifecycle tests on real PostgreSQL; parser subprocess runs actual synthetic CSV input."""
# ruff: noqa: E402
import subprocess
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest

psycopg = pytest.importorskip("psycopg")
pytest.importorskip("fastapi")
from fastapi.testclient import TestClient
from test_backend import backend as backend_fixture
from test_backend import database as database_fixture

from src.backend import worker as worker_module
from src.backend.api import create_app
from src.backend.database import AccessDenied
from src.backend.jobs import ExtractionInput, ExtractionQueue
from src.backend.service import Conflict, NotFound
from src.backend.worker import process_one
from src.ingestion.ocr_persian import document

database = database_fixture
backend = backend_fixture


def enqueue(b, key="job", content="شرح,مبلغ\nخرید,۱۲۳\n", name="source.csv"):
    source = b["service"].document(b["owner"], b["business"], "doc:" + key, name, "text/csv", content.encode())
    queue = ExtractionQueue(b["service"])
    identity = queue.enqueue(b["owner"], b["business"], key, ExtractionInput(document_id=source))
    return queue, identity, source


def expire(b, identity):
    with psycopg.connect(b["admin"]) as c:
        c.execute("UPDATE herman.extraction_jobs SET leased_until=now()-interval '1 second' "
                  "WHERE business_id=%s AND id=%s", (b["business"], identity))


def test_real_csv_subprocess_and_read_only_candidates(backend, monkeypatch):
    b = backend
    original_run = subprocess.run
    monkeypatch.setenv("HERMAN_PRIVATE_TEST", "never-forward")

    def checked_run(*args, **kwargs):
        assert not any(key.upper().startswith("HERMAN") for key in kwargs["env"])
        assert kwargs["timeout"] == 120
        assert kwargs["stdin"] == subprocess.DEVNULL
        return original_run(*args, **kwargs)

    monkeypatch.setattr(worker_module.subprocess, "run", checked_run)
    queue, identity, source = enqueue(b)
    assert process_one(queue, b["tokens"][0], b["business"]) == identity
    job = queue.read(b["owner"], b["business"], identity)
    assert job["status"] == "succeeded", job
    result = job["extraction"]["payload"]
    assert result["requires_review"] is True
    assert result["document_id"] == str(source)
    assert result["structured_data"]["rows"][0]["values"]["amount"] == "123"
    assert "source_file" not in result and "evidence" not in result
    assert result["dependencies"]["pydantic"]
    with b["db"].transaction(b["owner"], b["business"]) as c:
        assert c.execute("SELECT count(*) AS n FROM herman.records").fetchone()["n"] == 0
    assert process_one(queue, b["tokens"][0], b["business"]) is None
    assert queue.enqueue(b["owner"], b["business"], "job", ExtractionInput(document_id=source)) == identity
    with pytest.raises(psycopg.errors.InsufficientPrivilege), b["db"].transaction(b["owner"], b["business"]) as c:
        c.execute("UPDATE herman.extractions SET parser_version='forged'")


def test_concurrent_claim_and_expired_worker_fencing(backend, tmp_path):
    b = backend
    queue, identity, _ = enqueue(b)
    with ThreadPoolExecutor(max_workers=6) as pool:
        claims = list(pool.map(lambda _: queue.claim(b["owner"], b["business"]), range(6)))
    claimed = [row for row in claims if row]
    assert len(claimed) == 1
    first = claimed[0]
    expire(b, identity)
    second = queue.claim(b["owner"], b["business"])
    assert second["lease_token"] != first["lease_token"]
    assert second["attempts"] == 2
    with pytest.raises(Conflict):
        queue.fail(b["owner"], b["business"], identity, first["lease_token"], "timeout", True)
    path = tmp_path / "source.csv"
    path.write_bytes("شرح,مبلغ\nخرید,۱۲۳\n".encode())
    result = document("synthetic", path, "csv", 1)
    with pytest.raises(Conflict):
        queue.complete(b["owner"], b["business"], identity, first["lease_token"], result, {})
    queue.complete(b["owner"], b["business"], identity, second["lease_token"], result, {})
    with pytest.raises(Conflict):
        queue.complete(b["owner"], b["business"], identity, second["lease_token"], result, {})


def test_retry_backoff_and_attempt_exhaustion(backend):
    b = backend
    queue, identity, _ = enqueue(b)
    for attempt in range(1, 4):
        claimed = queue.claim(b["owner"], b["business"])
        assert claimed["attempts"] == attempt
        queue.fail(b["owner"], b["business"], identity, claimed["lease_token"], "storage_unavailable", True)
        assert queue.claim(b["owner"], b["business"]) is None
        with psycopg.connect(b["admin"]) as c:
            c.execute("UPDATE herman.extraction_jobs SET available_at=now()-interval '1 second' "
                      "WHERE business_id=%s AND id=%s", (b["business"], identity))
    assert queue.read(b["owner"], b["business"], identity)["status"] == "failed"


def test_crashes_exhaust_lease_budget(backend):
    b = backend
    queue, identity, _ = enqueue(b)
    for attempt in range(1, 4):
        assert queue.claim(b["owner"], b["business"])["attempts"] == attempt
        expire(b, identity)
    assert queue.claim(b["owner"], b["business"]) is None
    assert queue.read(b["owner"], b["business"], identity)["error_code"] == "lease_exhausted"


def test_invalid_csv_fails_without_retry_or_financial_writes(backend):
    b = backend
    queue, identity, _ = enqueue(b, content="مبلغ,مبلغ\n۱,۲\n")
    process_one(queue, b["tokens"][0], b["business"])
    job = queue.read(b["owner"], b["business"], identity)
    assert job["status"] == "failed"
    assert job["error_code"] == "invalid_document"
    assert job["attempts"] == 1 and job["extraction"] is None


def test_queue_api_tenant_and_role_isolation(backend):
    b = backend
    queue, identity, _ = enqueue(b)
    with pytest.raises(AccessDenied):
        queue.claim(b["viewer"], b["business"])
    with pytest.raises(AccessDenied):
        queue.read(b["stranger"], b["business"], identity)
    with b["db"].transaction(b["stranger"], b["other"]) as c:
        assert not c.execute("SELECT * FROM herman.extraction_jobs").fetchall()
    with pytest.raises(NotFound):
        queue.enqueue(b["owner"], b["business"], "unknown", ExtractionInput(document_id=uuid4()))
    with TestClient(create_app(b["db"], b["blob_root"])) as client:
        headers = {"Authorization": "Bearer " + b["tokens"][0]}
        assert client.get(f"/businesses/{b['business']}/document-jobs", headers=headers).status_code == 200
        detail = client.get(f"/businesses/{b['business']}/document-jobs/{identity}", headers=headers)
        assert detail.status_code == 200 and "lease_token" not in detail.json()
        denied = {"Authorization": "Bearer " + b["tokens"][1]}
        assert client.get(f"/businesses/{b['business']}/document-jobs/{identity}", headers=denied).status_code == 403


def test_timeout_retries_and_modified_evidence_fails(backend, monkeypatch):
    b = backend
    queue, identity, source = enqueue(b)

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("parser", 120)

    monkeypatch.setattr(worker_module.subprocess, "run", timeout)
    process_one(queue, b["tokens"][0], b["business"])
    job = queue.read(b["owner"], b["business"], identity)
    assert job["status"] == "queued" and job["error_code"] == "timeout"
    metadata, _ = b["service"].read_document(b["owner"], b["business"], source)
    (b["blob_root"] / str(b["business"]) / metadata["sha256"]).write_bytes(b"tampered")
    with psycopg.connect(b["admin"]) as c:
        c.execute("UPDATE herman.extraction_jobs SET available_at=now()-interval '1 second' "
                  "WHERE business_id=%s AND id=%s", (b["business"], identity))
    process_one(queue, b["tokens"][0], b["business"])
    job = queue.read(b["owner"], b["business"], identity)
    assert job["status"] == "failed" and job["error_code"] == "evidence_changed"
    with b["db"].transaction(b["owner"], b["business"]) as c:
        actions = [row["action"] for row in c.execute("SELECT action FROM herman.audit_events WHERE entity_id=%s",
                                                    (identity,)).fetchall()]
    assert "extraction.retry_scheduled.timeout.attempt_1" in actions
    assert "extraction.failed.evidence_changed.attempt_2" in actions
