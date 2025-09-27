#!/usr/bin/env python3
"""Check what's already in the database"""

import asyncio
import sys
import os

# Add the app directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

from app.db import get_pool
from app.logger import get_logger

logger = get_logger(__name__)

async def check_database():
    """Check what's already in the database"""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            # Check proposals
            proposals_count = await conn.fetchval('SELECT COUNT(*) FROM proposals')
            print(f"Proposals in database: {proposals_count}")
            
            # Check embeddings
            embeddings_count = await conn.fetchval('SELECT COUNT(*) FROM proposals_embeddings')
            print(f"Embeddings in database: {embeddings_count}")
            
            # Check networks
            networks = await conn.fetch('SELECT DISTINCT network FROM proposals ORDER BY network')
            print(f"Networks: {[row['network'] for row in networks]}")
            
            # Check proposal types
            types = await conn.fetch('SELECT DISTINCT type FROM proposals ORDER BY type')
            print(f"Proposal types: {[row['type'] for row in types]}")
            
    except Exception as e:
        print(f"Error checking database: {e}")

if __name__ == "__main__":
    asyncio.run(check_database())

