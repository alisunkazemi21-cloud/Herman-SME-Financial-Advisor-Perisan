CREATE TABLE herman.journal_import_batches (
    business_id uuid NOT NULL, id uuid NOT NULL, extraction_id uuid NOT NULL, document_id uuid NOT NULL,
    source_sha256 text NOT NULL CHECK(source_sha256 ~ '^[a-f0-9]{64}$'), mapping jsonb NOT NULL,
    created_xid xid8 NOT NULL, created_by uuid NOT NULL REFERENCES herman.users(id),
    created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(business_id,id),
    FOREIGN KEY(business_id,extraction_id) REFERENCES herman.extractions(business_id,id),
    FOREIGN KEY(business_id,document_id) REFERENCES herman.documents(business_id,id)
);
CREATE TABLE herman.journal_import_sources (
    business_id uuid NOT NULL, batch_id uuid NOT NULL, entry_id uuid NOT NULL, line_number integer NOT NULL,
    sheet text NOT NULL CHECK(length(sheet) BETWEEN 1 AND 200), source_row integer NOT NULL CHECK(source_row BETWEEN 2 AND 1048576),
    source_sha256 text NOT NULL CHECK(source_sha256 ~ '^[a-f0-9]{64}$'), source_values jsonb NOT NULL,
    created_by uuid NOT NULL REFERENCES herman.users(id),
    PRIMARY KEY(business_id,entry_id,line_number), UNIQUE(business_id,source_sha256,sheet,source_row),
    FOREIGN KEY(business_id,batch_id) REFERENCES herman.journal_import_batches(business_id,id),
    FOREIGN KEY(business_id,entry_id,line_number) REFERENCES herman.journal_lines(business_id,entry_id,line_number)
);
CREATE INDEX journal_import_batch_sources ON herman.journal_import_sources(business_id,batch_id,entry_id,line_number);
CREATE TRIGGER stamp BEFORE INSERT ON herman.journal_import_batches FOR EACH ROW EXECUTE FUNCTION herman.journal_stamp();
CREATE FUNCTION herman.journal_source_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NOT EXISTS(
        SELECT 1 FROM herman.journal_import_batches b
        JOIN herman.extractions e ON (e.business_id,e.id)=(b.business_id,b.extraction_id)
        JOIN herman.extraction_jobs j ON (j.business_id,j.id)=(e.business_id,e.job_id)
        JOIN herman.documents d ON (d.business_id,d.id)=(b.business_id,b.document_id)
        JOIN herman.journal_entries h ON h.business_id=b.business_id AND h.id=NEW.entry_id
        JOIN herman.journal_lines l ON l.business_id=h.business_id AND l.entry_id=h.id AND l.line_number=NEW.line_number
        WHERE b.business_id=NEW.business_id AND b.id=NEW.batch_id
          AND b.created_xid=pg_current_xact_id() AND h.created_xid=pg_current_xact_id()
          AND b.created_by=NEW.created_by AND h.created_by=NEW.created_by
          AND j.status='succeeded' AND j.document_id=b.document_id AND l.document_id=b.document_id
          AND b.source_sha256=NEW.source_sha256 AND e.source_sha256=NEW.source_sha256 AND d.sha256=NEW.source_sha256
          AND e.payload->>'extraction_method' IN ('csv','excel')
          AND b.mapping->>'extraction_id'=b.extraction_id::text AND b.mapping->>'sheet'=NEW.sheet
          AND (b.mapping->'rows') @> jsonb_build_array(NEW.source_row)
          AND l.locator=format('%s:row:%s',NEW.sheet,NEW.source_row)
          AND EXISTS(SELECT 1 FROM jsonb_array_elements(e.payload->'structured_data'->'rows') r
                     WHERE r->>'sheet'=NEW.sheet AND r->>'row'=NEW.source_row::text AND r->'values'=NEW.source_values)
    ) THEN RAISE EXCEPTION 'inconsistent or late journal import source' USING ERRCODE='23514'; END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER source_guard BEFORE INSERT ON herman.journal_import_sources FOR EACH ROW EXECUTE FUNCTION herman.journal_source_guard();
CREATE FUNCTION herman.journal_batch_complete() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE target uuid; expected integer; actual integer;
BEGIN
    IF TG_TABLE_NAME='journal_import_batches' THEN target:=NEW.id; ELSE target:=NEW.batch_id; END IF;
    SELECT jsonb_array_length(mapping->'rows') INTO expected FROM herman.journal_import_batches WHERE business_id=NEW.business_id AND id=target;
    SELECT count(*) INTO actual FROM herman.journal_import_sources WHERE business_id=NEW.business_id AND batch_id=target;
    IF expected IS NULL OR expected NOT BETWEEN 2 AND 500 OR actual<>expected
    THEN RAISE EXCEPTION 'journal import must contain complete source rows' USING ERRCODE='23514'; END IF;
    RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER batch_complete AFTER INSERT ON herman.journal_import_batches
    DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION herman.journal_batch_complete();
CREATE CONSTRAINT TRIGGER batch_complete AFTER INSERT ON herman.journal_import_sources
    DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION herman.journal_batch_complete();
CREATE FUNCTION herman.journal_entry_sources_complete() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE n integer; batches integer; lines integer;
BEGIN
    SELECT count(*),count(DISTINCT batch_id) INTO n,batches FROM herman.journal_import_sources
        WHERE business_id=NEW.business_id AND entry_id=NEW.entry_id;
    IF n>0 THEN
        SELECT count(*) INTO lines FROM herman.journal_lines WHERE business_id=NEW.business_id AND entry_id=NEW.entry_id;
        IF n<>lines OR batches<>1 THEN
            RAISE EXCEPTION 'imported entry requires one batch and provenance for every line' USING ERRCODE='23514';
        END IF;
    END IF;
    RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER import_entry_complete AFTER INSERT ON herman.journal_lines
    DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION herman.journal_entry_sources_complete();
CREATE CONSTRAINT TRIGGER import_entry_complete AFTER INSERT ON herman.journal_import_sources
    DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION herman.journal_entry_sources_complete();
DO $$
DECLARE t text;
BEGIN
    FOREACH t IN ARRAY ARRAY['journal_import_batches','journal_import_sources'] LOOP
        EXECUTE format('ALTER TABLE herman.%I ENABLE ROW LEVEL SECURITY',t);
        EXECUTE format('ALTER TABLE herman.%I FORCE ROW LEVEL SECURITY',t);
        EXECUTE format('CREATE POLICY tenant_read ON herman.%I FOR SELECT USING '
            || '(business_id=herman.business_id() AND (SELECT herman.member_role(herman.business_id())) IS NOT NULL)',t);
        EXECUTE format('CREATE POLICY tenant_insert ON herman.%I FOR INSERT WITH CHECK '
            || '(business_id=herman.business_id() AND created_by=herman.user_id() AND '
            || 'herman.member_role(business_id) IN (%L,%L,%L))',t,'owner','editor','reviewer');
        EXECUTE format('CREATE TRIGGER append_only BEFORE UPDATE OR DELETE ON herman.%I '
            || 'FOR EACH ROW EXECUTE FUNCTION herman.immutable_record()',t);
    END LOOP;
END $$;
REVOKE ALL ON herman.journal_import_batches,herman.journal_import_sources FROM PUBLIC;
INSERT INTO herman.schema_migrations(version) VALUES(12);
