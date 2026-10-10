import hashlib
import json
from datetime import date
from pathlib import Path
from threading import BoundedSemaphore
from typing import Annotated, Literal
from uuid import UUID

import psycopg
from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import AwareDatetime, Field, ValidationError

from src.ai_agent.agent import FinancialAgent
from src.backend.advisor import (
    BusinessAdvisor,
    BusinessContextInput,
    KnowledgeDecision,
    KnowledgeProposal,
    QuickContextInput,
    quick_context,
)
from src.backend.cases import BusinessCases, CaseInput, TurnInput
from src.backend.database import AccessDenied, Database
from src.backend.imports import TabularImport, TabularImporter
from src.backend.inventory import (
    Count,
    Fulfillment,
    InventoryRequest,
    Item,
    Movement,
    Recipe,
    UnitConversion,
    reconcile_inventory,
)
from src.backend.jobs import ExtractionInput, ExtractionQueue
from src.backend.journal_reports import JournalReports, MappingInput, ReportInput, ReportReview, ReviewInput
from src.backend.journals import AccountInput, JournalDates, JournalDecision, JournalInput, Journals
from src.backend.portfolio import FinancialPortfolio, FinancialSnapshot
from src.backend.service import AnalysisInput, Conflict, NotFound, Service, Warehouse
from src.models import Model


class BusinessInput(Model):
    name: str = Field(min_length=1, max_length=200)
    industry: str = Field(min_length=1, max_length=100)


class DecisionInput(Model):
    approved: bool
    reason_fa: str = Field(min_length=1, max_length=2000)
    duplicate_resolution: Literal["same_event", "distinct_event"] | None = None


def create_app(database: Database, blob_root: Path, draft_agent: FinancialAgent | None = None) -> FastAPI:
    app = FastAPI(title="Herman SME backend", version="0.2.0")
    service = Service(database, blob_root)
    advisor = BusinessAdvisor(service)
    financial = FinancialPortfolio(service)
    cases = BusinessCases(service, advisor)
    journals = Journals(service)
    journal_reports = JournalReports(service)
    queue = ExtractionQueue(service)
    importer = TabularImporter(service)
    bearer = HTTPBearer(auto_error=False)
    inference_slot = BoundedSemaphore(1)

    def actor(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]) -> UUID:
        if credentials is None:
            raise HTTPException(401, "اعتبار دسترسی لازم است")
        try:
            return database.authenticate(credentials.credentials)
        except AccessDenied:
            raise HTTPException(401, "اعتبار دسترسی نامعتبر است") from None

    Actor = Annotated[UUID, Depends(actor)]
    Key = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=200)]

    @app.exception_handler(AccessDenied)
    async def denied(request, exc):
        return JSONResponse(status_code=403, content={"detail": "دسترسی مجاز نیست"})

    @app.exception_handler(NotFound)
    async def missing(request, exc):
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(Conflict)
    async def conflict(request, exc):
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(ValueError)
    async def invalid(request, exc):
        # Do not echo submitted financial records or credentials in validation errors.
        detail = "ورودی با قرارداد داده سازگار نیست" if isinstance(exc, ValidationError) else str(exc)
        return JSONResponse(status_code=422, content={"detail": detail})

    @app.exception_handler(psycopg.IntegrityError)
    async def integrity(request, exc):
        return JSONResponse(status_code=409, content={"detail": "رکورد تکراری یا ارجاع نامعتبر در همین بیزینس"})

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.post("/businesses/{business}/journal/mappings", status_code=201)
    def propose_mapping(business: UUID, value: MappingInput, user: Actor, key: Key, response: Response):
        response.headers["Cache-Control"] = "no-store"
        return {"id": journal_reports.mapping(user, business, key, value)}

    @app.get("/businesses/{business}/journal/mappings")
    def journal_mappings(business: UUID, user: Actor, response: Response, after: UUID | None = None, limit: int = 20):
        response.headers["Cache-Control"] = "no-store"
        return journal_reports.page(user, business, "mappings", after, limit)

    @app.get("/businesses/{business}/journal/mappings/{identity}")
    def journal_mapping(business: UUID, identity: UUID, user: Actor, response: Response):
        response.headers["Cache-Control"] = "no-store"
        return journal_reports.read_mapping(user, business, identity)

    @app.post("/businesses/{business}/journal/mappings/{identity}/decision", status_code=201)
    def decide_mapping(business: UUID, identity: UUID, value: ReviewInput, user: Actor, key: Key, response: Response):
        response.headers["Cache-Control"] = "no-store"
        return {"id": journal_reports.review_mapping(user, business, key, identity, value)}

    @app.post("/businesses/{business}/journal/reports", status_code=201)
    def create_journal_report(business: UUID, value: ReportInput, user: Actor, key: Key, response: Response):
        response.headers["Cache-Control"] = "no-store"
        return {"id": journal_reports.create(user, business, key, value)}

    @app.get("/businesses/{business}/journal/reports")
    def journal_report_list(business: UUID, user: Actor, response: Response, after: UUID | None = None, limit: int = 20):
        response.headers["Cache-Control"] = "no-store"
        return journal_reports.page(user, business, "reports", after, limit)

    @app.get("/businesses/{business}/journal/reports/{identity}")
    def journal_report(business: UUID, identity: UUID, user: Actor, response: Response):
        response.headers["Cache-Control"] = "no-store"
        return journal_reports.read(user, business, identity)

    @app.post("/businesses/{business}/journal/reports/{identity}/decision", status_code=201)
    def decide_journal_report(business: UUID, identity: UUID, value: ReportReview, user: Actor, key: Key, response: Response):
        response.headers["Cache-Control"] = "no-store"
        return {"id": journal_reports.review(user, business, key, identity, value)}

    @app.post("/businesses/{business}/journal/accounts", status_code=201)
    def create_account(business: UUID, value: AccountInput, user: Actor, key: Key, response: Response):
        response.headers["Cache-Control"] = "no-store"
        return {"id": journals.account(user, business, key, value)}

    @app.get("/businesses/{business}/journal/accounts")
    def journal_accounts(business: UUID, user: Actor, response: Response, after: str = "", limit: int = 50):
        response.headers["Cache-Control"] = "no-store"
        return journals.accounts(user, business, after, limit)

    @app.post("/businesses/{business}/journal/entries", status_code=201)
    def propose_journal(business: UUID, value: JournalInput, user: Actor, key: Key, response: Response):
        response.headers["Cache-Control"] = "no-store"
        return {"id": journals.propose(user, business, key, value)}

    @app.get("/businesses/{business}/journal/entries")
    def journal_list(business: UUID, user: Actor, response: Response, after: UUID | None = None, limit: int = 50):
        response.headers["Cache-Control"] = "no-store"
        return journals.page(user, business, after, limit)

    @app.get("/businesses/{business}/journal/entries/{identity}")
    def journal_detail(business: UUID, identity: UUID, user: Actor, response: Response):
        response.headers["Cache-Control"] = "no-store"
        return journals.read(user, business, identity)

    @app.post("/businesses/{business}/journal/entries/{identity}/decision", status_code=201)
    def journal_decision(business: UUID, identity: UUID, value: JournalDecision, user: Actor, key: Key, response: Response):
        response.headers["Cache-Control"] = "no-store"
        return {"id": journals.decide(user, business, key, identity, value)}

    @app.post("/businesses/{business}/journal/entries/{identity}/reversals", status_code=201)
    def journal_reversal(business: UUID, identity: UUID, value: JournalDates, user: Actor, key: Key, response: Response):
        response.headers["Cache-Control"] = "no-store"
        return {"id": journals.reverse(user, business, key, identity, value)}

    @app.get("/businesses/{business}/journal/trial-balance")
    def trial_balance(business: UUID, start: date, end: date, user: Actor, response: Response):
        response.headers["Cache-Control"] = "no-store"
        return journals.trial_balance(user, business, start, end)

    @app.post("/businesses/{business}/tabular-imports", status_code=201)
    def import_rows(business: UUID, value: TabularImport, user: Actor, key: Key):
        identity = importer.create(user, business, key, value)
        return importer.read(user, business, identity)

    @app.get("/businesses/{business}/tabular-imports/{identity}")
    def import_batch(business: UUID, identity: UUID, user: Actor):
        return importer.read(user, business, identity)

    @app.post("/businesses/{business}/document-jobs", status_code=202)
    def enqueue(business: UUID, value: ExtractionInput, user: Actor, key: Key):
        return {"id": queue.enqueue(user, business, key, value)}

    @app.get("/businesses/{business}/document-jobs")
    def jobs(business: UUID, user: Actor, after: UUID | None = None, limit: int = 50):
        return queue.list(user, business, after, limit)

    @app.get("/businesses/{business}/document-jobs/{identity}")
    def job(business: UUID, identity: UUID, user: Actor):
        return queue.read(user, business, identity)

    @app.get("/businesses")
    def businesses(user: Actor):
        return service.businesses(user)

    @app.post("/businesses", status_code=201)
    def create_business(value: BusinessInput, user: Actor, key: Key):
        return {"id": service.create_business(user, value.name, value.industry, key)}

    @app.post("/businesses/{business}/documents", status_code=201)
    async def document(business: UUID, request: Request, user: Actor, key: Key,
                       filename: Annotated[str, Header(alias="X-Filename", min_length=1, max_length=200)]):
        content = bytearray()
        async for chunk in request.stream():
            content.extend(chunk)
            if len(content) > 10 * 1024 * 1024:
                raise HTTPException(413, "حداکثر اندازه سند ۱۰ مگابایت است")
        identity = await run_in_threadpool(service.document, user, business, key, filename,
            request.headers.get("content-type", "application/octet-stream"), bytes(content))
        duplicates = await run_in_threadpool(service.document_duplicates, user, business, identity)
        return {"id": identity, "duplicate_candidates": duplicates}

    @app.get("/businesses/{business}/documents/{identity}")
    def read_document(business: UUID, identity: UUID, user: Actor):
        _, content = service.read_document(user, business, identity)
        return Response(content, media_type="application/octet-stream",
                        headers={"Content-Disposition": "attachment", "X-Content-Type-Options": "nosniff",
                                 "Cache-Control": "no-store"})

    @app.get("/businesses/{business}/documents/{identity}/duplicates")
    def document_duplicates(business: UUID, identity: UUID, user: Actor):
        return service.document_duplicates(user, business, identity)

    @app.post("/businesses/{business}/warehouses", status_code=201)
    def warehouse(business: UUID, value: Warehouse, user: Actor, key: Key):
        return {"id": service.catalog(user, business, key, value)}

    @app.post("/businesses/{business}/items", status_code=201)
    def item(business: UUID, value: Item, user: Actor, key: Key):
        return {"id": service.catalog(user, business, key, value)}

    @app.post("/businesses/{business}/conversions", status_code=201)
    def conversion(business: UUID, value: UnitConversion, user: Actor, key: Key):
        return {"id": service.catalog(user, business, key, value)}

    @app.post("/businesses/{business}/counts", status_code=201)
    def count(business: UUID, value: Count, user: Actor, key: Key):
        return {"id": service.propose(user, business, key, value)}

    @app.post("/businesses/{business}/movements", status_code=201)
    def movement(business: UUID, value: Movement, user: Actor, key: Key):
        return {"id": service.propose(user, business, key, value)}

    @app.post("/businesses/{business}/recipes", status_code=201)
    def recipe(business: UUID, value: Recipe, user: Actor, key: Key):
        return {"id": service.propose(user, business, key, value)}

    @app.post("/businesses/{business}/fulfillments", status_code=201)
    def fulfillment(business: UUID, value: Fulfillment, user: Actor, key: Key):
        return {"id": service.propose(user, business, key, value)}

    @app.post("/businesses/{business}/records/{identity}/decision", status_code=201)
    def decision(business: UUID, identity: UUID, value: DecisionInput, user: Actor, key: Key):
        return {"id": service.approve(user, business, key, identity, value.approved, value.reason_fa,
                                      value.duplicate_resolution)}

    @app.post("/businesses/{business}/inventory-analyses", status_code=201)
    def analyze(business: UUID, value: AnalysisInput, user: Actor, key: Key):
        identity = service.analyze(user, business, key, value)
        return service.analysis(user, business, identity)

    @app.get("/businesses/{business}/inventory-analyses/{identity}")
    def analysis(business: UUID, identity: UUID, user: Actor):
        return service.analysis(user, business, identity)

    @app.get("/businesses/{business}/records/{identity}")
    def record(business: UUID, identity: UUID, user: Actor):
        return service.record(user, business, identity)

    @app.get("/businesses/{business}/resources/{resource}")
    def resources(business: UUID, resource: str, user: Actor, after: UUID | None = None, limit: int = 50):
        return service.page(user, business, resource, after, limit)

    @app.post("/businesses/{business}/financial-snapshots", status_code=201)
    def financial_proposal(business: UUID, value: FinancialSnapshot, user: Actor, key: Key):
        return {"id": financial.propose(user, business, key, value)}

    @app.get("/businesses/{business}/financial-snapshots/{identity}")
    def financial_record(business: UUID, identity: UUID, user: Actor, response: Response):
        response.headers["Cache-Control"] = "no-store"
        return financial.read(user, business, identity)

    @app.post("/businesses/{business}/financial-snapshots/{identity}/decision", status_code=201)
    def financial_decision(business: UUID, identity: UUID, value: KnowledgeDecision, user: Actor, key: Key):
        return {"id": financial.decide(user, business, key, identity, value.approved, value.reason_fa)}

    @app.get("/advisor/portfolio")
    def portfolio(effective_at: AwareDatetime, user: Actor, response: Response,
                  after: UUID | None = None, limit: int = 10):
        response.headers["Cache-Control"] = "no-store"
        return advisor.portfolio(user, effective_at, after, limit)

    @app.get("/businesses/{business}/overview")
    def business_overview(business: UUID, effective_at: AwareDatetime, user: Actor, response: Response):
        response.headers["Cache-Control"] = "no-store"
        return advisor.overview(user, business, effective_at)

    @app.post("/businesses/{business}/knowledge", status_code=201)
    def propose_knowledge(business: UUID, value: KnowledgeProposal, user: Actor, key: Key):
        return {"id": advisor.propose(user, business, key, value)}

    @app.get("/businesses/{business}/knowledge/{identity}")
    def knowledge(business: UUID, identity: UUID, user: Actor, response: Response):
        response.headers["Cache-Control"] = "no-store"
        return advisor.claim(user, business, identity)

    @app.post("/businesses/{business}/knowledge/{identity}/decision", status_code=201)
    def review_knowledge(business: UUID, identity: UUID, value: KnowledgeDecision, user: Actor, key: Key):
        return {"id": advisor.decide(user, business, key, identity, value)}

    @app.post("/businesses/{business}/advisor/context")
    def business_context(business: UUID, value: BusinessContextInput, user: Actor, response: Response):
        response.headers["Cache-Control"] = "no-store"
        return advisor.context(user, business, value)

    @app.post("/quick/advisor/context")
    def request_context(value: QuickContextInput, user: Actor, response: Response):
        response.headers["Cache-Control"] = "no-store"
        return quick_context(value)

    def draft(context: dict) -> dict:
        if draft_agent is None or not inference_slot.acquire(blocking=False):
            raise HTTPException(503, "مدل محلی فعال نیست یا در حال پاسخ‌گویی است",
                                headers={"Cache-Control": "no-store", "Retry-After": "5"})
        try:
            answer = draft_agent.advise(context)
        except (OSError, ValueError, TimeoutError):
            raise HTTPException(503, "پاسخ معتبر از مدل محلی دریافت نشد؛ زمینه محاسبه‌شده همچنان قابل دریافت است",
                                headers={"Cache-Control": "no-store"}) from None
        finally:
            inference_slot.release()
        digest = hashlib.sha256(json.dumps(context, ensure_ascii=False, sort_keys=True,
                                           separators=(",", ":")).encode("utf-8")).hexdigest()
        return dict(status="draft", verified=False, persisted=False,
                    context_sha256=digest, context=context, draft=answer)

    @app.post("/businesses/{business}/advisor/cases", status_code=201)
    def create_case(business: UUID, value: CaseInput, user: Actor, key: Key, response: Response):
        response.headers["Cache-Control"] = "no-store"
        return {"id": cases.create(user, business, key, value)}

    @app.get("/businesses/{business}/advisor/cases")
    def case_list(business: UUID, user: Actor, response: Response, after: UUID | None = None, limit: int = 20):
        response.headers["Cache-Control"] = "no-store"
        return cases.page(user, business, after, limit)

    @app.get("/businesses/{business}/advisor/cases/{case}/turns")
    def turn_list(business: UUID, case: UUID, user: Actor, response: Response, after: int = 0, limit: int = 20):
        response.headers["Cache-Control"] = "no-store"
        return cases.turns(user, business, case, after, limit)

    @app.get("/businesses/{business}/advisor/cases/{case}/turns/{identity}")
    def turn_detail(business: UUID, case: UUID, identity: UUID, user: Actor, response: Response):
        response.headers["Cache-Control"] = "no-store"
        return cases.read(user, business, case, identity)

    @app.post("/businesses/{business}/advisor/cases/{case}/turns", status_code=201)
    def append_turn(business: UUID, case: UUID, value: TurnInput, user: Actor, key: Key, response: Response,
                    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]):
        response.headers["Cache-Control"] = "no-store"
        def authenticated_draft(context: dict) -> dict:
            receipt = draft(context)
            # A revoked/expired credential must not publish after a slow model request.
            if actor(credentials) != user:
                raise AccessDenied("اعتبار دسترسی تغییر کرده است")
            return receipt
        identity = cases.append(user, business, case, key, value, authenticated_draft)
        return cases.read(user, business, case, identity)

    @app.post("/businesses/{business}/advisor/draft")
    def business_draft(business: UUID, value: BusinessContextInput, user: Actor, response: Response):
        response.headers["Cache-Control"] = "no-store"
        return draft(advisor.context(user, business, value))

    @app.post("/quick/advisor/draft")
    def quick_draft(value: QuickContextInput, user: Actor, response: Response):
        response.headers["Cache-Control"] = "no-store"
        return draft(quick_context(value))

    @app.post("/quick/inventory")
    def quick(value: InventoryRequest, user: Actor, response: Response):
        # Authentication only: all financial inputs come from this request. No business retrieval/writes.
        response.headers["Cache-Control"] = "no-store"
        return reconcile_inventory(value)

    return app
