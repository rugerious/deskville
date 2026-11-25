-- Layer 4 (D30-D31): documents become chunks with their metadata, a vector index,
-- and the one search function residents' queries go through.
-- Additive only; the TEST rows of the isolation suite (doc_id NULL) stay valid.
SET ROLE deskville_owner;

ALTER TABLE app.documents
  ADD COLUMN IF NOT EXISTS doc_id      text,
  ADD COLUMN IF NOT EXISTS chunk_index integer,
  ADD COLUMN IF NOT EXISTS heading     text,
  ADD COLUMN IF NOT EXISTS sources     text[] NOT NULL DEFAULT '{}',
  ADD COLUMN IF NOT EXISTS retrieved   date,
  ADD COLUMN IF NOT EXISTS visibility  text NOT NULL DEFAULT 'public',
  ADD COLUMN IF NOT EXISTS cache_key   text;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'documents_visibility_check') THEN
    ALTER TABLE app.documents
      ADD CONSTRAINT documents_visibility_check CHECK (visibility IN ('public', 'internal'));
  END IF;
END $$;

-- One row per chunk per council.
CREATE UNIQUE INDEX IF NOT EXISTS documents_tenant_doc_chunk
  ON app.documents (tenant_id, doc_id, chunk_index);

-- Approximate nearest-neighbour index (cosine; Titan vectors are normalised).
-- Note: an HNSW scan picks the nearest vectors first and row-level security
-- filters them afterwards, so without iterative scans a council can get fewer
-- results than asked for. search_public turns iterative scans on (pgvector 0.8).
CREATE INDEX IF NOT EXISTS documents_embedding_hnsw
  ON app.documents USING hnsw (embedding vector_cosine_ops);

-- The resident-facing search: public chunks only, k nearest, RLS applies
-- (SECURITY INVOKER: it runs with the caller's rights and tenant).
CREATE OR REPLACE FUNCTION app.search_public(query vector(1024), k integer DEFAULT 5)
RETURNS TABLE (doc_id text, chunk_index integer, heading text, chunk text,
               sources text[], retrieved date, distance double precision)
LANGUAGE sql STABLE SECURITY INVOKER
SET hnsw.iterative_scan = 'relaxed_order'
AS $fn$
  WITH nearest AS MATERIALIZED (
    SELECT d.doc_id, d.chunk_index, d.heading, d.chunk, d.sources, d.retrieved,
           d.embedding <=> query AS distance
      FROM app.documents d
     WHERE d.visibility = 'public' AND d.doc_id IS NOT NULL
     ORDER BY d.embedding <=> query
     LIMIT k
  )
  SELECT * FROM nearest ORDER BY distance;  -- relaxed_order can be slightly out of order
$fn$;

REVOKE ALL ON FUNCTION app.search_public(vector, integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION app.search_public(vector, integer) TO deskville_app;

RESET ROLE;
