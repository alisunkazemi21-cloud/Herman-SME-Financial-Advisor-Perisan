CREATE TABLE herman.knowledge_claims (
    business_id uuid NOT NULL REFERENCES herman.businesses(id), id uuid NOT NULL,
    key text NOT NULL CHECK(length(key) BETWEEN 1 AND 80),
    statement_fa text NOT NULL CHECK(length(statement_fa) BETWEEN 1 AND 2000),
    document_id uuid NOT NULL, locator text NOT NULL CHECK(length(locator) BETWEEN 1 AND 500),
    valid_from timestamptz NOT NULL, valid_to timestamptz,
    created_by uuid NOT NULL REFERENCES herman.users(id), created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY(business_id,id), CHECK(valid_to IS NULL OR valid_to>valid_from),
    FOREIGN KEY(business_id,document_id) REFERENCES herman.documents(business_id,id)
);
CREATE TABLE herman.knowledge_decisions (
    business_id uuid NOT NULL, claim_id uuid NOT NULL, approved boolean NOT NULL,
    created_by uuid NOT NULL REFERENCES herman.users(id),
    reason_fa text NOT NULL CHECK(length(reason_fa) BETWEEN 1 AND 2000),
    created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(business_id,claim_id),
    FOREIGN KEY(business_id,claim_id) REFERENCES herman.knowledge_claims(business_id,id)
);
CREATE INDEX knowledge_scope_idx ON herman.knowledge_claims(business_id,key,valid_from,id);
DO $$
DECLARE t text;
BEGIN
    FOREACH t IN ARRAY ARRAY['knowledge_claims','knowledge_decisions'] LOOP
        EXECUTE format('ALTER TABLE herman.%I ENABLE ROW LEVEL SECURITY',t);
        EXECUTE format('ALTER TABLE herman.%I FORCE ROW LEVEL SECURITY',t);
        EXECUTE format('CREATE POLICY tenant_read ON herman.%I FOR SELECT USING '
            || '(business_id=herman.business_id() AND '
            || '(SELECT herman.member_role(herman.business_id())) IS NOT NULL)',t);
        EXECUTE format('CREATE TRIGGER append_only BEFORE UPDATE OR DELETE ON herman.%I '
            || 'FOR EACH ROW EXECUTE FUNCTION herman.immutable_record()',t);
    END LOOP;
END $$;
CREATE POLICY tenant_insert ON herman.knowledge_claims FOR INSERT WITH CHECK (
    business_id=herman.business_id() AND created_by=herman.user_id()
    AND herman.member_role(business_id) IN ('owner','editor','reviewer')
);
CREATE POLICY tenant_insert ON herman.knowledge_decisions FOR INSERT WITH CHECK (
    business_id=herman.business_id() AND created_by=herman.user_id()
    AND herman.member_role(business_id) IN ('owner','reviewer')
);
REVOKE ALL ON herman.knowledge_claims,herman.knowledge_decisions FROM PUBLIC;
INSERT INTO herman.schema_migrations(version) VALUES(6);
