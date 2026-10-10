ALTER TABLE herman.journal_reports ADD COLUMN supersedes uuid,
    ADD FOREIGN KEY(business_id,supersedes) REFERENCES herman.journal_reports(business_id,id),
    ADD CHECK(supersedes IS NULL OR supersedes<>id);
ALTER TABLE herman.journal_report_decisions ADD COLUMN supersedes uuid;
CREATE UNIQUE INDEX journal_report_one_replacement ON herman.journal_report_decisions(business_id,supersedes)
    WHERE approved AND supersedes IS NOT NULL;
CREATE FUNCTION herman.journal_report_replacement() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE current_report herman.journal_reports%ROWTYPE;
BEGIN
    SELECT * INTO STRICT current_report FROM herman.journal_reports WHERE business_id=NEW.business_id AND id=NEW.report_id;
    NEW.supersedes := current_report.supersedes;
    IF NEW.approved AND NEW.supersedes IS NOT NULL AND NOT EXISTS(
        SELECT 1 FROM herman.journal_reports r JOIN herman.journal_report_decisions d
        ON (d.business_id,d.report_id)=(r.business_id,r.id)
        WHERE r.business_id=NEW.business_id AND r.id=NEW.supersedes AND d.approved
        AND r.period_start=current_report.period_start AND r.period_end=current_report.period_end
    ) THEN RAISE EXCEPTION 'replacement needs approved predecessor with same period' USING ERRCODE='23514'; END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER report_replacement BEFORE INSERT ON herman.journal_report_decisions
    FOR EACH ROW EXECUTE FUNCTION herman.journal_report_replacement();
INSERT INTO herman.schema_migrations(version) VALUES(11);
