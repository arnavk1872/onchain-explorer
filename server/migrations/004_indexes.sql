-- Migration 004: Add indexes for exact, fuzzy, and semantic retrieval
-- Full-text search, trigram similarity, and vector HNSW index

-- Full-text search index
ALTER TABLE proposals ADD COLUMN IF NOT EXISTS doc_tsv tsvector;
UPDATE proposals SET doc_tsv = to_tsvector('simple', coalesce(title,'') || ' ' || coalesce(description,''));
CREATE INDEX IF NOT EXISTS idx_proposals_tsv ON proposals USING GIN (doc_tsv);

-- Trigram similarity indexes for fuzzy search
CREATE INDEX IF NOT EXISTS idx_proposals_title_trgm ON proposals USING GIN (title gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_proposals_proposer_trgm ON proposals USING GIN (proposer gin_trgm_ops);

-- Vector HNSW index for semantic search
CREATE INDEX IF NOT EXISTS idx_embeddings_hnsw ON proposals_embeddings USING hnsw (embedding vector_ip_ops);

-- Additional performance indexes
CREATE INDEX IF NOT EXISTS idx_proposals_network ON proposals (network);
CREATE INDEX IF NOT EXISTS idx_proposals_type ON proposals (type);
CREATE INDEX IF NOT EXISTS idx_proposals_status ON proposals (status);
CREATE INDEX IF NOT EXISTS idx_proposals_created_at ON proposals (created_at);
CREATE INDEX IF NOT EXISTS idx_proposals_amount ON proposals (amount_numeric);
