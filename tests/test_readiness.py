import asyncio
from contextlib import contextmanager
from threading import Event
from types import SimpleNamespace

import httpx
import psycopg
import pytest
from fastapi.testclient import TestClient
from test_backend import backend as backend_fixture
from test_backend import database as database_fixture

from src.backend import api, readiness
from src.backend.api import create_app

backend = backend_fixture
database = database_fixture


@pytest.fixture
def connected(monkeypatch):
    calls = []

    @contextmanager
    def connect(*args, **kwargs):
        calls.append(kwargs)
        yield SimpleNamespace(execute=lambda query: None)

    monkeypatch.setattr(readiness.psycopg, "connect", connect)
    return calls


def test_probe_uses_real_temporary_io_and_cleans_up(tmp_path, connected):
    original = tmp_path / "customer-evidence"
    original.write_bytes(b"immutable")
    assert readiness.dependencies_ready(SimpleNamespace(dsn="private"), tmp_path)
    assert list(tmp_path.iterdir()) == [original]
    assert original.read_bytes() == b"immutable"
    assert connected[0]["connect_timeout"] == 2
    assert "statement_timeout=2000" in connected[0]["options"]
    assert "lock_timeout=500" in connected[0]["options"]
    assert "default_transaction_read_only=on" in connected[0]["options"]


@pytest.mark.parametrize("failure", [
    psycopg.OperationalError, psycopg.errors.UndefinedColumn, psycopg.errors.InsufficientPrivilege,
])
def test_database_failure_is_generic_and_liveness_survives(tmp_path, monkeypatch, failure):
    app = create_app(SimpleNamespace(dsn="private"), tmp_path)
    with TestClient(app) as client:
        def fail(*args, **kwargs):
            raise failure("private DSN password and file path")

        monkeypatch.setattr(readiness.psycopg, "connect", fail)
        response = client.get("/ready")
        assert response.status_code == 503
        assert response.json() == {"status": "unavailable"}
        assert response.headers["Cache-Control"] == "no-store"
        assert client.get("/health").json() == {"status": "ok"}
    assert list(tmp_path.iterdir()) == []


def test_storage_failure_and_recovery_after_startup(tmp_path, connected):
    root = tmp_path / "blobs"
    root.mkdir()
    with TestClient(create_app(SimpleNamespace(dsn="private"), root)) as client:
        assert client.get("/ready").json() == {"status": "ready"}
        root.rmdir()
        root.write_bytes(b"not a directory")
        response = client.get("/ready")
        assert response.status_code == 503
        assert response.json() == {"status": "unavailable"}
        assert response.headers["Cache-Control"] == "no-store"
        assert client.get("/health").status_code == 200
        root.unlink()
        root.mkdir()
        assert client.get("/ready").status_code == 200


def test_partial_probe_io_failure_removes_temporary_file(tmp_path, connected, monkeypatch):
    def fail(fd):
        raise OSError("private filesystem path")

    monkeypatch.setattr(readiness.os, "fsync", fail)
    assert not readiness.dependencies_ready(SimpleNamespace(dsn="private"), tmp_path)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("cancel_request", [False, True])
def test_single_flight_rejects_busy_probe_and_releases_slot(tmp_path, monkeypatch, cancel_request):
    entered, release = Event(), Event()
    calls = []

    def blocked(*args):
        calls.append(True)
        entered.set()
        assert release.wait(10)
        return False

    monkeypatch.setattr(api, "dependencies_ready", blocked)

    async def scenario():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=create_app(SimpleNamespace(dsn="private"), tmp_path)),
            base_url="http://test",
        ) as client:
            first = asyncio.create_task(client.get("/ready"))
            try:
                assert await asyncio.to_thread(entered.wait, 10)
                if cancel_request:
                    first.cancel()
                    with pytest.raises(asyncio.CancelledError):
                        await first
                busy = await client.get("/ready")
                assert busy.status_code == 503
                assert busy.headers["Cache-Control"] == "no-store"
                assert len(calls) == 1
                assert (await client.get("/health")).status_code == 200
            finally:
                release.set()
                if not first.cancelled():
                    await first
            monkeypatch.setattr(api, "dependencies_ready", lambda *args: True)
            # Cancellation leaves the shielded probe running until its actual I/O finishes.
            for _ in range(200):
                response = await client.get("/ready")
                if response.status_code == 200:
                    break
                await asyncio.sleep(0.01)
            assert response.status_code == 200

    asyncio.run(scenario())


def test_restricted_postgres_probe_and_later_outage(backend, monkeypatch):
    b = backend
    b["blob_root"].mkdir(exist_ok=True)
    with TestClient(create_app(b["db"], b["blob_root"])) as client:
        healthy = client.get("/ready")
        assert healthy.status_code == 200
        assert healthy.json() == {"status": "ready"}

        def fail(*args, **kwargs):
            raise psycopg.OperationalError("private connection details")

        with monkeypatch.context() as patch:
            patch.setattr(readiness.psycopg, "connect", fail)
            assert client.get("/ready").status_code == 503
            assert client.get("/health").status_code == 200
        assert client.get("/ready").status_code == 200
    assert list(b["blob_root"].iterdir()) == []
