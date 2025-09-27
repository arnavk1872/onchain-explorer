-- Migration 001: Add required PostgreSQL extensions
-- pg_trgm for trigram similarity search
-- pgvector for vector operations and HNSW index

CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS vector;
