CREATE TABLE herman.extraction_jobs (
    business_id uuid NOT NULL, id uuid NOT NULL, document_id uuid NOT NULL,
    created_by uuid NOT NULL REFERENCES herman.users(id),
    engine text NOT NULL CHECK(engine IN ('tesseract','easyocr')),
    created_at timestamptz NOT NULL DEFAULT now(),
    status text NOT NULL DEFAULT 'queued' CHECK(status IN ('queued','running','succeeded','failed')),
    attempts integer NOT NULL DEFAULT 0 CHECK(attempts BETWEEN 0 AND 3),
    available_at timestamptz NOT NULL DEFAULT now(),
    lease_token uuid, leased_until timestamptz, error_code text,
    PRIMARY KEY(business_id,id),
    FOREIGN KEY(business_id,document_id) REFERENCES herman.documents(business_id,id),
    CHECK((status='running')=(lease_token IS NOT NULL AND leased_until IS NOT NULL))
);
CREATE TABLE herman.extractions (
    business_id uuid NOT NULL, id uuid NOT NULL, job_id uuid NOT NULL,
    source_sha256 text NOT NULL CHECK(source_sha256 ~ '^[0-9a-f]{64}$'),
    parser_version text NOT NULL, payload jsonb NOT NULL,
    created_by uuid NOT NULL REFERENCES herman.users(id), created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY(business_id,id), UNIQUE(business_id,job_id),
    FOREIGN KEY(business_id,job_id) REFERENCES herman.extraction_jobs(business_id,id)
);
CREATE INDEX extraction_ready_idx ON herman.extraction_jobs(business_id,available_at,created_at,id)
    WHERE status IN ('queued','running');
CREATE INDEX extraction_document_idx ON herman.extraction_jobs(business_id,document_id,created_at,id);
DO $$
DECLARE table_name text;
BEGIN
    FOREACH table_name IN ARRAY ARRAY['extraction_jobs','extractions'] LOOP
        EXECUTE format('ALTER TABLE herman.%I ENABLE ROW LEVEL SECURITY',table_name);
        EXECUTE format('ALTER TABLE herman.%I FORCE ROW LEVEL SECURITY',table_name);
        EXECUTE format('CREATE POLICY tenant_read ON herman.%I FOR SELECT USING '
            || '(business_id=herman.business_id() AND '
            || '(SELECT herman.member_role(herman.business_id())) IS NOT NULL)',table_name);
        EXECUTE format('CREATE POLICY tenant_insert ON herman.%I FOR INSERT WITH CHECK '
            || '(business_id=herman.business_id() AND created_by=herman.user_id() AND '
            || 'herman.member_role(business_id) IN (%L,%L,%L))',table_name,'owner','editor','reviewer');
    END LOOP;
END $$;
CREATE POLICY job_initial ON herman.extraction_jobs AS RESTRICTIVE FOR INSERT
    WITH CHECK(status='queued' AND attempts=0 AND lease_token IS NULL AND leased_until IS NULL);
CREATE POLICY job_update ON herman.extraction_jobs FOR UPDATE USING (
    business_id=herman.business_id() AND herman.member_role(business_id) IN ('owner','editor','reviewer')
) WITH CHECK(business_id=herman.business_id());
CREATE TRIGGER extraction_append_only BEFORE UPDATE OR DELETE ON herman.extractions
    FOR EACH ROW EXECUTE FUNCTION herman.immutable_record();
REVOKE ALL ON herman.extraction_jobs,herman.extractions FROM PUBLIC;
INSERT INTO herman.schema_migrations(version) VALUES(3);
