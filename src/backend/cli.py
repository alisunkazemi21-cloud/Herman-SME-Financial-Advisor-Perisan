"""Administrative commands keep connection strings and bearer credentials out of command arguments."""
from __future__ import annotations

import argparse
import hashlib
import os
import secrets
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

import psycopg

from src.backend.database import Database, migrate


def main() -> None:
    parser = argparse.ArgumentParser(description="Herman backend operations")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("migrate")
    provision = sub.add_parser("provision-user")
    provision.add_argument("--name", required=True)
    provision.add_argument("--credential-file", type=Path, required=True)
    serve = sub.add_parser("serve")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--blob-root", type=Path, default=Path("data/backend/blobs"))
    worker = sub.add_parser("worker-once", help="Claim and process at most one job for one authorized business")
    worker.add_argument("--business", type=UUID, required=True)
    worker.add_argument("--credential-file", type=Path, required=True)
    worker.add_argument("--blob-root", type=Path, default=Path("data/backend/blobs"))
    continuous = sub.add_parser("worker", help="Continuously process one authorized business")
    continuous.add_argument("--business", type=UUID, required=True)
    continuous.add_argument("--credential-file", type=Path, required=True)
    continuous.add_argument("--blob-root", type=Path, default=Path("data/backend/blobs"))
    continuous.add_argument("--poll-seconds", type=int, choices=range(1, 61), default=2)
    args = parser.parse_args()
    if args.command == "migrate":
        migrate(os.environ["HERMAN_ADMIN_DSN"])
        print("Schema migrated; provision a separate LOGIN member of herman_app.")
    elif args.command == "provision-user":
        token, identity = secrets.token_urlsafe(48), uuid4()
        # Exclusive file creation prevents accidentally overwriting another user's credential.
        with args.credential_file.open("x", encoding="utf-8") as target:
            with psycopg.connect(os.environ["HERMAN_ADMIN_DSN"]) as c:
                c.execute("INSERT INTO herman.users(id,display_name) VALUES(%s,%s)", (identity, args.name))
                c.execute("INSERT INTO herman.api_credentials(digest,user_id,expires_at) VALUES(%s,%s,%s)",
                    (hashlib.sha256(token.encode()).hexdigest(), identity,
                     datetime.now(timezone.utc) + timedelta(days=30)))
                target.write(token)
                target.flush()
                os.fsync(target.fileno())
        print(f"User {identity} provisioned; credential saved to the requested private file (30 days).")
    elif args.command in ("worker-once", "worker"):
        from src.backend.jobs import ExtractionQueue
        from src.backend.service import Service
        from src.backend.worker import process_one
        queue = ExtractionQueue(Service(Database(os.environ["HERMAN_DATABASE_DSN"]), args.blob_root))
        try:
            while True:
                identity = process_one(queue, args.credential_file.read_text(encoding="utf-8").strip(), args.business)
                if identity:
                    print(f"Handled job {identity}", flush=True)
                if args.command == "worker-once":
                    break
                if identity is None:
                    time.sleep(args.poll_seconds)
        except KeyboardInterrupt:
            print("Worker stopped; unfinished leases remain recoverable.")
    else:
        import uvicorn

        from src.backend.api import create_app
        app = create_app(Database(os.environ["HERMAN_DATABASE_DSN"]), args.blob_root)
        uvicorn.run(app, host="127.0.0.1", port=args.port, access_log=False)


if __name__ == "__main__":
    main()
