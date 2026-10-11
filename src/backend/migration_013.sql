ALTER TABLE herman.knowledge_claims ADD COLUMN supersedes uuid,
    ADD FOREIGN KEY(business_id,supersedes) REFERENCES herman.knowledge_claims(business_id,id),
    ADD CHECK(supersedes IS NULL OR supersedes<>id);
ALTER TABLE herman.knowledge_decisions ADD COLUMN supersedes uuid;
CREATE INDEX knowledge_predecessor_idx ON herman.knowledge_claims(business_id,supersedes,id)
    WHERE supersedes IS NOT NULL;
CREATE UNIQUE INDEX knowledge_one_replacement ON herman.knowledge_decisions(business_id,supersedes)
    WHERE approved AND supersedes IS NOT NULL;

-- Existing approved predecessors make correction links acyclic without recursive reads.
CREATE FUNCTION herman.knowledge_correction_proposal() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.supersedes IS NOT NULL THEN
        IF NOT EXISTS (
            SELECT 1 FROM herman.knowledge_claims k JOIN herman.knowledge_decisions d
            ON (d.business_id,d.claim_id)=(k.business_id,k.id)
            WHERE k.business_id=NEW.business_id AND k.id=NEW.supersedes AND k.key=NEW.key AND d.approved
        ) OR EXISTS (
            SELECT 1 FROM herman.knowledge_decisions d
            WHERE d.business_id=NEW.business_id AND d.supersedes=NEW.supersedes AND d.approved
        ) THEN
            RAISE EXCEPTION 'correction needs current approved predecessor with same key' USING ERRCODE='23514';
        END IF;
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER knowledge_correction_proposal BEFORE INSERT ON herman.knowledge_claims
    FOR EACH ROW EXECUTE FUNCTION herman.knowledge_correction_proposal();

CREATE FUNCTION herman.knowledge_correction_decision() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE claim herman.knowledge_claims%ROWTYPE;
BEGIN
    SELECT * INTO STRICT claim FROM herman.knowledge_claims
        WHERE business_id=NEW.business_id AND id=NEW.claim_id;
    -- Clients cannot hide a competing correction by forging or omitting this link.
    NEW.supersedes := claim.supersedes;
    IF NEW.approved AND NEW.supersedes IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM herman.knowledge_claims k JOIN herman.knowledge_decisions d
        ON (d.business_id,d.claim_id)=(k.business_id,k.id)
        WHERE k.business_id=NEW.business_id AND k.id=NEW.supersedes AND k.key=claim.key AND d.approved
    ) THEN
        RAISE EXCEPTION 'correction approval needs approved predecessor with same key' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER knowledge_correction_decision BEFORE INSERT ON herman.knowledge_decisions
    FOR EACH ROW EXECUTE FUNCTION herman.knowledge_correction_decision();
INSERT INTO herman.schema_migrations(version) VALUES(13);
