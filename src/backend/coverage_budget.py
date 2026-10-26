"""Bound completeness SQL without leaving the caller's transaction aborted."""

from collections.abc import Iterator
from contextlib import contextmanager

import psycopg

from src.backend.pack_binding_selection import SelectionLimit

MAX_COVERAGE_STATEMENT_MS = 15000


class CoverageTimeout(SelectionLimit):
    """Recorded completeness could not be assessed within the SQL time budget."""


@contextmanager
def coverage_budget(connection: psycopg.Connection) -> Iterator[None]:
    try:
        # Selection always runs in an existing scoped transaction. A nested
        # transaction supplies a savepoint so a cancelled read can be recovered.
        with connection.transaction():
            previous = connection.execute(
                "SELECT current_setting('statement_timeout') AS setting, "
                "extract(epoch FROM current_setting('statement_timeout')::interval)*1000 AS milliseconds"
            ).fetchone()
            changed = previous["milliseconds"] == 0 or previous["milliseconds"] > MAX_COVERAGE_STATEMENT_MS
            if changed:
                connection.execute("SELECT set_config('statement_timeout',%s,true)",
                                   (str(MAX_COVERAGE_STATEMENT_MS),))
            yield
            if changed:
                connection.execute("SELECT set_config('statement_timeout',%s,true)", (previous["setting"],))
    except psycopg.errors.QueryCanceled:
        raise CoverageTimeout("زمان بررسی پوشش اسناد بیش از حد مجاز است؛ محدودهٔ کوچک‌تری انتخاب کنید") from None
