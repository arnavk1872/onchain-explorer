#!/usr/bin/env python3
"""
Generate embeddings for all proposals in the database
This processes proposals in batches to avoid memory issues
"""

import asyncio
import os
import sys
from pathlib import Path

# Add the app directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

from app.db import get_pool
from app.services.etl import ETLService
from app.logger import get_logger

logger = get_logger(__name__)

async def generate_embeddings_from_db():
    """Generate embeddings for all proposals in the database"""
    
    logger.info("Starting embedding generation from database...")
    
    # Get database pool
    pool = await get_pool()
    
    # Get total count
    async with pool.acquire() as conn:
        total_proposals = await conn.fetchval("SELECT COUNT(*) FROM proposals")
        logger.info(f"Total proposals in database: {total_proposals}")
        
        # Check existing embeddings
        existing_embeddings = await conn.fetchval("SELECT COUNT(*) FROM proposals_embeddings")
        logger.info(f"Existing embeddings: {existing_embeddings}")
        
        if existing_embeddings >= total_proposals:
            logger.info("All proposals already have embeddings!")
            return
        
        remaining_proposals = total_proposals - existing_embeddings
        logger.info(f"Remaining proposals to process: {remaining_proposals}")
    
    # Create ETL service
    etl_service = ETLService(
        embedding_provider="openai",
        batch_size=50
    )
    
    # Process in batches
    batch_size = 1000
    offset = 0
    total_processed = 0
    
    while True:
        async with pool.acquire() as conn:
            # Get batch of proposals without embeddings
            proposals = await conn.fetch("""
                SELECT p.id, p.title, p.description, p.network, p.type
                FROM proposals p 
                LEFT JOIN proposals_embeddings pe ON p.id = pe.proposal_id
                WHERE pe.proposal_id IS NULL
                ORDER BY p.created_at DESC
                LIMIT $1 OFFSET $2
            """, batch_size, offset)
            
            if not proposals:
                break
            
            logger.info(f"Processing batch: {len(proposals)} proposals (offset: {offset})")
            
            # Process in smaller embedding batches (reduced for token limits)
            embedding_batch_size = 20
            for i in range(0, len(proposals), embedding_batch_size):
                batch = proposals[i:i + embedding_batch_size]
                batch_num = i // embedding_batch_size + 1
                
                logger.info(f"  Processing embedding batch {batch_num}/{(len(proposals) + embedding_batch_size - 1) // embedding_batch_size}")
                
                # Prepare texts for embedding with length limits
                texts = []
                proposal_ids = []
                
                for proposal in batch:
                    title = proposal['title'] or ''
                    description = proposal['description'] or ''
                    
                    # Truncate description if too long (keep first 2000 chars)
                    if len(description) > 2000:
                        description = description[:2000] + "..."
                    
                    text = f"{title}\n{description}".strip()
                    
                    # Skip if text is too long (safety check)
                    if len(text) > 6000:
                        text = text[:6000] + "..."
                    
                    if text:
                        texts.append(text)
                        proposal_ids.append(proposal['id'])
                
                if not texts:
                    logger.warning(f"    Batch {batch_num} has no valid texts, skipping")
                    continue
                
                # Compute embeddings
                try:
                    embeddings = await etl_service.embedding_provider.get_embeddings_batch(texts)
                    
                    # Store embeddings in a new connection
                    async with pool.acquire() as store_conn:
                        for proposal_id, embedding in zip(proposal_ids, embeddings):
                            embedding_str = '[' + ','.join(map(str, embedding)) + ']'
                            await store_conn.execute("""
                                INSERT INTO proposals_embeddings (proposal_id, embedding)
                                VALUES ($1, $2::vector)
                                ON CONFLICT (proposal_id) 
                                DO UPDATE SET embedding = EXCLUDED.embedding
                            """, proposal_id, embedding_str)
                    
                    logger.info(f"    Stored {len(embeddings)} embeddings for batch {batch_num}")
                    total_processed += len(embeddings)
                    
                except Exception as e:
                    logger.error(f"    Error processing batch {batch_num}: {e}")
                    continue
            
            offset += batch_size
            
            # Progress update
            progress = (total_processed / remaining_proposals) * 100
            logger.info(f"Progress: {total_processed} embeddings generated ({progress:.1f}% of remaining)")
            
            if len(proposals) < batch_size:
                break
    
    # Final verification
    async with pool.acquire() as conn:
        final_embeddings = await conn.fetchval("SELECT COUNT(*) FROM proposals_embeddings")
        logger.info(f"Embedding generation completed!")
        logger.info(f"Total embeddings: {final_embeddings}/{total_proposals}")
        logger.info(f"Coverage: {(final_embeddings/total_proposals)*100:.1f}%")

def main():
    try:
        asyncio.run(generate_embeddings_from_db())
        return 0
    except Exception as e:
        logger.error(f"Embedding generation failed: {e}")
        return 1

if __name__ == "__main__":
    exit(main())
