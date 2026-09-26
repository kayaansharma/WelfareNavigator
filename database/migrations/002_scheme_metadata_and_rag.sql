-- Additive metadata and RAG storage scaffold for existing Welfare Navigator DBs.
-- Runtime demo mode currently uses a cached in-memory sparse index; pgvector
-- storage is ready for a configured PostgreSQL deployment.
CREATE EXTENSION IF NOT EXISTS vector;

ALTER TABLE schemes ADD COLUMN IF NOT EXISTS sub_category TEXT;
ALTER TABLE schemes ADD COLUMN IF NOT EXISTS target_groups JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE schemes ADD COLUMN IF NOT EXISTS required_profile_attributes JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE schemes ADD COLUMN IF NOT EXISTS exclusion_attributes JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE schemes ADD COLUMN IF NOT EXISTS keywords JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE schemes ADD COLUMN IF NOT EXISTS synonyms JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE schemes ADD COLUMN IF NOT EXISTS government_level TEXT;

CREATE TABLE IF NOT EXISTS scheme_rag_chunks (
    id BIGSERIAL PRIMARY KEY,
    scheme_id TEXT NOT NULL REFERENCES schemes(id) ON DELETE CASCADE,
    chunk_type TEXT NOT NULL CHECK (chunk_type IN ('overview','eligibility','benefits','documents','application','guideline')),
    content TEXT NOT NULL,
    source_url TEXT NOT NULL,
    source_name TEXT NOT NULL,
    last_verified DATE,
    embedding vector(384),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS scheme_rag_chunks_scheme_id_idx ON scheme_rag_chunks(scheme_id);
CREATE INDEX IF NOT EXISTS scheme_rag_chunks_embedding_idx
    ON scheme_rag_chunks USING hnsw (embedding vector_cosine_ops)
    WHERE embedding IS NOT NULL;
