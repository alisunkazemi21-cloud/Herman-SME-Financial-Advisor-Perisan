CREATE INDEX document_hash_idx ON herman.documents(business_id,sha256,id);
ALTER TABLE herman.approvals ADD COLUMN duplicate_resolution text
    CHECK(duplicate_resolution IN ('same_event','distinct_event'));
ALTER TABLE herman.approvals ADD CONSTRAINT duplicate_rejection_check
    CHECK(duplicate_resolution IS DISTINCT FROM 'same_event' OR NOT approved);
INSERT INTO herman.schema_migrations(version) VALUES(5);
