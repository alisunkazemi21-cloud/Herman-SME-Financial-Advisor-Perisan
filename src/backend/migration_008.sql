CREATE TABLE herman.advisor_cases (
    business_id uuid NOT NULL REFERENCES herman.businesses(id), id uuid NOT NULL,
    title_fa text NOT NULL CHECK(length(title_fa) BETWEEN 1 AND 200),
    created_by uuid NOT NULL REFERENCES herman.users(id), created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY(business_id,id)
);
CREATE TABLE herman.advisor_turns (
    business_id uuid NOT NULL, id uuid NOT NULL, case_id uuid NOT NULL,
    turn_number integer NOT NULL CHECK(turn_number>0), request jsonb NOT NULL, receipt jsonb NOT NULL,
    created_by uuid NOT NULL REFERENCES herman.users(id), created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY(business_id,id), UNIQUE(business_id,case_id,turn_number),
    FOREIGN KEY(business_id,case_id) REFERENCES herman.advisor_cases(business_id,id),
    CHECK(octet_length(receipt::text)<=131072)
);
DO $$
DECLARE t text;
BEGIN
    FOREACH t IN ARRAY ARRAY['advisor_cases','advisor_turns'] LOOP
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
REVOKE ALL ON herman.advisor_cases,herman.advisor_turns FROM PUBLIC;
INSERT INTO herman.schema_migrations(version) VALUES(8);
