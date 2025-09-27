import asyncpg
import os
from pathlib import Path
from typing import Optional, List
from contextlib import asynccontextmanager
from app.config import settings
from app.logger import get_logger

logger = get_logger(__name__)

# Global connection pool
pool: Optional[asyncpg.Pool] = None


async def get_pool() -> asyncpg.Pool:
    """Get or create the database connection pool"""
    global pool
    if pool is None:
        try:
            pool = await asyncpg.create_pool(
                settings.db_connection_string,
                min_size=1,
                max_size=10,
                command_timeout=60
            )
            logger.info("Database connection pool created successfully")
        except Exception as e:
            logger.error(f"Failed to create database pool: {str(e)}")
            raise
    return pool


async def close_pool():
    """Close the database connection pool"""
    global pool
    if pool:
        await pool.close()
        pool = None
        logger.info("Database connection pool closed")


@asynccontextmanager
async def get_session():
    """Context manager for database sessions"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        try:
            yield conn
        except Exception as e:
            logger.error(f"Database session error: {str(e)}")
            raise


async def run_migrations() -> bool:
    """Run database migrations in order"""
    try:
        migrations_dir = Path(__file__).parent.parent / "migrations"
        migration_files = sorted([
            f for f in migrations_dir.glob("*.sql")
            if f.name.endswith('.sql')
        ])
        
        logger.info(f"Found {len(migration_files)} migration files")
        
        async with get_session() as conn:
            for migration_file in migration_files:
                logger.info(f"Running migration: {migration_file.name}")
                
                # Read and execute migration
                with open(migration_file, 'r') as f:
                    sql = f.read()
                
                await conn.execute(sql)
                logger.info(f"Migration {migration_file.name} completed successfully")
        
        logger.info("All migrations completed successfully")
        return True
        
    except Exception as e:
        logger.error(f"Migration failed: {str(e)}")
        return False


async def init_db() -> bool:
    """Initialize database and run migrations"""
    try:
        logger.info("Initializing database...")
        
        # Test connection first
        async with get_session() as conn:
            await conn.execute("SELECT 1")
            logger.info("Database connection test successful")
        
        # Run migrations
        if await run_migrations():
            logger.info("Database initialization completed successfully")
            return True
        else:
            logger.error("Database initialization failed")
            return False
            
    except Exception as e:
        logger.error(f"Database initialization failed: {str(e)}")
        return False


async def test_connection() -> dict:
    """Test database connection"""
    try:
        async with get_session() as conn:
            result = await conn.fetchval("SELECT 1")
            logger.info("Database connection successful")
            return {"status": "success", "message": "Database connection successful"}
    except Exception as e:
        logger.error(f"Database connection failed: {str(e)}")
        return {"status": "error", "message": f"Database connection failed: {str(e)}"}


async def execute_query(query: str, *args):
    """Execute a database query"""
    try:
        async with get_session() as conn:
            result = await conn.fetch(query, *args)
            return result
    except Exception as e:
        logger.error(f"Query execution failed: {str(e)}")
        raise


async def execute_transaction(queries: List[tuple]):
    """Execute multiple queries in a transaction"""
    try:
        async with get_session() as conn:
            async with conn.transaction():
                results = []
                for query, *args in queries:
                    result = await conn.fetch(query, *args)
                    results.append(result)
                return results
    except Exception as e:
        logger.error(f"Transaction failed: {str(e)}")
        raise


# Proposal-specific database operations
async def create_proposal(proposal_data: dict) -> str:
    """Create a new proposal"""
    query = """
    INSERT INTO proposals (id, network, type, title, description, proposer, 
                          amount_numeric, currency, status, created_at, metadata)
    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
    RETURNING id
    """
    
    async with get_session() as conn:
        result = await conn.fetchval(
            query,
            proposal_data['id'],
            proposal_data['network'],
            proposal_data['type'],
            proposal_data.get('title'),
            proposal_data.get('description'),
            proposal_data.get('proposer'),
            proposal_data.get('amount_numeric'),
            proposal_data.get('currency'),
            proposal_data.get('status', 'pending'),
            proposal_data.get('created_at'),
            proposal_data.get('metadata', {})
        )
        return result


async def store_embedding(proposal_id: str, embedding: List[float]) -> bool:
    """Store vector embedding for a proposal"""
    query = """
    INSERT INTO proposals_embeddings (proposal_id, embedding)
    VALUES ($1, $2)
    ON CONFLICT (proposal_id) 
    DO UPDATE SET embedding = EXCLUDED.embedding
    """
    
    try:
        async with get_session() as conn:
            await conn.execute(query, proposal_id, embedding)
            return True
    except Exception as e:
        logger.error(f"Failed to store embedding: {str(e)}")
        return False


async def search_proposals_semantic(query_embedding: List[float], limit: int = 10) -> List[dict]:
    """Semantic search using vector similarity"""
    # Convert embedding to PostgreSQL vector format
    embedding_str = '[' + ','.join(map(str, query_embedding)) + ']'
    
    query = """
    SELECT p.*, 
           (pe.embedding <=> $1::vector) as similarity
    FROM proposals p
    JOIN proposals_embeddings pe ON p.id = pe.proposal_id
    ORDER BY similarity ASC
    LIMIT $2
    """
    
    async with get_session() as conn:
        results = await conn.fetch(query, embedding_str, limit)
        return [dict(row) for row in results]


async def search_proposals_fuzzy(search_term: str, limit: int = 10) -> List[dict]:
    """Fuzzy search using trigram similarity"""
    query = """
    SELECT *, 
           similarity(title, $1) as title_similarity,
           similarity(proposer, $1) as proposer_similarity
    FROM proposals
    WHERE title % $1 OR proposer % $1
    ORDER BY GREATEST(similarity(title, $1), similarity(proposer, $1)) DESC
    LIMIT $2
    """
    
    async with get_session() as conn:
        results = await conn.fetch(query, search_term, limit)
        return [dict(row) for row in results]


async def search_proposals_fulltext(search_term: str, limit: int = 10) -> List[dict]:
    """Full-text search using tsvector"""
    query = """
    SELECT *, 
           ts_rank(doc_tsv, plainto_tsquery('simple', $1)) as rank
    FROM proposals
    WHERE doc_tsv @@ plainto_tsquery('simple', $1)
    ORDER BY rank DESC
    LIMIT $2
    """
    
    async with get_session() as conn:
        results = await conn.fetch(query, search_term, limit)
        return [dict(row) for row in results]
