"""
Retrieval service for searching proposals with hybrid search (lexical + vector)
Implements RRF fusion and optional Cohere reranking
"""

import asyncio
import math
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime

import asyncpg
from app.db import get_session
from app.services.etl import EmbeddingProvider, OpenAIEmbeddingProvider, BGEM3EmbeddingProvider
from app.config import settings
from app.logger import get_logger

logger = get_logger(__name__)

# Cohere integration
try:
    import cohere
    COHERE_AVAILABLE = True
except ImportError:
    COHERE_AVAILABLE = False
    logger.warning("Cohere package not available. Install with: pip install cohere")


@dataclass
class SearchFilters:
    """Search filters for proposals"""
    network: Optional[str] = None
    proposal_type: Optional[str] = None
    status: Optional[str] = None
    min_amount: Optional[float] = None
    max_amount: Optional[float] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None


@dataclass
class SearchResult:
    """Search result with all required fields"""
    id: str
    title: str
    network: str
    type: str
    amount: Optional[float]
    created_at: datetime
    snippet: str
    score: float = 0.0
    description: Optional[str] = None
    proposer: Optional[str] = None
    status: Optional[str] = None


class RetrievalService:
    """Hybrid search service with RRF fusion and optional reranking"""
    
    def __init__(self, embedding_provider: str = "openai"):
        self.embedding_provider = self._create_embedding_provider(embedding_provider)
        self.cohere_client = None
        
        if COHERE_AVAILABLE and hasattr(settings, 'cohere_api_key') and settings.cohere_api_key:
            self.cohere_client = cohere.Client(api_key=settings.cohere_api_key)
            logger.info("Cohere client initialized for reranking")
    
    
    def _create_embedding_provider(self, provider: str) -> EmbeddingProvider:
        """Create embedding provider"""
        if provider.lower() == "openai":
            return OpenAIEmbeddingProvider()
        elif provider.lower() in ["bge-m3", "bge", "local"]:
            # Fallback to OpenAI if BGE-M3 is not available
            logger.warning("BGE-M3 not available, falling back to OpenAI")
            return OpenAIEmbeddingProvider()
        else:
            raise ValueError(f"Unknown embedding provider: {provider}")
    
    async def search_proposals(
        self, 
        query: str, 
        filters: Optional[SearchFilters] = None,
        top_k: int = 10,
        use_rerank: bool = True
    ) -> List[SearchResult]:
        """
        Search proposals using hybrid search with RRF fusion
        
        Args:
            query: Search query string
            filters: Optional filters to apply
            top_k: Number of results to return
            use_rerank: Whether to use Cohere reranking on top 30 results
            
        Returns:
            List of SearchResult objects
        """
        if not query or not query.strip():
            return []
        
        logger.info(f"Searching proposals with query: '{query}', filters: {filters}, top_k: {top_k}")
        
        try:
            # 1. Compute query embedding
            query_embedding = await self.embedding_provider.get_embedding(query.strip())
            
            # 2. Run both lexical and vector searches for all queries
            lexical_results = await self._lexical_search(query, filters, limit=30)
            vector_results = await self._vector_search(query_embedding, filters, limit=50)
            
            # 3. Fuse results with RRF (vector search gets much higher weight for better semantic understanding)
            fused_results = self._fuse_with_rrf(lexical_results, vector_results, k=60, vector_weight=4.0)
            
            # 4. Optional Cohere reranking on top 30
            if use_rerank and self.cohere_client and len(fused_results) > 0:
                rerank_limit = min(30, len(fused_results))
                reranked_results = await self._rerank_with_cohere(
                    query, 
                    fused_results[:rerank_limit]
                )
                # Merge reranked results with remaining results
                final_results = reranked_results + fused_results[rerank_limit:]
            else:
                final_results = fused_results
            
            # 5. Filter and return top_k results with snippets
            results = []
            for i, result in enumerate(final_results[:top_k]):
                # Filter results with meaningful relevance
                rrf_score = result.get('rrf_score', 0.0)
                if rrf_score < 0.045:  # Selective threshold to keep relevant results but filter irrelevant ones
                    continue
                    
                snippet = self._generate_snippet(result, query)
                search_result = SearchResult(
                    id=result['id'],
                    title=result.get('title', ''),
                    network=result.get('network', ''),
                    type=result.get('type', ''),
                    amount=result.get('amount_numeric'),
                    created_at=result.get('created_at'),
                    snippet=snippet,
                    score=rrf_score,
                    description=result.get('description'),
                    proposer=result.get('proposer'),
                    status=result.get('status')
                )
                results.append(search_result)
                
                # Limit to maximum 5 results to avoid overwhelming the user
                if len(results) >= 5:
                    break
            
            logger.info(f"Found {len(results)} results for query: '{query}'")
            return results
            
        except Exception as e:
            logger.error(f"Search failed for query '{query}': {str(e)}")
            return []
    
    async def _lexical_search(
        self, 
        query: str, 
        filters: Optional[SearchFilters], 
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Perform lexical search using full-text and fuzzy matching"""
        
        # Build WHERE clause with filters
        where_conditions = []
        params = []
        param_count = 0
        
        # Multiple search strategies for better entity matching
        search_conditions = []
        
        # 1. Full-text search
        param_count += 1
        search_conditions.append(f"doc_tsv @@ plainto_tsquery('simple', ${param_count})")
        params.append(query)
        
        # 2. Extract key terms for partial matching (for entity queries)
        import re
        words = re.findall(r'\b\w+\b', query.lower())
        key_terms = [word for word in words if len(word) > 2 and word not in {'tell', 'me', 'about', 'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by'}]
        
        # 3. Partial matching for key terms in title and description
        for term in key_terms:
            param_count += 1
            search_conditions.append(f"LOWER(title) LIKE ${param_count}")
            params.append(f'%{term}%')
            
            param_count += 1
            search_conditions.append(f"LOWER(description) LIKE ${param_count}")
            params.append(f'%{term}%')
        
        # Combine all search strategies with OR
        where_conditions.append(f"({' OR '.join(search_conditions)})")
        
        # Add filters
        if filters:
            if filters.network:
                param_count += 1
                where_conditions.append(f"network = ${param_count}")
                params.append(filters.network)
            
            if filters.proposal_type:
                param_count += 1
                where_conditions.append(f"type = ${param_count}")
                params.append(filters.proposal_type)
            
            if filters.status:
                param_count += 1
                where_conditions.append(f"status = ${param_count}")
                params.append(filters.status)
            
            if filters.min_amount is not None:
                param_count += 1
                where_conditions.append(f"amount_numeric >= ${param_count}")
                params.append(filters.min_amount)
            
            if filters.max_amount is not None:
                param_count += 1
                where_conditions.append(f"amount_numeric <= ${param_count}")
                params.append(filters.max_amount)
            
            if filters.start_date:
                param_count += 1
                where_conditions.append(f"created_at >= ${param_count}")
                params.append(filters.start_date)
            
            if filters.end_date:
                param_count += 1
                where_conditions.append(f"created_at <= ${param_count}")
                params.append(filters.end_date)
        
        where_clause = " AND ".join(where_conditions)
        
        # Add limit
        param_count += 1
        params.append(limit)
        
        # Build scoring logic dynamically based on key terms
        score_conditions = ["COALESCE(ts_rank(doc_tsv, plainto_tsquery('simple', $1)), 0)"]
        param_idx = 2
        
        for term in key_terms:
            score_conditions.append(f"CASE WHEN LOWER(title) LIKE ${param_idx} THEN 0.8 ELSE 0 END")
            param_idx += 1
            score_conditions.append(f"CASE WHEN LOWER(description) LIKE ${param_idx} THEN 0.6 ELSE 0 END")
            param_idx += 1
        
        query_sql = f"""
        SELECT p.*, 
               GREATEST({', '.join(score_conditions)}) as rank_score,
               'lexical' as search_type
        FROM proposals p
        WHERE {where_clause}
        ORDER BY rank_score DESC
        LIMIT ${param_count}
        """
        
        async with get_session() as conn:
            results = await conn.fetch(query_sql, *params)
            return [dict(row) for row in results]
    
    async def _vector_search(
        self, 
        query_embedding: List[float], 
        filters: Optional[SearchFilters], 
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Perform vector similarity search"""
        
        # Convert embedding to PostgreSQL vector format
        embedding_str = '[' + ','.join(map(str, query_embedding)) + ']'
        
        # Build WHERE clause with filters
        where_conditions = ["pe.embedding IS NOT NULL"]
        params = [embedding_str]
        param_count = 1
        
        if filters:
            if filters.network:
                param_count += 1
                where_conditions.append(f"p.network = ${param_count}")
                params.append(filters.network)
            
            if filters.proposal_type:
                param_count += 1
                where_conditions.append(f"p.type = ${param_count}")
                params.append(filters.proposal_type)
            
            if filters.status:
                param_count += 1
                where_conditions.append(f"p.status = ${param_count}")
                params.append(filters.status)
            
            if filters.min_amount is not None:
                param_count += 1
                where_conditions.append(f"p.amount_numeric >= ${param_count}")
                params.append(filters.min_amount)
            
            if filters.max_amount is not None:
                param_count += 1
                where_conditions.append(f"p.amount_numeric <= ${param_count}")
                params.append(filters.max_amount)
            
            if filters.start_date:
                param_count += 1
                where_conditions.append(f"p.created_at >= ${param_count}")
                params.append(filters.start_date)
            
            if filters.end_date:
                param_count += 1
                where_conditions.append(f"p.created_at <= ${param_count}")
                params.append(filters.end_date)
        
        where_clause = " AND ".join(where_conditions)
        
        # Add limit
        param_count += 1
        params.append(limit)
        
        query_sql = f"""
        SELECT p.*, 
               (pe.embedding <=> $1::vector) as similarity_score,
               'vector' as search_type
        FROM proposals p
        JOIN proposals_embeddings pe ON p.id = pe.proposal_id
        WHERE {where_clause}
        ORDER BY similarity_score ASC
        LIMIT ${param_count}
        """
        
        async with get_session() as conn:
            results = await conn.fetch(query_sql, *params)
            return [dict(row) for row in results]
    
    def _fuse_with_rrf(
        self, 
        lexical_results: List[Dict[str, Any]], 
        vector_results: List[Dict[str, Any]], 
        k: int = 60,
        vector_weight: float = 1.0
    ) -> List[Dict[str, Any]]:
        """Fuse results using Reciprocal Rank Fusion with optional vector weighting"""
        
        # Create score maps
        lexical_scores = {}
        vector_scores = {}
        
        for i, result in enumerate(lexical_results):
            proposal_id = result['id']
            lexical_scores[proposal_id] = 1.0 / (k + i + 1)
            result['lexical_score'] = lexical_scores[proposal_id]
        
        for i, result in enumerate(vector_results):
            proposal_id = result['id']
            vector_scores[proposal_id] = (1.0 / (k + i + 1)) * vector_weight
            result['vector_score'] = vector_scores[proposal_id]
        
        # Combine all unique proposals
        all_proposals = {}
        
        for result in lexical_results:
            proposal_id = result['id']
            all_proposals[proposal_id] = result.copy()
            all_proposals[proposal_id]['rrf_score'] = lexical_scores.get(proposal_id, 0.0)
        
        for result in vector_results:
            proposal_id = result['id']
            if proposal_id in all_proposals:
                all_proposals[proposal_id]['rrf_score'] += vector_scores.get(proposal_id, 0.0)
                all_proposals[proposal_id]['vector_score'] = vector_scores.get(proposal_id, 0.0)
            else:
                all_proposals[proposal_id] = result.copy()
                all_proposals[proposal_id]['rrf_score'] = vector_scores.get(proposal_id, 0.0)
        
        # Sort by RRF score
        fused_results = list(all_proposals.values())
        fused_results.sort(key=lambda x: x['rrf_score'], reverse=True)
        
        return fused_results
    
    async def _rerank_with_cohere(
        self, 
        query: str, 
        results: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Rerank results using Cohere API"""
        
        if not self.cohere_client or not results:
            return results
        
        try:
            # Prepare documents for reranking
            documents = []
            for result in results:
                # Create document text from title and description
                title = result.get('title', '')
                description = result.get('description', '')
                doc_text = f"{title}\n{description}".strip()
                documents.append(doc_text)
            
            # Call Cohere rerank API
            response = self.cohere_client.rerank(
                model='rerank-v3.5',
                query=query,
                documents=documents,
                top_n=len(documents)
            )
            
            # Reorder results based on Cohere ranking and filter by relevance
            reranked_results = []
            for rerank_result in response.results:
                original_index = rerank_result.index
                if original_index < len(results):
                    result = results[original_index].copy()
                    result['cohere_score'] = rerank_result.relevance_score
                    
                    # Only include results with high Cohere relevance scores
                    if rerank_result.relevance_score >= 0.5:  # Higher threshold for better quality
                        reranked_results.append(result)
            
            logger.info(f"Reranked {len(reranked_results)} results with Cohere")
            return reranked_results
            
        except Exception as e:
            logger.error(f"Cohere reranking failed: {str(e)}")
            return results  # Return original results on failure
    
    def _generate_snippet(self, result: Dict[str, Any], query: str) -> str:
        """Generate a short snippet from the result"""
        
        title = result.get('title', '')
        description = result.get('description', '')
        
        # Use title if available
        if title:
            snippet = title
        elif description:
            # Take first 150 characters of description
            snippet = description[:150]
            if len(description) > 150:
                snippet += "..."
        else:
            snippet = "No description available"
        
        return snippet


# Global service instance
_retrieval_service = None

def get_retrieval_service() -> RetrievalService:
    """Get or create the global retrieval service instance"""
    global _retrieval_service
    if _retrieval_service is None:
        _retrieval_service = RetrievalService()
    return _retrieval_service
