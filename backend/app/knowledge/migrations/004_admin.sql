ALTER TABLE kb_versions ADD COLUMN auto_activate boolean NOT NULL DEFAULT false;
ALTER TABLE kb_versions ADD COLUMN auto_publish boolean NOT NULL DEFAULT false;
ALTER TABLE kb_documents ADD COLUMN purged_at timestamptz;

CREATE TABLE kb_pending_uploads (
    id text PRIMARY KEY,
    session_id text NOT NULL,
    object_key text NOT NULL,
    suffix text NOT NULL CHECK (suffix IN ('.md', '.txt', '.pdf', '.docx')),
    declared_size integer NOT NULL CHECK (declared_size > 0),
    uploaded_size integer,
    expires_at timestamptz NOT NULL,
    consumed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX kb_pending_uploads_expiry ON kb_pending_uploads (expires_at)
    WHERE consumed_at IS NULL;
