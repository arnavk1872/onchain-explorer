-- Migration 003: Create proposals_embeddings table
-- Table for storing vector embeddings with foreign key reference

CREATE TABLE IF NOT EXISTS proposals_embeddings (
  proposal_id TEXT PRIMARY KEY REFERENCES proposals(id) ON DELETE CASCADE,
  embedding VECTOR(1536) -- 1536 for OpenAI, 1024/others if needed
);
