ALTER TABLE herman.analysis_runs ADD COLUMN pack_uses jsonb NOT NULL DEFAULT '[]'::jsonb;
INSERT INTO herman.schema_migrations(version) VALUES(16);
