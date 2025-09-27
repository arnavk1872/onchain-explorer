## Onchain Explorer

Hybrid question-answering over on-chain data (and beyond): LangGraph routes each question to the best path — Semantic Search (RAG) or Natural-Language-to-SQL — and merges results into a table + narrative for fast verification and easy reading.

This template is designed to generalize: swap the dataset and schema to use it for product analytics, support ops, research, finance, etc.

Typical stack (swap as needed): OpenAI/Anthropic/OSS model, Postgres/DuckDB/SQLite, FastAPI + LangGraph, optional web UI.

## Quickstart

Prereqs: Python 3.11+, SQL DB (Postgres or DuckDB/SQLite), Langgraph, COHERE optional.

Configure .env

OPENAI_API_KEY=sk-...
DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/onchain_db

Evaluation
NL→SQL: SQL correctness vs. gold, exec success, latency, row accuracy
Retrieval: recall, context precision, faithfulness


Security & Limits
Read-only DB, block non-SELECT, redact PII, rate limits, per-route budgets, caching where safe.


Contributing
PRs welcome—open an issue first for major changes, add tests for new router logic.
