CREATE EXTENSION IF NOT EXISTS btree_gist WITH SCHEMA public;

CREATE TABLE herman.item_definitions (
    business_id uuid NOT NULL, id uuid NOT NULL, item_id uuid NOT NULL,
    predecessor_id uuid, sku text NOT NULL, name_fa text NOT NULL,
    document_id uuid, locator text, baseline boolean NOT NULL DEFAULT false,
    created_by uuid REFERENCES herman.users(id), created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY(business_id,id),
    FOREIGN KEY(business_id,item_id) REFERENCES herman.items(business_id,id),
    FOREIGN KEY(business_id,document_id) REFERENCES herman.documents(business_id,id),
    FOREIGN KEY(business_id,predecessor_id) REFERENCES herman.item_definitions(business_id,id),
    CHECK(predecessor_id IS DISTINCT FROM id),
    CHECK((baseline AND id=item_id AND predecessor_id IS NULL AND created_by IS NULL
            AND document_id IS NULL AND locator IS NULL)
        OR (NOT baseline AND predecessor_id IS NOT NULL AND created_by IS NOT NULL
            AND document_id IS NOT NULL AND locator IS NOT NULL
            AND length(btrim(locator)) BETWEEN 1 AND 500
            AND length(btrim(sku)) BETWEEN 1 AND 100 AND length(btrim(name_fa)) BETWEEN 1 AND 200))
);
CREATE UNIQUE INDEX item_one_baseline ON herman.item_definitions(business_id,item_id) WHERE baseline;
CREATE INDEX item_definition_history ON herman.item_definitions(business_id,item_id,id);

CREATE TABLE herman.item_decisions (
    business_id uuid NOT NULL, definition_id uuid NOT NULL, predecessor_id uuid NOT NULL,
    approved boolean NOT NULL, actor_id uuid NOT NULL REFERENCES herman.users(id),
    reason_fa text NOT NULL CHECK(length(btrim(reason_fa)) BETWEEN 1 AND 2000),
    decided_at timestamptz NOT NULL DEFAULT clock_timestamp(), effective_at timestamptz,
    PRIMARY KEY(business_id,definition_id),
    FOREIGN KEY(business_id,definition_id) REFERENCES herman.item_definitions(business_id,id),
    FOREIGN KEY(business_id,predecessor_id) REFERENCES herman.item_definitions(business_id,id),
    CHECK((approved AND effective_at IS NOT NULL AND effective_at>=decided_at)
        OR (NOT approved AND effective_at IS NULL))
);
CREATE UNIQUE INDEX item_one_successor ON herman.item_decisions(business_id,predecessor_id) WHERE approved;

-- This index projection is derived state; definitions and decisions retain the immutable history.
CREATE TABLE herman.item_alias_periods (
    business_id uuid NOT NULL, definition_id uuid NOT NULL, item_id uuid NOT NULL,
    sku text NOT NULL, validity tstzrange NOT NULL CHECK(NOT isempty(validity)),
    PRIMARY KEY(business_id,definition_id),
    FOREIGN KEY(business_id,definition_id) REFERENCES herman.item_definitions(business_id,id),
    FOREIGN KEY(business_id,item_id) REFERENCES herman.items(business_id,id),
    EXCLUDE USING gist (business_id WITH =, sku WITH =, validity WITH &&)
);
CREATE INDEX item_alias_item_history ON herman.item_alias_periods(business_id,item_id,definition_id);

INSERT INTO herman.item_definitions(business_id,id,item_id,sku,name_fa,baseline)
    SELECT business_id,id,id,sku,name_fa,true FROM herman.items;
INSERT INTO herman.item_alias_periods(business_id,definition_id,item_id,sku,validity)
    SELECT business_id,id,item_id,sku,tstzrange(NULL,NULL,'[)') FROM herman.item_definitions WHERE baseline;

ALTER TABLE herman.record_sources ADD COLUMN item_definition_id uuid;
ALTER TABLE herman.record_sources ADD FOREIGN KEY(business_id,item_definition_id)
    REFERENCES herman.item_definitions(business_id,id);

CREATE FUNCTION herman.item_definition_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE previous herman.item_definitions%ROWTYPE;
BEGIN
    NEW.created_at := clock_timestamp();
    IF NEW.baseline THEN
        IF pg_trigger_depth()<2 OR NOT EXISTS (
            SELECT 1 FROM herman.items i WHERE (i.business_id,i.id,i.sku,i.name_fa)
                =(NEW.business_id,NEW.id,NEW.sku,NEW.name_fa)) THEN
            RAISE EXCEPTION 'baseline must originate from item insert' USING ERRCODE='23514';
        END IF;
    ELSE
        IF NEW.created_by IS DISTINCT FROM herman.user_id() THEN
            RAISE EXCEPTION 'definition author mismatch' USING ERRCODE='42501';
        END IF;
        SELECT * INTO previous FROM herman.item_definitions
            WHERE business_id=NEW.business_id AND id=NEW.predecessor_id;
        IF previous.id IS NULL OR previous.item_id<>NEW.item_id
            OR (NOT previous.baseline AND NOT EXISTS(SELECT 1 FROM herman.item_decisions
                WHERE business_id=NEW.business_id AND definition_id=previous.id AND approved))
            OR EXISTS(SELECT 1 FROM herman.item_decisions
                WHERE business_id=NEW.business_id AND predecessor_id=previous.id AND approved) THEN
            RAISE EXCEPTION 'definition needs current eligible predecessor' USING ERRCODE='23514';
        END IF;
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER item_definition_guard BEFORE INSERT ON herman.item_definitions
    FOR EACH ROW EXECUTE FUNCTION herman.item_definition_guard();

CREATE FUNCTION herman.item_capture_baseline() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    INSERT INTO herman.item_definitions(business_id,id,item_id,sku,name_fa,baseline)
        VALUES(NEW.business_id,NEW.id,NEW.id,NEW.sku,NEW.name_fa,true);
    RETURN NEW;
END $$;
CREATE TRIGGER item_capture_baseline AFTER INSERT ON herman.items
    FOR EACH ROW EXECUTE FUNCTION herman.item_capture_baseline();

CREATE FUNCTION herman.item_review_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE proposal herman.item_definitions%ROWTYPE; previous_time timestamptz;
BEGIN
    IF NEW.actor_id IS DISTINCT FROM herman.user_id()
        OR COALESCE(herman.member_role(NEW.business_id),'') NOT IN ('owner','reviewer') THEN
        RAISE EXCEPTION 'item decision requires reviewer' USING ERRCODE='42501';
    END IF;
    SELECT * INTO proposal FROM herman.item_definitions
        WHERE business_id=NEW.business_id AND id=NEW.definition_id;
    IF proposal.id IS NULL OR proposal.baseline THEN
        RAISE EXCEPTION 'only proposed replacement may be decided' USING ERRCODE='23514';
    END IF;
    NEW.predecessor_id := proposal.predecessor_id;
    NEW.decided_at := clock_timestamp();
    IF NEW.approved THEN
        NEW.effective_at := COALESCE(NEW.effective_at,NEW.decided_at);
        SELECT effective_at INTO previous_time FROM herman.item_decisions
            WHERE business_id=NEW.business_id AND definition_id=NEW.predecessor_id AND approved;
        IF previous_time IS NOT NULL AND NEW.effective_at<=previous_time THEN
            RAISE EXCEPTION 'successor must activate after predecessor' USING ERRCODE='23514';
        END IF;
    ELSE
        NEW.effective_at := NULL;
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER item_review_guard BEFORE INSERT ON herman.item_decisions
    FOR EACH ROW EXECUTE FUNCTION herman.item_review_guard();

CREATE FUNCTION herman.item_publish_alias() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
    SET search_path=pg_catalog,herman AS $$
DECLARE proposal herman.item_definitions%ROWTYPE;
BEGIN
    IF NEW.business_id IS DISTINCT FROM herman.business_id()
        OR COALESCE(herman.member_role(NEW.business_id),'') NOT IN ('owner','editor','reviewer') THEN
        RAISE EXCEPTION 'alias maintenance requires scoped membership' USING ERRCODE='42501';
    END IF;
    IF TG_TABLE_NAME='item_definitions' THEN
        IF NEW.baseline THEN
            INSERT INTO herman.item_alias_periods(business_id,definition_id,item_id,sku,validity)
                VALUES(NEW.business_id,NEW.id,NEW.item_id,NEW.sku,tstzrange(NULL,NULL,'[)'));
        END IF;
    ELSIF NEW.approved THEN
        SELECT * INTO proposal FROM herman.item_definitions
            WHERE business_id=NEW.business_id AND id=NEW.definition_id;
        UPDATE herman.item_alias_periods
            SET validity=tstzrange(lower(validity),NEW.effective_at,'[)')
            WHERE business_id=NEW.business_id AND definition_id=NEW.predecessor_id AND upper_inf(validity);
        IF NOT FOUND THEN
            RAISE EXCEPTION 'predecessor alias is not current' USING ERRCODE='23514';
        END IF;
        INSERT INTO herman.item_alias_periods(business_id,definition_id,item_id,sku,validity)
            VALUES(NEW.business_id,proposal.id,proposal.item_id,proposal.sku,
                tstzrange(NEW.effective_at,NULL,'[)'));
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER item_publish_baseline AFTER INSERT ON herman.item_definitions
    FOR EACH ROW EXECUTE FUNCTION herman.item_publish_alias();
CREATE TRIGGER item_publish_decision AFTER INSERT ON herman.item_decisions
    FOR EACH ROW EXECUTE FUNCTION herman.item_publish_alias();

CREATE FUNCTION herman.record_source_item_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE target_item uuid; event_time timestamptz;
BEGIN
    IF NEW.item_definition_id IS NULL THEN RETURN NEW; END IF;
    IF NEW.record_kind='count' THEN
        SELECT item_id,occurred_at INTO target_item,event_time FROM herman.stock_counts
            WHERE business_id=NEW.business_id AND id=NEW.id;
    ELSIF NEW.record_kind='movement' THEN
        SELECT item_id,occurred_at INTO target_item,event_time FROM herman.stock_movements
            WHERE business_id=NEW.business_id AND id=NEW.id;
    ELSIF NEW.record_kind='fulfillment' THEN
        SELECT product_id,occurred_at INTO target_item,event_time FROM herman.fulfillments
            WHERE business_id=NEW.business_id AND id=NEW.id;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM herman.item_alias_periods p
        WHERE p.business_id=NEW.business_id AND p.definition_id=NEW.item_definition_id
            AND p.item_id=target_item AND p.validity @> event_time) THEN
        RAISE EXCEPTION 'source item definition must match record item and event time' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER record_source_item_guard BEFORE INSERT ON herman.record_sources
    FOR EACH ROW EXECUTE FUNCTION herman.record_source_item_guard();

DO $$ DECLARE t text; BEGIN
    FOREACH t IN ARRAY ARRAY['item_definitions','item_decisions','item_alias_periods'] LOOP
        EXECUTE format('ALTER TABLE herman.%I ENABLE ROW LEVEL SECURITY',t);
        EXECUTE format('ALTER TABLE herman.%I FORCE ROW LEVEL SECURITY',t);
        EXECUTE format('CREATE POLICY tenant_read ON herman.%I FOR SELECT USING '
            || '(business_id=herman.business_id() AND herman.member_role(business_id) IS NOT NULL)',t);
        IF t<>'item_alias_periods' THEN
            EXECUTE format('CREATE TRIGGER append_only BEFORE UPDATE OR DELETE ON herman.%I '
                || 'FOR EACH ROW EXECUTE FUNCTION herman.immutable_record()',t);
        END IF;
    END LOOP;
END $$;
CREATE POLICY tenant_insert ON herman.item_definitions FOR INSERT WITH CHECK (
    business_id=herman.business_id() AND herman.member_role(business_id) IN ('owner','editor','reviewer')
    AND ((NOT baseline AND created_by=herman.user_id()) OR (baseline AND pg_trigger_depth()>0)));
CREATE POLICY tenant_insert ON herman.item_decisions FOR INSERT WITH CHECK (
    business_id=herman.business_id() AND actor_id=herman.user_id()
    AND herman.member_role(business_id) IN ('owner','reviewer'));
CREATE POLICY trigger_insert ON herman.item_alias_periods FOR INSERT WITH CHECK (
    pg_trigger_depth()>0 AND business_id=herman.business_id()
    AND herman.member_role(business_id) IN ('owner','editor','reviewer'));
CREATE POLICY trigger_update ON herman.item_alias_periods FOR UPDATE USING (
    pg_trigger_depth()>0 AND business_id=herman.business_id()
    AND herman.member_role(business_id) IN ('owner','editor','reviewer')) WITH CHECK (
    pg_trigger_depth()>0 AND business_id=herman.business_id()
    AND herman.member_role(business_id) IN ('owner','editor','reviewer'));
REVOKE ALL ON herman.item_definitions, herman.item_decisions, herman.item_alias_periods FROM PUBLIC;
REVOKE ALL ON FUNCTION herman.item_definition_guard(), herman.item_capture_baseline(),
    herman.item_review_guard(), herman.item_publish_alias(), herman.record_source_item_guard() FROM PUBLIC;
INSERT INTO herman.schema_migrations(version) VALUES(17);
