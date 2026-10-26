"""Accountable action state transitions and PostgreSQL enforcement."""
# ruff: noqa: F811
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError
from test_backend import backend, database  # noqa: F401

from src.backend.actions import ActionEvent, ActionProposal, Actions
from src.backend.database import AccessDenied
from src.backend.service import Conflict, NotFound, insert

psycopg = pytest.importorskip('psycopg')


def setup_action(b, **overrides):
    analysis = uuid4()
    # The action contract accepts any saved analysis, including an incomplete receipt.
    with b['db'].transaction(b['owner'], b['business'], write=True) as c:
        from psycopg.types.json import Jsonb
        insert(c, 'analysis_runs', dict(business_id=b['business'], id=analysis, actor_id=b['owner'],
            input_sha256='0' * 64, input_snapshot=Jsonb({}), result=Jsonb({'status': 'incomplete'})))
    document = b['service'].document(b['owner'], b['business'], str(uuid4()), 'شاهد.txt', 'text/plain', b'action')
    value = dict(id=uuid4(), analysis_id=analysis, kind='investigate', title_fa='بررسی موجودی',
        detail_fa='بررسی علت اختلاف', responsible_name_fa='مسئول انبار', responsible_user_id=b['editor'],
        follow_up_at=datetime.now(timezone.utc), evidence=dict(document_id=document, locator='صفحه ۱'))
    value.update(overrides)
    return Actions(b['service']), ActionProposal(**value)


def append(actions, b, proposal, kind, sequence, actor='owner', key=None, **kwargs):
    return actions.event(b[actor], b['business'], key or str(uuid4()), proposal.id,
        ActionEvent(kind=kind, expected_sequence=sequence, reason_fa='بررسی شد', **kwargs))


def test_action_lifecycle_and_immutable_receipt(backend):
    b = backend
    actions, proposal = setup_action(b)
    assert actions.propose(b['editor'], b['business'], 'propose', proposal) == proposal.id
    assert actions.detail(b['viewer'], b['business'], proposal.id)['state'] == 'proposed'
    for kind in ('start', 'note', 'complete'):
        with pytest.raises(Conflict):
            append(actions, b, proposal, kind, 0, outcome='inconclusive', evidence=proposal.evidence) if (
                kind == 'complete') else append(actions, b, proposal, kind, 0)
    append(actions, b, proposal, 'approve', 0)
    append(actions, b, proposal, 'start', 1, actor='editor')
    append(actions, b, proposal, 'note', 2, actor='editor')
    append(actions, b, proposal, 'complete', 3, outcome='inconclusive', evidence=proposal.evidence)
    detail = actions.detail(b['viewer'], b['business'], proposal.id)
    assert detail['state'] == 'completed' and detail['sequence'] == 4
    assert [e['sequence'] for e in detail['events']] == [1, 2, 3, 4]
    assert detail['events'][-1]['outcome'] == 'inconclusive'
    assert detail['proposal']['responsible_name_fa'] == proposal.responsible_name_fa
    for kind in ('note', 'cancel', 'approve'):
        with pytest.raises(Conflict):
            append(actions, b, proposal, kind, 4)
    with b['db'].transaction(b['owner'], b['business']) as c:
        saved = c.execute('SELECT result FROM herman.analysis_runs WHERE business_id=%s AND id=%s',
            (b['business'], proposal.analysis_id)).fetchone()
        assert saved['result'] == {'status': 'incomplete'}


@pytest.mark.parametrize('terminal', ['reject', 'cancel'])
def test_terminal_pending_and_active_cancellation(backend, terminal):
    b = backend
    actions, proposal = setup_action(b)
    actions.propose(b['owner'], b['business'], 'propose', proposal)
    append(actions, b, proposal, terminal, 0)
    assert actions.detail(b['owner'], b['business'], proposal.id)['state'] == (
        'rejected' if terminal == 'reject' else 'cancelled')
    with pytest.raises(Conflict):
        append(actions, b, proposal, 'approve', 1)
    second = proposal.model_copy(update={'id': uuid4()})
    actions.propose(b['owner'], b['business'], 'second', second)
    append(actions, b, second, 'approve', 0)
    with pytest.raises(Conflict):
        append(actions, b, second, 'reject', 1)
    append(actions, b, second, 'cancel', 1)
    assert actions.detail(b['owner'], b['business'], second.id)['state'] == 'cancelled'


def test_action_roles_tenants_and_active_responsibility(backend):
    b = backend
    actions, proposal = setup_action(b)
    with pytest.raises(AccessDenied):
        actions.propose(b['viewer'], b['business'], 'viewer', proposal)
    actions.propose(b['editor'], b['business'], 'propose', proposal)
    for kind in ('approve', 'reject', 'complete', 'cancel'):
        with pytest.raises(AccessDenied):
            append(actions, b, proposal, kind, 0, actor='editor', **(
                dict(outcome='confirmed', evidence=proposal.evidence) if kind == 'complete' else {}))
    with pytest.raises(AccessDenied):
        actions.detail(b['stranger'], b['business'], proposal.id)
    with pytest.raises(NotFound):
        actions.detail(b['stranger'], b['other'], proposal.id)
    with b['db'].transaction(b['stranger'], b['other']) as c:
        assert c.execute('SELECT * FROM herman.action_proposals').fetchall() == []
        assert c.execute('SELECT * FROM herman.action_events').fetchall() == []
    for linked in (b['stranger'], b['viewer']):
        if linked == b['viewer']:
            with psycopg.connect(b['admin']) as c:
                c.execute('UPDATE herman.memberships SET active=false WHERE business_id=%s AND user_id=%s',
                    (b['business'], linked))
        invalid = proposal.model_copy(update={'id': uuid4(), 'responsible_user_id': linked})
        with pytest.raises(psycopg.errors.CheckViolation):
            actions.propose(b['owner'], b['business'], str(uuid4()), invalid)
    named_only = proposal.model_copy(update={'id': uuid4(), 'responsible_user_id': None})
    actions.propose(b['owner'], b['business'], 'named-only', named_only)
    foreign_analysis = uuid4()
    with b['db'].transaction(b['stranger'], b['other'], write=True) as c:
        from psycopg.types.json import Jsonb
        insert(c, 'analysis_runs', dict(business_id=b['other'], id=foreign_analysis, actor_id=b['stranger'],
            input_sha256='0' * 64, input_snapshot=Jsonb({}), result=Jsonb({})))
    wrong_analysis = proposal.model_copy(update={'id': uuid4(), 'analysis_id': foreign_analysis})
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        actions.propose(b['owner'], b['business'], 'wrong-analysis', wrong_analysis)
    foreign_document = b['service'].document(b['stranger'], b['other'], 'foreign-doc',
        'شاهد.txt', 'text/plain', b'foreign')
    with pytest.raises(NotFound):
        actions.propose(b['owner'], b['business'], 'wrong-document', proposal.model_copy(update={
            'id': uuid4(), 'evidence': proposal.evidence.model_copy(update={'document_id': foreign_document})}))


def test_action_idempotency_sequence_race_and_paging(backend):
    b = backend
    actions, proposal = setup_action(b)
    actions.propose(b['owner'], b['business'], 'propose', proposal)
    assert actions.propose(b['owner'], b['business'], 'propose', proposal) == proposal.id
    with pytest.raises(Conflict):
        actions.propose(b['owner'], b['business'], 'propose', proposal.model_copy(update={'title_fa': 'تغییر'}))
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: append(actions, b, proposal, 'approve', 0, key='same'), range(2)))
    assert results[0] == results[1]
    assert append(actions, b, proposal, 'approve', 0, key='same') == results[0]
    with pytest.raises(Conflict):
        append(actions, b, proposal, 'cancel', 1, key='same')

    def race(kind):
        try:
            return append(actions, b, proposal, kind, 1)
        except Conflict:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(race, ['note', 'start']))
    assert sum(result is not None for result in results) == 1
    append(actions, b, proposal, 'note', 2)
    first = actions.detail(b['owner'], b['business'], proposal.id, limit=1)
    assert first['sequence'] == 3 and len(first['events']) == 1 and first['next_sequence'] == 1
    last = actions.detail(b['owner'], b['business'], proposal.id, after_sequence=2, limit=1)
    assert last['events'][0]['sequence'] == 3 and last['next_sequence'] is None
    second = proposal.model_copy(update={'id': uuid4()})
    actions.propose(b['owner'], b['business'], 'second', second)
    page = actions.page(b['owner'], b['business'], limit=1)
    assert len(page['proposals']) == 1 and page['next_cursor']
    end = actions.page(b['owner'], b['business'], after=page['next_cursor'], limit=1)
    assert end['next_cursor'] is None and len(end['proposals']) == 1
    for limit in (0, 101):
        with pytest.raises(ValueError):
            actions.page(b['owner'], b['business'], limit=limit)
        with pytest.raises(ValueError):
            actions.detail(b['owner'], b['business'], proposal.id, limit=limit)


def test_action_evidence_tampering_and_rejection_recovery(backend):
    b = backend
    actions, proposal = setup_action(b)
    actions.propose(b['owner'], b['business'], 'propose', proposal)
    with b['db'].transaction(b['owner'], b['business']) as c:
        digest = c.execute('SELECT sha256 FROM herman.documents WHERE business_id=%s AND id=%s',
            (b['business'], proposal.evidence.document_id)).fetchone()['sha256']
    path = b['blob_root'] / str(b['business']) / digest
    path.write_bytes(b'tampered')
    with pytest.raises(Conflict):
        actions.propose(b['owner'], b['business'], 'tampered', proposal.model_copy(update={'id': uuid4()}))
    with pytest.raises(Conflict):
        append(actions, b, proposal, 'approve', 0)
    assert actions.detail(b['owner'], b['business'], proposal.id)['state'] == 'proposed'
    append(actions, b, proposal, 'reject', 0)
    path.write_bytes(b'action')
    second = proposal.model_copy(update={'id': uuid4()})
    actions.propose(b['owner'], b['business'], 'second', second)
    append(actions, b, second, 'approve', 0)
    path.unlink()
    with pytest.raises(Conflict):
        append(actions, b, second, 'complete', 1, outcome='no_change', evidence=proposal.evidence)
    append(actions, b, second, 'cancel', 1)


@pytest.mark.parametrize('kind', ['approve', 'complete'])
def test_action_event_own_evidence_hash(backend, kind):
    b = backend
    actions, proposal = setup_action(b)
    actions.propose(b['owner'], b['business'], 'propose', proposal)
    sequence = 0
    if kind == 'complete':
        append(actions, b, proposal, 'approve', 0)
        sequence = 1
    document = b['service'].document(b['owner'], b['business'], 'outcome-document',
        'نتیجه.txt', 'text/plain', b'outcome')
    with b['db'].transaction(b['owner'], b['business']) as c:
        digest = c.execute('SELECT sha256 FROM herman.documents WHERE business_id=%s AND id=%s',
            (b['business'], document)).fetchone()['sha256']
    (b['blob_root'] / str(b['business']) / digest).write_bytes(b'changed')
    with pytest.raises(Conflict):
        append(actions, b, proposal, kind, sequence, evidence=dict(document_id=document, locator='۱'), **(
            dict(outcome='confirmed') if kind == 'complete' else {}))
    assert actions.detail(b['owner'], b['business'], proposal.id)['sequence'] == sequence


def test_action_direct_sql_guards(backend):
    b = backend
    actions, proposal = setup_action(b)
    actions.propose(b['owner'], b['business'], 'propose', proposal)
    fields = dict(business_id=b['business'], id=uuid4(), action_id=proposal.id, sequence=1,
        kind='approve', status='completed', actor_id=b['editor'], reason_fa='بررسی شد')
    with pytest.raises(psycopg.errors.InsufficientPrivilege), b['db'].transaction(b['editor'], b['business']) as c:
        insert(c, 'action_events', fields)
    fields['actor_id'] = b['owner']
    fields['created_at'] = datetime(2000, 1, 1, tzinfo=timezone.utc)
    with b['db'].transaction(b['owner'], b['business']) as c:
        insert(c, 'action_events', fields)
    result = actions.detail(b['owner'], b['business'], proposal.id)
    assert result['state'] == 'approved'  # Client cannot choose state or event time.
    assert result['events'][0]['created_at'] > fields['created_at']
    for updates in (dict(sequence=3, kind='note'), dict(sequence=2, kind='complete'),
                    dict(sequence=2, kind='note', reason_fa=' ')):
        with pytest.raises(psycopg.errors.CheckViolation), b['db'].transaction(b['owner'], b['business']) as c:
            insert(c, 'action_events', dict(fields, id=uuid4(), **updates))
    for table in ('action_proposals', 'action_events'):
        with pytest.raises(psycopg.errors.InsufficientPrivilege), psycopg.connect(b['admin']) as c:
            c.execute(f'DELETE FROM herman.{table} WHERE business_id=%s', (b['business'],))
        with pytest.raises(psycopg.errors.InsufficientPrivilege), psycopg.connect(b['admin']) as c:
            c.execute(f'UPDATE herman.{table} SET created_at=now() WHERE business_id=%s', (b['business'],))
    invalid = proposal.model_dump(exclude={'evidence'})
    invalid.update(proposal.evidence.model_dump())
    invalid.update(id=uuid4(), business_id=b['business'], created_by=b['owner'], responsible_name_fa=' ')
    with pytest.raises(psycopg.errors.CheckViolation), b['db'].transaction(b['owner'], b['business']) as c:
        insert(c, 'action_proposals', invalid)


def test_action_required_fields():
    proposal = dict(id=uuid4(), analysis_id=uuid4(), kind='investigate', title_fa='بررسی', detail_fa='جزئیات',
        responsible_name_fa='مسئول', follow_up_at='2026-10-26T12:00:00+03:30',
        evidence=dict(document_id=uuid4(), locator='۱'))
    for field in ('responsible_name_fa', 'title_fa', 'detail_fa'):
        with pytest.raises(ValidationError):
            ActionProposal(**dict(proposal, **{field: '  '}))
    with pytest.raises(ValidationError):
        ActionProposal(**dict(proposal, follow_up_at='2026-10-26T12:00:00'))
    for options in ({}, {'outcome': 'confirmed'}, {'evidence': proposal['evidence']}):
        with pytest.raises(ValidationError):
            ActionEvent(kind='complete', expected_sequence=0, reason_fa='بررسی', **options)
    with pytest.raises(ValidationError):
        ActionEvent(kind='note', expected_sequence=0, reason_fa=' ', outcome='confirmed')
