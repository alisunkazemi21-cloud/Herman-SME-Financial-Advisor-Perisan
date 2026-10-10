CREATE TABLE herman.journal_mappings (
    business_id uuid NOT NULL REFERENCES herman.businesses(id), id uuid NOT NULL,
    payload jsonb NOT NULL CHECK(octet_length(payload::text)<=262144),
    document_id uuid NOT NULL, locator text NOT NULL CHECK(length(locator) BETWEEN 1 AND 500),
    created_by uuid NOT NULL REFERENCES herman.users(id), created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY(business_id,id), FOREIGN KEY(business_id,document_id) REFERENCES herman.documents(business_id,id)
);
CREATE TABLE herman.journal_mapping_decisions (
    business_id uuid NOT NULL, mapping_id uuid NOT NULL, approved boolean NOT NULL,
    reason_fa text NOT NULL CHECK(length(reason_fa) BETWEEN 3 AND 2000),
    reviewed_values boolean NOT NULL CHECK(reviewed_values),
    created_by uuid NOT NULL REFERENCES herman.users(id), created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY(business_id,mapping_id),
    FOREIGN KEY(business_id,mapping_id) REFERENCES herman.journal_mappings(business_id,id)
);
CREATE TABLE herman.journal_reports (
    business_id uuid NOT NULL, id uuid NOT NULL, mapping_id uuid NOT NULL,
    period_start date NOT NULL, period_end date NOT NULL CHECK(period_end>=period_start),
    manifest jsonb NOT NULL CHECK(octet_length(manifest::text)<=16777216),
    result jsonb NOT NULL CHECK(octet_length(result::text)<=1048576),
    input_sha256 text NOT NULL CHECK(input_sha256 ~ '^[a-f0-9]{64}$'),
    result_sha256 text NOT NULL CHECK(result_sha256 ~ '^[a-f0-9]{64}$'),
    created_by uuid NOT NULL REFERENCES herman.users(id), created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY(business_id,id), FOREIGN KEY(business_id,mapping_id) REFERENCES herman.journal_mappings(business_id,id)
);
CREATE TABLE herman.journal_report_decisions (
    business_id uuid NOT NULL, report_id uuid NOT NULL, approved boolean NOT NULL,
    reviewed_values boolean NOT NULL CHECK(reviewed_values), scope_confirmed boolean NOT NULL,
    reason_fa text NOT NULL CHECK(length(reason_fa) BETWEEN 3 AND 2000),
    created_by uuid NOT NULL REFERENCES herman.users(id), created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY(business_id,report_id), CHECK(NOT approved OR scope_confirmed),
    FOREIGN KEY(business_id,report_id) REFERENCES herman.journal_reports(business_id,id)
);
CREATE INDEX journal_report_period ON herman.journal_reports(business_id,period_end DESC,id);
DO $$
DECLARE t text;
BEGIN
    FOREACH t IN ARRAY ARRAY['journal_mappings','journal_mapping_decisions','journal_reports','journal_report_decisions'] LOOP
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
    FOREACH t IN ARRAY ARRAY['journal_mapping_decisions','journal_report_decisions'] LOOP
        EXECUTE format('DROP POLICY tenant_insert ON herman.%I',t);
        EXECUTE format('CREATE POLICY tenant_insert ON herman.%I FOR INSERT WITH CHECK '
            || '(business_id=herman.business_id() AND created_by=herman.user_id() AND '
            || 'herman.member_role(business_id) IN (%L,%L))',t,'owner','reviewer');
    END LOOP;
END $$;
REVOKE ALL ON herman.journal_mappings,herman.journal_mapping_decisions,herman.journal_reports,herman.journal_report_decisions FROM PUBLIC;
INSERT INTO herman.schema_migrations(version) VALUES(10);
