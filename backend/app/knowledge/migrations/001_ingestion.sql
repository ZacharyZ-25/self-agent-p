CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE kb_documents (
    id text PRIMARY KEY,
    title text NOT NULL,
    project text,
    fact_type text NOT NULL CHECK (fact_type IN ('project', 'external_reference', 'identity')),
    author text NOT NULL,
    subject_relation text NOT NULL,
    visibility text NOT NULL CHECK (visibility IN ('private_preview', 'public_answer')),
    published boolean NOT NULL DEFAULT false,
    active_version_id text,
    deleted_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE kb_versions (
    id text PRIMARY KEY,
    document_id text NOT NULL REFERENCES kb_documents(id),
    fingerprint text NOT NULL,
    content_hash text NOT NULL,
    object_key text NOT NULL,
    file_type text NOT NULL CHECK (file_type IN ('.md', '.txt', '.pdf', '.docx')),
    source_date date NOT NULL,
    effective_at date NOT NULL,
    replaces text,
    parser_version text NOT NULL,
    chunker_version text NOT NULL,
    state text NOT NULL DEFAULT 'queued' CHECK (state IN
      ('queued','parsing','chunking','awaiting_embedding','needs_review','failed','ready')),
    parsed_blocks jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (document_id, fingerprint),
    UNIQUE (document_id, id),
    FOREIGN KEY (document_id, replaces) REFERENCES kb_versions(document_id, id)
);
ALTER TABLE kb_documents ADD CONSTRAINT kb_active_belongs_to_document
  FOREIGN KEY (id, active_version_id) REFERENCES kb_versions(document_id, id);
CREATE TABLE kb_chunks (
    id text PRIMARY KEY,
    version_id text NOT NULL REFERENCES kb_versions(id) ON DELETE CASCADE,
    ordinal integer NOT NULL,
    body text NOT NULL,
    locations jsonb NOT NULL,
    token_count integer NOT NULL CHECK (token_count > 0),
    content_hash text NOT NULL,
    keywords tsvector,
    UNIQUE (version_id, ordinal)
);
CREATE TABLE kb_embeddings (
    chunk_id text NOT NULL REFERENCES kb_chunks(id) ON DELETE CASCADE,
    model text NOT NULL,
    revision text NOT NULL,
    dimensions integer NOT NULL CHECK (dimensions = 1536),
    index_generation text NOT NULL,
    embedding vector(1536) NOT NULL,
    PRIMARY KEY (chunk_id, index_generation)
);
CREATE TABLE kb_jobs (
    id text PRIMARY KEY,
    version_id text NOT NULL UNIQUE REFERENCES kb_versions(id),
    stage text NOT NULL DEFAULT 'queued' CHECK (stage IN
      ('queued','parsing','chunking','extracted','needs_review','failed')),
    attempts integer NOT NULL DEFAULT 0,
    max_attempts integer NOT NULL,
    lease_token text,
    lease_until timestamptz,
    heartbeat_at timestamptz,
    available_at timestamptz NOT NULL DEFAULT now(),
    error_code text,
    pipeline_version text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX kb_jobs_available ON kb_jobs (available_at, created_at)
 WHERE stage IN ('queued','parsing','chunking');
CREATE TABLE kb_events (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    document_id text NOT NULL REFERENCES kb_documents(id),
    version_id text REFERENCES kb_versions(id),
    action text NOT NULL,
    actor text NOT NULL,
    details jsonb NOT NULL DEFAULT '{}',
    created_at timestamptz NOT NULL DEFAULT now()
);
