CREATE TABLE herman.action_proposals (
    business_id uuid NOT NULL, id uuid NOT NULL, analysis_id uuid NOT NULL,
    kind text NOT NULL CHECK(kind IN ('investigate','recount','correct_recipe','record_missing','reduce_waste','other')),
    title_fa text NOT NULL CHECK(length(btrim(title_fa,E' \t\n\r')) BETWEEN 1 AND 300),
    detail_fa text NOT NULL CHECK(length(btrim(detail_fa,E' \t\n\r')) BETWEEN 1 AND 4000),
    responsible_name_fa text NOT NULL CHECK(length(btrim(responsible_name_fa,E' \t\n\r')) BETWEEN 1 AND 200),
    responsible_user_id uuid REFERENCES herman.users(id), follow_up_at timestamptz NOT NULL,
    document_id uuid NOT NULL, locator text NOT NULL CHECK(length(btrim(locator,E' \t\n\r')) BETWEEN 1 AND 500),
    created_by uuid NOT NULL REFERENCES herman.users(id), created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY(business_id,id),
    FOREIGN KEY(business_id,analysis_id) REFERENCES herman.analysis_runs(business_id,id),
    FOREIGN KEY(business_id,document_id) REFERENCES herman.documents(business_id,id),
    CHECK(isfinite(follow_up_at))
);

CREATE TABLE herman.action_events (
    business_id uuid NOT NULL, id uuid NOT NULL, action_id uuid NOT NULL,
    sequence integer NOT NULL CHECK(sequence>0),
    kind text NOT NULL CHECK(kind IN ('approve','reject','start','note','complete','cancel')),
    status text NOT NULL CHECK(status IN ('approved','in_progress','completed','rejected','cancelled')),
    reason_fa text NOT NULL CHECK(length(btrim(reason_fa,E' \t\n\r')) BETWEEN 1 AND 4000),
    outcome text CHECK(outcome IN ('confirmed','no_change','inconclusive')),
    document_id uuid, locator text,
    actor_id uuid NOT NULL REFERENCES herman.users(id), created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY(business_id,id), UNIQUE(business_id,action_id,sequence),
    FOREIGN KEY(business_id,action_id) REFERENCES herman.action_proposals(business_id,id),
    FOREIGN KEY(business_id,document_id) REFERENCES herman.documents(business_id,id),
    CHECK((document_id IS NULL AND locator IS NULL) OR
        (document_id IS NOT NULL AND locator IS NOT NULL AND length(btrim(locator,E' \t\n\r')) BETWEEN 1 AND 500)),
    CHECK((kind='complete' AND outcome IS NOT NULL AND document_id IS NOT NULL)
        OR (kind<>'complete' AND outcome IS NULL))
);

-- Membership lookup stays inside this scoped trigger; runtime has no membership-table access.
CREATE FUNCTION herman.action_proposal_guard() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
    SET search_path=pg_catalog,herman AS $$
BEGIN
    IF NEW.business_id IS DISTINCT FROM herman.business_id() OR NEW.created_by IS DISTINCT FROM herman.user_id()
        OR COALESCE(herman.member_role(NEW.business_id),'') NOT IN ('owner','editor','reviewer') THEN
        RAISE EXCEPTION 'action proposal requires scoped editor' USING ERRCODE='42501';
    END IF;
    IF NEW.responsible_user_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM herman.memberships
        WHERE business_id=NEW.business_id AND user_id=NEW.responsible_user_id AND active) THEN
        RAISE EXCEPTION 'responsible user must be active member' USING ERRCODE='23514';
    END IF;
    NEW.created_at := clock_timestamp();
    RETURN NEW;
END $$;
CREATE TRIGGER action_proposal_guard BEFORE INSERT ON herman.action_proposals
    FOR EACH ROW EXECUTE FUNCTION herman.action_proposal_guard();

CREATE FUNCTION herman.action_event_guard() RETURNS trigger LANGUAGE plpgsql
    SET search_path=pg_catalog,herman AS $$
DECLARE previous herman.action_events%ROWTYPE; current_status text := 'proposed'; prior_sequence integer := 0;
BEGIN
    IF NEW.business_id IS DISTINCT FROM herman.business_id() OR NEW.actor_id IS DISTINCT FROM herman.user_id()
        OR COALESCE(herman.member_role(NEW.business_id),'') NOT IN ('owner','editor','reviewer') THEN
        RAISE EXCEPTION 'action event requires scoped editor' USING ERRCODE='42501';
    END IF;
    IF NEW.kind IN ('approve','reject','complete','cancel')
        AND COALESCE(herman.member_role(NEW.business_id),'') NOT IN ('owner','reviewer') THEN
        RAISE EXCEPTION 'action event requires reviewer' USING ERRCODE='42501';
    END IF;
    SELECT * INTO previous FROM herman.action_events WHERE business_id=NEW.business_id AND action_id=NEW.action_id
        ORDER BY sequence DESC LIMIT 1;
    IF FOUND THEN current_status := previous.status; prior_sequence := previous.sequence; END IF;
    IF NEW.sequence<>prior_sequence+1 THEN
        RAISE EXCEPTION 'action sequence conflict' USING ERRCODE='23514';
    END IF;
    IF current_status IN ('completed','rejected','cancelled') THEN
        RAISE EXCEPTION 'action is terminal' USING ERRCODE='23514';
    END IF;
    IF NEW.kind='approve' AND current_status='proposed' THEN NEW.status := 'approved';
    ELSIF NEW.kind='reject' AND current_status='proposed' THEN NEW.status := 'rejected';
    ELSIF NEW.kind='start' AND current_status='approved' THEN NEW.status := 'in_progress';
    ELSIF NEW.kind='note' AND current_status IN ('approved','in_progress') THEN NEW.status := current_status;
    ELSIF NEW.kind='complete' AND current_status IN ('approved','in_progress') THEN NEW.status := 'completed';
    ELSIF NEW.kind='cancel' AND current_status IN ('proposed','approved','in_progress') THEN NEW.status := 'cancelled';
    ELSE RAISE EXCEPTION 'invalid action transition' USING ERRCODE='23514';
    END IF;
    NEW.created_at := clock_timestamp();
    RETURN NEW;
END $$;
CREATE TRIGGER action_event_guard BEFORE INSERT ON herman.action_events
    FOR EACH ROW EXECUTE FUNCTION herman.action_event_guard();

DO $$ DECLARE t text; BEGIN
    FOREACH t IN ARRAY ARRAY['action_proposals','action_events'] LOOP
        EXECUTE format('ALTER TABLE herman.%I ENABLE ROW LEVEL SECURITY',t);
        EXECUTE format('ALTER TABLE herman.%I FORCE ROW LEVEL SECURITY',t);
        EXECUTE format('CREATE POLICY tenant_read ON herman.%I FOR SELECT USING '
            || '(business_id=herman.business_id() AND herman.member_role(business_id) IS NOT NULL)',t);
        EXECUTE format('CREATE TRIGGER append_only BEFORE UPDATE OR DELETE ON herman.%I '
            || 'FOR EACH ROW EXECUTE FUNCTION herman.immutable_record()',t);
    END LOOP;
END $$;
CREATE POLICY tenant_insert ON herman.action_proposals FOR INSERT WITH CHECK (
    business_id=herman.business_id() AND created_by=herman.user_id()
    AND herman.member_role(business_id) IN ('owner','editor','reviewer'));
CREATE POLICY tenant_insert ON herman.action_events FOR INSERT WITH CHECK (
    business_id=herman.business_id() AND actor_id=herman.user_id()
    AND herman.member_role(business_id) IN ('owner','editor','reviewer'));
REVOKE ALL ON herman.action_proposals,herman.action_events FROM PUBLIC;
REVOKE ALL ON FUNCTION herman.action_proposal_guard(),herman.action_event_guard() FROM PUBLIC;
INSERT INTO herman.schema_migrations(version) VALUES(20);
