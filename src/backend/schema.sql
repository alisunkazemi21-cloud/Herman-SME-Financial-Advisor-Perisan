CREATE SCHEMA IF NOT EXISTS herman;
CREATE TABLE IF NOT EXISTS herman.schema_migrations (
    version integer PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE herman.users (
    id uuid PRIMARY KEY, display_name text NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE herman.api_credentials (
    digest text PRIMARY KEY CHECK (digest ~ '^[0-9a-f]{64}$'),
    user_id uuid NOT NULL REFERENCES herman.users(id),
    expires_at timestamptz NOT NULL, revoked boolean NOT NULL DEFAULT false
);
CREATE TABLE herman.businesses (
    id uuid PRIMARY KEY, name text NOT NULL, industry text NOT NULL,
    currency text NOT NULL DEFAULT 'IRR' CHECK (currency = 'IRR'),
    timezone text NOT NULL DEFAULT 'Asia/Tehran', created_by uuid NOT NULL REFERENCES herman.users(id),
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE herman.memberships (
    business_id uuid NOT NULL REFERENCES herman.businesses(id),
    user_id uuid NOT NULL REFERENCES herman.users(id),
    role text NOT NULL CHECK (role IN ('owner','editor','reviewer','viewer')),
    active boolean NOT NULL DEFAULT true, PRIMARY KEY (business_id,user_id)
);
CREATE TABLE herman.business_requests (
    user_id uuid NOT NULL REFERENCES herman.users(id), key text NOT NULL,
    name text NOT NULL, industry text NOT NULL,
    business_id uuid NOT NULL REFERENCES herman.businesses(id), PRIMARY KEY(user_id,key)
);
CREATE FUNCTION herman.user_id() RETURNS uuid LANGUAGE sql STABLE AS $$
    SELECT nullif(current_setting('herman.user_id', true), '')::uuid
$$;
CREATE FUNCTION herman.business_id() RETURNS uuid LANGUAGE sql STABLE AS $$
    SELECT nullif(current_setting('herman.business_id', true), '')::uuid
$$;
CREATE FUNCTION herman.member_role(target uuid) RETURNS text
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, herman AS $$
    SELECT role FROM herman.memberships
    WHERE business_id = target AND user_id = herman.user_id() AND active
$$;
CREATE FUNCTION herman.authenticate(token_digest text) RETURNS uuid
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, herman AS $$
    SELECT user_id FROM herman.api_credentials
    WHERE digest = token_digest AND NOT revoked AND expires_at > now()
$$;
CREATE FUNCTION herman.create_business(request_name text, request_industry text, request_key text) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, herman AS $$
DECLARE result uuid := gen_random_uuid(); actor uuid := herman.user_id(); previous herman.business_requests%ROWTYPE;
BEGIN
    IF actor IS NULL OR NOT EXISTS(SELECT 1 FROM herman.users WHERE id=actor) THEN
        RAISE EXCEPTION 'authenticated user required' USING ERRCODE='42501';
    END IF;
    IF length(request_key) NOT BETWEEN 1 AND 200 THEN
        RAISE EXCEPTION 'invalid idempotency key' USING ERRCODE='22023';
    END IF;
    SELECT * INTO previous FROM herman.business_requests WHERE user_id=actor AND key=request_key;
    IF FOUND THEN
        IF previous.name<>request_name OR previous.industry<>request_industry THEN
            RAISE EXCEPTION 'idempotency conflict' USING ERRCODE='22023';
        END IF;
        RETURN previous.business_id;
    END IF;
    INSERT INTO herman.businesses(id,name,industry,created_by) VALUES(result,request_name,request_industry,actor);
    INSERT INTO herman.memberships(business_id,user_id,role) VALUES(result,actor,'owner');
    INSERT INTO herman.business_requests VALUES(actor,request_key,request_name,request_industry,result);
    RETURN result;
END $$;
CREATE FUNCTION herman.list_businesses() RETURNS TABLE(id uuid, name text, industry text, role text)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, herman AS $$
    SELECT b.id,b.name,b.industry,m.role FROM herman.businesses b
    JOIN herman.memberships m ON m.business_id=b.id
    WHERE m.user_id=herman.user_id() AND m.active ORDER BY b.created_at,b.id
$$;
CREATE TABLE herman.warehouses (
    business_id uuid NOT NULL REFERENCES herman.businesses(id), id uuid NOT NULL,
    name text NOT NULL, PRIMARY KEY(business_id,id)
);
CREATE TABLE herman.documents (
    business_id uuid NOT NULL REFERENCES herman.businesses(id), id uuid NOT NULL,
    sha256 text NOT NULL CHECK(sha256 ~ '^[0-9a-f]{64}$'), original_name text NOT NULL,
    media_type text NOT NULL, byte_size bigint NOT NULL CHECK(byte_size >= 0),
    created_by uuid NOT NULL REFERENCES herman.users(id), created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY(business_id,id)
);
CREATE TABLE herman.items (
    business_id uuid NOT NULL REFERENCES herman.businesses(id), id uuid NOT NULL,
    sku text NOT NULL, name_fa text NOT NULL, base_unit text NOT NULL CHECK(base_unit IN ('g','ml','each')),
    consumption_mode text NOT NULL CHECK(consumption_mode IN ('direct','recipe')),
    PRIMARY KEY(business_id,id), UNIQUE(business_id,sku)
);
CREATE TABLE herman.unit_conversions (
    business_id uuid NOT NULL, id uuid NOT NULL, item_id uuid NOT NULL,
    unit text NOT NULL CHECK(unit='pack'), base_quantity numeric(24,6) NOT NULL CHECK(base_quantity>0),
    document_id uuid NOT NULL, locator text NOT NULL,
    PRIMARY KEY(business_id,id), UNIQUE(business_id,item_id,unit),
    FOREIGN KEY(business_id,item_id) REFERENCES herman.items(business_id,id),
    FOREIGN KEY(business_id,document_id) REFERENCES herman.documents(business_id,id)
);
CREATE TABLE herman.records (
    business_id uuid NOT NULL REFERENCES herman.businesses(id), id uuid NOT NULL,
    kind text NOT NULL CHECK(kind IN ('count','movement','recipe','fulfillment')),
    document_id uuid NOT NULL, locator text NOT NULL, created_by uuid NOT NULL REFERENCES herman.users(id),
    created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(business_id,id),
    FOREIGN KEY(business_id,document_id) REFERENCES herman.documents(business_id,id)
);
CREATE TABLE herman.approvals (
    business_id uuid NOT NULL, record_id uuid NOT NULL, approved boolean NOT NULL,
    actor_id uuid NOT NULL REFERENCES herman.users(id), reason_fa text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(business_id,record_id),
    FOREIGN KEY(business_id,record_id) REFERENCES herman.records(business_id,id)
);
CREATE TABLE herman.stock_counts (
    business_id uuid NOT NULL, id uuid NOT NULL, warehouse_id uuid NOT NULL, item_id uuid NOT NULL,
    occurred_at timestamptz NOT NULL, quantity numeric(24,6) NOT NULL CHECK(quantity>=0), unit text NOT NULL,
    PRIMARY KEY(business_id,id),
    FOREIGN KEY(business_id,id) REFERENCES herman.records(business_id,id),
    FOREIGN KEY(business_id,warehouse_id) REFERENCES herman.warehouses(business_id,id),
    FOREIGN KEY(business_id,item_id) REFERENCES herman.items(business_id,id)
);
CREATE TABLE herman.stock_movements (
    business_id uuid NOT NULL, id uuid NOT NULL, warehouse_id uuid NOT NULL, item_id uuid NOT NULL,
    occurred_at timestamptz NOT NULL, quantity numeric(24,6) NOT NULL CHECK(quantity>=0), unit text NOT NULL,
    kind text NOT NULL CHECK(kind IN ('purchase','transfer_in','transfer_out','supplier_return',
        'customer_return','waste','other_use','count_adjustment','service_usage')),
    PRIMARY KEY(business_id,id),
    FOREIGN KEY(business_id,id) REFERENCES herman.records(business_id,id),
    FOREIGN KEY(business_id,warehouse_id) REFERENCES herman.warehouses(business_id,id),
    FOREIGN KEY(business_id,item_id) REFERENCES herman.items(business_id,id)
);
CREATE TABLE herman.recipes (
    business_id uuid NOT NULL, id uuid NOT NULL, product_id uuid NOT NULL,
    valid_from timestamptz NOT NULL, valid_to timestamptz,
    output_quantity numeric(24,6) NOT NULL CHECK(output_quantity>0), output_unit text NOT NULL,
    CHECK(valid_to IS NULL OR valid_to>valid_from), PRIMARY KEY(business_id,id),
    FOREIGN KEY(business_id,id) REFERENCES herman.records(business_id,id),
    FOREIGN KEY(business_id,product_id) REFERENCES herman.items(business_id,id)
);
CREATE TABLE herman.recipe_lines (
    business_id uuid NOT NULL, recipe_id uuid NOT NULL, item_id uuid NOT NULL,
    quantity numeric(24,6) NOT NULL CHECK(quantity>0), unit text NOT NULL,
    basis text NOT NULL CHECK(basis IN ('raw','net')),
    preparation_yield numeric(9,6) NOT NULL CHECK(preparation_yield>0 AND preparation_yield<=1),
    CHECK(basis<>'raw' OR preparation_yield=1), PRIMARY KEY(business_id,recipe_id,item_id),
    FOREIGN KEY(business_id,recipe_id) REFERENCES herman.recipes(business_id,id),
    FOREIGN KEY(business_id,item_id) REFERENCES herman.items(business_id,id)
);
CREATE TABLE herman.fulfillments (
    business_id uuid NOT NULL, id uuid NOT NULL, warehouse_id uuid NOT NULL, product_id uuid NOT NULL,
    occurred_at timestamptz NOT NULL, quantity numeric(24,6) NOT NULL CHECK(quantity>=0), unit text NOT NULL,
    kind text NOT NULL CHECK(kind IN ('sale','complimentary','staff','production')), fulfilled boolean NOT NULL,
    PRIMARY KEY(business_id,id),
    FOREIGN KEY(business_id,id) REFERENCES herman.records(business_id,id),
    FOREIGN KEY(business_id,warehouse_id) REFERENCES herman.warehouses(business_id,id),
    FOREIGN KEY(business_id,product_id) REFERENCES herman.items(business_id,id)
);
CREATE TABLE herman.analysis_runs (
    business_id uuid NOT NULL REFERENCES herman.businesses(id), id uuid NOT NULL,
    actor_id uuid NOT NULL REFERENCES herman.users(id), input_sha256 text NOT NULL,
    input_snapshot jsonb NOT NULL, result jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY(business_id,id)
);
CREATE TABLE herman.audit_events (
    business_id uuid NOT NULL REFERENCES herman.businesses(id), id uuid NOT NULL,
    actor_id uuid NOT NULL REFERENCES herman.users(id), action text NOT NULL, entity_id uuid,
    request_id uuid NOT NULL, occurred_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY(business_id,id)
);
CREATE TABLE herman.idempotency_keys (
    business_id uuid NOT NULL REFERENCES herman.businesses(id), key text NOT NULL,
    request_hash text NOT NULL, result_id uuid NOT NULL, PRIMARY KEY(business_id,key)
);
CREATE INDEX movement_period_idx ON herman.stock_movements(business_id,warehouse_id,item_id,occurred_at,id);
CREATE INDEX count_period_idx ON herman.stock_counts(business_id,warehouse_id,item_id,occurred_at,id);
CREATE INDEX fulfillment_period_idx ON herman.fulfillments(business_id,warehouse_id,occurred_at,id);
CREATE INDEX recipe_version_idx ON herman.recipes(business_id,product_id,valid_from);
CREATE INDEX audit_period_idx ON herman.audit_events(business_id,occurred_at,id);
CREATE INDEX document_period_idx ON herman.documents(business_id,created_at,id);

-- Runtime can never modify or delete posted source records or audit events.
CREATE FUNCTION herman.immutable_record() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'append-only relation' USING ERRCODE='42501'; END $$;
DO $$
DECLARE table_name text;
BEGIN
    FOREACH table_name IN ARRAY ARRAY['businesses','warehouses','documents','items','unit_conversions',
        'records','approvals','stock_counts','stock_movements','recipes','recipe_lines','fulfillments',
        'analysis_runs','audit_events','idempotency_keys'] LOOP
        EXECUTE format('ALTER TABLE herman.%I ENABLE ROW LEVEL SECURITY',table_name);
        EXECUTE format('ALTER TABLE herman.%I FORCE ROW LEVEL SECURITY',table_name);
        IF table_name='businesses' THEN
            EXECUTE 'CREATE POLICY tenant_read ON herman.businesses FOR SELECT USING '
                || '(id=herman.business_id() AND herman.member_role(id) IS NOT NULL)';
        ELSE
            EXECUTE format('CREATE POLICY tenant_read ON herman.%I FOR SELECT USING '
                || '(business_id=herman.business_id() AND herman.member_role(business_id) IS NOT NULL)',table_name);
            EXECUTE format('CREATE POLICY tenant_insert ON herman.%I FOR INSERT WITH CHECK '
                || '(business_id=herman.business_id() AND herman.member_role(business_id) IN (%L,%L,%L))',
                table_name,'owner','editor','reviewer');
        END IF;
        EXECUTE format('CREATE TRIGGER append_only BEFORE UPDATE OR DELETE ON herman.%I '
            || 'FOR EACH ROW EXECUTE FUNCTION herman.immutable_record()',table_name);
    END LOOP;
END $$;
-- Defense in depth: decisions require a reviewer, and audit/source authors cannot be supplied by clients.
DROP POLICY tenant_insert ON herman.approvals;
CREATE POLICY tenant_insert ON herman.approvals FOR INSERT WITH CHECK (
    business_id=herman.business_id() AND herman.member_role(business_id) IN ('owner','reviewer')
    AND actor_id=herman.user_id()
);
CREATE POLICY author_check ON herman.documents AS RESTRICTIVE FOR INSERT
    WITH CHECK (created_by=herman.user_id());
CREATE POLICY author_check ON herman.records AS RESTRICTIVE FOR INSERT
    WITH CHECK (created_by=herman.user_id());
CREATE POLICY author_check ON herman.analysis_runs AS RESTRICTIVE FOR INSERT
    WITH CHECK (actor_id=herman.user_id());
CREATE POLICY author_check ON herman.audit_events AS RESTRICTIVE FOR INSERT
    WITH CHECK (actor_id=herman.user_id());
REVOKE ALL ON ALL TABLES IN SCHEMA herman FROM PUBLIC;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA herman FROM PUBLIC;
INSERT INTO herman.schema_migrations(version) VALUES(1);
