CREATE TABLE herman.import_batches (
    business_id uuid NOT NULL, id uuid NOT NULL, extraction_id uuid NOT NULL,
    created_by uuid NOT NULL REFERENCES herman.users(id), mapping jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(business_id,id),
    FOREIGN KEY(business_id,extraction_id) REFERENCES herman.extractions(business_id,id)
);
CREATE TABLE herman.record_sources (
    business_id uuid NOT NULL, id uuid NOT NULL, batch_id uuid NOT NULL,
    extraction_id uuid NOT NULL, document_id uuid NOT NULL,
    sheet text NOT NULL, source_row integer NOT NULL CHECK(source_row>=2),
    record_kind text NOT NULL CHECK(record_kind IN ('count','movement','fulfillment')),
    source_values jsonb NOT NULL, created_by uuid NOT NULL REFERENCES herman.users(id),
    PRIMARY KEY(business_id,id), UNIQUE(business_id,document_id,sheet,source_row,record_kind),
    FOREIGN KEY(business_id,id) REFERENCES herman.records(business_id,id),
    FOREIGN KEY(business_id,batch_id) REFERENCES herman.import_batches(business_id,id),
    FOREIGN KEY(business_id,extraction_id) REFERENCES herman.extractions(business_id,id),
    FOREIGN KEY(business_id,document_id) REFERENCES herman.documents(business_id,id)
);
CREATE INDEX record_source_batch_idx ON herman.record_sources(business_id,batch_id,id);
ALTER TABLE herman.analysis_runs ADD COLUMN source_provenance jsonb NOT NULL DEFAULT '[]'::jsonb;
DO $$
DECLARE table_name text;
BEGIN
    FOREACH table_name IN ARRAY ARRAY['import_batches','record_sources'] LOOP
        EXECUTE format('ALTER TABLE herman.%I ENABLE ROW LEVEL SECURITY',table_name);
        EXECUTE format('ALTER TABLE herman.%I FORCE ROW LEVEL SECURITY',table_name);
        EXECUTE format('CREATE POLICY tenant_read ON herman.%I FOR SELECT USING '
            || '(business_id=herman.business_id() AND '
            || '(SELECT herman.member_role(herman.business_id())) IS NOT NULL)',table_name);
        EXECUTE format('CREATE POLICY tenant_insert ON herman.%I FOR INSERT WITH CHECK '
            || '(business_id=herman.business_id() AND created_by=herman.user_id() AND '
            || 'herman.member_role(business_id) IN (%L,%L,%L))',table_name,'owner','editor','reviewer');
        EXECUTE format('CREATE TRIGGER append_only BEFORE UPDATE OR DELETE ON herman.%I '
            || 'FOR EACH ROW EXECUTE FUNCTION herman.immutable_record()',table_name);
    END LOOP;
END $$;
-- Source relations must refer to the same document, extraction, record kind and batch.
CREATE FUNCTION herman.check_record_source() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM herman.records r
        JOIN herman.extractions e ON e.business_id=r.business_id AND e.id=NEW.extraction_id
        JOIN herman.extraction_jobs j ON (j.business_id,j.id)=(e.business_id,e.job_id)
        JOIN herman.import_batches b ON b.business_id=r.business_id AND b.id=NEW.batch_id
        WHERE r.business_id=NEW.business_id AND r.id=NEW.id AND r.kind=NEW.record_kind
          AND r.document_id=NEW.document_id AND j.document_id=NEW.document_id
          AND b.extraction_id=NEW.extraction_id
    ) THEN RAISE EXCEPTION 'inconsistent extraction provenance' USING ERRCODE='23514'; END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER source_consistency BEFORE INSERT ON herman.record_sources
    FOR EACH ROW EXECUTE FUNCTION herman.check_record_source();
REVOKE ALL ON herman.import_batches,herman.record_sources FROM PUBLIC;
REVOKE ALL ON FUNCTION herman.check_record_source() FROM PUBLIC;
INSERT INTO herman.schema_migrations(version) VALUES(4);
