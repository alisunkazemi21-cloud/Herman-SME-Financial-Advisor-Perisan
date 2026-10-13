CREATE TABLE herman.pack_definitions (
    business_id uuid NOT NULL, id uuid NOT NULL, item_id uuid NOT NULL,
    predecessor_id uuid, base_quantity numeric(24,6) NOT NULL CHECK(base_quantity>0),
    document_id uuid NOT NULL, locator text NOT NULL CHECK(length(btrim(locator)) BETWEEN 1 AND 500),
    baseline boolean NOT NULL DEFAULT false, created_by uuid REFERENCES herman.users(id),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY(business_id,id),
    FOREIGN KEY(business_id,item_id) REFERENCES herman.items(business_id,id),
    FOREIGN KEY(business_id,document_id) REFERENCES herman.documents(business_id,id),
    FOREIGN KEY(business_id,predecessor_id) REFERENCES herman.pack_definitions(business_id,id),
    CHECK(predecessor_id IS DISTINCT FROM id),
    CHECK((baseline AND predecessor_id IS NULL AND created_by IS NULL)
       OR (NOT baseline AND predecessor_id IS NOT NULL AND created_by IS NOT NULL))
);
CREATE UNIQUE INDEX pack_one_baseline ON herman.pack_definitions(business_id,item_id) WHERE baseline;
CREATE INDEX pack_history ON herman.pack_definitions(business_id,item_id,id);
CREATE TABLE herman.pack_decisions (
    business_id uuid NOT NULL, definition_id uuid NOT NULL, predecessor_id uuid NOT NULL,
    approved boolean NOT NULL, actor_id uuid NOT NULL REFERENCES herman.users(id),
    reason_fa text NOT NULL CHECK(length(btrim(reason_fa)) BETWEEN 1 AND 2000),
    decided_at timestamptz NOT NULL DEFAULT clock_timestamp(), effective_at timestamptz,
    PRIMARY KEY(business_id,definition_id),
    FOREIGN KEY(business_id,definition_id) REFERENCES herman.pack_definitions(business_id,id),
    FOREIGN KEY(business_id,predecessor_id) REFERENCES herman.pack_definitions(business_id,id),
    CHECK((approved AND effective_at IS NOT NULL AND effective_at>=decided_at)
        OR (NOT approved AND effective_at IS NULL))
);
CREATE UNIQUE INDEX pack_one_successor ON herman.pack_decisions(business_id,predecessor_id) WHERE approved;

-- Baselines describe existing data, not retrospective human approvals.
INSERT INTO herman.pack_definitions(business_id,id,item_id,base_quantity,document_id,locator,baseline)
    SELECT business_id,id,item_id,base_quantity,document_id,locator,true FROM herman.unit_conversions;

CREATE FUNCTION herman.pack_definition_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE previous herman.pack_definitions%ROWTYPE;
BEGIN
    NEW.created_at := clock_timestamp();
    IF NEW.baseline THEN
        IF pg_trigger_depth()<2 OR NOT EXISTS (
            SELECT 1 FROM herman.unit_conversions c WHERE (c.business_id,c.id,c.item_id,c.base_quantity,
                c.document_id,c.locator)=(NEW.business_id,NEW.id,NEW.item_id,NEW.base_quantity,
                NEW.document_id,NEW.locator)) THEN
            RAISE EXCEPTION 'baseline must originate from conversion insert' USING ERRCODE='23514';
        END IF;
    ELSE
        IF NEW.created_by IS DISTINCT FROM herman.user_id() THEN
            RAISE EXCEPTION 'definition author mismatch' USING ERRCODE='42501';
        END IF;
        SELECT * INTO previous FROM herman.pack_definitions
            WHERE business_id=NEW.business_id AND id=NEW.predecessor_id;
        IF previous.id IS NULL OR previous.item_id<>NEW.item_id
            OR (NOT previous.baseline AND NOT EXISTS(SELECT 1 FROM herman.pack_decisions
                WHERE business_id=NEW.business_id AND definition_id=previous.id AND approved))
            OR EXISTS(SELECT 1 FROM herman.pack_decisions
                WHERE business_id=NEW.business_id AND predecessor_id=previous.id AND approved) THEN
            RAISE EXCEPTION 'definition needs current eligible predecessor' USING ERRCODE='23514';
        END IF;
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER pack_definition_guard BEFORE INSERT ON herman.pack_definitions
    FOR EACH ROW EXECUTE FUNCTION herman.pack_definition_guard();

CREATE FUNCTION herman.pack_capture_baseline() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    INSERT INTO herman.pack_definitions(business_id,id,item_id,base_quantity,document_id,locator,baseline)
        VALUES(NEW.business_id,NEW.id,NEW.item_id,NEW.base_quantity,NEW.document_id,NEW.locator,true);
    RETURN NEW;
END $$;
CREATE TRIGGER pack_capture_baseline AFTER INSERT ON herman.unit_conversions
    FOR EACH ROW EXECUTE FUNCTION herman.pack_capture_baseline();

CREATE FUNCTION herman.pack_review_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE proposal herman.pack_definitions%ROWTYPE; previous_time timestamptz;
BEGIN
    IF NEW.actor_id IS DISTINCT FROM herman.user_id()
        OR COALESCE(herman.member_role(NEW.business_id),'') NOT IN ('owner','reviewer') THEN
        RAISE EXCEPTION 'pack decision requires reviewer' USING ERRCODE='42501';
    END IF;
    SELECT * INTO proposal FROM herman.pack_definitions
        WHERE business_id=NEW.business_id AND id=NEW.definition_id;
    IF proposal.id IS NULL OR proposal.baseline THEN
        RAISE EXCEPTION 'only proposed replacement may be decided' USING ERRCODE='23514';
    END IF;
    NEW.predecessor_id := proposal.predecessor_id;
    NEW.decided_at := clock_timestamp();
    IF NEW.approved THEN
        NEW.effective_at := COALESCE(NEW.effective_at,NEW.decided_at);
        SELECT effective_at INTO previous_time FROM herman.pack_decisions
            WHERE business_id=NEW.business_id AND definition_id=NEW.predecessor_id AND approved;
        IF previous_time IS NOT NULL AND NEW.effective_at<=previous_time THEN
            RAISE EXCEPTION 'successor must activate after predecessor' USING ERRCODE='23514';
        END IF;
    ELSE
        NEW.effective_at := NULL;
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER pack_review_guard BEFORE INSERT ON herman.pack_decisions
    FOR EACH ROW EXECUTE FUNCTION herman.pack_review_guard();

DO $$ DECLARE t text; BEGIN
    FOREACH t IN ARRAY ARRAY['pack_definitions','pack_decisions'] LOOP
        EXECUTE format('ALTER TABLE herman.%I ENABLE ROW LEVEL SECURITY',t);
        EXECUTE format('ALTER TABLE herman.%I FORCE ROW LEVEL SECURITY',t);
        EXECUTE format('CREATE POLICY tenant_read ON herman.%I FOR SELECT USING '
            || '(business_id=herman.business_id() AND herman.member_role(business_id) IS NOT NULL)',t);
        EXECUTE format('CREATE TRIGGER append_only BEFORE UPDATE OR DELETE ON herman.%I '
            || 'FOR EACH ROW EXECUTE FUNCTION herman.immutable_record()',t);
    END LOOP;
END $$;
CREATE POLICY tenant_insert ON herman.pack_definitions FOR INSERT WITH CHECK (
    business_id=herman.business_id() AND (
        (NOT baseline AND created_by=herman.user_id()
            AND herman.member_role(business_id) IN ('owner','editor','reviewer'))
        OR (baseline AND herman.member_role(business_id) IN ('owner','reviewer'))));
CREATE POLICY tenant_insert ON herman.pack_decisions FOR INSERT WITH CHECK (
    business_id=herman.business_id() AND actor_id=herman.user_id()
    AND herman.member_role(business_id) IN ('owner','reviewer'));
INSERT INTO herman.schema_migrations(version) VALUES(15);
