"""Request intake controls, generic no-store errors and bounded background cleanup."""

from __future__ import annotations

import asyncio
from threading import BoundedSemaphore
from typing import Callable

from fastapi import HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from starlette.requests import ClientDisconnect

from src.backend.quick_document_models import (
    MAX_UPLOAD,
    RECEIVE_SECONDS,
    DocumentError,
    DocumentFormat,
    OcrEngine,
)
from src.backend.quick_documents import extract_temporary


class QuickDocumentRoute(APIRoute):
    def get_route_handler(self) -> Callable:
        original = super().get_route_handler()

        async def handle(request: Request):
            try:
                response = await original(request)
            except (RequestValidationError, ValueError):
                response = JSONResponse(status_code=422, content={"detail": "ورودی با قرارداد داده سازگار نیست"})
            except DocumentError as exc:
                response = JSONResponse(status_code=exc.status, content={"code": exc.code, "detail": exc.detail})
                if exc.code == "busy":
                    response.headers["Retry-After"] = "5"
            except HTTPException as exc:
                response = JSONResponse(status_code=exc.status_code, content={"detail": exc.detail},
                                        headers=exc.headers)
            response.headers["Cache-Control"] = "no-store"
            return response

        return handle


async def receive_and_extract(request: Request, format: DocumentFormat, engine: OcrEngine,
                              slot: BoundedSemaphore) -> dict:
    if not slot.acquire(blocking=False):
        raise DocumentError("busy")
    handed_off = False
    try:
        length = request.headers.get("content-length")
        if length is not None:
            if len(length) > 20 or not length.isascii() or not length.isdecimal():
                raise DocumentError("invalid_document")
            if int(length) > MAX_UPLOAD:
                raise DocumentError("resource_limit")
        content = bytearray()
        try:
            async with asyncio.timeout(RECEIVE_SECONDS):
                async for chunk in request.stream():
                    if len(content) + len(chunk) > MAX_UPLOAD:
                        raise DocumentError("resource_limit")
                    content.extend(chunk)
        except TimeoutError:
            raise DocumentError("receive_timeout") from None
        except ClientDisconnect:
            raise DocumentError("invalid_document") from None

        def work() -> dict:
            try:
                return extract_temporary(bytes(content), format, engine)
            finally:
                slot.release()

        # The worker owns temporary cleanup and the slot after handoff. A cancelled
        # HTTP request may stop awaiting, but must not abandon a live parser's slot.
        task = asyncio.create_task(run_in_threadpool(work))
        handed_off = True
        task.add_done_callback(lambda done: done.exception() if not done.cancelled() else None)
        return await asyncio.shield(task)
    finally:
        if not handed_off:
            slot.release()
