CREATE TABLE herman.financial_snapshots (
    business_id uuid NOT NULL REFERENCES herman.businesses(id), id uuid NOT NULL,
    period_start date NOT NULL, period_end date NOT NULL CHECK(period_end>period_start),
    payload jsonb NOT NULL, created_by uuid NOT NULL REFERENCES herman.users(id),
    created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(business_id,id)
);
CREATE TABLE herman.financial_snapshot_sources (
    business_id uuid NOT NULL, snapshot_id uuid NOT NULL, field text NOT NULL,
    document_id uuid NOT NULL, locator text NOT NULL CHECK(length(locator) BETWEEN 1 AND 500),
    created_by uuid NOT NULL REFERENCES herman.users(id), PRIMARY KEY(business_id,snapshot_id,field),
    FOREIGN KEY(business_id,snapshot_id) REFERENCES herman.financial_snapshots(business_id,id),
    FOREIGN KEY(business_id,document_id) REFERENCES herman.documents(business_id,id)
);
CREATE TABLE herman.financial_snapshot_decisions (
    business_id uuid NOT NULL, snapshot_id uuid NOT NULL, approved boolean NOT NULL,
    created_by uuid NOT NULL REFERENCES herman.users(id),
    reason_fa text NOT NULL CHECK(length(reason_fa) BETWEEN 1 AND 2000),
    created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(business_id,snapshot_id),
    FOREIGN KEY(business_id,snapshot_id) REFERENCES herman.financial_snapshots(business_id,id)
);
CREATE INDEX financial_period_idx ON herman.financial_snapshots(business_id,period_end DESC,id);
DO $$
DECLARE t text;
BEGIN
    FOREACH t IN ARRAY ARRAY['financial_snapshots','financial_snapshot_sources','financial_snapshot_decisions'] LOOP
        EXECUTE format('ALTER TABLE herman.%I ENABLE ROW LEVEL SECURITY',t);
        EXECUTE format('ALTER TABLE herman.%I FORCE ROW LEVEL SECURITY',t);
        EXECUTE format('CREATE POLICY tenant_read ON herman.%I FOR SELECT USING '
            || '(business_id=herman.business_id() AND '
            || '(SELECT herman.member_role(herman.business_id())) IS NOT NULL)',t);
        EXECUTE format('CREATE POLICY tenant_insert ON herman.%I FOR INSERT WITH CHECK '
            || '(business_id=herman.business_id() AND created_by=herman.user_id() AND '
            || 'herman.member_role(business_id) IN (%L,%L,%L))',t,'owner','editor','reviewer');
        EXECUTE format('CREATE TRIGGER append_only BEFORE UPDATE OR DELETE ON herman.%I '
            || 'FOR EACH ROW EXECUTE FUNCTION herman.immutable_record()',t);
    END LOOP;
END $$;
DROP POLICY tenant_insert ON herman.financial_snapshot_decisions;
CREATE POLICY tenant_insert ON herman.financial_snapshot_decisions FOR INSERT WITH CHECK (
    business_id=herman.business_id() AND created_by=herman.user_id()
    AND herman.member_role(business_id) IN ('owner','reviewer')
);
REVOKE ALL ON herman.financial_snapshots,herman.financial_snapshot_sources,
    herman.financial_snapshot_decisions FROM PUBLIC;
INSERT INTO herman.schema_migrations(version) VALUES(7);
