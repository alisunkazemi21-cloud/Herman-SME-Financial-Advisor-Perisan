CREATE TABLE herman.journal_accounts (
    business_id uuid NOT NULL REFERENCES herman.businesses(id), id uuid NOT NULL,
    code text NOT NULL CHECK(code ~ '^[A-Za-z0-9_-]{1,32}$'),
    name_fa text NOT NULL CHECK(length(name_fa) BETWEEN 1 AND 200),
    kind text NOT NULL CHECK(kind IN ('asset','liability','equity','revenue','expense')),
    created_by uuid NOT NULL REFERENCES herman.users(id), created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY(business_id,code), UNIQUE(business_id,id)
);
CREATE TABLE herman.journal_entries (
    business_id uuid NOT NULL REFERENCES herman.businesses(id), id uuid NOT NULL,
    entry_date date NOT NULL, jalali_date text NOT NULL,
    currency text NOT NULL CHECK(currency='IRR'),
    description_fa text NOT NULL CHECK(length(description_fa) BETWEEN 3 AND 2000),
    event_fingerprint text NOT NULL CHECK(event_fingerprint ~ '^[a-f0-9]{64}$'),
    reversal_of uuid, created_xid xid8 NOT NULL,
    created_by uuid NOT NULL REFERENCES herman.users(id), created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY(business_id,id),
    FOREIGN KEY(business_id,reversal_of) REFERENCES herman.journal_entries(business_id,id),
    CHECK(reversal_of IS NULL OR reversal_of<>id)
);
CREATE TABLE herman.journal_lines (
    business_id uuid NOT NULL, entry_id uuid NOT NULL, line_number integer NOT NULL CHECK(line_number BETWEEN 1 AND 100),
    account_code text NOT NULL, side text NOT NULL CHECK(side IN ('debit','credit')),
    amount numeric NOT NULL CHECK(amount>0 AND amount<1e22 AND amount=round(amount,6)),
    document_id uuid NOT NULL, locator text NOT NULL CHECK(length(locator) BETWEEN 1 AND 500),
    created_by uuid NOT NULL REFERENCES herman.users(id),
    PRIMARY KEY(business_id,entry_id,line_number), UNIQUE(business_id,entry_id,account_code),
    FOREIGN KEY(business_id,entry_id) REFERENCES herman.journal_entries(business_id,id),
    FOREIGN KEY(business_id,account_code) REFERENCES herman.journal_accounts(business_id,code),
    FOREIGN KEY(business_id,document_id) REFERENCES herman.documents(business_id,id)
);
CREATE TABLE herman.journal_decisions (
    business_id uuid NOT NULL, entry_id uuid NOT NULL, approved boolean NOT NULL,
    reviewed_values boolean NOT NULL CHECK(reviewed_values),
    reason_fa text NOT NULL CHECK(length(reason_fa) BETWEEN 3 AND 2000),
    duplicate_resolution text CHECK(duplicate_resolution IN ('distinct_event','same_event')),
    event_fingerprint text NOT NULL, reversal_of uuid,
    created_by uuid NOT NULL REFERENCES herman.users(id), created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY(business_id,entry_id),
    FOREIGN KEY(business_id,entry_id) REFERENCES herman.journal_entries(business_id,id),
    CHECK(NOT approved OR duplicate_resolution IS DISTINCT FROM 'same_event')
);
CREATE UNIQUE INDEX journal_first_event ON herman.journal_decisions(business_id,event_fingerprint)
    WHERE approved AND duplicate_resolution IS NULL;
CREATE UNIQUE INDEX journal_one_reversal ON herman.journal_decisions(business_id,reversal_of)
    WHERE approved AND reversal_of IS NOT NULL;
CREATE INDEX journal_dates ON herman.journal_entries(business_id,entry_date,id);
CREATE INDEX journal_patterns ON herman.journal_entries(business_id,event_fingerprint,id);
CREATE INDEX journal_account_lines ON herman.journal_lines(business_id,account_code,entry_id);

CREATE FUNCTION herman.journal_stamp() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN NEW.created_xid := pg_current_xact_id(); RETURN NEW; END $$;
CREATE TRIGGER stamp BEFORE INSERT ON herman.journal_entries FOR EACH ROW EXECUTE FUNCTION herman.journal_stamp();
CREATE FUNCTION herman.journal_line_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NOT EXISTS(SELECT 1 FROM herman.journal_entries WHERE business_id=NEW.business_id AND id=NEW.entry_id
                  AND created_xid=pg_current_xact_id() AND created_by=NEW.created_by) THEN
        RAISE EXCEPTION 'journal lines must be inserted with their entry' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER line_guard BEFORE INSERT ON herman.journal_lines FOR EACH ROW EXECUTE FUNCTION herman.journal_line_guard();

CREATE FUNCTION herman.journal_check() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE target uuid; entry herman.journal_entries%ROWTYPE; original herman.journal_entries%ROWTYPE;
    n integer; net numeric; pattern text;
BEGIN
    IF TG_TABLE_NAME='journal_entries' THEN target:=NEW.id; ELSE target:=NEW.entry_id; END IF;
    SELECT * INTO STRICT entry FROM herman.journal_entries WHERE business_id=NEW.business_id AND id=target;
    SELECT count(*),sum(CASE WHEN side='debit' THEN amount ELSE -amount END),
           string_agg(account_code || ':' || side || ':' || (amount::numeric(28,6))::text,'|' ORDER BY account_code COLLATE "C")
      INTO n,net,pattern FROM herman.journal_lines WHERE business_id=NEW.business_id AND entry_id=target;
    IF n NOT BETWEEN 2 AND 100 OR net<>0 THEN
        RAISE EXCEPTION 'journal must contain balanced lines' USING ERRCODE='23514';
    END IF;
    IF entry.event_fingerprint<>encode(sha256(convert_to(to_char(entry.entry_date,'YYYY-MM-DD') || '|IRR|' || pattern,'UTF8')),'hex') THEN
        RAISE EXCEPTION 'journal pattern mismatch' USING ERRCODE='23514';
    END IF;
    IF entry.reversal_of IS NOT NULL THEN
        SELECT * INTO original FROM herman.journal_entries WHERE business_id=NEW.business_id AND id=entry.reversal_of;
        IF original.reversal_of IS NOT NULL OR entry.entry_date<original.entry_date OR NOT EXISTS(
            SELECT 1 FROM herman.journal_decisions WHERE business_id=NEW.business_id AND entry_id=entry.reversal_of AND approved
        ) THEN RAISE EXCEPTION 'invalid reversal target' USING ERRCODE='23514'; END IF;
        IF EXISTS(
            SELECT 1 FROM (SELECT * FROM herman.journal_lines WHERE business_id=NEW.business_id AND entry_id=target) a
            FULL JOIN (SELECT * FROM herman.journal_lines WHERE business_id=NEW.business_id AND entry_id=entry.reversal_of) b
            ON a.account_code=b.account_code
            WHERE a.account_code IS NULL OR b.account_code IS NULL OR a.side=b.side OR a.amount<>b.amount
               OR a.document_id<>b.document_id OR a.locator<>b.locator
        ) THEN RAISE EXCEPTION 'reversal must invert original lines and evidence' USING ERRCODE='23514'; END IF;
    END IF;
    RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER journal_balanced AFTER INSERT ON herman.journal_entries
    DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION herman.journal_check();
CREATE CONSTRAINT TRIGGER journal_balanced AFTER INSERT ON herman.journal_lines
    DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION herman.journal_check();

CREATE FUNCTION herman.journal_decision_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    SELECT event_fingerprint,reversal_of INTO NEW.event_fingerprint,NEW.reversal_of FROM herman.journal_entries
        WHERE business_id=NEW.business_id AND id=NEW.entry_id;
    IF NEW.approved AND NEW.duplicate_resolution IS NULL AND EXISTS(
        SELECT 1 FROM herman.journal_decisions WHERE business_id=NEW.business_id
        AND event_fingerprint=NEW.event_fingerprint AND approved
    ) THEN RAISE EXCEPTION 'duplicate pattern requires review' USING ERRCODE='23514'; END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER decision_guard BEFORE INSERT ON herman.journal_decisions
    FOR EACH ROW EXECUTE FUNCTION herman.journal_decision_guard();
DO $$
DECLARE t text;
BEGIN
    FOREACH t IN ARRAY ARRAY['journal_accounts','journal_entries','journal_lines','journal_decisions'] LOOP
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
DROP POLICY tenant_insert ON herman.journal_decisions;
CREATE POLICY tenant_insert ON herman.journal_decisions FOR INSERT WITH CHECK (
    business_id=herman.business_id() AND created_by=herman.user_id()
    AND herman.member_role(business_id) IN ('owner','reviewer')
);
REVOKE ALL ON herman.journal_accounts,herman.journal_entries,herman.journal_lines,herman.journal_decisions FROM PUBLIC;
INSERT INTO herman.schema_migrations(version) VALUES(9);
