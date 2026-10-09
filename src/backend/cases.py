"""Immutable business conversations; history is context, never accounting evidence."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb
from pydantic import Field

from src.backend.advisor import BusinessAdvisor, BusinessContextInput, bounded_context
from src.backend.service import Conflict, NotFound, Service, canonical, insert
from src.models import Model


class CaseInput(Model):
    title_fa: str = Field(min_length=1, max_length=200)


class TurnInput(Model):
    context: BusinessContextInput
    expected_turn: int = Field(ge=0, le=2147483646)
    generate_draft: bool = True


class BusinessCases:
    def __init__(self, service: Service, advisor: BusinessAdvisor) -> None:
        self.service = service
        self.advisor = advisor

    def create(self, actor: UUID, business: UUID, key: str, value: CaseInput) -> UUID:
        def store(c):
            identity = uuid4()
            insert(
                c,
                "advisor_cases",
                dict(business_id=business, id=identity, title_fa=value.title_fa, created_by=actor),
            )
            return identity

        return self.service._write(actor, business, key, "case.created", value.model_dump(mode="json"), store)

    @staticmethod
    def _state(c, business: UUID, case: UUID) -> int:
        if not c.execute(
            "SELECT 1 FROM herman.advisor_cases WHERE business_id=%s AND id=%s", (business, case)
        ).fetchone():
            raise NotFound("پرونده موجود نیست")
        return c.execute(
            "SELECT coalesce(max(turn_number),0) AS n FROM herman.advisor_turns "
            "WHERE business_id=%s AND case_id=%s",
            (business, case),
        ).fetchone()["n"]

    def page(self, actor: UUID, business: UUID, after: UUID | None = None, limit: int = 20) -> list[dict]:
        if not 1 <= limit <= 50:
            raise ValueError("اندازه صفحه باید بین ۱ و ۵۰ باشد")
        with self.service.database.transaction(actor, business) as c:
            return c.execute(
                "SELECT k.*,(SELECT coalesce(max(t.turn_number),0) FROM herman.advisor_turns t "
                "WHERE t.business_id=k.business_id AND t.case_id=k.id) AS latest_turn "
                "FROM herman.advisor_cases k WHERE business_id=%s AND (%s::uuid IS NULL OR id>%s) "
                "ORDER BY id LIMIT %s",
                (business, after, after, limit),
            ).fetchall()

    def turns(self, actor: UUID, business: UUID, case: UUID, after: int = 0, limit: int = 20) -> list[dict]:
        if after < 0 or not 1 <= limit <= 50:
            raise ValueError("شماره نوبت یا اندازه صفحه نامعتبر است")
        with self.service.database.transaction(actor, business) as c:
            self._state(c, business, case)
            return c.execute(
                "SELECT id,case_id,turn_number,created_by,created_at,"
                "request->'context'->>'question_fa' AS question_fa,receipt->>'status' AS status "
                "FROM herman.advisor_turns WHERE business_id=%s AND case_id=%s AND turn_number>%s "
                "ORDER BY turn_number LIMIT %s",
                (business, case, after, limit),
            ).fetchall()

    def read(self, actor: UUID, business: UUID, case: UUID, identity: UUID) -> dict:
        with self.service.database.transaction(actor, business) as c:
            row = c.execute(
                "SELECT * FROM herman.advisor_turns WHERE business_id=%s AND case_id=%s AND id=%s",
                (business, case, identity),
            ).fetchone()
            if row is None:
                raise NotFound("نوبت گفتگو موجود نیست")
            return row

    def append(
        self,
        actor: UUID,
        business: UUID,
        case: UUID,
        key: str,
        value: TurnInput,
        generate: Callable[[dict], dict],
    ) -> UUID:
        if not 1 <= len(key) <= 200:
            raise ValueError("کلید درخواست نامعتبر است")
        payload = dict(case_id=str(case), **value.model_dump(mode="json"))
        action = "case.turn_created"
        digest = hashlib.sha256(canonical(dict(action=action, payload=payload)).encode()).hexdigest()
        with self.service.database.transaction(actor, business, write=True) as c:
            previous = c.execute(
                "SELECT * FROM herman.idempotency_keys WHERE business_id=%s AND key=%s", (business, key)
            ).fetchone()
            if previous:
                if previous["request_hash"] != digest:
                    raise Conflict("این کلید برای درخواست متفاوتی استفاده شده است")
                return previous["result_id"]
            number = self._state(c, business, case)
            if number != value.expected_turn:
                raise Conflict("گفتگو تغییر کرده است؛ آخرین نوبت را بخوانید و دوباره ارسال کنید")
            rows = c.execute(
                "SELECT id,turn_number,request->'context'->>'question_fa' AS question_fa,"
                "receipt->>'status' AS status,receipt->'draft'->>'text_fa' AS draft_fa,"
                "receipt->'context'->>'explanation_fa' AS explanation_fa "
                "FROM herman.advisor_turns WHERE business_id=%s AND case_id=%s "
                "ORDER BY turn_number DESC LIMIT 3",
                (business, case),
            ).fetchall()
        history = []
        for row in reversed(rows):
            text = row["draft_fa"] or row["explanation_fa"] or ""
            history.append(
                dict(
                    turn_id=str(row["id"]),
                    turn_number=row["turn_number"],
                    question_fa=row["question_fa"],
                    reply_fa=text[:1500],
                    reply_truncated=len(text) > 1500,
                    authoritative=False,
                    reply_kind=row["status"],
                )
            )
        # Current structured context is rebuilt; old prose never supplies calculation inputs.
        context = self.advisor.context(actor, business, value.context)
        context.update(
            case_id=str(case),
            conversation_history_unverified=history,
            history_truncated=number > 3,
            history_used=bool(history),
            persisted=True,
        )
        context = bounded_context(context)
        if value.generate_draft:
            receipt = generate(context)
        else:
            receipt = dict(
                status="context_only",
                verified=False,
                context=context,
                context_sha256=hashlib.sha256(canonical(context).encode()).hexdigest(),
                draft=None,
            )
        receipt = bounded_context({**receipt, "persisted": True})

        def store(c):
            if self._state(c, business, case) != value.expected_turn:
                raise Conflict("گفتگو هنگام تولید پاسخ تغییر کرد؛ پاسخ ثبت نشد")
            identity = uuid4()
            insert(
                c,
                "advisor_turns",
                dict(
                    business_id=business,
                    id=identity,
                    case_id=case,
                    turn_number=value.expected_turn + 1,
                    request=Jsonb(value.model_dump(mode="json")),
                    receipt=Jsonb(receipt),
                    created_by=actor,
                ),
            )
            return identity

        return self.service._write(actor, business, key, action, payload, store)
