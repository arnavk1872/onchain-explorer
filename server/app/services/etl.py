"""
ETL Service for processing Polkassembly data
Loads JSON/CSV files, normalizes data, and upserts to database with embeddings
"""

import argparse
import asyncio
import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Union, Set
from urllib.parse import urlparse

import polars as pl
import asyncpg
from sqlalchemy import create_engine, text, MetaData, Table, Column, String, Numeric, DateTime, JSON, Text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import sessionmaker
import numpy as np

# Embedding providers
try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False

from app.config import settings
from app.logger import get_logger

logger = get_logger(__name__)

class EmbeddingProvider:
    """Base class for embedding providers"""
    
    def __init__(self, model_name: str):
        self.model_name = model_name
        self.dimension = self._get_dimension()
    
    def _get_dimension(self) -> int:
        """Get embedding dimension for the model"""
        raise NotImplementedError
    
    async def get_embedding(self, text: str) -> List[float]:
        """Get embedding for text"""
        raise NotImplementedError
    
    async def get_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """Get embeddings for batch of texts"""
        raise NotImplementedError

class OpenAIEmbeddingProvider(EmbeddingProvider):
    """OpenAI embedding provider"""
    
    def __init__(self, model_name: str = "text-embedding-3-small"):
        if not OPENAI_AVAILABLE:
            raise ImportError("OpenAI package not available. Install with: pip install openai")
        
        super().__init__(model_name)
        from app.config import settings
        self.client = openai.AsyncOpenAI(api_key=settings.openai_api_key)
        
        # Rate limiting
        self.requests_per_minute = 3000
        self.tokens_per_minute = 1000000
        self.last_request_time = 0
        self.request_count = 0
        self.token_count = 0
        self.min_interval = 60.0 / self.requests_per_minute
    
    def _get_dimension(self) -> int:
        """Get embedding dimension for OpenAI models"""
        if "3-large" in self.model_name:
            return 3072
        elif "3-small" in self.model_name:
            return 1536
        elif "ada-002" in self.model_name:
            return 1536
        else:
            return 1536  # Default
    
    async def _rate_limit(self, tokens: int):
        """Implement rate limiting"""
        current_time = time.time()
        
        # Reset counters every minute
        if current_time - self.last_request_time >= 60:
            self.request_count = 0
            self.token_count = 0
            self.last_request_time = current_time
        
        # Check rate limits
        if self.request_count >= self.requests_per_minute:
            sleep_time = 60 - (current_time - self.last_request_time)
            if sleep_time > 0:
                logger.info(f"Rate limit reached, sleeping for {sleep_time:.2f}s")
                await asyncio.sleep(sleep_time)
                self.request_count = 0
                self.token_count = 0
                self.last_request_time = time.time()
        
        if self.token_count + tokens >= self.tokens_per_minute:
            sleep_time = 60 - (current_time - self.last_request_time)
            if sleep_time > 0:
                logger.info(f"Token limit reached, sleeping for {sleep_time:.2f}s")
                await asyncio.sleep(sleep_time)
                self.request_count = 0
                self.token_count = 0
                self.last_request_time = time.time()
        
        # Ensure minimum interval between requests
        time_since_last = current_time - self.last_request_time
        if time_since_last < self.min_interval:
            await asyncio.sleep(self.min_interval - time_since_last)
        
        self.request_count += 1
        self.token_count += tokens
    
    async def get_embedding(self, text: str) -> List[float]:
        """Get single embedding with rate limiting"""
        if not text or not text.strip():
            return [0.0] * self.dimension
        
        # Estimate tokens (rough approximation)
        estimated_tokens = len(text.split()) * 1.3
        await self._rate_limit(int(estimated_tokens))
        
        try:
            response = await self.client.embeddings.create(
                model=self.model_name,
                input=text.strip()
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"OpenAI embedding error: {e}")
            # Return zero vector on error
            return [0.0] * self.dimension
    
    async def get_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """Get batch embeddings with rate limiting"""
        if not texts:
            return []
        
        # Filter out empty texts
        valid_texts = [text.strip() for text in texts if text and text.strip()]
        if not valid_texts:
            return [[0.0] * self.dimension] * len(texts)
        
        # Estimate tokens
        total_tokens = sum(len(text.split()) * 1.3 for text in valid_texts)
        await self._rate_limit(int(total_tokens))
        
        try:
            response = await self.client.embeddings.create(
                model=self.model_name,
                input=valid_texts
            )
            
            embeddings = [data.embedding for data in response.data]
            
            # Pad with zero vectors for empty texts
            result = []
            valid_idx = 0
            for text in texts:
                if text and text.strip():
                    result.append(embeddings[valid_idx])
                    valid_idx += 1
                else:
                    result.append([0.0] * self.dimension)
            
            return result
        except Exception as e:
            logger.error(f"OpenAI batch embedding error: {e}")
            return [[0.0] * self.dimension] * len(texts)

class BGEM3EmbeddingProvider(EmbeddingProvider):
    """BGE-M3 local embedding provider"""
    
    def __init__(self, model_name: str = "BAAI/bge-m3"):
        if not SENTENCE_TRANSFORMERS_AVAILABLE:
            raise ImportError("sentence-transformers package not available. Install with: pip install sentence-transformers")
        
        super().__init__(model_name)
        logger.info(f"Loading BGE-M3 model: {model_name}")
        self.model = SentenceTransformer(model_name)
        logger.info("BGE-M3 model loaded successfully")
    
    def _get_dimension(self) -> int:
        """Get embedding dimension for BGE-M3"""
        return 1024  # BGE-M3 dimension
    
    async def get_embedding(self, text: str) -> List[float]:
        """Get single embedding"""
        if not text or not text.strip():
            return [0.0] * self.dimension
        
        try:
            # Run in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            embedding = await loop.run_in_executor(
                None, 
                lambda: self.model.encode(text.strip(), normalize_embeddings=True)
            )
            return embedding.tolist()
        except Exception as e:
            logger.error(f"BGE-M3 embedding error: {e}")
            return [0.0] * self.dimension
    
    async def get_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """Get batch embeddings"""
        if not texts:
            return []
        
        # Filter out empty texts
        valid_texts = [text.strip() for text in texts if text and text.strip()]
        if not valid_texts:
            return [[0.0] * self.dimension] * len(texts)
        
        try:
            # Run in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            embeddings = await loop.run_in_executor(
                None,
                lambda: self.model.encode(valid_texts, normalize_embeddings=True)
            )
            
            # Convert to list format
            embeddings_list = embeddings.tolist()
            
            # Pad with zero vectors for empty texts
            result = []
            valid_idx = 0
            for text in texts:
                if text and text.strip():
                    result.append(embeddings_list[valid_idx])
                    valid_idx += 1
                else:
                    result.append([0.0] * self.dimension)
            
            return result
        except Exception as e:
            logger.error(f"BGE-M3 batch embedding error: {e}")
            return [[0.0] * self.dimension] * len(texts)

class ETLService:
    """ETL service for processing Polkassembly data"""
    
    def __init__(self, embedding_provider: str = "openai", batch_size: int = 100):
        self.batch_size = batch_size
        self.embedding_provider = self._create_embedding_provider(embedding_provider)
        self.engine = None
        self.Session = None
        
        # Database tables metadata
        self.metadata = MetaData()
        self.proposals_table = Table(
            'proposals', self.metadata,
            Column('id', String, primary_key=True),
            Column('network', String, nullable=False),
            Column('type', String, nullable=False),
            Column('title', Text),
            Column('description', Text),
            Column('proposer', String),
            Column('amount_numeric', Numeric),
            Column('currency', String),
            Column('status', String),
            Column('created_at', DateTime, nullable=False),
            Column('updated_at', DateTime),
            Column('metadata', JSON),
            Column('doc_tsv', Text)  # Will be computed
        )
        
        self.embeddings_table = Table(
            'proposals_embeddings', self.metadata,
            Column('proposal_id', String, primary_key=True),
            Column('embedding', String)  # Will be converted to vector
        )
    
    def _create_embedding_provider(self, provider: str) -> EmbeddingProvider:
        """Create embedding provider based on string"""
        if provider.lower() == "openai":
            if not OPENAI_AVAILABLE:
                raise ImportError("OpenAI not available. Install with: pip install openai")
            return OpenAIEmbeddingProvider()
        elif provider.lower() in ["bge-m3", "bge", "local"]:
            if not SENTENCE_TRANSFORMERS_AVAILABLE:
                raise ImportError("sentence-transformers not available. Install with: pip install sentence-transformers")
            return BGEM3EmbeddingProvider()
        else:
            raise ValueError(f"Unknown embedding provider: {provider}")
    
    def _setup_database(self):
        """Setup database connection"""
        self.engine = create_engine(settings.db_connection_string)
        self.Session = sessionmaker(bind=self.engine)
        logger.info("Database connection established")
    
    def _normalize_network(self, network: str) -> str:
        """Normalize network name"""
        if not network:
            return "polkadot"  # Default
        
        network_lower = network.lower().strip()
        if network_lower in ["polkadot", "dot"]:
            return "polkadot"
        elif network_lower in ["kusama", "ksm"]:
            return "kusama"
        else:
            return network_lower
    
    def _normalize_type(self, proposal_type: str) -> str:
        """Normalize proposal type"""
        if not proposal_type:
            return "Unknown"
        
        # Map common variations
        type_mapping = {
            "democracyproposal": "DemocracyProposal",
            "democracy_proposal": "DemocracyProposal",
            "DemocracyProposal": "DemocracyProposal",  # Exact match
            "techcommitteeproposal": "TechCommitteeProposal",
            "tech_committee_proposal": "TechCommitteeProposal",
            "treasuryproposal": "TreasuryProposal",
            "treasury_proposal": "TreasuryProposal",
            "referendum": "Referendum",
            "councilmotion": "CouncilMotion",
            "council_motion": "CouncilMotion",
            "bounty": "Bounty",
            "tip": "Tip",
            "childbounty": "ChildBounty",
            "child_bounty": "ChildBounty",
            "referendumv2": "ReferendumV2",
            "referendum_v2": "ReferendumV2",
            "fellowshipreferendum": "FellowshipReferendum",
            "fellowship_referendum": "FellowshipReferendum"
        }
        
        normalized = proposal_type.lower().strip()
        return type_mapping.get(normalized, proposal_type)
    
    def _normalize_amount(self, amount: Any) -> Optional[float]:
        """Normalize amount to numeric value"""
        if amount is None:
            return None
        
        if isinstance(amount, (int, float)):
            return float(amount)
        
        if isinstance(amount, str):
            # Remove common currency symbols and whitespace
            cleaned = amount.strip().replace(",", "").replace("$", "").replace("€", "").replace("£", "")
            try:
                return float(cleaned)
            except ValueError:
                return None
        
        return None
    
    def _normalize_currency(self, currency: Any) -> Optional[str]:
        """Normalize currency"""
        if not currency:
            return None
        
        if isinstance(currency, str):
            currency_upper = currency.upper().strip()
            # Map common variations
            currency_mapping = {
                "DOT": "DOT",
                "KSM": "KSM",
                "USD": "USD",
                "USDT": "USDT",
                "USDC": "USDC",
                "EUR": "EUR",
                "GBP": "GBP"
            }
            return currency_mapping.get(currency_upper, currency_upper)
        
        return str(currency).upper() if currency else None
    
    def _normalize_created_at(self, created_at: Any) -> datetime:
        """Normalize created_at timestamp"""
        if isinstance(created_at, datetime):
            return created_at
        
        if isinstance(created_at, str):
            # Try common formats
            formats = [
                "%Y-%m-%dT%H:%M:%S.%fZ",
                "%Y-%m-%dT%H:%M:%SZ",
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%d"
            ]
            
            for fmt in formats:
                try:
                    return datetime.strptime(created_at, fmt)
                except ValueError:
                    continue
            
            # If all formats fail, try parsing with dateutil
            try:
                from dateutil import parser
                return parser.parse(created_at)
            except:
                pass
        
        # Default to current time if parsing fails
        logger.warning(f"Could not parse created_at: {created_at}, using current time")
        return datetime.now()
    
    def _compute_doc_tsv(self, title: str, description: str) -> str:
        """Compute document text search vector"""
        # Combine title and description for full-text search
        doc_text = f"{title or ''} {description or ''}".strip()
        
        if not doc_text:
            return ""
        
        # Sanitize text for PostgreSQL tsvector compatibility
        import re
        # Remove control characters and normalize whitespace
        doc_text = re.sub(r'[\x00-\x1f\x7f-\x9f]', ' ', doc_text)
        # Replace multiple whitespace with single space
        doc_text = re.sub(r'\s+', ' ', doc_text)
        # Remove any remaining problematic characters that might break tsvector
        # Keep only alphanumeric, spaces, and basic punctuation
        doc_text = re.sub(r'[^\w\s\-.,!?():;]', ' ', doc_text)
        # Remove any remaining problematic sequences
        doc_text = re.sub(r'[^\w\s]', ' ', doc_text)
        
        return doc_text.strip()[:1000]  # Limit length to avoid issues
    
    def _get_existing_proposals(self, proposal_ids: List[str]) -> Set[str]:
        """Get set of proposal IDs that exist in the database"""
        if not proposal_ids:
            return set()
        
        try:
            with self.Session() as session:
                result = session.execute(
                    text("SELECT id FROM proposals WHERE id = ANY(:ids)"),
                    {"ids": proposal_ids}
                )
                return {row[0] for row in result}
        except Exception as e:
            logger.error(f"Error checking existing proposals: {e}")
            return set()
    
    def load_data(self, file_paths: List[str]) -> pl.DataFrame:
        """Load data from JSON/CSV files using Polars"""
        all_data = []
        
        for file_path in file_paths:
            file_path = Path(file_path)
            if not file_path.exists():
                logger.warning(f"File not found: {file_path}")
                continue
            
            logger.info(f"Loading data from: {file_path}")
            
            try:
                if file_path.suffix.lower() == '.json':
                    # Load JSON file
                    with open(file_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    # Handle different JSON structures
                    if isinstance(data, dict):
                        if 'items' in data:
                            items = data['items']
                        elif 'data' in data:
                            items = data['data']
                        else:
                            items = [data]
                    elif isinstance(data, list):
                        items = data
                    else:
                        logger.warning(f"Unexpected JSON structure in {file_path}")
                        continue
                    
                    # Convert to Polars DataFrame
                    if items:
                        try:
                            df = pl.DataFrame(items, infer_schema_length=1000)
                            all_data.append(df)
                        except Exception as e:
                            logger.warning(f"Schema inference failed for {file_path}, trying with larger inference length: {e}")
                            try:
                                df = pl.DataFrame(items, infer_schema_length=None)
                                all_data.append(df)
                            except Exception as e2:
                                logger.error(f"Failed to load {file_path} even with full inference: {e2}")
                                continue
                
                elif file_path.suffix.lower() == '.csv':
                    # Load CSV file
                    df = pl.read_csv(file_path)
                    all_data.append(df)
                
                else:
                    logger.warning(f"Unsupported file format: {file_path.suffix}")
                    continue
                    
            except Exception as e:
                logger.error(f"Error loading {file_path}: {e}")
                continue
        
        if not all_data:
            raise ValueError("No data loaded from any files")
        
        # Combine all DataFrames
        try:
            combined_df = pl.concat(all_data, how="vertical_relaxed")
        except Exception as e:
            logger.warning(f"Vertical relaxed concatenation failed: {e}, trying with vertical_align")
            try:
                combined_df = pl.concat(all_data, how="vertical_align")
            except Exception as e2:
                logger.warning(f"Vertical align concatenation failed: {e2}, trying with horizontal")
                # If all else fails, try horizontal concatenation
                combined_df = pl.concat(all_data, how="horizontal")
        
        logger.info(f"Loaded {len(combined_df)} records from {len(file_paths)} files")
        
        return combined_df
    
    def normalize_data(self, df: pl.DataFrame) -> pl.DataFrame:
        """Normalize and clean the data"""
        logger.info("Normalizing data...")
        
        # Create normalized DataFrame
        normalized_data = []
        
        for row in df.iter_rows(named=True):
            # Extract and normalize fields
            proposal_id = str(row.get('id', ''))
            if not proposal_id or proposal_id == 'None':
                # Generate ID from other fields if missing
                index = row.get('index', '')
                network = row.get('network', '')
                if index and network:
                    proposal_id = f"{network}_{index}"
                else:
                    # Generate a unique ID using timestamp and random
                    import time
                    import random
                    proposal_id = f"{network}_{int(time.time())}_{random.randint(1000, 9999)}"
            
            # Extract onChainInfo if available
            on_chain_info = row.get('onChainInfo', {}) if isinstance(row.get('onChainInfo'), dict) else {}
            
            # Normalize fields - handle both direct fields and nested onChainInfo
            network = self._normalize_network(row.get('network', ''))
            
            # Try multiple field names for proposal type
            proposal_type = self._normalize_type(
                row.get('type') or 
                row.get('proposalType') or 
                on_chain_info.get('type', '')
            )
            
            title = str(row.get('title', '')).strip() if row.get('title') else None
            description = str(row.get('description') or row.get('content', '')).strip() if (row.get('description') or row.get('content')) else None
            proposer = str(row.get('proposer') or on_chain_info.get('proposer', '')).strip() if (row.get('proposer') or on_chain_info.get('proposer')) else None
            amount = self._normalize_amount(row.get('amount', row.get('amount_numeric')))
            currency = self._normalize_currency(row.get('currency', ''))
            status = str(row.get('status') or on_chain_info.get('status', '')).strip() if (row.get('status') or on_chain_info.get('status')) else 'pending'
            created_at = self._normalize_created_at(row.get('created_at', row.get('createdAt')))
            
            # Compute doc_tsv
            doc_tsv = self._compute_doc_tsv(title, description)
            
            # Prepare metadata (exclude already processed fields)
            metadata = {k: v for k, v in row.items() 
                       if k not in ['id', 'network', 'type', 'proposalType', 'title', 'description', 'content',
                                  'proposer', 'amount', 'amount_numeric', 'currency', 
                                  'status', 'created_at', 'createdAt', 'onChainInfo']}
            
            normalized_data.append({
                'id': proposal_id,
                'network': network,
                'type': proposal_type,
                'title': title,
                'description': description,
                'proposer': proposer,
                'amount_numeric': amount,
                'currency': currency,
                'status': status,
                'created_at': created_at,
                'updated_at': datetime.now(),
                'metadata': metadata,
                'doc_tsv': doc_tsv
            })
        
        normalized_df = pl.DataFrame(normalized_data)
        logger.info(f"Normalized {len(normalized_df)} records")
        
        return normalized_df
    
    async def upsert_proposals(self, df: pl.DataFrame):
        """Bulk upsert proposals using SQLAlchemy core with ON CONFLICT"""
        logger.info(f"Upserting {len(df)} proposals...")
        
        if not self.engine:
            self._setup_database()
        
        # Convert Polars DataFrame to list of dicts and deduplicate by ID
        proposals_data = df.to_dicts()
        
        # Deduplicate by ID, keeping the last occurrence
        seen_ids = set()
        unique_proposals = []
        for proposal in proposals_data:
            proposal_id = proposal.get('id')
            if proposal_id and proposal_id not in seen_ids:
                seen_ids.add(proposal_id)
                unique_proposals.append(proposal)
            elif proposal_id:
                logger.warning(f"Duplicate proposal ID found: {proposal_id}, skipping")
        
        proposals_data = unique_proposals
        logger.info(f"After deduplication: {len(proposals_data)} unique proposals")
        
                # Process in batches
        successful_inserts = 0
        for i in range(0, len(proposals_data), self.batch_size):
            batch = proposals_data[i:i + self.batch_size]
            
            try:
                with self.Session() as session:
                    # Use PostgreSQL UPSERT (ON CONFLICT)
                    stmt = insert(self.proposals_table)
                    
                    # Define what to do on conflict
                    stmt = stmt.on_conflict_do_update(
                        index_elements=['id'],
                        set_={
                            'network': stmt.excluded.network,
                            'type': stmt.excluded.type,
                            'title': stmt.excluded.title,
                            'description': stmt.excluded.description,
                            'proposer': stmt.excluded.proposer,
                            'amount_numeric': stmt.excluded.amount_numeric,
                            'currency': stmt.excluded.currency,
                            'status': stmt.excluded.status,
                            'updated_at': stmt.excluded.updated_at,
                            'metadata': stmt.excluded.metadata,
                            'doc_tsv': stmt.excluded.doc_tsv
                        }
                    )
                    
                    result = session.execute(stmt, batch)
                    session.commit()
                    successful_inserts += len(batch)
                    
                logger.info(f"Upserted batch {i//self.batch_size + 1}/{(len(proposals_data) + self.batch_size - 1)//self.batch_size}")
                
            except Exception as e:
                logger.error(f"Error upserting batch {i//self.batch_size + 1}: {e}")
                # Try inserting records one by one to identify problematic ones
                for record in batch:
                    try:
                        with self.Session() as session:
                            stmt = insert(self.proposals_table)
                            stmt = stmt.on_conflict_do_update(
                                index_elements=['id'],
                                set_={
                                    'network': stmt.excluded.network,
                                    'type': stmt.excluded.type,
                                    'title': stmt.excluded.title,
                                    'description': stmt.excluded.description,
                                    'proposer': stmt.excluded.proposer,
                                    'amount_numeric': stmt.excluded.amount_numeric,
                                    'currency': stmt.excluded.currency,
                                    'status': stmt.excluded.status,
                                    'updated_at': stmt.excluded.updated_at,
                                    'metadata': stmt.excluded.metadata,
                                    'doc_tsv': stmt.excluded.doc_tsv
                                }
                            )
                            session.execute(stmt, [record])
                            session.commit()
                            successful_inserts += 1
                    except Exception as record_error:
                        logger.warning(f"Failed to insert record {record.get('id', 'unknown')}: {record_error}")
                        continue
                continue
        
        logger.info(f"Successfully upserted {successful_inserts} out of {len(proposals_data)} proposals")
        
        logger.info("Proposal upserts completed")
    
    async def recompute_doc_tsv(self):
        """Recompute doc_tsv for all proposals"""
        logger.info("Recomputing doc_tsv for all proposals...")
        
        if not self.engine:
            self._setup_database()
        
        try:
            with self.Session() as session:
                # Update doc_tsv using PostgreSQL's to_tsvector function
                update_stmt = text("""
                    UPDATE proposals 
                    SET doc_tsv = to_tsvector('simple', coalesce(title,'') || ' ' || coalesce(description,''))
                    WHERE doc_tsv IS NULL OR doc_tsv = ''
                """)
                
                result = session.execute(update_stmt)
                session.commit()
                
                logger.info(f"Updated doc_tsv for {result.rowcount} proposals")
                
        except Exception as e:
            logger.error(f"Error recomputing doc_tsv: {e}")
    
    async def compute_embeddings(self, df: pl.DataFrame):
        """Compute embeddings for proposals and upsert to embeddings table"""
        logger.info(f"Computing embeddings for {len(df)} proposals...")
        
        if not self.engine:
            self._setup_database()
        
        # First, check which proposals actually exist in the database
        all_proposal_ids = [row['id'] for row in df.iter_rows(named=True)]
        existing_proposals = self._get_existing_proposals(all_proposal_ids)
        
        if not existing_proposals:
            logger.warning("No proposals found in database, skipping embeddings")
            return
        
        logger.info(f"Found {len(existing_proposals)} existing proposals in database")
        
        # Prepare texts for embedding (only for existing proposals)
        texts = []
        proposal_ids = []
        
        for row in df.iter_rows(named=True):
            proposal_id = row.get('id', '')
            if not proposal_id or proposal_id == 'None' or proposal_id not in existing_proposals:
                continue
                
            # Create structured text for better embedding quality
            title = row.get('title', '') or ''
            description = row.get('description', '') or ''
            proposer = row.get('proposer', '') or ''
            network = row.get('network', '') or ''
            proposal_type = row.get('type', '') or ''
            
            # Create structured text with metadata for better semantic understanding
            text_parts = []
            
            # Add title with emphasis
            if title:
                text_parts.append(f"Title: {title}")
            
            # Add structured metadata
            if proposer and proposer != 'Unknown':
                text_parts.append(f"Proposer: {proposer}")
            if network and network != 'Unknown':
                text_parts.append(f"Network: {network}")
            if proposal_type:
                text_parts.append(f"Type: {proposal_type}")
            
            # Add description (truncated if too long)
            if description and description != 'No description available':
                # Truncate very long descriptions to focus on key content
                if len(description) > 2000:
                    description = description[:2000] + "..."
                text_parts.append(f"Description: {description}")
            
            text = "\n".join(text_parts).strip()
            
            if text:  # Only compute embeddings for non-empty texts
                texts.append(text)
                proposal_ids.append(proposal_id)
        
        if not texts:
            logger.warning("No texts to embed")
            return
        
        # Compute embeddings in batches
        all_embeddings = []
        
        for i in range(0, len(texts), self.batch_size):
            batch_texts = texts[i:i + self.batch_size]
            batch_ids = proposal_ids[i:i + self.batch_size]
            
            logger.info(f"Computing embeddings for batch {i//self.batch_size + 1}/{(len(texts) + self.batch_size - 1)//self.batch_size}")
            
            try:
                # Get embeddings from provider
                embeddings = await self.embedding_provider.get_embeddings_batch(batch_texts)
                
                # Prepare data for upsert
                embeddings_data = []
                for proposal_id, embedding in zip(batch_ids, embeddings):
                    # Convert embedding to string format for PostgreSQL vector
                    embedding_str = '[' + ','.join(map(str, embedding)) + ']'
                    embeddings_data.append({
                        'proposal_id': proposal_id,
                        'embedding': embedding_str
                    })
                
                # Upsert embeddings
                with self.Session() as session:
                    stmt = insert(self.embeddings_table)
                    stmt = stmt.on_conflict_do_update(
                        index_elements=['proposal_id'],
                        set_={'embedding': stmt.excluded.embedding}
                    )
                    
                    session.execute(stmt, embeddings_data)
                    session.commit()
                    
                    all_embeddings.extend(embeddings)
                    logger.info(f"Upserted embeddings for batch {i//self.batch_size + 1}")
                    
            except Exception as e:
                logger.error(f"Error computing embeddings for batch {i//self.batch_size + 1}: {e}")
                continue
        
        logger.info(f"Computed and stored {len(all_embeddings)} embeddings")
    
    async def process_files(self, file_paths: List[str]):
        """Main ETL process"""
        logger.info(f"Starting ETL process for {len(file_paths)} files")
        
        try:
            # Load data
            df = self.load_data(file_paths)
            
            # Normalize data
            normalized_df = self.normalize_data(df)
            
            # Upsert proposals
            await self.upsert_proposals(normalized_df)
            
            # Recompute doc_tsv
            await self.recompute_doc_tsv()
            
            # Compute embeddings
            await self.compute_embeddings(normalized_df)
            
            logger.info("ETL process completed successfully")
            
        except Exception as e:
            logger.error(f"ETL process failed: {e}")
            raise

def main():
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(description="ETL Service for Polkassembly Data")
    parser.add_argument("--input", "-i", nargs="+", required=True,
                       help="Input JSON/CSV files to process")
    parser.add_argument("--batch-size", "-b", type=int, default=100,
                       help="Batch size for processing (default: 100)")
    parser.add_argument("--provider", "-p", choices=["openai", "bge-m3", "bge", "local"], 
                       default="openai", help="Embedding provider (default: openai)")
    
    args = parser.parse_args()
    
    # Validate input files
    for file_path in args.input:
        if not Path(file_path).exists():
            logger.error(f"Input file not found: {file_path}")
            return 1
    
    # Create and run ETL service
    try:
        etl_service = ETLService(
            embedding_provider=args.provider,
            batch_size=args.batch_size
        )
        
        # Run async ETL process
        asyncio.run(etl_service.process_files(args.input))
        
        logger.info("ETL process completed successfully")
        return 0
        
    except Exception as e:
        logger.error(f"ETL process failed: {e}")
        return 1

if __name__ == "__main__":
    exit(main())
