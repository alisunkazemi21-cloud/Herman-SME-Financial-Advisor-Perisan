-- C17 is additive. The migration runner supplies transaction and lock budgets.
CREATE FUNCTION herman.coverage_dossier(b uuid,w uuid,s timestamptz,e timestamptz,basis text)
RETURNS jsonb LANGUAGE plpgsql STABLE SET search_path=pg_catalog,herman AS $$
DECLARE answer jsonb;
BEGIN
    IF b IS DISTINCT FROM herman.business_id() OR herman.member_role(b) IS NULL THEN
        RAISE EXCEPTION 'coverage scope denied' USING ERRCODE='42501';
    END IF;
    IF s IS NULL OR e IS NULL OR NOT isfinite(s) OR NOT isfinite(e) OR s>=e
        OR basis IS NULL OR basis NOT IN ('service','production')
        OR NOT EXISTS(SELECT 1 FROM herman.warehouses WHERE business_id=b AND id=w) THEN
        RAISE EXCEPTION 'invalid coverage scope' USING ERRCODE='23514';
    END IF;
    WITH details AS (
        SELECT t.id,'count' AS kind,CASE WHEN t.occurred_at=s THEN 'opening_count' ELSE 'closing_count' END AS category,
            (to_jsonb(t)-'business_id'-'occurred_at') || jsonb_build_object('occurred_at',extract(epoch FROM t.occurred_at),
                'base_unit',i.base_unit,'consumption_mode',i.consumption_mode) AS data,true AS event,false AS requires_recipe
        FROM herman.stock_counts t JOIN herman.items i ON (i.business_id,i.id)=(t.business_id,t.item_id)
        WHERE t.business_id=b AND t.warehouse_id=w AND t.occurred_at IN (s,e)
        UNION ALL
        SELECT t.id,'movement',CASE t.kind WHEN 'purchase' THEN 'purchases'
            WHEN 'supplier_return' THEN 'returns' WHEN 'customer_return' THEN 'returns'
            WHEN 'transfer_in' THEN 'transfers' WHEN 'transfer_out' THEN 'transfers'
            WHEN 'waste' THEN 'waste' ELSE 'other_use' END,
            (to_jsonb(t)-'business_id'-'occurred_at') || jsonb_build_object('occurred_at',extract(epoch FROM t.occurred_at),
                'base_unit',i.base_unit,'consumption_mode',i.consumption_mode),true,false
        FROM herman.stock_movements t JOIN herman.items i ON (i.business_id,i.id)=(t.business_id,t.item_id)
        WHERE t.business_id=b AND t.warehouse_id=w AND t.occurred_at>=s AND t.occurred_at<e
        UNION ALL
        SELECT t.id,'fulfillment',CASE t.kind WHEN 'sale' THEN 'sales' WHEN 'staff' THEN 'staff_meals'
            WHEN 'complimentary' THEN 'complimentary' ELSE 'production' END,
            (to_jsonb(t)-'business_id'-'occurred_at') || jsonb_build_object('occurred_at',extract(epoch FROM t.occurred_at),
                'base_unit',i.base_unit,'consumption_mode',i.consumption_mode),t.fulfilled,t.fulfilled AND i.consumption_mode='recipe'
        FROM herman.fulfillments t JOIN herman.items i ON (i.business_id,i.id)=(t.business_id,t.product_id)
        WHERE t.business_id=b AND t.warehouse_id=w AND t.occurred_at>=s AND t.occurred_at<e
        UNION ALL
        SELECT t.id,'recipe','recipes',(to_jsonb(t)-'business_id'-'valid_from'-'valid_to') ||
            jsonb_build_object('valid_from',extract(epoch FROM t.valid_from),'valid_to',extract(epoch FROM t.valid_to),
                'base_unit',i.base_unit,'consumption_mode',i.consumption_mode),true,false
        FROM herman.recipes t JOIN herman.items i ON (i.business_id,i.id)=(t.business_id,t.product_id)
        WHERE t.business_id=b AND t.valid_from<e AND (t.valid_to IS NULL OR t.valid_to>s)
    ), active AS MATERIALIZED (
        SELECT d.*,r.document_id,r.locator,a.approved,
            d.data || jsonb_build_object('record_id',r.id,'document_id',r.document_id,'locator',r.locator,
                'created_by',r.created_by,'created_at',extract(epoch FROM r.created_at),'supersedes',r.supersedes,
                'approval',CASE WHEN a.record_id IS NULL THEN NULL ELSE
                    (to_jsonb(a)-'business_id'-'created_at') || jsonb_build_object('created_at',extract(epoch FROM a.created_at)) END,
                'source_sha256',doc.sha256) AS payload
        -- New tenants can be absent from statistics after a bulk import. Fence
        -- exact primary-key probes so a one-row estimate cannot rescan the whole
        -- materialized operational union once for every source header.
        FROM details d JOIN LATERAL (
            SELECT * FROM herman.records source WHERE source.business_id=b AND source.id=d.id LIMIT 1
        ) r ON true
        JOIN LATERAL (
            SELECT * FROM herman.documents source WHERE (source.business_id,source.id)=(r.business_id,r.document_id) LIMIT 1
        ) doc ON true
        LEFT JOIN herman.approvals a ON (a.business_id,a.record_id)=(r.business_id,r.id)
        WHERE (a.approved IS NULL OR a.approved) AND (r.supersedes IS NULL OR a.approved)
            AND NOT EXISTS(SELECT 1 FROM herman.approvals successor WHERE successor.business_id=b
                AND successor.supersedes=r.id AND successor.approved)
        ORDER BY d.kind,d.id LIMIT 10001
    ), facts AS MATERIALIZED (
        SELECT kind || ':' || id::text AS key,payload FROM active
        UNION ALL
        SELECT 'recipe_line:' || l.recipe_id::text || ':' || l.item_id::text,
            (to_jsonb(l)-'business_id') || jsonb_build_object('base_unit',i.base_unit,'consumption_mode',i.consumption_mode)
        FROM herman.recipe_lines l JOIN active a ON a.kind='recipe' AND a.id=l.recipe_id
        JOIN herman.items i ON (i.business_id,i.id)=(l.business_id,l.item_id)
        WHERE l.business_id=b
        ORDER BY key LIMIT 10001
    ), category_names AS (
        SELECT unnest(ARRAY['opening_count','closing_count','purchases','sales','returns','transfers',
            'waste','staff_meals','complimentary','production','other_use','recipes']) AS category
    ), stats AS (
        SELECT n.category,jsonb_build_object('event_count',count(a.id) FILTER(WHERE a.event),
            'approved_count',count(a.id) FILTER(WHERE a.event AND a.approved),
            'pending_count',count(a.id) FILTER(WHERE a.event AND a.approved IS NULL)) AS value
        FROM category_names n LEFT JOIN active a ON a.category=n.category GROUP BY n.category
    ), summary AS (
        SELECT count(*) AS row_count,jsonb_agg(jsonb_build_object('key',key,'value',payload) ORDER BY key) AS data FROM facts
    )
    SELECT CASE WHEN row_count>10000 THEN jsonb_build_object('available',false,'signature',NULL,
        'row_count',row_count,'stats','{}'::jsonb,'required_recipe_products',0,'unreviewed_count',0,'evidence_refs','[]'::jsonb)
    ELSE jsonb_build_object('available',true,'signature',encode(sha256(convert_to(jsonb_build_object(
        'business_id',b,'warehouse_id',w,'start',extract(epoch FROM s),'end',extract(epoch FROM e),
        'basis',basis,'facts',coalesce(data,'[]'::jsonb))::text,'UTF8')),'hex'),
        'row_count',row_count,'stats',(SELECT jsonb_object_agg(category,value) FROM stats),
        'required_recipe_products',(SELECT count(*) FROM active WHERE requires_recipe),
        'unreviewed_count',(SELECT count(*) FROM active WHERE approved IS NULL),
        'evidence_refs',coalesce((SELECT jsonb_agg(ref ORDER BY ref::text) FROM (
            SELECT DISTINCT jsonb_build_object('document_id',document_id,'locator',locator) AS ref FROM active
        ) refs),'[]'::jsonb)) END INTO answer FROM summary;
    RETURN answer;
END $$;

CREATE TABLE herman.coverage_assessments (
    business_id uuid NOT NULL, id uuid NOT NULL, warehouse_id uuid NOT NULL,
    period_start timestamptz NOT NULL CHECK(isfinite(period_start)),
    period_end timestamptz NOT NULL CHECK(isfinite(period_end) AND period_end>period_start),
    basis text NOT NULL CHECK(basis IN ('service','production')),supersedes_id uuid,
    categories jsonb NOT NULL CHECK(jsonb_typeof(categories)='object'),
    document_id uuid NOT NULL,locator text NOT NULL CHECK(length(btrim(locator)) BETWEEN 1 AND 500),
    created_by uuid NOT NULL REFERENCES herman.users(id),created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY(business_id,id),
    FOREIGN KEY(business_id,warehouse_id) REFERENCES herman.warehouses(business_id,id),
    FOREIGN KEY(business_id,document_id) REFERENCES herman.documents(business_id,id),
    FOREIGN KEY(business_id,supersedes_id) REFERENCES herman.coverage_assessments(business_id,id),
    CHECK(supersedes_id IS DISTINCT FROM id)
);
CREATE INDEX coverage_scope ON herman.coverage_assessments(business_id,warehouse_id,period_start,period_end,basis,id);
CREATE TABLE herman.coverage_decisions (
    business_id uuid NOT NULL,assessment_id uuid NOT NULL,warehouse_id uuid NOT NULL,
    period_start timestamptz NOT NULL,period_end timestamptz NOT NULL,basis text NOT NULL,supersedes_id uuid,
    approved boolean NOT NULL,actor_id uuid NOT NULL REFERENCES herman.users(id),
    reason_fa text NOT NULL CHECK(length(btrim(reason_fa)) BETWEEN 1 AND 2000),
    decided_at timestamptz NOT NULL DEFAULT clock_timestamp(),dataset jsonb NOT NULL,
    PRIMARY KEY(business_id,assessment_id),
    FOREIGN KEY(business_id,assessment_id) REFERENCES herman.coverage_assessments(business_id,id)
);
CREATE UNIQUE INDEX coverage_one_successor ON herman.coverage_decisions
    (business_id,warehouse_id,period_start,period_end,basis,supersedes_id) NULLS NOT DISTINCT WHERE approved;

CREATE FUNCTION herman.coverage_proposal_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE entry record;ref jsonb;previous herman.coverage_assessments%ROWTYPE;
BEGIN
    IF NEW.created_by IS DISTINCT FROM herman.user_id() THEN
        RAISE EXCEPTION 'coverage author mismatch' USING ERRCODE='42501';
    END IF;
    NEW.created_at:=clock_timestamp();
    IF (SELECT array_agg(key ORDER BY key) FROM jsonb_object_keys(NEW.categories) key) IS DISTINCT FROM
        ARRAY['closing_count','complimentary','opening_count','other_use','production','purchases','recipes',
            'returns','sales','staff_meals','transfers','waste']::text[] THEN
        RAISE EXCEPTION 'exactly twelve coverage categories required' USING ERRCODE='23514';
    END IF;
    FOR entry IN SELECT * FROM jsonb_each(NEW.categories) LOOP
        IF jsonb_typeof(entry.value)<>'object' OR
            (SELECT array_agg(key ORDER BY key) FROM jsonb_object_keys(entry.value) key) IS DISTINCT FROM
                ARRAY['evidence','note_fa','status']::text[] OR
            coalesce(entry.value->>'status','') NOT IN ('records_complete','no_events','not_applicable','missing','incomplete') OR
            jsonb_typeof(entry.value->'note_fa') IS DISTINCT FROM 'string' OR
            length(btrim(entry.value->>'note_fa')) NOT BETWEEN 1 AND 2000 OR
            (entry.value->>'status'='not_applicable' AND entry.key<>'recipes') OR
            (entry.key IN ('opening_count','closing_count') AND entry.value->>'status'='no_events') THEN
            RAISE EXCEPTION 'invalid coverage category' USING ERRCODE='23514';
        END IF;
        ref:=entry.value->'evidence';
        IF ref IS NULL OR ref='null'::jsonb THEN
            IF entry.value->>'status' IN ('records_complete','no_events','not_applicable') THEN
                RAISE EXCEPTION 'positive coverage assertion requires evidence' USING ERRCODE='23514';
            END IF;
        ELSE
            IF jsonb_typeof(ref)<>'object' OR
                (SELECT array_agg(key ORDER BY key) FROM jsonb_object_keys(ref) key) IS DISTINCT FROM
                    ARRAY['document_id','locator']::text[] OR
                jsonb_typeof(ref->'locator') IS DISTINCT FROM 'string' OR
                length(btrim(ref->>'locator')) NOT BETWEEN 1 AND 500 OR
                NOT EXISTS(SELECT 1 FROM herman.documents WHERE business_id=NEW.business_id AND id=(ref->>'document_id')::uuid) THEN
                RAISE EXCEPTION 'invalid category evidence' USING ERRCODE='23514';
            END IF;
        END IF;
    END LOOP;
    IF NEW.supersedes_id IS NOT NULL THEN
        SELECT p.* INTO previous FROM herman.coverage_assessments p JOIN herman.coverage_decisions d
            ON (d.business_id,d.assessment_id)=(p.business_id,p.id)
            WHERE p.business_id=NEW.business_id AND p.id=NEW.supersedes_id AND d.approved;
        IF previous.id IS NULL OR (previous.warehouse_id,previous.period_start,previous.period_end,previous.basis)
            IS DISTINCT FROM (NEW.warehouse_id,NEW.period_start,NEW.period_end,NEW.basis) OR
            EXISTS(SELECT 1 FROM herman.coverage_decisions WHERE business_id=NEW.business_id
                AND supersedes_id=NEW.supersedes_id AND approved) THEN
            RAISE EXCEPTION 'coverage needs current same-scope approved predecessor' USING ERRCODE='23514';
        END IF;
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER coverage_proposal_guard BEFORE INSERT ON herman.coverage_assessments
    FOR EACH ROW EXECUTE FUNCTION herman.coverage_proposal_guard();

CREATE FUNCTION herman.coverage_decision_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE proposal herman.coverage_assessments%ROWTYPE;
BEGIN
    IF NEW.actor_id IS DISTINCT FROM herman.user_id() OR
        coalesce(herman.member_role(NEW.business_id),'') NOT IN ('owner','reviewer') THEN
        RAISE EXCEPTION 'coverage decision requires reviewer' USING ERRCODE='42501';
    END IF;
    SELECT * INTO STRICT proposal FROM herman.coverage_assessments WHERE business_id=NEW.business_id AND id=NEW.assessment_id;
    NEW.warehouse_id:=proposal.warehouse_id;NEW.period_start:=proposal.period_start;NEW.period_end:=proposal.period_end;
    NEW.basis:=proposal.basis;NEW.supersedes_id:=proposal.supersedes_id;NEW.decided_at:=clock_timestamp();
    -- A client-supplied dataset never becomes review authority.
    NEW.dataset:=herman.coverage_dossier(NEW.business_id,NEW.warehouse_id,NEW.period_start,NEW.period_end,NEW.basis);
    IF NEW.approved AND NOT (NEW.dataset->>'available')::boolean THEN
        RAISE EXCEPTION 'coverage dossier exceeds review limit' USING ERRCODE='23514';
    END IF;
    IF NEW.approved AND NEW.supersedes_id IS NOT NULL AND (
        NOT EXISTS(SELECT 1 FROM herman.coverage_decisions WHERE business_id=NEW.business_id
            AND assessment_id=NEW.supersedes_id AND approved) OR
        EXISTS(SELECT 1 FROM herman.coverage_decisions WHERE business_id=NEW.business_id
            AND supersedes_id=NEW.supersedes_id AND approved)) THEN
        RAISE EXCEPTION 'coverage predecessor is no longer current' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER coverage_decision_guard BEFORE INSERT ON herman.coverage_decisions
    FOR EACH ROW EXECUTE FUNCTION herman.coverage_decision_guard();

DO $$ DECLARE t text; BEGIN
    FOREACH t IN ARRAY ARRAY['coverage_assessments','coverage_decisions'] LOOP
        EXECUTE format('ALTER TABLE herman.%I ENABLE ROW LEVEL SECURITY',t);
        EXECUTE format('ALTER TABLE herman.%I FORCE ROW LEVEL SECURITY',t);
        EXECUTE format('CREATE POLICY tenant_read ON herman.%I FOR SELECT USING '
            || '(business_id=herman.business_id() AND herman.member_role(business_id) IS NOT NULL)',t);
        EXECUTE format('CREATE TRIGGER append_only BEFORE UPDATE OR DELETE ON herman.%I '
            || 'FOR EACH ROW EXECUTE FUNCTION herman.immutable_record()',t);
    END LOOP;
END $$;
CREATE POLICY tenant_insert ON herman.coverage_assessments FOR INSERT WITH CHECK (
    business_id=herman.business_id() AND created_by=herman.user_id()
    AND herman.member_role(business_id) IN ('owner','editor','reviewer'));
CREATE POLICY tenant_insert ON herman.coverage_decisions FOR INSERT WITH CHECK (
    business_id=herman.business_id() AND actor_id=herman.user_id()
    AND herman.member_role(business_id) IN ('owner','reviewer'));
REVOKE ALL ON FUNCTION herman.coverage_dossier(uuid,uuid,timestamptz,timestamptz,text) FROM PUBLIC;
INSERT INTO herman.schema_migrations(version) VALUES(19);
