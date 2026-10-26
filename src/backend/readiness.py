"""Point-in-time dependency probes, without tenant data or diagnostic disclosure."""

import os
import secrets
from pathlib import Path
from tempfile import NamedTemporaryFile

import psycopg

from src.backend.database import Database


def dependencies_ready(database: Database, blob_root: Path) -> bool:
    try:
        with psycopg.connect(
            database.dsn, connect_timeout=2, autocommit=True,
            options="-c statement_timeout=2000 -c lock_timeout=500 -c default_transaction_read_only=on",
        ) as connection:
            connection.execute("SELECT pack_uses FROM herman.analysis_runs WHERE false")
            connection.execute("SELECT id FROM herman.pack_definitions WHERE false")
            connection.execute("SELECT definition_id FROM herman.pack_decisions WHERE false")
            connection.execute("SELECT d.id,a.validity FROM herman.item_definitions d "
                               "JOIN herman.item_alias_periods a "
                               "ON (a.business_id,a.definition_id)=(d.business_id,d.id) WHERE false")
            connection.execute("SELECT item_definition_id FROM herman.record_sources WHERE false")
            connection.execute("SELECT pack_binding_legacy FROM herman.records WHERE false")
            connection.execute("SELECT captured_at FROM herman.pack_binding_cutover WHERE false")
            connection.execute("SELECT observed_at FROM herman.pack_definition_observations WHERE false")
            connection.execute("SELECT definition_id FROM herman.pack_binding_checks WHERE false")
            connection.execute("SELECT definition_id FROM herman.pack_binding_reviews WHERE false")
            connection.execute("SELECT id FROM herman.coverage_assessments WHERE false")
            connection.execute("SELECT assessment_id FROM herman.coverage_decisions WHERE false")
            connection.execute("SELECT id FROM herman.action_proposals WHERE false")
            connection.execute("SELECT sequence FROM herman.action_events WHERE false")
        expected = secrets.token_bytes(32)
        with NamedTemporaryFile(mode="w+b", prefix=".herman-ready-", dir=blob_root) as probe:
            probe.write(expected)
            probe.flush()
            os.fsync(probe.fileno())
            probe.seek(0)
            if probe.read() != expected:
                return False
        return True
    except Exception:
        # Dependency messages can contain credentials, connection details or private paths.
        return False
