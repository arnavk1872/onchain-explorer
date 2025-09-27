#!/usr/bin/env python3
"""
Script to regenerate embeddings for existing proposals
This will only compute and store embeddings without touching the proposals data
"""

import asyncio
import os
import sys
from pathlib import Path

# Add the app directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

from app.db import get_session
from app.services.etl import ETLService
from app.logger import get_logger

logger = get_logger(__name__)

async def regenerate_embeddings():
    """Regenerate embeddings for all existing proposals"""
    
    logger.info("Starting embedding regeneration for existing proposals...")
    
    # Get all proposals that don't have embeddings
    async with get_session() as conn:
        # Check how many proposals exist
        total_proposals = await conn.fetchval("SELECT COUNT(*) FROM proposals")
        logger.info(f"Total proposals in database: {total_proposals}")
        
        # Check how many have embeddings
        proposals_with_embeddings = await conn.fetchval("""
            SELECT COUNT(*) FROM proposals p 
            JOIN proposals_embeddings pe ON p.id = pe.proposal_id
        """)
        logger.info(f"Proposals with embeddings: {proposals_with_embeddings}")
        
        # Process in smaller batches to avoid timeout
        batch_size = 1000
        offset = 0
        total_processed = 0
        
        while True:
            # Get batch of proposals without embeddings
            proposals_batch = await conn.fetch("""
                SELECT p.id, p.title, p.description, p.network, p.type
                FROM proposals p 
                LEFT JOIN proposals_embeddings pe ON p.id = pe.proposal_id
                WHERE pe.proposal_id IS NULL
                ORDER BY p.created_at DESC
                LIMIT $1 OFFSET $2
            """, batch_size, offset)
            
            if not proposals_batch:
                break
                
            logger.info(f"Processing batch: {len(proposals_batch)} proposals (offset: {offset})")
            total_processed += len(proposals_batch)
        
            # Create ETL service for embedding generation
            etl_service = ETLService(
                embedding_provider="openai",
                batch_size=50
            )
            
            # Process proposals in smaller embedding batches
            embedding_batch_size = 50
            total_embedding_batches = (len(proposals_batch) + embedding_batch_size - 1) // embedding_batch_size
            
            for i in range(0, len(proposals_batch), embedding_batch_size):
                batch = proposals_batch[i:i + embedding_batch_size]
                batch_num = i // embedding_batch_size + 1
                
                logger.info(f"Processing embedding batch {batch_num}/{total_embedding_batches} ({len(batch)} proposals)")
                
                # Prepare texts for embedding
                texts = []
                proposal_ids = []
                
                for proposal in batch:
                    # Create text for embedding (title + description)
                    title = proposal['title'] or ''
                    description = proposal['description'] or ''
                    text = f"{title}\n{description}".strip()
                    
                    if text:  # Only process non-empty texts
                        texts.append(text)
                        proposal_ids.append(proposal['id'])
                
                if not texts:
                    logger.warning(f"Embedding batch {batch_num} has no valid texts, skipping")
                    continue
                
                # Compute embeddings
                try:
                    embeddings = await etl_service.embedding_provider.get_embeddings_batch(texts)
                    
                    # Store embeddings
                    for proposal_id, embedding in zip(proposal_ids, embeddings):
                        embedding_str = '[' + ','.join(map(str, embedding)) + ']'
                        await conn.execute("""
                            INSERT INTO proposals_embeddings (proposal_id, embedding)
                            VALUES ($1, $2::vector)
                            ON CONFLICT (proposal_id) 
                            DO UPDATE SET embedding = EXCLUDED.embedding
                        """, proposal_id, embedding_str)
                    
                    logger.info(f"Embedding batch {batch_num} completed: {len(embeddings)} embeddings stored")
                    
                except Exception as e:
                    logger.error(f"Error processing embedding batch {batch_num}: {e}")
                    continue
            
            offset += batch_size
            
            if len(proposals_batch) < batch_size:
                break
        
        # Verify final count
        async with get_session() as conn:
            final_embeddings = await conn.fetchval("""
                SELECT COUNT(*) FROM proposals p 
                JOIN proposals_embeddings pe ON p.id = pe.proposal_id
            """)
        
        logger.info(f"Embedding regeneration completed!")
        logger.info(f"Total processed: {total_processed} proposals")
        logger.info(f"Final count - Proposals with embeddings: {final_embeddings}/{total_proposals}")

def main():
    """Run the embedding regeneration"""
    try:
        asyncio.run(regenerate_embeddings())
        logger.info("Embedding regeneration completed successfully")
        return 0
    except Exception as e:
        logger.error(f"Embedding regeneration failed: {e}")
        return 1

if __name__ == "__main__":
    exit(main())
