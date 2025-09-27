#!/usr/bin/env python3
"""
Complete ETL pipeline script
1. Fetch data using onchain_data.py
2. Process data using ETL service
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

# Add the app directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

from app.onchain_data import fetch_onchain_data
from app.services.etl import ETLService
from app.logger import get_logger

logger = get_logger(__name__)

def main():
    parser = argparse.ArgumentParser(description="Complete ETL Pipeline for Polkassembly Data")
    parser.add_argument("--fetch-data", action="store_true", 
                       help="Fetch fresh data from Polkassembly API")
    parser.add_argument("--max-items", type=int, default=100,
                       help="Maximum items per proposal type to fetch (default: 100)")
    parser.add_argument("--data-dir", type=str,
                       help="Directory to store/read data files")
    parser.add_argument("--input-files", nargs="+",
                       help="Specific input files to process (if not fetching)")
    parser.add_argument("--batch-size", type=int, default=100,
                       help="Batch size for ETL processing (default: 100)")
    parser.add_argument("--provider", choices=["openai", "bge-m3", "bge", "local"], 
                       default="openai", help="Embedding provider (default: openai)")
    parser.add_argument("--skip-fetch", action="store_true",
                       help="Skip data fetching, only run ETL on existing files")
    
    args = parser.parse_args()
    
    # Determine data directory
    if args.data_dir:
        data_dir = args.data_dir
    else:
        # Default to data directory in project root
        script_dir = os.path.dirname(os.path.abspath(__file__))
        data_dir = os.path.join(script_dir, "..", "data", "onchain_data")
        data_dir = os.path.abspath(data_dir)
    
    logger.info(f"Using data directory: {data_dir}")
    
    # Ensure data directory exists
    os.makedirs(data_dir, exist_ok=True)
    
    # Step 1: Fetch data (if requested)
    if args.fetch_data and not args.skip_fetch:
        logger.info("Fetching fresh data from Polkassembly API...")
        try:
            fetch_onchain_data(
                max_items_per_type=args.max_items,
                data_dir=data_dir
            )
            logger.info("Data fetching completed")
        except Exception as e:
            logger.error(f"Data fetching failed: {e}")
            return 1
    
    # Step 2: Determine input files for ETL
    if args.input_files:
        input_files = args.input_files
    else:
        # Find all JSON files in data directory
        data_path = Path(data_dir)
        input_files = list(data_path.glob("*.json"))
        input_files = [str(f) for f in input_files]
        
        if not input_files:
            logger.error(f"No JSON files found in {data_dir}")
            logger.info("Use --fetch-data to fetch fresh data or --input-files to specify files")
            return 1
    
    logger.info(f"Processing {len(input_files)} files: {input_files}")
    
    # Step 3: Run ETL process
    try:
        etl_service = ETLService(
            embedding_provider=args.provider,
            batch_size=args.batch_size
        )
        
        # Run async ETL process
        asyncio.run(etl_service.process_files(input_files))
        
        logger.info("ETL pipeline completed successfully")
        return 0
        
    except Exception as e:
        logger.error(f"ETL pipeline failed: {e}")
        return 1

if __name__ == "__main__":
    exit(main())
