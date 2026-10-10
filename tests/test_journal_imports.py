"""Extracted tables become reviewable journal proposals with immutable row lineage."""

# ruff: noqa: E402
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal, localcontext
from io import BytesIO
from uuid import UUID, uuid4

import pytest

psycopg = pytest.importorskip("psycopg")
pytest.importorskip("fastapi")
from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb
from pydantic import TypeAdapter
from test_backend import backend as backend_fixture
from test_backend import database as database_fixture

from src.backend.api import create_app
from src.backend.database import AccessDenied
from src.backend.inventory import Quantity
from src.backend.jobs import ExtractionInput, ExtractionQueue
from src.backend.journal_imports import JournalImport, JournalImporter, proposals
from src.backend.journal_reports import JournalReports, MappingInput, ReportInput, ReviewInput
from src.backend.journals import AccountInput, JournalDecision, Journals
from src.backend.journals import Amount as JournalAmount
from src.backend.portfolio import Amount as PortfolioAmount
from src.backend.service import Conflict, NotFound, insert
from src.backend.worker import process_one
from src.ingestion.normalizer import to_jalali

backend = backend_fixture
database = database_fixture
DAY = date(2026, 10, 9)
HEADER = "voucher,account,debit,credit,day,description\n"
CSV = HEADER + f"A,1000,۱۰۰,,{to_jalali(DAY)},فروش روز\nA,4000,,۱۰۰,{to_jalali(DAY)},فروش روز\n"


@pytest.mark.parametrize("amount_type", [JournalAmount, PortfolioAmount, Quantity])
def test_fraction_limits_do_not_depend_on_decimal_context(amount_type):
    adapter = TypeAdapter(amount_type)
    with localcontext() as ctx:
        ctx.prec = 6
        with pytest.raises(ValueError):
            adapter.validate_python("1.000000000000000000000000000000000001")
        assert adapter.validate_python("1.230000000000000000") == Decimal("1.23")
        whole_digits = 18 if amount_type == Quantity else 22
        boundary = "9" * whole_digits + ".999999"
        assert adapter.validate_python(boundary) == Decimal(boundary)


def request(extraction=None, **changes):
    return JournalImport(
        **(
            dict(
                extraction_id=extraction or uuid4(),
                sheet="CSV",
                rows=[2, 3],
                voucher_column="voucher",
                account_column="account",
                debit_column="debit",
                credit_column="credit",
                date_column="day",
                description_column="description",
                date_kind="jalali",
                amount_unit="IRT",
            )
            | changes
        )
    )


def accounts(b):
    ledger = Journals(b["service"])
    for code, kind in [("1000", "asset"), ("1100", "asset"), ("3000", "equity"), ("4000", "revenue")]:
        ledger.account(
            b["owner"], b["business"], code, AccountInput(code=code, name_fa="حساب نمونه", kind=kind)
        )
    return ledger


def extract(b, content=None, key="csv", name="journal.csv"):
    content = CSV.encode() if content is None else content
    doc = b["service"].document(b["owner"], b["business"], key, name, "application/octet-stream", content)
    queue = ExtractionQueue(b["service"])
    job = queue.enqueue(b["owner"], b["business"], key + "-job", ExtractionInput(document_id=doc))
    process_one(queue, b["tokens"][0], b["business"])
    row = queue.read(b["owner"], b["business"], job)
    assert row["status"] == "succeeded", row
    return doc, row["extraction"]["id"]


def pure_payload():
    return dict(
        structured_data=dict(
            rows=[
                dict(
                    sheet="CSV",
                    row=i,
                    values=dict(
                        voucher="A",
                        account=code,
                        debit=debit,
                        credit=credit,
                        day=to_jalali(DAY),
                        description="فروش روز",
                    ),
                )
                for i, code, debit, credit in [(2, "1000", "100", ""), (3, "4000", "", "100")]
            ]
        )
    )


@pytest.mark.parametrize(
    "invalid",
    [
        "unbalanced",
        "both_sides",
        "negative",
        "fraction",
        "date",
        "description",
        "repeated_account",
        "blank_key",
    ],
)
def test_mapping_rejects_ambiguous_or_inexact_rows(invalid):
    payload = pure_payload()
    rows = payload["structured_data"]["rows"]
    if invalid == "unbalanced":
        rows[0]["values"]["debit"] = "99"
    elif invalid == "both_sides":
        rows[0]["values"]["credit"] = "1"
    elif invalid == "negative":
        rows[0]["values"]["debit"] = "-100"
    elif invalid == "fraction":
        rows[0]["values"]["debit"] = rows[1]["values"]["credit"] = "1.000000000000000000000000000000000001"
    elif invalid == "date":
        rows[1]["values"]["day"] = "1405/07/18"
    elif invalid == "description":
        rows[1]["values"]["description"] = "شرح متفاوت"
    elif invalid == "repeated_account":
        rows[1]["values"]["account"] = "1000"
    else:
        rows[1]["values"]["voucher"] = ""
    with pytest.raises(ValueError):
        proposals(payload, request(), uuid4())


def test_mapping_requires_units_dates_distinct_columns_and_whole_voucher():
    for change in [
        dict(amount_unit=None),
        dict(date_kind=None),
        dict(rows=[2, 2]),
        dict(rows=[True, 3]),
        dict(credit_column="debit"),
    ]:
        with pytest.raises(ValueError):
            request(**change)
    payload = pure_payload()
    extra = [
        dict(
            sheet="CSV",
            row=i,
            values=dict(
                voucher="A",
                account=code,
                debit=debit,
                credit=credit,
                day=to_jalali(DAY),
                description="فروش روز",
            ),
        )
        for i, code, debit, credit in [(4, "1100", "50", ""), (5, "3000", "", "50")]
    ]
    payload["structured_data"]["rows"] += extra
    with pytest.raises(ValueError):
        proposals(payload, request(), uuid4())
    assert len(proposals(payload, request(rows=[2, 3, 4, 5]), uuid4())[0][1].lines) == 4


def test_preview_import_review_and_report_keep_full_row_lineage(backend):
    b = backend
    ledger = accounts(b)
    doc, extraction = extract(b)
    value = request(extraction)
    importer = JournalImporter(b["service"])
    base = f"/businesses/{b['business']}/journal/imports"
    headers = {"Authorization": "Bearer " + b["tokens"][2], "Idempotency-Key": "import"}
    with TestClient(create_app(b["db"], b["blob_root"])) as client:
        assert client.post(base + "/preview", json=value.model_dump(mode="json")).status_code == 401
        preview = client.post(base + "/preview", headers=headers, json=value.model_dump(mode="json"))
        assert preview.status_code == 200, preview.text
        assert preview.headers["cache-control"] == "no-store" and not preview.json()["persisted"]
        assert preview.json()["entries"][0]["proposal"]["lines"][0]["amount"] == "1000"
        assert ledger.page(b["viewer"], b["business"]) == []
        response = client.post(base, headers=headers, json=value.model_dump(mode="json"))
        assert response.status_code == 201, response.text
        identity = UUID(response.json()["id"])
    assert importer.create(b["editor"], b["business"], "import", value) == identity
    batch = importer.read(b["viewer"], b["business"], identity)
    assert len(batch["entries"]) == 1 and batch["entries"][0]["approved"] is None
    entry = batch["entries"][0]["id"]
    trace = ledger.read(b["viewer"], b["business"], entry)
    assert trace["lines"][0]["amount"] == "1000"
    assert trace["origin"]["rows"][0]["source_values"]["debit"] == "100"
    assert trace["origin"]["batches"][0]["mapping"]["amount_unit"] == "IRT"
    assert trace["origin"]["batches"][0]["extraction_id"] == extraction
    ledger.decide(
        b["owner"],
        b["business"],
        "review-entry",
        entry,
        JournalDecision(approved=True, reviewed_values=True, reason_fa="بررسی منبع و تبدیل تومان"),
    )
    reports = JournalReports(b["service"])
    mapping = reports.mapping(
        b["owner"],
        b["business"],
        "mapping",
        MappingInput(
            title_fa="نگاشت گزارش",
            accounts={"1000": "cash", "1100": "current_asset", "3000": "equity", "4000": "revenue"},
            evidence=dict(document_id=doc, locator="سرستون"),
        ),
    )
    reports.review_mapping(
        b["owner"],
        b["business"],
        "review-map",
        mapping,
        ReviewInput(approved=True, reviewed_values=True, reason_fa="نگاشت بررسی شد"),
    )
    report = reports.create(
        b["owner"],
        b["business"],
        "report",
        ReportInput(mapping_id=mapping, period_start=date(2026, 10, 1), period_end=DAY),
    )
    saved = reports.read(b["viewer"], b["business"], report)
    assert saved["manifest"]["import_provenance"]["batches"][0]["extraction_id"] == str(extraction)
    assert saved["manifest"]["import_provenance"]["rows"][1]["source_row"] == 3
    assert saved["result"]["financial"]["constants"]["revenue"] == "1000"


def test_whole_batch_rolls_back_when_one_voucher_is_invalid(backend):
    b = backend
    accounts(b)
    content = CSV + f"B,1000,5,,{to_jalali(DAY)},ثبت دوم\nB,4000,,6,{to_jalali(DAY)},ثبت دوم\n"
    _, extraction = extract(b, content.encode())
    importer = JournalImporter(b["service"])
    with pytest.raises(ValueError):
        importer.create(b["owner"], b["business"], "invalid", request(extraction, rows=[2, 3, 4, 5]))
    with b["db"].transaction(b["owner"], b["business"]) as c:
        for table in ("journal_entries", "journal_lines", "journal_import_batches", "journal_import_sources"):
            assert c.execute(f"SELECT count(*) AS n FROM herman.{table}").fetchone()["n"] == 0
        assert not c.execute("SELECT 1 FROM herman.idempotency_keys WHERE key='invalid'").fetchone()


def test_concurrent_retries_and_reused_rows_across_extractions_and_identical_files(backend):
    b = backend
    accounts(b)
    content = (CSV + f"B,1000,5,,{to_jalali(DAY)},ثبت دوم\nB,4000,,5,{to_jalali(DAY)},ثبت دوم\n").encode()
    doc, extraction = extract(b, content)
    importer, value = JournalImporter(b["service"]), request(extraction, rows=[2, 3, 4, 5])
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(
            pool.map(lambda _: importer.create(b["owner"], b["business"], "same", value), range(3))
        )
    assert len(set(results)) == 1
    saved = importer.read(b["owner"], b["business"], results[0])
    assert len(saved["entries"]) == 2 and len(saved["origin"]["rows"]) == 4
    with pytest.raises(Conflict):
        importer.create(b["owner"], b["business"], "different", value)
    queue = ExtractionQueue(b["service"])
    job = queue.enqueue(b["owner"], b["business"], "again", ExtractionInput(document_id=doc))
    process_one(queue, b["tokens"][0], b["business"])
    again = queue.read(b["owner"], b["business"], job)["extraction"]["id"]
    with pytest.raises(Conflict):
        importer.create(b["owner"], b["business"], "new-version", request(again))
    _, renamed = extract(b, content, key="renamed", name="renamed.csv")
    with pytest.raises(Conflict):
        importer.create(b["owner"], b["business"], "renamed-import", request(renamed))


def test_xlsx_gregorian_import_uses_explicit_rial_amounts(backend):
    import openpyxl

    b = backend
    ledger = accounts(b)
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.title = "دفتر"
    sheet.append(HEADER.strip().split(","))
    sheet.append(["A", "1000", "۱۲.۱۲۳۴۵۶", "", DAY.isoformat(), "فروش روز"])
    sheet.append(["A", "4000", "", "۱۲.۱۲۳۴۵۶", DAY.isoformat(), "فروش روز"])
    data = BytesIO()
    book.save(data)
    book.close()
    _, extraction = extract(b, data.getvalue(), key="xlsx", name="journal.xlsx")
    importer = JournalImporter(b["service"])
    identity = importer.create(
        b["owner"],
        b["business"],
        "xlsx-import",
        request(extraction, sheet="دفتر", date_kind="gregorian", amount_unit="IRR"),
    )
    entry = importer.read(b["owner"], b["business"], identity)["entries"][0]["id"]
    assert ledger.read(b["owner"], b["business"], entry)["lines"][0]["amount"] == "12.123456"


def test_tenant_role_and_evidence_checks_before_import(backend):
    b = backend
    accounts(b)
    doc, extraction = extract(b)
    importer, value = JournalImporter(b["service"]), request(extraction)
    with pytest.raises(AccessDenied):
        importer.create(b["viewer"], b["business"], "viewer", value)
    assert importer.preview(b["viewer"], b["business"], value)["persisted"] is False
    with pytest.raises(NotFound):
        importer.create(b["stranger"], b["other"], "cross", value)
    metadata, _ = b["service"].read_document(b["owner"], b["business"], doc)
    (b["blob_root"] / str(b["business"]) / metadata["sha256"]).write_bytes(b"changed")
    with pytest.raises(Conflict):
        importer.create(b["owner"], b["business"], "changed", value)
    assert importer.page(b["owner"], b["business"]) == []


def test_database_rejects_forged_or_late_sources_and_empty_batches(backend):
    b = backend
    accounts(b)
    _, extraction = extract(b)
    importer, value = JournalImporter(b["service"]), request(extraction)
    identity = importer.create(b["owner"], b["business"], "import", value)
    saved = importer.read(b["owner"], b["business"], identity)
    batch = saved["batch"]
    with b["db"].transaction(b["stranger"], b["other"]) as c:
        assert c.execute("SELECT * FROM herman.journal_import_batches").fetchall() == []
        assert c.execute("SELECT * FROM herman.journal_import_sources").fetchall() == []
    with pytest.raises(psycopg.errors.InsufficientPrivilege), psycopg.connect(b["admin"]) as c:
        c.execute(
            "UPDATE herman.journal_import_sources SET source_values='{}' WHERE business_id=%s",
            (b["business"],),
        )
    for late in (False, True):
        with (
            pytest.raises(psycopg.errors.CheckViolation),
            b["db"].transaction(b["owner"], b["business"], write=True) as c,
        ):
            new_batch = uuid4()
            insert(
                c,
                "journal_import_batches",
                dict(
                    business_id=b["business"],
                    id=new_batch,
                    extraction_id=extraction,
                    document_id=batch["document_id"],
                    source_sha256=batch["source_sha256"],
                    mapping=Jsonb(value.model_dump(mode="json")),
                    created_by=b["owner"],
                ),
            )
            if late:
                row = saved["origin"]["rows"][0]
                insert(
                    c,
                    "journal_import_sources",
                    dict(
                        business_id=b["business"],
                        batch_id=new_batch,
                        entry_id=row["entry_id"],
                        line_number=row["line_number"],
                        sheet="CSV",
                        source_row=2,
                        source_sha256=batch["source_sha256"],
                        source_values=Jsonb({"forged": "values"}),
                        created_by=b["owner"],
                    ),
                )


@pytest.mark.parametrize("invalid", ["forged", "missing", "extra_after_check"])
def test_database_seals_each_imported_line_to_its_extracted_row(backend, invalid):
    b = backend
    ledger = accounts(b)
    _, extraction_id = extract(b)
    value = request(extraction_id)
    importer = JournalImporter(b["service"])
    message = "inconsistent or late" if invalid == "forged" else "provenance for every line"
    with (
        pytest.raises(psycopg.errors.CheckViolation, match=message),
        b["db"].transaction(b["owner"], b["business"], write=True) as c,
    ):
        extraction, mapped = importer._prepare(c, b["business"], value)
        batch = uuid4()
        insert(
            c,
            "journal_import_batches",
            dict(
                business_id=b["business"],
                id=batch,
                extraction_id=extraction_id,
                document_id=extraction["document_id"],
                source_sha256=extraction["source_sha256"],
                mapping=Jsonb(value.model_dump(mode="json")),
                created_by=b["owner"],
            ),
        )
        _, proposal, rows = mapped[0]
        entry = ledger._store(c, b["owner"], b["business"], proposal)
        for number, row in enumerate(rows, 1):
            if invalid == "missing" and number == 2:
                break
            insert(
                c,
                "journal_import_sources",
                dict(
                    business_id=b["business"],
                    batch_id=batch,
                    entry_id=entry,
                    line_number=number,
                    sheet=value.sheet,
                    source_row=row["row"],
                    source_sha256=extraction["source_sha256"],
                    source_values=Jsonb({"forged": "values"} if invalid == "forged" else row["values"]),
                    created_by=b["owner"],
                ),
            )
        if invalid == "extra_after_check":
            c.execute("SET CONSTRAINTS ALL IMMEDIATE")
            c.execute("SET CONSTRAINTS ALL DEFERRED")
            for number, account, side in [(3, "1100", "debit"), (4, "3000", "credit")]:
                insert(
                    c,
                    "journal_lines",
                    dict(
                        business_id=b["business"],
                        entry_id=entry,
                        line_number=number,
                        account_code=account,
                        side=side,
                        amount=Decimal(1),
                        document_id=extraction["document_id"],
                        locator="CSV:row:2",
                        created_by=b["owner"],
                    ),
                )
        c.execute("SET CONSTRAINTS herman.import_entry_complete IMMEDIATE")
