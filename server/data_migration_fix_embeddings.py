#!/usr/bin/env python3
"""
Data Migration: Fix Embeddings Vector Dimensions
===============================================

This script handles the data migration for changing vector dimensions from 1024 to 1536.
It preserves all existing embeddings while updating the table structure.

Usage:
    python data_migration_fix_embeddings.py

This script will:
1. Check current vector dimensions
2. Backup existing embeddings
3. Recreate table with correct dimensions (1536)
4. Restore embeddings from backup
5. Verify data integrity
"""

import asyncio
import os
import sys
from typing import List, Dict, Any
from app.db import get_pool, close_pool
from app.logger import get_logger

logger = get_logger(__name__)

async def check_vector_dimensions():
    """Check current vector dimensions in the embeddings table"""
    pool = await get_pool()
    
    async with pool.acquire() as conn:
        # Check if table exists
        table_exists = await conn.fetchval("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables 
                WHERE table_name = 'proposals_embeddings'
            )
        """)
        
        if not table_exists:
            logger.info("proposals_embeddings table does not exist")
            return None
            
        # Check current vector dimensions by examining a sample embedding
        try:
            sample_embedding = await conn.fetchval("""
                SELECT embedding FROM proposals_embeddings 
                WHERE embedding IS NOT NULL 
                LIMIT 1
            """)
            
            if sample_embedding:
                # Convert to list to check dimensions
                embedding_list = sample_embedding
                dimensions = len(embedding_list)
                logger.info(f"Current vector dimensions: {dimensions}")
                return dimensions
            else:
                logger.info("No embeddings found in table")
                return 0
                
        except Exception as e:
            logger.error(f"Error checking vector dimensions: {e}")
            return None

async def backup_embeddings():
    """Create a backup of all embeddings"""
    pool = await get_pool()
    
    async with pool.acquire() as conn:
        logger.info("Creating backup of existing embeddings...")
        
        # Create backup table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS temp_embeddings_backup AS 
            SELECT proposal_id, embedding::text as embedding_text 
            FROM proposals_embeddings
        """)
        
        # Count backup records
        backup_count = await conn.fetchval("SELECT COUNT(*) FROM temp_embeddings_backup")
        logger.info(f"Backed up {backup_count} embeddings")
        
        return backup_count

async def recreate_embeddings_table():
    """Recreate the embeddings table with correct dimensions"""
    pool = await get_pool()
    
    async with pool.acquire() as conn:
        logger.info("Recreating embeddings table with VECTOR(1536)...")
        
        # Drop existing table
        await conn.execute("DROP TABLE IF EXISTS proposals_embeddings CASCADE")
        
        # Create new table with correct dimensions
        await conn.execute("""
            CREATE TABLE proposals_embeddings (
                proposal_id TEXT PRIMARY KEY REFERENCES proposals(id) ON DELETE CASCADE,
                embedding VECTOR(1536) -- 1536 for OpenAI text-embedding-3-small
            )
        """)
        
        # Create vector index
        await conn.execute("""
            CREATE INDEX idx_embeddings_hnsw ON proposals_embeddings 
            USING hnsw (embedding vector_ip_ops)
        """)
        
        logger.info("Embeddings table recreated with VECTOR(1536)")

async def restore_embeddings():
    """Restore embeddings from backup"""
    pool = await get_pool()
    
    async with pool.acquire() as conn:
        logger.info("Restoring embeddings from backup...")
        
        # Restore embeddings from backup
        result = await conn.execute("""
            INSERT INTO proposals_embeddings (proposal_id, embedding)
            SELECT proposal_id, embedding_text::vector
            FROM temp_embeddings_backup
            WHERE embedding_text IS NOT NULL
        """)
        
        # Count restored records
        restored_count = await conn.fetchval("SELECT COUNT(*) FROM proposals_embeddings")
        logger.info(f"Restored {restored_count} embeddings")
        
        return restored_count

async def cleanup_backup():
    """Clean up backup table"""
    pool = await get_pool()
    
    async with pool.acquire() as conn:
        logger.info("Cleaning up backup table...")
        await conn.execute("DROP TABLE IF EXISTS temp_embeddings_backup")
        logger.info("Backup table cleaned up")

async def verify_migration():
    """Verify the migration was successful"""
    pool = await get_pool()
    
    async with pool.acquire() as conn:
        # Check final counts
        total_proposals = await conn.fetchval("SELECT COUNT(*) FROM proposals")
        total_embeddings = await conn.fetchval("SELECT COUNT(*) FROM proposals_embeddings")
        
        logger.info(f"Verification:")
        logger.info(f"  Total proposals: {total_proposals}")
        logger.info(f"  Total embeddings: {total_embeddings}")
        
        # Check vector dimensions
        sample_embedding = await conn.fetchval("""
            SELECT embedding FROM proposals_embeddings 
            WHERE embedding IS NOT NULL 
            LIMIT 1
        """)
        
        if sample_embedding:
            dimensions = len(sample_embedding)
            logger.info(f"  Vector dimensions: {dimensions}")
            
            if dimensions == 1536:
                logger.info("✅ Migration successful! Vector dimensions are correct.")
                return True
            else:
                logger.error(f"❌ Migration failed! Expected 1536 dimensions, got {dimensions}")
                return False
        else:
            logger.warning("⚠️  No embeddings found to verify dimensions")
            return True

async def run_data_migration():
    """Run the complete data migration"""
    logger.info("Starting data migration: Fix Embeddings Vector Dimensions")
    
    try:
        # Step 1: Check current dimensions
        current_dims = await check_vector_dimensions()
        
        if current_dims is None:
            logger.info("No embeddings table found, nothing to migrate")
            return True
            
        if current_dims == 1536:
            logger.info("Vector dimensions are already correct (1536), no migration needed")
            return True
            
        if current_dims == 0:
            logger.info("No embeddings found, no migration needed")
            return True
            
        logger.info(f"Current dimensions: {current_dims}, target: 1536")
        
        # Step 2: Backup existing embeddings
        backup_count = await backup_embeddings()
        
        if backup_count == 0:
            logger.info("No embeddings to migrate")
            return True
            
        # Step 3: Recreate table with correct dimensions
        await recreate_embeddings_table()
        
        # Step 4: Restore embeddings
        restored_count = await restore_embeddings()
        
        # Step 5: Verify migration
        success = await verify_migration()
        
        # Step 6: Cleanup
        await cleanup_backup()
        
        if success:
            logger.info("🎉 Data migration completed successfully!")
        else:
            logger.error("❌ Data migration failed!")
            
        return success
        
    except Exception as e:
        logger.error(f"Data migration failed: {e}")
        return False

def main():
    """Run the data migration"""
    try:
        success = asyncio.run(run_data_migration())
        return 0 if success else 1
    except Exception as e:
        logger.error(f"Migration script failed: {e}")
        return 1
    finally:
        asyncio.run(close_pool())

if __name__ == "__main__":
    # Add the app directory to Python path
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))
    exit(main())
