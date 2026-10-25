-- Additive storage only: existing inventory and analysis receipts are untouched.
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '120s';
-- Establish one cutover boundary after all prior source/definition writers commit.
-- These locks also hold new inserts until legacy flags and native capture guards exist.
LOCK TABLE herman.records,herman.pack_definitions IN ACCESS EXCLUSIVE MODE;

CREATE TABLE herman.pack_binding_cutover (
    singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton),
    captured_at timestamptz NOT NULL, captured_xid xid8 NOT NULL
);
INSERT INTO herman.pack_binding_cutover VALUES(true,clock_timestamp(),pg_current_xact_id());
CREATE TRIGGER append_only BEFORE UPDATE OR DELETE ON herman.pack_binding_cutover
    FOR EACH ROW EXECUTE FUNCTION herman.immutable_record();
-- A stable flag survives logical restore; transaction IDs are descriptive only.
ALTER TABLE herman.records ADD COLUMN pack_binding_legacy boolean NOT NULL DEFAULT true;
ALTER TABLE herman.records ALTER COLUMN pack_binding_legacy SET DEFAULT false;
CREATE FUNCTION herman.pack_binding_stamp_source() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN NEW.pack_binding_legacy := false; RETURN NEW; END $$;
CREATE TRIGGER pack_binding_stamp_source BEFORE INSERT ON herman.records
    FOR EACH ROW EXECUTE FUNCTION herman.pack_binding_stamp_source();

CREATE TABLE herman.pack_definition_observations (
    business_id uuid NOT NULL, definition_id uuid NOT NULL,
    observed_at timestamptz NOT NULL,
    origin text NOT NULL CHECK(origin IN ('migration_observation','native_capture')),
    PRIMARY KEY(business_id,definition_id),
    FOREIGN KEY(business_id,definition_id) REFERENCES herman.pack_definitions(business_id,id)
);
INSERT INTO herman.pack_definition_observations
    SELECT d.business_id,d.id,c.captured_at,'migration_observation'
    FROM herman.pack_definitions d CROSS JOIN herman.pack_binding_cutover c;

CREATE FUNCTION herman.pack_observe_definition() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
    SET search_path=pg_catalog,herman AS $$
BEGIN
    IF NEW.business_id IS DISTINCT FROM herman.business_id()
        OR COALESCE(herman.member_role(NEW.business_id),'') NOT IN ('owner','editor','reviewer') THEN
        RAISE EXCEPTION 'definition observation requires scoped membership' USING ERRCODE='42501';
    END IF;
    INSERT INTO herman.pack_definition_observations VALUES
        (NEW.business_id,NEW.id,clock_timestamp(),'native_capture');
    RETURN NEW;
END $$;
CREATE TRIGGER pack_observe_definition AFTER INSERT ON herman.pack_definitions
    FOR EACH ROW EXECUTE FUNCTION herman.pack_observe_definition();

-- Candidates describe interval eligibility; callers separately enforce prior knowledge.
CREATE FUNCTION herman.pack_binding_candidates(business uuid,item uuid,event_time timestamptz)
RETURNS TABLE(definition_id uuid,baseline boolean,observed_at timestamptz,observation_origin text)
LANGUAGE sql STABLE SET search_path=pg_catalog,herman AS $$
    SELECT d.id,d.baseline,o.observed_at,o.origin
    FROM herman.pack_definitions d
    JOIN herman.pack_definition_observations o ON (o.business_id,o.definition_id)=(d.business_id,d.id)
    LEFT JOIN herman.pack_decisions a ON (a.business_id,a.definition_id)=(d.business_id,d.id) AND a.approved
    LEFT JOIN herman.pack_decisions successor
        ON (successor.business_id,successor.predecessor_id)=(d.business_id,d.id) AND successor.approved
    WHERE d.business_id=business AND d.item_id=item
        AND (d.baseline OR (a.decided_at<=a.effective_at AND a.effective_at<=event_time))
        AND (successor.effective_at IS NULL OR event_time<successor.effective_at)
$$;

CREATE FUNCTION herman.pack_binding_context(business uuid,record uuid,ingredient uuid,
    fulfillment uuid,path uuid[])
RETURNS TABLE(item_id uuid,occurred_at timestamptz,legacy boolean)
LANGUAGE plpgsql STABLE SET search_path=pg_catalog,herman AS $$
DECLARE source_kind text; source_legacy boolean; root_product uuid; parent_recipe uuid;
    node uuid; recipe herman.recipes%ROWTYPE; cutoff herman.pack_binding_cutover%ROWTYPE;
BEGIN
    SELECT * INTO STRICT cutoff FROM herman.pack_binding_cutover;
    SELECT r.kind,r.pack_binding_legacy INTO source_kind,source_legacy FROM herman.records r
        WHERE r.business_id=business AND r.id=record;
    IF source_kind IS NULL OR path IS NULL OR array_position(path,NULL) IS NOT NULL
        OR cardinality(path)>33 OR (cardinality(path)>0
            AND (array_ndims(path)<>1 OR array_lower(path,1)<>1))
        OR cardinality(path)<>(SELECT count(DISTINCT x) FROM unnest(path) x) THEN
        RAISE EXCEPTION 'invalid pack context' USING ERRCODE='23514';
    END IF;
    legacy := source_legacy;
    IF source_kind IN ('count','movement','fulfillment') THEN
        IF ingredient IS NOT NULL OR cardinality(path)<>0
            OR (source_kind='fulfillment' AND fulfillment IS DISTINCT FROM record)
            OR (source_kind<>'fulfillment' AND fulfillment IS NOT NULL) THEN
            RAISE EXCEPTION 'invalid direct pack context' USING ERRCODE='23514';
        END IF;
        IF source_kind='count' THEN
            SELECT s.item_id,s.occurred_at INTO item_id,occurred_at FROM herman.stock_counts s
                WHERE s.business_id=business AND s.id=record AND s.unit='pack';
        ELSIF source_kind='movement' THEN
            SELECT s.item_id,s.occurred_at INTO item_id,occurred_at FROM herman.stock_movements s
                WHERE s.business_id=business AND s.id=record AND s.unit='pack';
        ELSE
            SELECT s.product_id,s.occurred_at INTO item_id,occurred_at FROM herman.fulfillments s
                WHERE s.business_id=business AND s.id=record AND s.unit='pack';
        END IF;
    ELSIF source_kind='recipe' THEN
        IF fulfillment IS NULL OR cardinality(path)=0 OR path[array_upper(path,1)]<>record THEN
            RAISE EXCEPTION 'recipe needs originating fulfillment and path' USING ERRCODE='23514';
        END IF;
        SELECT f.product_id,f.occurred_at,r.pack_binding_legacy INTO root_product,occurred_at,source_legacy
            FROM herman.fulfillments f JOIN herman.records r ON (r.business_id,r.id)=(f.business_id,f.id)
            WHERE f.business_id=business AND f.id=fulfillment AND r.kind='fulfillment';
        IF root_product IS NULL THEN
            RAISE EXCEPTION 'invalid root fulfillment' USING ERRCODE='23514';
        END IF;
        legacy := legacy AND source_legacy;
        FOREACH node IN ARRAY path LOOP
            SELECT s.* INTO recipe FROM herman.recipes s JOIN herman.records r
                ON (r.business_id,r.id)=(s.business_id,s.id)
                WHERE s.business_id=business AND s.id=node AND r.kind='recipe'
                    AND s.valid_from<=occurred_at AND (s.valid_to IS NULL OR occurred_at<s.valid_to);
            IF recipe.id IS NULL OR (parent_recipe IS NULL AND recipe.product_id<>root_product)
                OR (parent_recipe IS NOT NULL AND NOT EXISTS(SELECT 1 FROM herman.recipe_lines l
                    WHERE l.business_id=business AND l.recipe_id=parent_recipe AND l.item_id=recipe.product_id)) THEN
                RAISE EXCEPTION 'invalid recipe topology or event validity' USING ERRCODE='23514';
            END IF;
            SELECT r.pack_binding_legacy INTO source_legacy FROM herman.records r WHERE r.business_id=business AND r.id=node;
            legacy := legacy AND source_legacy;
            parent_recipe := node;
        END LOOP;
        IF ingredient IS NULL THEN
            IF recipe.output_unit='pack' THEN item_id := recipe.product_id; END IF;
        ELSE
            SELECT l.item_id INTO item_id FROM herman.recipe_lines l WHERE l.business_id=business
                AND l.recipe_id=record AND l.item_id=ingredient AND l.unit='pack';
        END IF;
    ELSE
        RAISE EXCEPTION 'unsupported pack source' USING ERRCODE='23514';
    END IF;
    IF item_id IS NULL OR occurred_at IS NULL OR occurred_at>clock_timestamp() THEN
        RAISE EXCEPTION 'pack check requires concrete past pack use' USING ERRCODE='23514';
    END IF;
    legacy := legacy AND occurred_at<=cutoff.captured_at;
    RETURN NEXT;
END $$;

CREATE TABLE herman.pack_binding_checks (
    business_id uuid NOT NULL,id uuid NOT NULL,record_id uuid NOT NULL,ingredient_id uuid,
    fulfillment_id uuid,recipe_path uuid[] NOT NULL DEFAULT '{}',item_id uuid NOT NULL,
    occurred_at timestamptz NOT NULL,definition_id uuid,
    origin text NOT NULL CHECK(origin IN ('migration_derived','known_before_event','requires_review')),
    state text NOT NULL CHECK(state IN ('bound','unresolved')),missing_reason text,
    created_by uuid REFERENCES herman.users(id),captured_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY(business_id,id),
    UNIQUE NULLS NOT DISTINCT(business_id,record_id,ingredient_id,fulfillment_id,recipe_path),
    FOREIGN KEY(business_id,record_id) REFERENCES herman.records(business_id,id),
    FOREIGN KEY(business_id,ingredient_id) REFERENCES herman.items(business_id,id),
    FOREIGN KEY(business_id,fulfillment_id) REFERENCES herman.fulfillments(business_id,id),
    FOREIGN KEY(business_id,item_id) REFERENCES herman.items(business_id,id),
    FOREIGN KEY(business_id,definition_id) REFERENCES herman.pack_definitions(business_id,id),
    CHECK((state='bound' AND definition_id IS NOT NULL AND missing_reason IS NULL
            AND origin IN ('migration_derived','known_before_event'))
        OR (state='unresolved' AND definition_id IS NULL AND missing_reason IS NOT NULL AND origin='requires_review'))
);

-- Backfill runs as migration administrator, before runtime guards/RLS are enabled.
INSERT INTO herman.pack_binding_checks(business_id,id,record_id,fulfillment_id,item_id,occurred_at,
    definition_id,origin,state,missing_reason)
SELECT s.business_id,gen_random_uuid(),s.id,s.fulfillment_id,s.item_id,s.occurred_at,
    CASE WHEN count(d.definition_id)=1 THEN (array_agg(d.definition_id))[1] END,
    CASE WHEN count(d.definition_id)=1 THEN
        CASE WHEN bool_and(d.baseline) THEN 'migration_derived' ELSE 'known_before_event' END
        ELSE 'requires_review' END,
    CASE WHEN count(d.definition_id)=1 THEN 'bound' ELSE 'unresolved' END,
    CASE WHEN count(d.definition_id)=0 THEN 'missing_definition' WHEN count(d.definition_id)>1 THEN 'ambiguous_definition' END
FROM (
    SELECT business_id,id,NULL::uuid fulfillment_id,item_id,occurred_at FROM herman.stock_counts WHERE unit='pack'
    UNION ALL SELECT business_id,id,NULL::uuid,item_id,occurred_at FROM herman.stock_movements WHERE unit='pack'
    UNION ALL SELECT business_id,id,id,product_id,occurred_at FROM herman.fulfillments WHERE unit='pack'
) s LEFT JOIN LATERAL herman.pack_binding_candidates(s.business_id,s.item_id,s.occurred_at) d ON true
WHERE s.occurred_at<=(SELECT captured_at FROM herman.pack_binding_cutover)
GROUP BY s.business_id,s.id,s.fulfillment_id,s.item_id,s.occurred_at;

CREATE FUNCTION herman.pack_binding_check_guard() RETURNS trigger LANGUAGE plpgsql
    SET search_path=pg_catalog,herman AS $$
DECLARE context record; candidate record; matches integer; candidate_id uuid;
    candidate_baseline boolean; observation_time timestamptz; observation_origin text;
BEGIN
    IF NEW.business_id IS DISTINCT FROM herman.business_id()
        OR COALESCE(herman.member_role(NEW.business_id),'') NOT IN ('owner','editor','reviewer') THEN
        RAISE EXCEPTION 'pack check requires scoped writer' USING ERRCODE='42501';
    END IF;
    SELECT * INTO STRICT context FROM herman.pack_binding_context(NEW.business_id,NEW.record_id,
        NEW.ingredient_id,NEW.fulfillment_id,NEW.recipe_path);
    NEW.item_id := context.item_id; NEW.occurred_at := context.occurred_at;
    matches := 0;
    FOR candidate IN SELECT * FROM herman.pack_binding_candidates(NEW.business_id,NEW.item_id,NEW.occurred_at) LOOP
        matches := matches+1; candidate_id := candidate.definition_id; candidate_baseline := candidate.baseline;
        observation_time := candidate.observed_at; observation_origin := candidate.observation_origin;
    END LOOP;
    NEW.definition_id := NULL; NEW.state := 'unresolved'; NEW.origin := 'requires_review';
    NEW.missing_reason := CASE WHEN matches=0 THEN 'missing_definition' WHEN matches>1 THEN 'ambiguous_definition'
        ELSE 'baseline_not_known_before_event' END;
    IF matches=1 THEN
        IF NOT candidate_baseline OR observation_time<=NEW.occurred_at THEN
            NEW.definition_id := candidate_id; NEW.state := 'bound'; NEW.origin := 'known_before_event';
        ELSIF context.legacy AND observation_origin='migration_observation' THEN
            NEW.definition_id := candidate_id; NEW.state := 'bound'; NEW.origin := 'migration_derived';
        END IF;
    END IF;
    IF NEW.state='bound' THEN NEW.missing_reason := NULL; END IF;
    NEW.created_by := herman.user_id(); NEW.captured_at := clock_timestamp();
    RETURN NEW;
END $$;
CREATE TRIGGER pack_binding_check_guard BEFORE INSERT ON herman.pack_binding_checks
    FOR EACH ROW EXECUTE FUNCTION herman.pack_binding_check_guard();

CREATE FUNCTION herman.pack_capture_direct_check() RETURNS trigger LANGUAGE plpgsql
    SET search_path=pg_catalog,herman AS $$
BEGIN
    IF NEW.unit='pack' AND NEW.occurred_at<=clock_timestamp() THEN
        INSERT INTO herman.pack_binding_checks(business_id,id,record_id,fulfillment_id)
            VALUES(NEW.business_id,gen_random_uuid(),NEW.id,CASE WHEN TG_TABLE_NAME='fulfillments' THEN NEW.id END);
    END IF;
    RETURN NEW;
END $$;
DO $$ DECLARE t text; BEGIN
    FOREACH t IN ARRAY ARRAY['stock_counts','stock_movements','fulfillments'] LOOP
        EXECUTE format('CREATE TRIGGER pack_capture_direct_check AFTER INSERT ON herman.%I '
            || 'FOR EACH ROW EXECUTE FUNCTION herman.pack_capture_direct_check()',t);
    END LOOP;
END $$;

CREATE TABLE herman.pack_binding_reviews (
    business_id uuid NOT NULL,id uuid NOT NULL,check_id uuid NOT NULL,approved boolean NOT NULL,
    definition_id uuid,actor_id uuid NOT NULL REFERENCES herman.users(id),
    reason_fa text NOT NULL CHECK(length(btrim(reason_fa)) BETWEEN 1 AND 2000),
    document_id uuid NOT NULL,locator text NOT NULL CHECK(length(btrim(locator)) BETWEEN 1 AND 500),
    decided_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY(business_id,id),
    FOREIGN KEY(business_id,check_id) REFERENCES herman.pack_binding_checks(business_id,id),
    FOREIGN KEY(business_id,definition_id) REFERENCES herman.pack_definitions(business_id,id),
    FOREIGN KEY(business_id,document_id) REFERENCES herman.documents(business_id,id),
    CHECK((approved AND definition_id IS NOT NULL) OR (NOT approved AND definition_id IS NULL))
);
CREATE UNIQUE INDEX pack_binding_one_approval ON herman.pack_binding_reviews(business_id,check_id) WHERE approved;
CREATE INDEX pack_binding_review_history ON herman.pack_binding_reviews(business_id,check_id,id);
CREATE FUNCTION herman.pack_binding_review_guard() RETURNS trigger LANGUAGE plpgsql
    SET search_path=pg_catalog,herman AS $$
DECLARE target herman.pack_binding_checks%ROWTYPE;
BEGIN
    IF NEW.business_id IS DISTINCT FROM herman.business_id() OR NEW.actor_id IS DISTINCT FROM herman.user_id()
        OR COALESCE(herman.member_role(NEW.business_id),'') NOT IN ('owner','reviewer') THEN
        RAISE EXCEPTION 'pack binding decision requires scoped reviewer' USING ERRCODE='42501';
    END IF;
    SELECT * INTO target FROM herman.pack_binding_checks WHERE business_id=NEW.business_id AND id=NEW.check_id;
    IF target.id IS NULL OR target.state<>'unresolved' THEN
        RAISE EXCEPTION 'only unresolved pack checks may be reviewed' USING ERRCODE='23514';
    END IF;
    IF NEW.approved AND NOT EXISTS(SELECT 1 FROM herman.pack_binding_candidates(
        NEW.business_id,target.item_id,target.occurred_at) c WHERE c.definition_id=NEW.definition_id) THEN
        RAISE EXCEPTION 'review needs eligible event-time definition' USING ERRCODE='23514';
    END IF;
    NEW.decided_at := clock_timestamp();
    RETURN NEW;
END $$;
CREATE TRIGGER pack_binding_review_guard BEFORE INSERT ON herman.pack_binding_reviews
    FOR EACH ROW EXECUTE FUNCTION herman.pack_binding_review_guard();

DO $$ DECLARE t text; BEGIN
    FOREACH t IN ARRAY ARRAY['pack_definition_observations','pack_binding_checks','pack_binding_reviews'] LOOP
        EXECUTE format('ALTER TABLE herman.%I ENABLE ROW LEVEL SECURITY',t);
        EXECUTE format('ALTER TABLE herman.%I FORCE ROW LEVEL SECURITY',t);
        EXECUTE format('CREATE POLICY tenant_read ON herman.%I FOR SELECT USING '
            || '(business_id=herman.business_id() AND herman.member_role(business_id) IS NOT NULL)',t);
        EXECUTE format('CREATE TRIGGER append_only BEFORE UPDATE OR DELETE ON herman.%I '
            || 'FOR EACH ROW EXECUTE FUNCTION herman.immutable_record()',t);
    END LOOP;
END $$;
CREATE POLICY trigger_insert ON herman.pack_definition_observations FOR INSERT WITH CHECK (
    pg_trigger_depth()>0 AND business_id=herman.business_id()
    AND herman.member_role(business_id) IN ('owner','editor','reviewer'));
CREATE POLICY tenant_insert ON herman.pack_binding_checks FOR INSERT WITH CHECK (
    business_id=herman.business_id() AND created_by=herman.user_id()
    AND herman.member_role(business_id) IN ('owner','editor','reviewer'));
CREATE POLICY tenant_insert ON herman.pack_binding_reviews FOR INSERT WITH CHECK (
    business_id=herman.business_id() AND actor_id=herman.user_id()
    AND herman.member_role(business_id) IN ('owner','reviewer'));
REVOKE ALL ON herman.pack_binding_cutover,herman.pack_definition_observations,
    herman.pack_binding_checks,herman.pack_binding_reviews FROM PUBLIC;
REVOKE ALL ON FUNCTION herman.pack_observe_definition(),herman.pack_binding_check_guard(),
    herman.pack_binding_stamp_source(),
    herman.pack_capture_direct_check(),herman.pack_binding_review_guard(),
    herman.pack_binding_context(uuid,uuid,uuid,uuid,uuid[]),
    herman.pack_binding_candidates(uuid,uuid,timestamptz) FROM PUBLIC;
INSERT INTO herman.schema_migrations(version) VALUES(18);
