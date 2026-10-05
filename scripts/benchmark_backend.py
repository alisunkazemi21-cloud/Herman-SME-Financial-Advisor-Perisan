"""Synthetic PostgreSQL read benchmark; use a dedicated disposable database.

No financial documents are generated. This measures indexed movement reads under RLS,
not ingestion/OCR/LLM latency or full reconciliation capacity. Run once per database.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import platform
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

from src.backend.database import AccessDenied, Database

QUERY = """SELECT count(*) AS n, sum(quantity) AS quantity
FROM herman.stock_movements
WHERE business_id=%s AND warehouse_id=%s AND item_id=%s
AND occurred_at>='2026-09-01T00:00:00Z' AND occurred_at<'2026-10-01T00:00:00Z'"""


def seed(admin: str) -> list[dict]:
    with psycopg.connect(admin, row_factory=dict_row) as c:
        if c.execute("SELECT 1 FROM herman.businesses LIMIT 1").fetchone():
            raise ValueError("Benchmark seeding requires an empty, disposable database")
        c.execute("""CREATE TEMP TABLE seed_tenants ON COMMIT DROP AS
            SELECT n,gen_random_uuid() AS business_id,gen_random_uuid() AS actor,
                gen_random_uuid() AS warehouse,gen_random_uuid() AS item,gen_random_uuid() AS document,
                CASE WHEN n<=10 THEN 50000 WHEN n=11 THEN 5500 ELSE 500 END AS events
            FROM generate_series(1,1000) n""")
        c.execute("INSERT INTO herman.users(id,display_name) SELECT actor,'synthetic' FROM seed_tenants")
        c.execute("INSERT INTO herman.businesses(id,name,industry,created_by) "
                  "SELECT business_id,'synthetic '||n,'retail',actor FROM seed_tenants")
        c.execute("INSERT INTO herman.memberships(business_id,user_id,role) "
                  "SELECT business_id,actor,'owner' FROM seed_tenants")
        c.execute("INSERT INTO herman.warehouses SELECT business_id,warehouse,'synthetic' FROM seed_tenants")
        c.execute("INSERT INTO herman.items SELECT business_id,item,'SKU','synthetic','each','direct' FROM seed_tenants")
        c.execute("INSERT INTO herman.documents(business_id,id,sha256,original_name,media_type,byte_size,created_by) "
                  "SELECT business_id,document,repeat('0',64),'SYNTHETIC-NO-BLOB','text/plain',0,actor FROM seed_tenants")
        c.execute("""CREATE TEMP TABLE seed_events ON COMMIT DROP AS
            SELECT business_id,actor,warehouse,item,document,gen_random_uuid() AS id,
                '2026-09-01T00:00:00Z'::timestamptz+(x%29)*interval '1 day' AS occurred_at
            FROM seed_tenants CROSS JOIN LATERAL generate_series(1,events) x""")
        print("Seeding 1,000,000 normalized records and movements...", flush=True)
        c.execute("INSERT INTO herman.records(business_id,id,kind,document_id,locator,created_by) "
                  "SELECT business_id,id,'movement',document,'synthetic',actor FROM seed_events")
        c.execute("INSERT INTO herman.stock_movements "
                  "SELECT business_id,id,warehouse,item,occurred_at,1,'each','purchase' FROM seed_events")
        tenants = c.execute("SELECT * FROM seed_tenants ORDER BY n").fetchall()
    with psycopg.connect(admin, autocommit=True) as c:
        c.execute("ANALYZE herman.stock_movements")
        c.execute("ANALYZE herman.memberships")
    return tenants


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--reuse-fixture", action="store_true")
    args = parser.parse_args()
    admin, app = os.environ["HERMAN_ADMIN_DSN"], os.environ["HERMAN_DATABASE_DSN"]
    database = Database(app)
    started = time.perf_counter()
    if args.reuse_fixture:
        with psycopg.connect(admin, row_factory=dict_row) as c:
            tenants = c.execute("""SELECT b.id AS business_id,b.created_by AS actor,w.id AS warehouse,
                i.id AS item,(SELECT count(*) FROM herman.stock_movements m WHERE m.business_id=b.id) AS events
                FROM herman.businesses b JOIN herman.warehouses w ON w.business_id=b.id
                JOIN herman.items i ON i.business_id=b.id
                WHERE b.name LIKE 'synthetic %' AND b.industry='retail'
                ORDER BY substring(b.name FROM 11)::integer""").fetchall()
        if len(tenants) != 1000 or sum(t["events"] for t in tenants) != 1000000:
            raise ValueError("existing fixture does not match benchmark profile")
        seed_seconds = None
    else:
        tenants = seed(admin)
        seed_seconds = round(time.perf_counter() - started, 2)
    failures = []
    durations = []
    isolation_errors = 0

    def read(tenant):
        started = time.perf_counter()
        with database.transaction(tenant["actor"], tenant["business_id"]) as c:
            result = c.execute(QUERY, (tenant["business_id"], tenant["warehouse"], tenant["item"])).fetchone()
            if result["n"] != tenant["events"] or result["quantity"] != tenant["events"]:
                raise AssertionError("incorrect tenant aggregate")
            # Predicate intentionally absent: count distinct tenants across the whole relation.
            visible = c.execute("SELECT DISTINCT business_id FROM herman.stock_movements").fetchall()
            if visible != [{"business_id": tenant["business_id"]}]:
                raise AssertionError("cross-tenant rows visible")
        return (time.perf_counter() - started) * 1000

    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=25) as pool:
        futures = [pool.submit(read, tenant) for tenant in tenants]
        for future in futures:
            try:
                durations.append(future.result())
            except Exception as exc:
                failures.append(type(exc).__name__)
    total_seconds = time.perf_counter() - started
    for tenant in tenants[:25]:
        try:
            with database.transaction(tenant["actor"], tenants[-1]["business_id"]):
                isolation_errors += 1
        except AccessDenied:
            pass
    ordered = sorted(durations)

    def percentile(p):
        return round(ordered[max(0, math.ceil(p * len(ordered)) - 1)], 2) if ordered else None

    largest = tenants[0]
    with database.transaction(largest["actor"], largest["business_id"]) as c:
        plan = c.execute("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + QUERY,
                         (largest["business_id"], largest["warehouse"], largest["item"])).fetchone()
    with psycopg.connect(admin) as c:
        version = c.execute("SELECT version()").fetchone()[0]
        settings = dict(c.execute("SELECT name,setting FROM pg_settings WHERE name IN "
                                  "('shared_buffers','max_connections','work_mem')").fetchall())
        db_bytes = c.execute("SELECT pg_database_size(current_database())").fetchone()[0]
    result = dict(timestamp_utc=datetime.now(timezone.utc).isoformat(),
        scope="Synthetic RLS movement aggregates + isolation reads; includes a new connection per request. "
              "Not full API, reconciliation, ingestion, OCR or LLM throughput; no cold-cache claim.",
        businesses=1000, movements=1000000, concurrency=25, requests=1000,
        distribution="10 tenants x 50000, 1 x 5500, 989 x 500 movements",
        seed_seconds=seed_seconds, reused_fixture=args.reuse_fixture, elapsed_seconds=round(total_seconds, 2),
        latency_ms=dict(p50=percentile(.5), p95=percentile(.95), p99=percentile(.99),
                        maximum=round(max(ordered), 2) if ordered else None),
        successful_reads=len(durations), errors=failures, unauthorized_accesses=isolation_errors,
        environment=dict(os=platform.platform(), python=platform.python_version(),
                         logical_cpus=os.cpu_count(), cpu=platform.processor(), postgres=version,
                         postgres_settings=settings, database_bytes=db_bytes), largest_tenant_plan=plan)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k not in ("largest_tenant_plan", "environment")}, indent=2))
    if failures or isolation_errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
