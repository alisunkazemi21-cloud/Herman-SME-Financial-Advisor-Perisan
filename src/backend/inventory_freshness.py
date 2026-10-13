"""Read-time change impact; immutable analysis and case receipts are never rewritten."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from uuid import UUID

from psycopg import Connection
from pydantic import ValidationError

from src.backend.dated_inventory import DatedInventoryRequest, PackDefinition
from src.backend.inventory import (
    Count,
    Fulfillment,
    InventoryRequest,
    InventoryResult,
    Item,
    Movement,
    Recipe,
    UnitConversion,
)
from src.backend.inventory_history import current_successor
from src.backend.inventory_selection import SelectionLimit, select_inputs

MAX_INPUT_ROWS = 10000
MAX_INPUT_BYTES = 8 * 1024 * 1024
MAX_CHANGE_EXAMPLES = 20
COLLECTIONS = {
    "items": Item, "conversions": UnitConversion, "movements": Movement,
    "recipes": Recipe, "fulfillments": Fulfillment, "opening": Count, "closing": Count,
}
REASONS_FA = {
    "current": "ورودی‌های ثبت‌شده با انتخاب فعلی یکسان‌اند؛ کامل‌بودن اسناد و صحت فایل‌ها دوباره تأیید نشده است.",
    "stale": "ورودی‌ها یا تصمیم‌های بررسی تغییر کرده‌اند؛ شمارش و پوشش را بررسی و تحلیل تازه تهیه کنید.",
    "unknown": "تازگی این تحلیل در محدوده بررسی قابل تعیین نیست؛ از ارقام آن به‌عنوان وضعیت فعلی استفاده نکنید.",
}


def _encoded(value: dict) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode()


def _index(inputs: dict) -> dict[tuple[str, str], dict]:
    result = {}
    for name, model in COLLECTIONS.items():
        rows = [inputs[name]] if name in ("opening", "closing") and inputs[name] else inputs[name]
        for row in rows or ():
            typed = model.model_validate(row).model_dump()
            # Line order is not part of a recipe's meaning.
            if name == "recipes":
                typed["lines"] = sorted(typed["lines"], key=lambda line: str(line["item_id"]))
            result[(name, str(typed["id"]))] = typed
    definitions = inputs.get("pack_definitions")
    if definitions is None:
        definitions = [dict(row, decision="baseline") for row in inputs["conversions"]]
    for row in definitions:
        typed = PackDefinition.model_validate(row).model_dump()
        result[("pack_definitions", str(typed["id"]))] = typed
    return result


def freshness(c: Connection, business: UUID, row: dict) -> dict:
    """Compare current recorded inputs, not source bytes or reconstructed historical approvals."""
    common = dict(comparison_version="inventory.selection.v1", checked_at=datetime.now(timezone.utc),
                  evidence_verification="not_rechecked")

    def unknown(reason: str) -> dict:
        return dict(**common, status="unknown", stale=None, reason=reason, reason_fa=REASONS_FA["unknown"],
                    changes=None, count_selection_required=[])

    try:
        raw = row["input_snapshot"]
        encoded = _encoded(raw)
        if len(encoded) > MAX_INPUT_BYTES:
            return unknown("input_byte_limit")
        if hashlib.sha256(encoded).hexdigest() != row["input_sha256"]:
            return unknown("input_hash_mismatch")
        if row["result"]["metric_version"] != "inventory.unexplained_variance.v1":
            return unknown("unsupported_metric_version")
        inventory_raw = dict(raw)
        definitions = inventory_raw.pop("pack_definitions", None)
        request = InventoryRequest.model_validate(inventory_raw)
        if definitions is not None:
            DatedInventoryRequest(inventory=request.model_copy(update={"conversions": ()}),
                                  definitions=definitions)
        if request.scope.business_id != business:
            return unknown("invalid_scope")
        result = InventoryResult.model_validate(row["result"])
        if result.scope != request.scope or result.target_item_id != request.target_item_id:
            return unknown("result_scope_mismatch")
        saved = _index(raw)
        saved_rows = len(saved) + sum(len(r["lines"]) for r in request.model_dump()["recipes"])
        if saved_rows > MAX_INPUT_ROWS:
            return unknown("input_row_limit")
        selected = select_inputs(c, business, request.scope,
            request.opening.id if request.opening else None, request.closing.id if request.closing else None,
            max_rows=MAX_INPUT_ROWS)
        if len(_encoded(selected)) > MAX_INPUT_BYTES:
            return unknown("input_byte_limit")
        current = _index(selected)
        added = sorted(current.keys() - saved.keys())
        removed = sorted(saved.keys() - current.keys())
        changed = sorted(key for key in current.keys() & saved.keys() if current[key] != saved[key])

        def sample(keys: list[tuple[str, str]], change: str) -> dict:
            examples = []
            for collection, identity in keys[:MAX_CHANGE_EXAMPLES]:
                key = (collection, identity)
                entry = dict(collection=collection, id=identity)
                if change == "changed":
                    entry.update(before_status=saved[key].get("status"), after_status=current[key].get("status"))
                    entry["fields"] = sorted(field for field in saved[key] if saved[key][field] != current[key][field])
                if change == "removed" and collection not in ("items", "conversions", "pack_definitions"):
                    successor = current_successor(c, business, UUID(identity))
                    entry["superseded_by"] = str(successor) if successor else None
                examples.append(entry)
            return dict(count=len(keys), examples=examples, truncated=len(keys) > MAX_CHANGE_EXAMPLES)

        counts = []
        for role in ("opening", "closing"):
            old = getattr(request, role)
            if old and selected[role] is None:
                successor = current_successor(c, business, old.id)
                counts.append(dict(role=role, id=str(old.id), superseded_by=str(successor) if successor else None))
        status = "stale" if added or removed or changed else "current"
        return dict(**common, status=status, stale=status == "stale", reason_fa=REASONS_FA[status],
                    saved_inputs=len(saved), current_inputs=len(current), count_selection_required=counts,
                    changes=dict(added=sample(added, "added"), removed=sample(removed, "removed"),
                                 changed=sample(changed, "changed")))
    except SelectionLimit:
        return unknown("input_row_limit")
    except (ValidationError, KeyError, TypeError, ValueError):
        return unknown("invalid_or_unsupported_input")


def advice_summary(c: Connection, business: UUID, row: dict) -> dict:
    status = freshness(c, business, row)
    current = status["status"] == "current"
    result = row["result"] if isinstance(row["result"], dict) else {}
    saved_status = result.get("status") if result.get("status") in ("complete", "incomplete") else None
    return dict(id=row["id"], input_sha256=row["input_sha256"], created_at=row["created_at"],
                saved_status=saved_status, freshness=status,
                available_for_current_advice=current and saved_status == "complete",
                result=row["result"] if current else None,
                source_provenance=row.get("source_provenance", []) if current else [],
                correction_provenance=row.get("correction_provenance", []) if current else [],
                pack_uses=row.get("pack_uses", []) if current else [])
