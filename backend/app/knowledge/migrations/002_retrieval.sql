-- Phase 8.2: the local multilingual baseline has 384 dimensions.
ALTER TABLE kb_embeddings ALTER COLUMN embedding TYPE vector(384);
ALTER TABLE kb_embeddings DROP CONSTRAINT kb_embeddings_dimensions_check;
ALTER TABLE kb_embeddings ADD CONSTRAINT kb_embeddings_dimensions_check CHECK (dimensions = 384);

CREATE TABLE kb_index_generations (
    id text PRIMARY KEY,
    model text NOT NULL,
    revision text NOT NULL,
    dimensions integer NOT NULL CHECK (dimensions = 384),
    active boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX kb_one_active_generation ON kb_index_generations (active) WHERE active;
CREATE INDEX kb_chunks_keywords ON kb_chunks USING gin (keywords);
CREATE INDEX kb_embeddings_generation ON kb_embeddings (index_generation);
CREATE INDEX kb_versions_history ON kb_versions (document_id, effective_at DESC);
