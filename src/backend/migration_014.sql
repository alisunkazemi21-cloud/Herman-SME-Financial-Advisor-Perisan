ALTER TABLE herman.records ADD COLUMN supersedes uuid, ADD COLUMN created_xid xid8,
    ADD FOREIGN KEY(business_id,supersedes) REFERENCES herman.records(business_id,id),
    ADD CHECK(supersedes IS NULL OR supersedes<>id);
ALTER TABLE herman.approvals ADD COLUMN supersedes uuid;
ALTER TABLE herman.analysis_runs ADD COLUMN correction_provenance jsonb NOT NULL DEFAULT '[]'::jsonb;
CREATE INDEX record_predecessor_idx ON herman.records(business_id,supersedes,id) WHERE supersedes IS NOT NULL;
CREATE UNIQUE INDEX inventory_one_replacement ON herman.approvals(business_id,supersedes)
    WHERE approved AND supersedes IS NOT NULL;

CREATE FUNCTION herman.inventory_stamp() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    NEW.created_xid := pg_current_xact_id();
    IF NEW.supersedes IS NOT NULL AND (
        NOT EXISTS (SELECT 1 FROM herman.records r JOIN herman.approvals a
            ON (a.business_id,a.record_id)=(r.business_id,r.id)
            WHERE r.business_id=NEW.business_id AND r.id=NEW.supersedes AND r.kind=NEW.kind AND a.approved)
        OR EXISTS (SELECT 1 FROM herman.approvals a WHERE a.business_id=NEW.business_id
            AND a.supersedes=NEW.supersedes AND a.approved)
    ) THEN RAISE EXCEPTION 'correction needs current approved predecessor of same kind' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER inventory_stamp BEFORE INSERT ON herman.records
    FOR EACH ROW EXECUTE FUNCTION herman.inventory_stamp();

CREATE FUNCTION herman.inventory_detail_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE target uuid; expected text;
BEGIN
    IF TG_TABLE_NAME='recipe_lines' THEN target := NEW.recipe_id; ELSE target := NEW.id; END IF;
    expected := CASE TG_TABLE_NAME WHEN 'stock_counts' THEN 'count' WHEN 'stock_movements' THEN 'movement'
        WHEN 'fulfillments' THEN 'fulfillment' WHEN 'recipes' THEN 'recipe' WHEN 'recipe_lines' THEN 'recipe' END;
    IF NOT EXISTS (SELECT 1 FROM herman.records r WHERE r.business_id=NEW.business_id AND r.id=target
        AND r.created_xid=pg_current_xact_id() AND (expected IS NULL OR r.kind=expected)
        AND (TG_TABLE_NAME<>'record_sources' OR r.supersedes IS NULL)
        AND NOT EXISTS (SELECT 1 FROM herman.approvals a
            WHERE a.business_id=r.business_id AND a.record_id=r.id)) THEN
        RAISE EXCEPTION 'inventory details must be inserted with unreviewed header of matching kind'
            USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END $$;
DO $$ DECLARE t text; BEGIN
    FOREACH t IN ARRAY ARRAY['stock_counts','stock_movements','recipes','recipe_lines','fulfillments','record_sources'] LOOP
        EXECUTE format('CREATE TRIGGER inventory_detail_guard BEFORE INSERT ON herman.%I '
            || 'FOR EACH ROW EXECUTE FUNCTION herman.inventory_detail_guard()',t);
    END LOOP;
END $$;

CREATE FUNCTION herman.inventory_structure(business uuid, identity uuid) RETURNS void LANGUAGE plpgsql AS $$
DECLARE record herman.records%ROWTYPE; valid boolean;
BEGIN
    SELECT * INTO STRICT record FROM herman.records WHERE business_id=business AND id=identity;
    valid := CASE record.kind
        WHEN 'count' THEN EXISTS(SELECT 1 FROM herman.stock_counts WHERE business_id=business AND id=identity)
        WHEN 'movement' THEN EXISTS(SELECT 1 FROM herman.stock_movements WHERE business_id=business AND id=identity)
        WHEN 'fulfillment' THEN EXISTS(SELECT 1 FROM herman.fulfillments WHERE business_id=business AND id=identity)
        WHEN 'recipe' THEN EXISTS(SELECT 1 FROM herman.recipes WHERE business_id=business AND id=identity)
            AND EXISTS(SELECT 1 FROM herman.recipe_lines WHERE business_id=business AND recipe_id=identity)
        ELSE false END;
    IF NOT valid THEN RAISE EXCEPTION 'inventory record needs complete typed detail' USING ERRCODE='23514'; END IF;
END $$;
CREATE FUNCTION herman.inventory_complete() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    PERFORM herman.inventory_structure(NEW.business_id,NEW.id);
    RETURN NEW;
END $$;
CREATE CONSTRAINT TRIGGER inventory_complete AFTER INSERT ON herman.records
    DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION herman.inventory_complete();

CREATE FUNCTION herman.inventory_review_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE record herman.records%ROWTYPE;
BEGIN
    -- RLS remains authoritative, including for attempts to review a nonexistent row.
    IF NEW.actor_id IS DISTINCT FROM herman.user_id()
        OR herman.member_role(NEW.business_id) NOT IN ('owner','reviewer') THEN
        RAISE EXCEPTION 'inventory review requires reviewer' USING ERRCODE='42501';
    END IF;
    SELECT * INTO STRICT record FROM herman.records WHERE business_id=NEW.business_id AND id=NEW.record_id;
    PERFORM herman.inventory_structure(NEW.business_id,NEW.record_id);
    NEW.supersedes := record.supersedes;
    IF NEW.approved AND NEW.supersedes IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM herman.records r JOIN herman.approvals a ON (a.business_id,a.record_id)=(r.business_id,r.id)
        WHERE r.business_id=NEW.business_id AND r.id=NEW.supersedes AND r.kind=record.kind AND a.approved
    ) THEN RAISE EXCEPTION 'correction review needs approved predecessor' USING ERRCODE='23514'; END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER inventory_review_guard BEFORE INSERT ON herman.approvals
    FOR EACH ROW EXECUTE FUNCTION herman.inventory_review_guard();
INSERT INTO herman.schema_migrations(version) VALUES(14);
