"""A completeness timeout withholds figures while preserving the scoped transaction."""

import pytest
from test_backend import backend as backend_fixture
from test_backend import database as database_fixture
from test_backend import inventory_payload as inventory_fixture
from test_backend import seed_inventory

from src.backend import coverage_budget, inventory_freshness, service
from src.backend.coverage_budget import CoverageTimeout

backend = backend_fixture
database = database_fixture
inventory_payload = inventory_fixture


@pytest.mark.parametrize("prior,expected", [("0", "15s"), ("50ms", "50ms"), ("60s", "15s")])
def test_budget_preserves_stricter_timeout_and_restores_previous_setting(backend, prior, expected):
    b = backend
    with b["db"].transaction(b["viewer"], b["business"]) as c:
        c.execute("SELECT set_config('statement_timeout',%s,true)", (prior,))
        original = c.execute("SHOW statement_timeout").fetchone()["statement_timeout"]
        with coverage_budget.coverage_budget(c):
            assert c.execute("SHOW statement_timeout").fetchone()["statement_timeout"] == expected
            assert c.execute("SELECT 1 AS n").fetchone()["n"] == 1
        assert c.execute("SHOW statement_timeout").fetchone()["statement_timeout"] == original


def test_cancelled_query_rolls_back_savepoint_and_preserves_outer_context(backend, monkeypatch):
    b = backend
    monkeypatch.setattr(coverage_budget, "MAX_COVERAGE_STATEMENT_MS", 50)
    with b["db"].transaction(b["viewer"], b["business"]) as c:
        c.execute("SELECT set_config('herman.budget_marker','outer',true)")
        with pytest.raises(CoverageTimeout):
            with coverage_budget.coverage_budget(c):
                c.execute("SELECT set_config('herman.budget_marker','inner',true)")
                c.execute("SELECT pg_sleep(0.25)")
        assert c.execute("SHOW statement_timeout").fetchone()["statement_timeout"] == "0"
        assert c.execute("SELECT current_setting('herman.budget_marker') AS marker").fetchone()["marker"] == "outer"
        assert c.execute("SELECT herman.business_id() AS id").fetchone()["id"] == b["business"]


def timed_selection(c, *args, **kwargs):
    with coverage_budget.coverage_budget(c):
        c.execute("SELECT pg_sleep(0.25)")
    raise AssertionError("the test query must exceed its explicit timeout")


def test_timeout_is_unknown_for_advice_without_aborting_later_reads(backend, inventory_payload, monkeypatch):
    b = backend
    value = seed_inventory(b, inventory_payload)
    identity = b["service"].analyze(b["owner"], b["business"], "before-timeout", value)
    row = b["service"].analysis(b["viewer"], b["business"], identity)
    monkeypatch.setattr(coverage_budget, "MAX_COVERAGE_STATEMENT_MS", 50)
    monkeypatch.setattr(inventory_freshness, "select_inputs", timed_selection)
    with b["db"].transaction(b["viewer"], b["business"]) as c:
        summary = inventory_freshness.advice_summary(c, b["business"], row)
        assert summary["freshness"]["status"] == "unknown"
        assert summary["freshness"]["reason"] == "coverage_query_timeout"
        assert not summary["available_for_current_advice"] and summary["result"] is None
        assert c.execute("SELECT 1 AS n").fetchone()["n"] == 1
    assert b["service"].analysis(b["viewer"], b["business"], identity) == row


def test_timeout_cannot_publish_partial_analysis_or_idempotency(backend, inventory_payload, monkeypatch):
    b = backend
    value = seed_inventory(b, inventory_payload)
    monkeypatch.setattr(coverage_budget, "MAX_COVERAGE_STATEMENT_MS", 50)
    monkeypatch.setattr(service, "select_inputs", timed_selection)
    with pytest.raises(ValueError, match="زمان"):
        b["service"].analyze(b["owner"], b["business"], "timed-out-analysis", value)
    with b["db"].transaction(b["viewer"], b["business"]) as c:
        assert not c.execute("SELECT 1 FROM herman.analysis_runs").fetchone()
        assert not c.execute("SELECT 1 FROM herman.idempotency_keys WHERE key='timed-out-analysis'").fetchone()
        assert not c.execute("SELECT 1 FROM herman.audit_events WHERE action='inventory.analyzed'").fetchone()
