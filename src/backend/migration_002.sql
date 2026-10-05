-- Tenant equality remains row-scoped. Actor membership is constant within the statement.
DO $$
DECLARE table_name text;
BEGIN
    FOREACH table_name IN ARRAY ARRAY['warehouses','documents','items','unit_conversions',
        'records','approvals','stock_counts','stock_movements','recipes','recipe_lines','fulfillments',
        'analysis_runs','audit_events','idempotency_keys'] LOOP
        EXECUTE format('ALTER POLICY tenant_read ON herman.%I USING '
            || '(business_id=herman.business_id() AND '
            || '(SELECT herman.member_role(herman.business_id())) IS NOT NULL)',table_name);
    END LOOP;
    ALTER POLICY tenant_read ON herman.businesses USING (
        id=herman.business_id() AND (SELECT herman.member_role(herman.business_id())) IS NOT NULL
    );
END $$;
INSERT INTO herman.schema_migrations(version) VALUES(2);
