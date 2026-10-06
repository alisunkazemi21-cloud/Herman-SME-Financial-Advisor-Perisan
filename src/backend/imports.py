"""Explicit, atomic mapping of extracted tabular rows to unapproved business records."""
from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb
from pydantic import AwareDatetime, Field, model_validator

from src.backend.duplicates import record_matches
from src.backend.inventory import Count, Fulfillment, Movement, Unit
from src.backend.service import Conflict, NotFound, Service, insert
from src.models import Model

Column = Annotated[str, Field(min_length=1, max_length=200)]


class TabularImport(Model):
    extraction_id: UUID
    sheet: str = Field(min_length=1, max_length=200)
    rows: tuple[Annotated[int, Field(ge=2, strict=True)], ...] = Field(min_length=1, max_length=100)
    record_kind: Literal["count", "movement", "fulfillment"]
    warehouse_id: UUID
    sku_column: Column
    quantity_column: Column
    unit_column: Column | None = None
    unit: Unit | None = None
    time_column: Column | None = None
    occurred_at: AwareDatetime | None = None
    movement_kind: Literal["purchase", "transfer_in", "transfer_out", "supplier_return", "customer_return",
                           "waste", "other_use"] | None = None
    fulfillment_kind: Literal["sale", "complimentary", "staff", "production"] | None = None

    @model_validator(mode="after")
    def consistent(self):
        if len(set(self.rows)) != len(self.rows):
            raise ValueError("شماره ردیف تکراری است")
        if (self.unit is None) == (self.unit_column is None):
            raise ValueError("واحد ثابت یا ستون واحد را دقیقاً یکی انتخاب کنید")
        if (self.occurred_at is None) == (self.time_column is None):
            raise ValueError("زمان ثابت یا ستون زمان را دقیقاً یکی انتخاب کنید")
        if (self.record_kind == "movement") != (self.movement_kind is not None):
            raise ValueError("نوع گردش باید صریح و فقط برای رکورد گردش باشد")
        if (self.record_kind == "fulfillment") != (self.fulfillment_kind is not None):
            raise ValueError("نوع تحقق باید صریح و فقط برای رکورد تحقق باشد")
        return self


class TabularImporter:
    def __init__(self, service: Service):
        self.service = service

    def create(self, actor: UUID, business: UUID, key: str, value: TabularImport) -> UUID:
        def import_rows(c):
            extraction = c.execute("SELECT e.*,j.document_id FROM herman.extractions e "
                "JOIN herman.extraction_jobs j ON (j.business_id,j.id)=(e.business_id,e.job_id) "
                "WHERE e.business_id=%s AND e.id=%s AND j.status='succeeded'",
                (business, value.extraction_id)).fetchone()
            if extraction is None:
                raise NotFound("استخراج موفق در این بیزینس موجود نیست")
            payload = extraction["payload"]
            if payload.get("extraction_method") not in ("csv", "excel"):
                raise ValueError("این مسیر فقط استخراج جدولی CSV/XLSX را می‌پذیرد")
            # Revalidate archived source bytes at import time; successful extraction alone is insufficient.
            metadata, _ = self.service.read_document(actor, business, extraction["document_id"])
            if metadata["sha256"] != extraction["source_sha256"]:
                raise Conflict("هش نسخه استخراج با سند همخوانی ندارد")
            if not c.execute("SELECT 1 FROM herman.warehouses WHERE business_id=%s AND id=%s",
                             (business, value.warehouse_id)).fetchone():
                raise NotFound("انبار در این بیزینس موجود نیست")
            extracted_rows = payload.get("structured_data", {}).get("rows", [])
            selected = [row for row in extracted_rows if row.get("sheet") == value.sheet and row.get("row") in value.rows]
            if len(selected) != len(value.rows) or len({row["row"] for row in selected}) != len(value.rows):
                raise ValueError("ردیف انتخاب‌شده موجود یا یکتا نیست")
            batch = uuid4()
            insert(c, "import_batches", dict(business_id=business, id=batch, extraction_id=value.extraction_id,
                created_by=actor, mapping=Jsonb(value.model_dump(mode="json"))))
            for row in sorted(selected, key=lambda row: row["row"]):
                columns = row["values"]

                def column(name):
                    if name not in columns or not isinstance(columns[name], str) or not columns[name].strip():
                        raise ValueError("ستون انتخاب‌شده وجود ندارد یا مقدار آن خالی است")
                    return columns[name].strip()

                item = c.execute("SELECT id FROM herman.items WHERE business_id=%s AND sku=%s",
                                 (business, column(value.sku_column))).fetchone()
                if item is None:
                    raise ValueError("SKU ردیف در کاتالوگ این بیزینس تعریف نشده است")
                if c.execute("SELECT 1 FROM herman.record_sources WHERE business_id=%s AND document_id=%s "
                    "AND sheet=%s AND source_row=%s AND record_kind=%s",
                    (business, extraction["document_id"], value.sheet, row["row"], value.record_kind)).fetchone():
                    raise Conflict("این ردیف سند قبلاً به همین نوع رکورد تبدیل شده است")
                fields = dict(id=uuid4(), business_id=business, warehouse_id=value.warehouse_id,
                    occurred_at=value.occurred_at if value.time_column is None else column(value.time_column),
                    quantity=column(value.quantity_column), unit=value.unit if value.unit_column is None else column(value.unit_column),
                    evidence=dict(document_id=extraction["document_id"], locator=f"{value.sheet}:row:{row['row']}"))
                if value.record_kind == "fulfillment":
                    record = Fulfillment(**fields, product_id=item["id"], kind=value.fulfillment_kind)
                elif value.record_kind == "movement":
                    record = Movement(**fields, item_id=item["id"], kind=value.movement_kind)
                else:
                    record = Count(**fields, item_id=item["id"])
                self.service._insert_proposal(c, actor, business, record)
                insert(c, "record_sources", dict(business_id=business, id=record.id, batch_id=batch,
                    extraction_id=value.extraction_id, document_id=extraction["document_id"], sheet=value.sheet,
                    source_row=row["row"], record_kind=value.record_kind, source_values=Jsonb(columns), created_by=actor))
                self.service._audit(c, actor, business, value.record_kind + ".proposed", record.id)
            return batch

        return self.service._write(actor, business, key, "import.proposed", value.model_dump(mode="json"), import_rows)

    def read(self, actor: UUID, business: UUID, identity: UUID) -> dict:
        with self.service.database.transaction(actor, business) as c:
            batch = c.execute("SELECT * FROM herman.import_batches WHERE business_id=%s AND id=%s",
                              (business, identity)).fetchone()
            if batch is None:
                raise NotFound("بسته ورود موجود نیست")
            batch["records"] = c.execute("SELECT id,sheet,source_row,record_kind,source_values FROM herman.record_sources "
                "WHERE business_id=%s AND batch_id=%s ORDER BY source_row", (business, identity)).fetchall()
            for record in batch["records"]:
                record["duplicate_candidates"] = record_matches(c, business, record["id"])
            return batch
