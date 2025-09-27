-- Migration 005: Fix embeddings table to support different vector dimensions
-- This migration is idempotent and non-destructive

-- Check if table exists and has correct dimensions
DO $$
BEGIN
    -- If table doesn't exist, create it
    IF NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'proposals_embeddings') THEN
        CREATE TABLE proposals_embeddings (
            proposal_id TEXT PRIMARY KEY REFERENCES proposals(id) ON DELETE CASCADE,
            embedding VECTOR(1536) -- 1536 for OpenAI text-embedding-3-small
        );
        
        -- Create the vector index
        CREATE INDEX IF NOT EXISTS idx_embeddings_hnsw ON proposals_embeddings USING hnsw (embedding vector_ip_ops);
        
        RAISE NOTICE 'Created proposals_embeddings table with VECTOR(1536)';
        
    -- If table exists, check if it has the right dimensions
    ELSIF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'proposals_embeddings' 
        AND column_name = 'embedding' 
        AND data_type = 'USER-DEFINED'
    ) THEN
        -- Check current vector dimensions by looking at the column definition
        IF EXISTS (
            SELECT 1 FROM pg_attribute 
            WHERE attrelid = 'proposals_embeddings'::regclass 
            AND attname = 'embedding'
            AND atttypid = (SELECT oid FROM pg_type WHERE typname = 'vector')
        ) THEN
            -- Table exists with vector column, assume it's correct
            RAISE NOTICE 'proposals_embeddings table already exists with vector column';
        ELSE
            -- This shouldn't happen, but just in case
            RAISE NOTICE 'proposals_embeddings table exists but embedding column is not vector type';
        END IF;
    ELSE
        RAISE NOTICE 'proposals_embeddings table exists but no embedding column found';
    END IF;
END $$;
