"""Read-time change impact; immutable analysis and case receipts are never rewritten."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from uuid import UUID

from psycopg import Connection
from pydantic import ValidationError

from src.backend.coverage_budget import CoverageTimeout
from src.backend.coverage_models import CoverageSnapshot
from src.backend.dated_inventory import DatedInventoryRequest, PackDefinition
from src.backend.inventory import (
    Count,
    Coverage,
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
from src.backend.item_selection import ItemLabelState
from src.backend.pack_interpretation import BoundInventoryRequest, PackBindingState

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
    if inputs.get("item_labels") is not None:
        labels = ItemLabelState.model_validate(inputs["item_labels"])
        for label in labels.labels:
            # A future successor can close this interval without changing selection here.
            typed = label.model_dump(exclude={"valid_to"})
            typed.update(contract_version=labels.contract_version, effective_at=labels.effective_at)
            result[("item_labels", str(label.item_id))] = typed
    if inputs.get("pack_bindings") is not None:
        bindings = PackBindingState.model_validate(inputs["pack_bindings"])
        result[("binding_cutover", "singleton")] = dict(
            business_id=bindings.business_id, cutover_at=bindings.cutover_at,
            contract_version=bindings.contract_version)
        for identity in bindings.legacy_record_ids:
            result[("binding_legacy_sources", str(identity))] = dict(id=identity)
        for name, rows, key in (
            ("binding_observations", bindings.observations, "definition_id"),
            ("binding_checks", bindings.checks, "id"),
            ("binding_resolutions", bindings.resolutions, "id"),
        ):
            for entry in rows:
                result[(name, str(getattr(entry, key)))] = entry.model_dump()
    if inputs.get("coverage_review") is not None:
        completeness = CoverageSnapshot.model_validate(inputs["coverage_review"])
        result[("coverage_review", "scope")] = completeness.model_dump(exclude={"as_of"})
    return result


def _contains_pack_quantities(request: InventoryRequest) -> bool:
    direct = (*request.movements, *request.fulfillments,
              *(row for row in (request.opening, request.closing) if row is not None))
    return any(row.unit == "pack" for row in direct) or any(
        recipe.output_unit == "pack" or any(line.unit == "pack" for line in recipe.lines)
        for recipe in request.recipes)


def freshness(c: Connection, business: UUID, row: dict) -> dict:
    """Compare current recorded inputs, not source bytes or reconstructed historical approvals."""
    common = dict(comparison_version="inventory.selection.v2", checked_at=datetime.now(timezone.utc),
                  evidence_verification="not_rechecked")

    def unknown(reason: str) -> dict:
        explanation = ("اطلاعات این تحلیل برای بررسی سابقهٔ تبدیل بسته کافی نیست؛ "
                       "تبدیل‌ها را بررسی و تحلیل تازه‌ای تهیه کنید."
                       if reason == "legacy_pack_context_missing" else REASONS_FA["unknown"])
        if reason == "legacy_coverage_missing":
            explanation = "این تحلیل سابقهٔ بررسی دسته‌های اسناد را ندارد؛ برای استفاده از آن به‌عنوان وضعیت فعلی، پوشش اسناد را بررسی و تحلیل تازه تهیه کنید."
        elif reason == "coverage_query_timeout":
            explanation = "بررسی پوشش اسناد در زمان مجاز ممکن نشد؛ ارقام این تحلیل برای وضعیت فعلی ارائه نمی‌شوند."
        return dict(**common, status="unknown", stale=None, reason=reason, reason_fa=explanation,
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
        bindings = inventory_raw.pop("pack_bindings", None)
        labels = inventory_raw.pop("item_labels", None)
        coverage_review = inventory_raw.pop("coverage_review", None)
        declaration = inventory_raw.pop("coverage_declaration", None)
        request = InventoryRequest.model_validate(inventory_raw)
        if labels is not None:
            ItemLabelState.model_validate(labels).validate_selection(request.items, business, request.scope.end)
        if bindings is not None:
            if definitions is None:
                return unknown("invalid_or_unsupported_input")
            BoundInventoryRequest(inventory=request.model_copy(update={"conversions": ()}),
                                  definitions=definitions, bindings=bindings)
        elif _contains_pack_quantities(request):
            return unknown("legacy_pack_context_missing")
        elif definitions is not None:
            DatedInventoryRequest(inventory=request.model_copy(update={"conversions": ()}),
                                  definitions=definitions)
        if coverage_review is None or declaration is None:
            return unknown("legacy_coverage_missing")
        completeness = CoverageSnapshot.model_validate(coverage_review)
        completeness.validate_scope(request.scope, request.basis)
        if completeness.derive(Coverage.model_validate(declaration)) != request.coverage:
            return unknown("invalid_coverage_derivation")
        if request.scope.business_id != business:
            return unknown("invalid_scope")
        result = InventoryResult.model_validate(row["result"])
        if result.scope != request.scope or result.target_item_id != request.target_item_id:
            return unknown("result_scope_mismatch")
        saved = _index(raw)
        saved_rows = len(saved) + sum(len(r["lines"]) for r in request.model_dump()["recipes"])
        saved_rows += completeness.dataset.row_count + int(completeness.assessment is not None)
        if saved_rows > MAX_INPUT_ROWS:
            return unknown("input_row_limit")
        selected = select_inputs(c, business, request.scope,
            request.opening.id if request.opening else None, request.closing.id if request.closing else None,
            max_rows=MAX_INPUT_ROWS, include_bindings=bindings is not None, coverage_basis=request.basis)
        if len(_encoded(selected)) > MAX_INPUT_BYTES:
            return unknown("input_byte_limit")
        current_labels = ItemLabelState.model_validate(selected["item_labels"])
        current_labels.validate_selection(
            (Item.model_validate(item) for item in selected["items"]), business, request.scope.end)
        if labels is None:
            # Legacy receipts compare their recorded item text without invented definition IDs.
            selected.pop("item_labels")
        current = _index(selected)
        live_completeness = CoverageSnapshot.model_validate(selected["coverage_review"])
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
                if change == "removed" and collection in ("opening", "closing", "movements", "recipes", "fulfillments"):
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
        explanation = REASONS_FA[status]
        if status == "current" and live_completeness.provisional:
            explanation = "بررسی پوشش پیش از پایان دوره انجام شده است؛ محاسبهٔ مشروط در رسید محفوظ است و ارقام آن برای وضعیت فعلی ارائه نمی‌شوند."
        return dict(**common, status=status, stale=status == "stale", reason_fa=explanation,
                    saved_inputs=len(saved), current_inputs=len(current), count_selection_required=counts,
                    completeness=dict(complete=live_completeness.complete, provisional=live_completeness.provisional,
                                      blockers_fa=live_completeness.blockers_fa),
                    changes=dict(added=sample(added, "added"), removed=sample(removed, "removed"),
                                 changed=sample(changed, "changed")))
    except CoverageTimeout:
        return unknown("coverage_query_timeout")
    except SelectionLimit:
        return unknown("input_row_limit")
    except (ValidationError, KeyError, TypeError, ValueError):
        return unknown("invalid_or_unsupported_input")


def advice_summary(c: Connection, business: UUID, row: dict) -> dict:
    status = freshness(c, business, row)
    current = status["status"] == "current"
    result = row["result"] if isinstance(row["result"], dict) else {}
    saved_status = result.get("status") if result.get("status") in ("complete", "incomplete") else None
    completeness = status.get("completeness", {})
    supported = current and completeness.get("complete") is True and not completeness.get("provisional", True)
    show_result = current and (supported or saved_status == "incomplete")
    return dict(id=row["id"], input_sha256=row["input_sha256"], created_at=row["created_at"],
                saved_status=saved_status, freshness=status,
                available_for_current_advice=supported and saved_status == "complete",
                result=row["result"] if show_result else None,
                source_provenance=row.get("source_provenance", []) if show_result else [],
                correction_provenance=row.get("correction_provenance", []) if show_result else [],
                pack_uses=row.get("pack_uses", []) if show_result else [])
