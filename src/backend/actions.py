"""Immutable, reviewed investigation actions; outcomes do not assert financial benefits."""
from typing import Literal
from uuid import UUID, uuid4

import psycopg
from pydantic import AwareDatetime, Field, model_validator

from src.backend.inventory import EvidenceRef
from src.backend.service import Conflict, NotFound, Service, insert
from src.models import Model


class ActionProposal(Model):
    id: UUID
    analysis_id: UUID
    kind: Literal['investigate', 'recount', 'correct_recipe', 'record_missing', 'reduce_waste', 'other']
    title_fa: str = Field(min_length=1, max_length=300)
    detail_fa: str = Field(min_length=1, max_length=4000)
    responsible_name_fa: str = Field(min_length=1, max_length=200)
    responsible_user_id: UUID | None = None
    follow_up_at: AwareDatetime
    evidence: EvidenceRef


class ActionEvent(Model):
    kind: Literal['approve', 'reject', 'start', 'note', 'complete', 'cancel']
    expected_sequence: int = Field(ge=0, le=2147483646, strict=True)
    reason_fa: str = Field(min_length=1, max_length=4000)
    evidence: EvidenceRef | None = None
    outcome: Literal['confirmed', 'no_change', 'inconclusive'] | None = None

    @model_validator(mode='after')
    def completion(self) -> 'ActionEvent':
        if self.kind == 'complete' and (self.outcome is None or self.evidence is None):
            raise ValueError('اتمام اقدام نیازمند نتیجه و شاهد است')
        if self.kind != 'complete' and self.outcome is not None:
            raise ValueError('نتیجه فقط برای اتمام اقدام ثبت می‌شود')
        return self


_PROJECTION = (
    'SELECT p.*,COALESCE(e.status,\'proposed\') AS state,COALESCE(e.sequence,0) AS sequence '
    'FROM herman.action_proposals p LEFT JOIN LATERAL '
    '(SELECT status,sequence FROM herman.action_events WHERE business_id=p.business_id AND action_id=p.id '
    'ORDER BY sequence DESC LIMIT 1) e ON true ')


class Actions:
    def __init__(self, service: Service):
        self.service = service

    @staticmethod
    def _proposal(c, business: UUID, identity: UUID) -> dict:
        row = c.execute(_PROJECTION + 'WHERE p.business_id=%s AND p.id=%s', (business, identity)).fetchone()
        if row is None:
            raise NotFound('اقدام در این بیزینس موجود نیست')
        return row

    def propose(self, actor: UUID, business: UUID, key: str, value: ActionProposal) -> UUID:
        def store(c):
            self.service._inventory_evidence(c, business, value.evidence.document_id)
            fields = value.model_dump()
            fields.update(fields.pop('evidence'))
            insert(c, 'action_proposals', dict(business_id=business, created_by=actor, **fields))
            return value.id

        return self.service._write(actor, business, key, 'action.proposed', value.model_dump(mode='json'), store)

    def event(self, actor: UUID, business: UUID, key: str, identity: UUID, value: ActionEvent) -> UUID:
        def store(c):
            proposal = self._proposal(c, business, identity)
            if proposal['sequence'] != value.expected_sequence:
                raise Conflict('تاریخچهٔ اقدام تغییر کرده است؛ صفحه را بازخوانی کنید')
            if value.kind in ('approve', 'complete'):
                self.service._inventory_evidence(c, business, proposal['document_id'])
                if value.evidence:
                    self.service._inventory_evidence(c, business, value.evidence.document_id)
            event_id = uuid4()
            fields = value.model_dump(exclude={'expected_sequence', 'evidence'})
            fields.update(value.evidence.model_dump() if value.evidence else dict(document_id=None, locator=None))
            insert(c, 'action_events', dict(business_id=business, id=event_id, action_id=identity,
                sequence=value.expected_sequence + 1, actor_id=actor, **fields))
            return event_id

        try:
            return self.service._write(actor, business, key, 'action.event',
                dict(id=str(identity), **value.model_dump(mode='json')), store,
                reviewer=value.kind in ('approve', 'reject', 'complete', 'cancel'))
        except (psycopg.errors.UniqueViolation, psycopg.errors.CheckViolation) as exc:
            raise Conflict('گذار یا شمارهٔ رویداد اقدام معتبر نیست') from exc

    def page(self, actor: UUID, business: UUID, after: UUID | None = None, limit: int = 50) -> dict:
        if not 1 <= limit <= 100:
            raise ValueError('اندازهٔ صفحه نامعتبر است')
        with self.service.database.transaction(actor, business) as c:
            rows = c.execute(_PROJECTION + 'WHERE p.business_id=%s AND (%s::uuid IS NULL OR p.id>%s) '
                'ORDER BY p.id LIMIT %s', (business, after, after, limit + 1)).fetchall()
            return dict(proposals=rows[:limit], next_cursor=rows[limit - 1]['id'] if len(rows) > limit else None,
                        evidence_verification='not_rechecked')

    def detail(self, actor: UUID, business: UUID, identity: UUID,
               after_sequence: int = 0, limit: int = 50) -> dict:
        if not 1 <= limit <= 100 or not 0 <= after_sequence <= 2147483647:
            raise ValueError('اندازهٔ صفحه یا شمارهٔ رویداد نامعتبر است')
        with self.service.database.transaction(actor, business) as c:
            proposal = self._proposal(c, business, identity)
            events = c.execute('SELECT * FROM herman.action_events WHERE business_id=%s AND action_id=%s '
                'AND sequence>%s ORDER BY sequence LIMIT %s', (business, identity, after_sequence, limit + 1)).fetchall()
            return dict(proposal=proposal, state=proposal['state'], sequence=proposal['sequence'],
                events=events[:limit], next_sequence=events[limit - 1]['sequence'] if len(events) > limit else None,
                evidence_verification='not_rechecked')
