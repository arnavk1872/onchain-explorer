# ETL Service for Polkassembly Data

This ETL (Extract, Transform, Load) service processes Polkassembly data from JSON/CSV files, normalizes the data, and loads it into the database with vector embeddings for semantic search.

## Features

- **Data Loading**: Loads JSON/CSV files using Polars for high performance
- **Field Normalization**: Normalizes network, type, amount, currency, and timestamp fields
- **Bulk Upserts**: Uses SQLAlchemy core with PostgreSQL ON CONFLICT for efficient upserts
- **Full-text Search**: Recomputes doc_tsv for PostgreSQL full-text search
- **Vector Embeddings**: Computes embeddings using OpenAI or local BGE-M3 models
- **Rate Limiting**: Built-in rate limiting and backoff for API calls
- **Robust Logging**: Comprehensive logging throughout the process

## Installation

Install the required dependencies:

```bash
pip install -r requirements.txt
```

## Environment Variables

For OpenAI embeddings, set your API key:

```bash
export OPENAI_API_KEY="your-api-key-here"
```

## Usage

### 1. Fetch Data from Polkassembly API

First, fetch data using the onchain_data.py script:

```bash
# Fetch data for all networks and proposal types
python -m app.onchain_data

# Or with custom parameters
python -m app.onchain_data --max-items 1000 --data-dir ./data/onchain_data
```

### 2. Process Data with ETL Service

#### Using the ETL service directly:

```bash
# Process specific files with OpenAI embeddings
python -m app.services.etl --input file1.json file2.json --provider openai --batch-size 100

# Process files with local BGE-M3 embeddings
python -m app.services.etl --input file1.json file2.json --provider bge-m3 --batch-size 50
```

#### Using the complete pipeline:

```bash
# Fetch fresh data and process it
python run_etl_pipeline.py --fetch-data --max-items 100 --provider openai

# Process existing files only
python run_etl_pipeline.py --input-files data/onchain_data/*.json --provider bge-m3
```

### 3. Programmatic Usage

```python
import asyncio
from app.services.etl import ETLService

async def process_data():
    # Create ETL service
    etl_service = ETLService(
        embedding_provider="openai",  # or "bge-m3"
        batch_size=100
    )
    
    # Process files
    await etl_service.process_files([
        "data/onchain_data/polkadot_DemocracyProposal_20241203.json",
        "data/onchain_data/kusama_TreasuryProposal_20241203.json"
    ])

# Run the async function
asyncio.run(process_data())
```

## Command Line Arguments

### ETL Service (`app/services/etl.py`)

- `--input`, `-i`: Input JSON/CSV files to process (required)
- `--batch-size`, `-b`: Batch size for processing (default: 100)
- `--provider`, `-p`: Embedding provider - "openai", "bge-m3", "bge", or "local" (default: openai)

### Pipeline Script (`run_etl_pipeline.py`)

- `--fetch-data`: Fetch fresh data from Polkassembly API
- `--max-items`: Maximum items per proposal type to fetch (default: 100)
- `--data-dir`: Directory to store/read data files
- `--input-files`: Specific input files to process
- `--batch-size`: Batch size for ETL processing (default: 100)
- `--provider`: Embedding provider (default: openai)
- `--skip-fetch`: Skip data fetching, only run ETL on existing files

## Data Normalization

The ETL service normalizes the following fields:

### Network
- Maps variations like "dot", "ksm" to "polkadot", "kusama"
- Defaults to "polkadot" if not specified

### Type
- Normalizes proposal types to standard format:
  - "democracyproposal" → "DemocracyProposal"
  - "treasury_proposal" → "TreasuryProposal"
  - etc.

### Amount
- Converts to numeric float values
- Removes currency symbols and commas
- Handles various input formats

### Currency
- Normalizes to uppercase
- Maps common variations

### Created At
- Parses various timestamp formats
- Falls back to current time if parsing fails

## Embedding Providers

### OpenAI (Default)
- Model: `text-embedding-3-large` (3072 dimensions)
- Requires: `OPENAI_API_KEY` environment variable
- Features: Rate limiting, batch processing, error handling

### BGE-M3 (Local)
- Model: `BAAI/bge-m3` (1024 dimensions)
- Runs locally, no API key required
- First run downloads the model (~2GB)

## Database Schema

The ETL service works with these tables:

### proposals
- `id`: Primary key
- `network`: Network name (polkadot/kusama)
- `type`: Proposal type
- `title`, `description`: Text content
- `proposer`: Proposer address
- `amount_numeric`: Numeric amount
- `currency`: Currency code
- `status`: Proposal status
- `created_at`, `updated_at`: Timestamps
- `metadata`: JSON metadata
- `doc_tsv`: Full-text search vector

### proposals_embeddings
- `proposal_id`: Foreign key to proposals
- `embedding`: Vector embedding (dimensions vary by provider)

## Performance Tips

1. **Batch Size**: Adjust batch size based on available memory and API limits
2. **Embedding Provider**: Use BGE-M3 for local processing, OpenAI for production
3. **File Size**: Process large datasets in chunks
4. **Rate Limiting**: The service includes built-in rate limiting for APIs

## Error Handling

The ETL service includes comprehensive error handling:

- Continues processing on individual record failures
- Logs all errors with context
- Implements exponential backoff for API rate limits
- Validates data before processing

## Logging

All operations are logged with appropriate levels:

- `INFO`: Progress updates and successful operations
- `WARNING`: Non-fatal issues (e.g., missing fields)
- `ERROR`: Fatal errors that stop processing

## Example Output

```
2024-12-03 12:34:56 INFO Loading data from: data/onchain_data/polkadot_DemocracyProposal_20241203.json
2024-12-03 12:34:56 INFO Loaded 150 records from 1 files
2024-12-03 12:34:56 INFO Normalizing data...
2024-12-03 12:34:57 INFO Normalized 150 records
2024-12-03 12:34:57 INFO Upserting 150 proposals...
2024-12-03 12:34:58 INFO Upserted batch 1/2
2024-12-03 12:34:58 INFO Upserted batch 2/2
2024-12-03 12:34:58 INFO Proposal upserts completed
2024-12-03 12:34:58 INFO Recomputing doc_tsv for all proposals...
2024-12-03 12:34:59 INFO Updated doc_tsv for 150 proposals
2024-12-03 12:34:59 INFO Computing embeddings for 150 proposals...
2024-12-03 12:35:00 INFO Computing embeddings for batch 1/2
2024-12-03 12:35:02 INFO Upserted embeddings for batch 1
2024-12-03 12:35:02 INFO Computing embeddings for batch 2/2
2024-12-03 12:35:04 INFO Upserted embeddings for batch 2
2024-12-03 12:35:04 INFO Computed and stored 150 embeddings
2024-12-03 12:35:04 INFO ETL process completed successfully
```
