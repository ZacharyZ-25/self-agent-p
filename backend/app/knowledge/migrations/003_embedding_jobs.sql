ALTER TABLE kb_jobs DROP CONSTRAINT kb_jobs_stage_check;
ALTER TABLE kb_jobs ADD CONSTRAINT kb_jobs_stage_check CHECK (stage IN
    ('queued','parsing','chunking','extracted','embedding','ready','needs_review','failed'));
