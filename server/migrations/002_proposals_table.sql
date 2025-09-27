-- Migration 002: Create proposals table
-- Main table for storing proposal data with proper constraints

CREATE TABLE IF NOT EXISTS proposals (
  id TEXT PRIMARY KEY,
  network TEXT NOT NULL CHECK (network IN ('polkadot','kusama')),
  type TEXT NOT NULL,
  title TEXT,
  description TEXT,
  proposer TEXT,
  amount_numeric NUMERIC,
  currency TEXT,
  status TEXT,
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ,
  metadata JSONB
);
