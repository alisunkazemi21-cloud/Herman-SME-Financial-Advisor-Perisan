"""Authenticated C16 workflows preserve reviewed history and immutable receipts."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from threading import Barrier, local
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from test_backend import backend as backend_fixture
from test_backend import database as database_fixture
from test_backend import inventory_payload as inventory_fixture
from test_dated_inventory import dated_payload as dated_fixture
from test_pack_integration import setup
from test_tabular_imports import setup_import, source

from src.backend.advisor import BusinessAdvisor, BusinessContextInput
from src.backend.api import create_app
from src.backend.cases import BusinessCases, CaseInput, TurnInput
from src.backend.inventory import Count, Fulfillment, Item, Recipe, UnitConversion
from src.backend.service import AnalysisInput, Warehouse

backend = backend_fixture
database = database_fixture
inventory_payload = inventory_fixture
dated_payload = dated_fixture


def headers(b, role="owner", key=None):
    index = {"owner": 0, "stranger": 1, "editor": 2, "viewer": 3}[role]
    result = {"Authorization": "Bearer " + b["tokens"][index]}
    if key is not None:
        result["Idempotency-Key"] = key
    return result


def catalog_url(b, suffix=""):
    return f"/businesses/{b['business']}/catalog{suffix}"


def bindings_url(b, suffix=""):
    return f"/businesses/{b['business']}/pack-bindings{suffix}"


def checked(response, status=200):
    assert response.status_code == status, response.text
    assert response.headers.get("cache-control") == "no-store"
    return response.json()


def get(client, b, url, role="viewer", **params):
    return checked(client.get(url, headers=headers(b, role), params=params))


def post(client, b, url, value, key, role="owner"):
    return checked(client.post(url, json=value, headers=headers(b, role, key)), 201)


def label_proposal(item, evidence, **changes):
    return dict(id=str(uuid4()), item_id=str(item), predecessor_id=str(item),
                sku="REVIEWED", name_fa="نام بررسی‌شده", evidence=evidence, **changes)


def decision(approved=True, when=None):
    result = dict(approved=approved, reason_fa="با شاهد بررسی شد")
    if when is not None:
        result["effective_at"] = when.isoformat()
    return result


@pytest.fixture
def catalog_seed(backend):
    b = backend
    item = Item(id=uuid4(), business_id=b["business"], sku="ORIGINAL", name_fa="نام اصلی",
                base_unit="each")
    b["service"].catalog(b["editor"], b["business"], "item", item)
    document = b["service"].document(b["owner"], b["business"], "catalog-source",
                                    "catalog.txt", "text/plain", b"synthetic catalog source")
    evidence = dict(document_id=str(document), locator="line:1")
    factor = UnitConversion(id=uuid4(), business_id=b["business"], item_id=item.id,
                            base_quantity="8.123456", evidence=evidence)
    b["service"].catalog(b["owner"], b["business"], "factor", factor)
    return b, item, factor, evidence


def test_http_catalog_half_open_labels_history_and_exact_pack_values(catalog_seed):
    b, item, factor, evidence = catalog_seed
    activation = datetime.now(timezone.utc) + timedelta(days=1)
    with TestClient(create_app(b["db"], b["blob_root"])) as client:
        before_clock = datetime.now(timezone.utc)
        initial = get(client, b, catalog_url(b, "/items"))
        after_clock = datetime.now(timezone.utc)
        assert before_clock <= datetime.fromisoformat(initial["effective_at"]) <= after_clock
        assert initial["evidence_verification"] == "not_rechecked"
        assert initial["items"][0]["label"]["definition_id"] == str(item.id)
        assert initial["next_cursor"] is None
        pending = label_proposal(item.id, evidence)
        rejected = label_proposal(item.id, evidence)
        for key, proposal in (("pending-label", pending), ("rejected-label", rejected)):
            assert post(client, b, catalog_url(b, "/item-revisions"), proposal, key, "editor") == {
                "id": proposal["id"]}
        post(client, b, catalog_url(b, f"/item-revisions/{rejected['id']}/decision"),
             decision(False), "reject-label")
        detail_url = catalog_url(b, f"/items/{item.id}")
        assert get(client, b, detail_url, effective_at=activation.isoformat())["label"]["definition_id"] == str(item.id)
        for _ in range(2):
            post(client, b, catalog_url(b, f"/item-revisions/{pending['id']}/decision"),
                 decision(when=activation), "approve-label")
        before = get(client, b, detail_url, effective_at=(activation-timedelta(microseconds=1)).isoformat())
        at = get(client, b, detail_url, effective_at=activation.isoformat())
        assert before["label"]["definition_id"] == str(item.id)
        assert datetime.fromisoformat(before["label"]["valid_to"]) == activation
        assert at["label"]["definition_id"] == pending["id"]
        assert at["item"]["id"] == str(item.id)
        assert at["item"]["sku"] == at["label"]["sku"] == pending["sku"]
        assert at["item"]["base_unit"] == "each" and at["item"]["consumption_mode"] == "direct"
        assert at["evidence_verification"] == "not_rechecked"
        assert at["historical_usage_status"] == "not_evaluated"
        assert at["pack_definition"]["base_quantity"] == "8.123456"
        assert get(client, b, detail_url)["label"]["definition_id"] == str(item.id)
        history = get(client, b, catalog_url(b, f"/items/{item.id}/labels"))
        assert {row["id"] for row in history} == {str(item.id), pending["id"], rejected["id"]}
        assert next(row for row in history if row["id"] == rejected["id"])["approved"] is False
        baseline = get(client, b, catalog_url(b, f"/item-revisions/{item.id}"))
        assert baseline["successor_id"] == pending["id"] and baseline["predecessor_id"] is None
        reviewed = get(client, b, catalog_url(b, f"/item-revisions/{pending['id']}"))
        assert reviewed["predecessor_id"] == str(item.id) and reviewed["approved"] is True
        assert reviewed["document_id"] == evidence["document_id"]
        assert reviewed["reason_fa"] == decision()["reason_fa"]
        # Stable ID pages include proposed/rejected definitions without selecting them.
        first = get(client, b, catalog_url(b, f"/items/{item.id}/labels"), limit=1)
        rest = get(client, b, catalog_url(b, f"/items/{item.id}/labels"), after=first[0]["id"])
        assert first + rest == history
        pack = dict(id=str(uuid4()), item_id=str(item.id), predecessor_id=str(factor.id),
                    base_quantity="10.000001", evidence=evidence)
        post(client, b, catalog_url(b, "/pack-revisions"), pack, "propose-pack", "editor")
        for _ in range(2):
            post(client, b, catalog_url(b, f"/pack-revisions/{pack['id']}/decision"),
                 decision(when=activation), "approve-pack")
        assert get(client, b, detail_url, effective_at=(activation-timedelta(microseconds=1)).isoformat())[
            "pack_definition"]["base_quantity"] == "8.123456"
        assert get(client, b, detail_url, effective_at=activation.isoformat())[
            "pack_definition"]["base_quantity"] == "10.000001"
        pack_history = get(client, b, catalog_url(b, f"/items/{item.id}/packs"))
        assert {row["base_quantity"] for row in pack_history} == {"8.123456", "10.000001"}
        old_pack = get(client, b, catalog_url(b, f"/pack-revisions/{factor.id}"))
        assert old_pack["successor_id"] == pack["id"]
        assert datetime.fromisoformat(old_pack["valid_to"]) == activation
        new_pack = get(client, b, catalog_url(b, f"/pack-revisions/{pack['id']}"))
        assert new_pack["predecessor_id"] == str(factor.id)
        assert datetime.fromisoformat(new_pack["valid_from"]) == activation
        raw = client.get(f"/businesses/{b['business']}/resources/items", headers=headers(b, "viewer")).json()
        assert raw[0]["sku"] == item.sku and raw[0]["name_fa"] == item.name_fa
        second = item.model_copy(update={"id": uuid4(), "sku": "SECOND"})
        b["service"].catalog(b["editor"], b["business"], "second-item", second)
        page = get(client, b, catalog_url(b, "/items"), limit=1, effective_at=activation.isoformat())
        following = get(client, b, catalog_url(b, "/items"), limit=1, after=page["next_cursor"],
                        effective_at=page["effective_at"])
        assert {page["items"][0]["item"]["id"], following["items"][0]["item"]["id"]} == {
            str(item.id), str(second.id)}
        assert following["next_cursor"] is None


def test_http_reviewed_versions_change_new_analysis_and_preserve_saved_case(backend, dated_payload):
    b = backend
    _, value, factor, activation = setup(b, dated_payload)
    analyses = f"/businesses/{b['business']}/inventory-analyses"
    with TestClient(create_app(b["db"], b["blob_root"])) as client:
        old_response = client.post(analyses, json=value.model_dump(mode="json"),
                                   headers=headers(b, key="before-http"))
        assert old_response.status_code == 201, old_response.text
        old = old_response.json()
        saved_old = b["service"].analysis(b["viewer"], b["business"], UUID(old["id"]))
        assert Decimal(old["result"]["unexplained_shortage"]) == 64
        assert len(old["pack_uses"]) == 6
        assert old["input_snapshot"]["item_labels"]["contract_version"] == "catalog.item_labels.v1"
        cases = BusinessCases(b["service"], BusinessAdvisor(b["service"]))
        case = cases.create(b["owner"], b["business"], "case", CaseInput(title_fa="بررسی بسته"))
        turn = TurnInput(expected_turn=0, generate_draft=False, context=BusinessContextInput(
            question_fa="اختلاف چقدر است؟", effective_at=value.scope.end, analysis_id=old["id"]))

        def no_model(_):
            raise AssertionError("context-only turn must not invoke a model")

        turn_id = cases.append(b["owner"], b["business"], case, "saved-turn", turn, no_model)
        saved = cases.read(b["viewer"], b["business"], case, turn_id)
        label_source = b["service"].document(b["owner"], b["business"], "separate-label-source",
            "label-only.txt", "text/plain", b"separate label approval evidence")
        proposal = label_proposal(value.target_item_id, dict(document_id=str(label_source), locator="line:1"))
        post(client, b, catalog_url(b, "/item-revisions"), proposal, "label-http", "editor")
        post(client, b, catalog_url(b, f"/item-revisions/{proposal['id']}/decision"),
             decision(when=activation), "label-review-http")
        stale = get(client, b, f"{analyses}/{old['id']}")
        assert stale["freshness"]["status"] == "stale"
        assert {k: v for k, v in stale.items() if k != "freshness"} == old
        pack = dict(id=str(uuid4()), item_id=str(factor.item_id), predecessor_id=str(factor.id),
                    base_quantity="10", evidence=factor.evidence.model_dump(mode="json"))
        post(client, b, catalog_url(b, "/pack-revisions"), pack, "pack-http", "editor")
        post(client, b, catalog_url(b, f"/pack-revisions/{pack['id']}/decision"),
             decision(when=activation), "pack-review-http")
        current_response = client.post(analyses, json=value.model_dump(mode="json"),
                                       headers=headers(b, key="after-http"))
        assert current_response.status_code == 201, current_response.text
        current = current_response.json()
        assert Decimal(current["result"]["unexplained_shortage"]) == 58
        assert Decimal(current["result"]["expected_usage"]) == 18
        assert {row["definition_id"] for row in current["pack_uses"]} == {str(factor.id), pack["id"]}
        selected = next(row for row in current["input_snapshot"]["items"] if row["id"] == str(factor.item_id))
        assert selected["sku"] == proposal["sku"] and selected["name_fa"] == proposal["name_fa"]
        assert get(client, b, f"{analyses}/{current['id']}")["freshness"]["status"] == "current"
        assert b["service"].analysis(b["viewer"], b["business"], UUID(old["id"])) == saved_old
        assert cases.read(b["viewer"], b["business"], case, turn_id) == saved
        saved_current = b["service"].analysis(b["viewer"], b["business"], UUID(current["id"]))
        metadata, _ = b["service"].read_document(b["owner"], b["business"], label_source)
        (b["blob_root"]/str(b["business"])/metadata["sha256"]).write_bytes(b"changed label-only source")
        failed = client.post(analyses, json=value.model_dump(mode="json"),
                             headers=headers(b, key="tampered-label-analysis"))
        assert failed.status_code == 409, failed.text
        with b["db"].transaction(b["viewer"], b["business"]) as c:
            assert not c.execute("SELECT 1 FROM herman.idempotency_keys WHERE key='tampered-label-analysis'").fetchone()
        assert b["service"].analysis(b["viewer"], b["business"], UUID(current["id"])) == saved_current


def test_http_label_decision_drives_event_time_import_without_rewriting_origin(backend):
    b = backend
    _, mapping = setup_import(b)
    imports = f"/businesses/{b['business']}/tabular-imports"
    with TestClient(create_app(b["db"], b["blob_root"])) as client:
        response = client.post(imports, json=mapping.model_dump(mode="json"),
                               headers=headers(b, "editor", "first-import"))
        assert response.status_code == 201, response.text
        original = response.json()
        with b["db"].transaction(b["viewer"], b["business"]) as c:
            item = c.execute("SELECT id FROM herman.items WHERE sku='MEAT'").fetchone()["id"]
            origin = c.execute("SELECT * FROM herman.record_sources WHERE batch_id=%s",
                               (original["id"],)).fetchone()
        activation = datetime.now(timezone.utc) + timedelta(days=1)
        proposal = label_proposal(item, dict(document_id=str(origin["document_id"]), locator="CSV:row:2"))
        post(client, b, catalog_url(b, "/item-revisions"), proposal, "rename", "editor")
        post(client, b, catalog_url(b, f"/item-revisions/{proposal['id']}/decision"),
             decision(when=activation), "review-rename")
        before = (activation-timedelta(microseconds=1)).isoformat()
        extracted = source(b, f"sku,quantity,unit,time\nMEAT,1,kg,{before}\nREVIEWED,2,kg,{activation.isoformat()}\n",
                           "dated-import-source")
        value = mapping.model_copy(update={"extraction_id": extracted, "rows": (2, 3)})
        response = client.post(imports, json=value.model_dump(mode="json"),
                               headers=headers(b, "editor", "dated-import"))
        assert response.status_code == 201, response.text
        with b["db"].transaction(b["viewer"], b["business"]) as c:
            assert c.execute("SELECT * FROM herman.record_sources WHERE batch_id=%s",
                             (original["id"],)).fetchone() == origin
            rows = c.execute("SELECT item_definition_id,source_values FROM herman.record_sources "
                             "WHERE batch_id=%s ORDER BY source_row", (response.json()["id"],)).fetchall()
        assert [str(row["item_definition_id"]) for row in rows] == [str(item), proposal["id"]]
        assert [row["source_values"]["sku"] for row in rows] == ["MEAT", "REVIEWED"]


@pytest.fixture
def unresolved_seed(backend):
    """A newly backdated pack source precedes its first observed definition."""
    b = backend
    service = b["service"]
    warehouse = Warehouse(id=uuid4(), business_id=b["business"], name="انبار")
    item = Item(id=uuid4(), business_id=b["business"], sku="HIST", name_fa="بسته تاریخی", base_unit="each")
    for key, value in (("warehouse", warehouse), ("item", item)):
        service.catalog(b["owner"], b["business"], key, value)
    documents = {name: service.document(b["owner"], b["business"], name, name+".txt", "text/plain", name.encode())
                 for name in ("record", "definition", "resolution")}
    event = datetime.now(timezone.utc)-timedelta(days=2)
    opening = Count(id=uuid4(), business_id=b["business"], warehouse_id=warehouse.id, item_id=item.id,
                    occurred_at=event, quantity="1", unit="pack",
                    evidence=dict(document_id=documents["record"], locator="line:1"))
    service.propose(b["editor"], b["business"], "opening", opening)
    service.approve(b["owner"], b["business"], "opening-decision", opening.id, True, "بررسی شد")
    closing = opening.model_copy(update={"id": uuid4(), "occurred_at": event+timedelta(days=1),
                                         "quantity": Decimal("6"), "unit": "each"})
    service.propose(b["editor"], b["business"], "closing", closing)
    service.approve(b["owner"], b["business"], "closing-decision", closing.id, True, "بررسی شد")
    factor = UnitConversion(id=uuid4(), business_id=b["business"], item_id=item.id, base_quantity="8",
                            evidence=dict(document_id=documents["definition"], locator="line:1"))
    service.catalog(b["owner"], b["business"], "factor", factor)
    ref = dict(document_id=documents["record"], locator="coverage:1")
    analysis = AnalysisInput(scope=dict(business_id=b["business"], warehouse_id=warehouse.id,
                                       start=event, end=closing.occurred_at), target_item_id=item.id,
        opening_id=opening.id, closing_id=closing.id,
        coverage=dict(movements_complete=True, fulfillment_complete=True, recipes_complete=True, evidence=ref),
        policy=dict(absolute_base_quantity="0", relative_fraction="0", evidence=ref))
    from coverage_helpers import attest_coverage
    # Catalog resolution changes the interpretation, independently of the
    # explicit human review of this synthetic period's operational records.
    attest_coverage(b, analysis)
    return b, opening, factor, documents, analysis


def test_http_unknown_past_requires_explicit_evidenced_review(unresolved_seed):
    b, opening, factor, documents, value = unresolved_seed
    analyses = f"/businesses/{b['business']}/inventory-analyses"
    with TestClient(create_app(b["db"], b["blob_root"])) as client:
        page = get(client, b, bindings_url(b), record=str(opening.id), limit=1)
        assert len(page["checks"]) == 1 and page["next_cursor"] is None
        check = page["checks"][0]["id"]
        original = get(client, b, bindings_url(b, f"/{check}"))
        assert original["effective_state"] == "unresolved" and original["resolution"] is None
        capture = dict(id=str(uuid4()), record_id=str(opening.id))
        for _ in range(2):
            assert post(client, b, bindings_url(b), capture, "capture", "editor") == {"id": check}
        response = client.post(analyses, json=value.model_dump(mode="json"), headers=headers(b, key="before"))
        assert response.status_code == 201, response.text
        old = response.json()
        assert old["result"]["status"] == "incomplete" and old["pack_uses"] == []
        rejected = dict(id=str(uuid4()), approved=False, reason_fa="شاهد کافی نیست",
                        evidence=dict(document_id=str(documents["resolution"]), locator="line:1"))
        post(client, b, bindings_url(b, f"/{check}/reviews"), rejected, "reject-resolution")
        assert get(client, b, bindings_url(b, f"/{check}"))["effective_state"] == "unresolved"
        review = dict(rejected, id=str(uuid4()), approved=True, definition_id=str(factor.id),
                      reason_fa="تبدیل تاریخی با شاهد بررسی شد")
        for _ in range(2):
            assert post(client, b, bindings_url(b, f"/{check}/reviews"), review, "approve-resolution") == {"id": review["id"]}
        resolved = get(client, b, bindings_url(b, f"/{check}"))
        assert resolved["check"] == original["check"] and resolved["effective_state"] == "bound"
        assert resolved["resolution"]["definition_id"] == str(factor.id)
        first = get(client, b, bindings_url(b, f"/{check}/reviews"), limit=1)
        second = get(client, b, bindings_url(b, f"/{check}/reviews"), limit=1, after=first["next_cursor"])
        assert {first["reviews"][0]["id"], second["reviews"][0]["id"]} == {rejected["id"], review["id"]}
        assert second["next_cursor"] is None
        stale = get(client, b, f"{analyses}/{old['id']}")
        assert stale["freshness"]["status"] == "stale"
        assert {k: v for k, v in stale.items() if k != "freshness"} == old
        response = client.post(analyses, json=value.model_dump(mode="json"), headers=headers(b, key="after"))
        assert response.status_code == 201, response.text
        current = response.json()
        assert current["result"]["status"] == "complete"
        assert Decimal(current["result"]["unexplained_shortage"]) == 2
        assert current["pack_uses"][0]["check_id"] == check
        assert current["pack_uses"][0]["resolution_id"] == review["id"]


def test_http_catalog_authority_redaction_and_handled_errors(catalog_seed):
    b, item, factor, evidence = catalog_seed
    proposal = label_proposal(item.id, evidence)
    urls = [catalog_url(b, "/items"), catalog_url(b, f"/items/{item.id}"),
            catalog_url(b, f"/items/{item.id}/labels"), catalog_url(b, f"/items/{item.id}/packs"),
            catalog_url(b, f"/item-revisions/{item.id}"), catalog_url(b, f"/pack-revisions/{factor.id}"),
            bindings_url(b)]
    with TestClient(create_app(b["db"], b["blob_root"])) as client:
        for url in urls:
            checked(client.get(url), 401)
            checked(client.get(url, headers=headers(b, "stranger")), 403)
            checked(client.get(url, headers=headers(b, "viewer")))
        checked(client.post(catalog_url(b, "/item-revisions"), json=proposal,
                            headers=headers(b, "viewer", "forbidden")), 403)
        checked(client.post(catalog_url(b, "/item-revisions"), json=proposal,
                            headers=headers(b, "editor")), 422)
        assert post(client, b, catalog_url(b, "/item-revisions"), proposal, "same", "editor") == {"id": proposal["id"]}
        assert post(client, b, catalog_url(b, "/item-revisions"), proposal, "same", "editor") == {"id": proposal["id"]}
        checked(client.post(catalog_url(b, "/item-revisions"), json=dict(proposal, name_fa="تغییر"),
                            headers=headers(b, "editor", "same")), 409)
        checked(client.post(catalog_url(b, f"/item-revisions/{proposal['id']}/decision"), json=decision(),
                            headers=headers(b, "editor", "bad-decision")), 403)
        for suffix in (f"/items/{uuid4()}", f"/item-revisions/{uuid4()}", f"/pack-revisions/{uuid4()}"):
            checked(client.get(catalog_url(b, suffix), headers=headers(b)), 404)
        foreign = f"/businesses/{b['other']}/catalog/items/{item.id}"
        checked(client.get(foreign, headers=headers(b, "stranger")), 404)
        secret = "PRIVATE-SUBMITTED-VALUE-DO-NOT-ECHO"
        invalid = [dict(proposal, id=secret), dict(proposal, actor_id=secret),
                   dict(proposal, approved=True), dict(proposal, source=secret),
                   dict(proposal, base_unit="kg"), dict(proposal, consumption_mode="recipe")]
        for index, body in enumerate(invalid):
            response = client.post(catalog_url(b, "/item-revisions"), json=body,
                                   headers=headers(b, "editor", f"invalid:{index}"))
            checked(response, 422)
            assert secret not in response.text
            assert all("input" not in error for error in response.json().get("detail", []) if isinstance(error, dict))
        for query in ({"limit": 0}, {"limit": 101}, {"effective_at": "2026-10-26T10:00:00"}, {"after": secret}):
            response = client.get(catalog_url(b, "/items"), params=query, headers=headers(b))
            checked(response, 422)
            assert secret not in response.text
        checked(client.get(bindings_url(b), params={"limit": 51}, headers=headers(b)), 422)
        checked(client.post(catalog_url(b, f"/item-revisions/{proposal['id']}/decision"),
                            json=dict(approved=True, reason_fa="   "), headers=headers(b, key="blank")), 422)
        checked(client.post(catalog_url(b, "/pack-revisions"), json=dict(id=str(uuid4()),
            item_id=str(item.id), predecessor_id=str(factor.id), base_quantity="0", evidence=evidence),
            headers=headers(b, "editor", "zero-factor")), 422)
        # A foreign source reference is rejected atomically by existing scope guards.
        foreign_doc = b["service"].document(b["stranger"], b["other"], "foreign", "foreign.txt", "text/plain", b"other")
        checked(client.post(catalog_url(b, "/item-revisions"),
            json=dict(proposal, id=str(uuid4()), evidence=dict(document_id=str(foreign_doc), locator="1")),
            headers=headers(b, "editor", "foreign-evidence")), 404)


@pytest.mark.parametrize("kind", ["item", "pack"])
def test_http_catalog_source_tamper_rolls_back_approval_and_allows_rejection(catalog_seed, kind):
    b, item, factor, evidence = catalog_seed
    proposal = (label_proposal(item.id, evidence) if kind == "item" else
                dict(id=str(uuid4()), item_id=str(item.id), predecessor_id=str(factor.id),
                     base_quantity="10", evidence=evidence))
    route = catalog_url(b, f"/{kind}-revisions")
    with TestClient(create_app(b["db"], b["blob_root"])) as client:
        post(client, b, route, proposal, "proposal", "editor")
        metadata, _ = b["service"].read_document(b["owner"], b["business"], UUID(evidence["document_id"]))
        (b["blob_root"]/str(b["business"])/metadata["sha256"]).write_bytes(b"changed source")
        # History reads disclose recorded provenance and never imply a fresh hash check.
        get(client, b, catalog_url(b, f"/items/{item.id}"))
        checked(client.post(f"{route}/{proposal['id']}/decision", json=decision(),
                            headers=headers(b, key="tampered-approval")), 409)
        with b["db"].transaction(b["viewer"], b["business"]) as c:
            assert not c.execute("SELECT 1 FROM herman.idempotency_keys WHERE key='tampered-approval'").fetchone()
        detail = get(client, b, f"{route}/{proposal['id']}")
        assert detail["approved"] is None
        post(client, b, f"{route}/{proposal['id']}/decision", decision(False), "reject")
        assert get(client, b, f"{route}/{proposal['id']}")["approved"] is False


@pytest.mark.parametrize("kind", ["item", "pack"])
def test_http_concurrent_competing_decisions_publish_one_successor(catalog_seed, kind):
    b, item, factor, evidence = catalog_seed
    proposals = [(label_proposal(item.id, evidence) if kind == "item" else
                  dict(id=str(uuid4()), item_id=str(item.id), predecessor_id=str(factor.id),
                       base_quantity="10", evidence=evidence)) for _ in range(2)]
    app = create_app(b["db"], b["blob_root"])
    activation = datetime.now(timezone.utc)+timedelta(days=1)
    with TestClient(app) as client:
        for index, value in enumerate(proposals):
            post(client, b, catalog_url(b, f"/{kind}-revisions"), value, f"proposal:{index}", "editor")
        barrier = Barrier(2)

        def approve(index):
            barrier.wait(10)
            response = client.post(catalog_url(b, f"/{kind}-revisions/{proposals[index]['id']}/decision"),
                                   json=decision(when=activation), headers=headers(b, key=f"approval:{index}"))
            checked(response, response.status_code)
            return response.status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            assert sorted(pool.map(approve, (0, 1))) == [201, 409]
        selected = get(client, b, catalog_url(b, f"/items/{item.id}"), effective_at=activation.isoformat())
        selected_id = selected["label"]["definition_id"] if kind == "item" else selected["pack_definition"]["id"]
        assert selected_id in {value["id"] for value in proposals}
        history = get(client, b, catalog_url(b, f"/items/{item.id}/{'labels' if kind == 'item' else 'packs'}"))
        assert sum(row["approved"] is True for row in history) == 1


def test_http_binding_roles_tamper_and_resolution_source_rollback(unresolved_seed):
    b, opening, factor, documents, _ = unresolved_seed
    with TestClient(create_app(b["db"], b["blob_root"])) as client:
        check = get(client, b, bindings_url(b), record=str(opening.id))["checks"][0]["id"]
        review_url = bindings_url(b, f"/{check}/reviews")
        review = dict(id=str(uuid4()), approved=True, definition_id=str(factor.id), reason_fa="بررسی تاریخی",
                      evidence=dict(document_id=str(documents["resolution"]), locator="line:1"))
        for url in (bindings_url(b, f"/{check}"), review_url):
            checked(client.get(url), 401)
            checked(client.get(url, headers=headers(b, "stranger")), 403)
            foreign = url.replace(str(b["business"]), str(b["other"]))
            checked(client.get(foreign, headers=headers(b, "stranger")), 404)
        checked(client.post(bindings_url(b), json=dict(id=str(uuid4()), record_id=str(opening.id)),
                            headers=headers(b, "viewer", "viewer-capture")), 403)
        checked(client.post(review_url, json=review, headers=headers(b, "editor", "editor-review")), 403)
        checked(client.post(review_url, json=dict(review, reason_fa="  "), headers=headers(b, key="blank")), 422)
        metadata, _ = b["service"].read_document(b["owner"], b["business"], documents["resolution"])
        (b["blob_root"]/str(b["business"])/metadata["sha256"]).write_bytes(b"changed resolution")
        checked(client.post(review_url, json=review, headers=headers(b, key="tampered-resolution")), 409)
        assert get(client, b, review_url)["reviews"] == []
        with b["db"].transaction(b["viewer"], b["business"]) as c:
            assert not c.execute("SELECT 1 FROM herman.idempotency_keys WHERE key='tampered-resolution'").fetchone()
        rejected = dict(review, id=str(uuid4()), approved=False, definition_id=None)
        post(client, b, review_url, rejected, "reject")
        assert get(client, b, bindings_url(b, f"/{check}"))["effective_state"] == "unresolved"


def test_http_concurrent_manual_recipe_captures_reuse_one_source_context(unresolved_seed, monkeypatch):
    b, opening, _, documents, _ = unresolved_seed
    service = b["service"]
    product = Item(id=uuid4(), business_id=b["business"], sku="MEAL", name_fa="غذا", base_unit="each",
                   consumption_mode="recipe")
    service.catalog(b["owner"], b["business"], "product", product)
    evidence = dict(document_id=documents["record"], locator="recipe:1")
    recipe = Recipe(id=uuid4(), business_id=b["business"], product_id=product.id,
                    valid_from=opening.occurred_at-timedelta(days=1), output_quantity="1", output_unit="each",
                    lines=[dict(item_id=opening.item_id, quantity="1", unit="pack")], evidence=evidence)
    service.propose(b["editor"], b["business"], "recipe", recipe)
    fulfillment = Fulfillment(id=uuid4(), business_id=b["business"], warehouse_id=opening.warehouse_id,
        product_id=product.id, occurred_at=opening.occurred_at, quantity="1", unit="each", evidence=evidence)
    service.propose(b["editor"], b["business"], "fulfillment", fulfillment)
    barrier, attempts = Barrier(2), local()
    from src.backend import pack_bindings

    original_insert = pack_bindings._insert_check

    def simultaneous(c, business, value):
        if not getattr(attempts, "entered", False):
            attempts.entered = True
            barrier.wait(10)
        return original_insert(c, business, value)

    monkeypatch.setattr(pack_bindings, "_insert_check", simultaneous)
    with TestClient(create_app(b["db"], b["blob_root"])) as client:
        def capture(index):
            value = dict(id=str(uuid4()), record_id=str(recipe.id), ingredient_id=str(opening.item_id),
                         fulfillment_id=str(fulfillment.id), recipe_path=[str(recipe.id)])
            return post(client, b, bindings_url(b), value, f"capture:{index}", "editor")["id"]

        with ThreadPoolExecutor(max_workers=2) as pool:
            identities = list(pool.map(capture, (0, 1)))
        assert len(set(identities)) == 1
        page = get(client, b, bindings_url(b), record=str(recipe.id))
        assert len(page["checks"]) == 1 and page["checks"][0]["id"] == identities[0]
        assert page["checks"][0]["recipe_path"] == [str(recipe.id)]
