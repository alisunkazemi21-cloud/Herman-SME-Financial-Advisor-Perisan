"""Bounded trusted binding metadata and write-only batch capture."""

from collections.abc import Callable, Iterable
from datetime import datetime
from uuid import UUID, uuid4

from psycopg import Connection

from src.backend.dated_inventory import PackDefinition
from src.backend.pack_interpretation import PackBindingState, PackContext

MAX_BINDING_ROWS = 10000


class SelectionLimit(ValueError):
    """A complete comparison cannot be established within its read budget."""


def _ids(values: Iterable[UUID]) -> list[UUID]:
    result = set()
    for position, identity in enumerate(values):
        if position >= MAX_BINDING_ROWS:
            raise SelectionLimit("binding identity selection exceeds row limit")
        result.add(identity)
    return sorted(result)


def select_binding_state(
    c: Connection, business: UUID, definitions: tuple[PackDefinition, ...],
    record_ids: Iterable[UUID], fulfillment_ids: Iterable[UUID], *, read: Callable | None = None,
) -> PackBindingState:
    """Read one scoped snapshot; a supplied reader shares its caller's row budget."""
    if len(definitions) > MAX_BINDING_ROWS or any(d.business_id != business for d in definitions):
        raise ValueError("binding definitions exceed the supported scope or limit")
    sources, roots = _ids(record_ids), _ids(fulfillment_ids)
    remaining = MAX_BINDING_ROWS

    def rows(query: str, parameters: tuple) -> list[dict]:
        nonlocal remaining
        selected = (read(query, parameters) if read is not None else
                    c.execute(query + " LIMIT %s", (*parameters, remaining + 1)).fetchall())
        remaining -= len(selected)
        if remaining < 0:
            raise SelectionLimit("binding metadata exceeds comparison row limit")
        return selected

    observations = rows(
        "SELECT definition_id,observed_at,origin FROM herman.pack_definition_observations "
        "WHERE business_id=%s AND definition_id=ANY(%s::uuid[]) ORDER BY definition_id",
        (business, [d.id for d in definitions]),
    ) if definitions else []
    legacy = rows(
        "SELECT id FROM herman.records WHERE business_id=%s AND id=ANY(%s::uuid[]) "
        "AND pack_binding_legacy ORDER BY id", (business, sources),
    ) if sources else []
    checks = rows(
        "SELECT business_id,id,record_id,ingredient_id,fulfillment_id,recipe_path,item_id,occurred_at,"
        "definition_id,origin,state,missing_reason,created_by,captured_at "
        "FROM herman.pack_binding_checks WHERE business_id=%s AND record_id=ANY(%s::uuid[]) "
        "AND (fulfillment_id IS NULL OR fulfillment_id=ANY(%s::uuid[])) ORDER BY id",
        (business, sources, roots),
    ) if sources else []
    resolutions = rows(
        "SELECT business_id,id,check_id,approved,definition_id,actor_id,reason_fa,document_id,locator,decided_at "
        "FROM herman.pack_binding_reviews WHERE business_id=%s AND check_id=ANY(%s::uuid[]) "
        "AND approved ORDER BY id", (business, [check["id"] for check in checks]),
    ) if checks else []
    for resolution in resolutions:
        resolution["evidence"] = dict(document_id=resolution.pop("document_id"), locator=resolution.pop("locator"))
    boundary = rows(
        "SELECT captured_at AS cutover_at,clock_timestamp() AS as_of "
        "FROM herman.pack_binding_cutover ORDER BY singleton", (),
    )
    if len(boundary) != 1:
        raise ValueError("binding cutover metadata is unavailable")
    return PackBindingState(business_id=business, **boundary[0], observations=observations,
                            legacy_record_ids=[row["id"] for row in legacy], checks=checks,
                            resolutions=resolutions)


def capture_past_contexts(c: Connection, business: UUID, contexts: Iterable[PackContext], as_of: datetime) -> None:
    """Capture source keys in the authorized transaction; SQL derives their meaning."""
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("binding capture needs an aware server observation instant")
    selected = {}
    for position, context in enumerate(contexts):
        if position >= MAX_BINDING_ROWS:
            raise SelectionLimit("binding capture exceeds context limit")
        if context.occurred_at <= as_of:
            previous = selected.get(context.key)
            if previous is not None and previous != context:
                raise ValueError("binding source key has contradictory context")
            selected[context.key] = context
    if not selected:
        return
    with c.cursor() as cursor:
        cursor.executemany(
            "INSERT INTO herman.pack_binding_checks(business_id,id,record_id,ingredient_id,fulfillment_id,recipe_path) "
            "VALUES(%s,%s,%s,%s,%s,%s::uuid[]) "
            "ON CONFLICT(business_id,record_id,ingredient_id,fulfillment_id,recipe_path) DO NOTHING",
            [(business, uuid4(), context.record_id, context.ingredient_id, context.fulfillment_id,
              list(context.recipe_path)) for context in sorted(selected.values(), key=lambda row: str(row.key))],
        )
