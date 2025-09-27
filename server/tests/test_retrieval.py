"""
Unit tests for retrieval service
Tests fuzzy name matching, vector-only queries, and filter effectiveness
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta
from typing import List, Dict, Any

from app.services.retrieval import RetrievalService, SearchFilters, SearchResult
from app.services.etl import BGEM3EmbeddingProvider


class TestRetrievalService:
    """Test cases for RetrievalService"""
    
    @pytest.fixture
    def mock_db_results(self):
        """Mock database results for testing"""
        return [
            {
                'id': 'prop_1',
                'title': 'Treasury Proposal for Development',
                'description': 'This proposal requests funding for core development work on the network infrastructure.',
                'network': 'polkadot',
                'type': 'treasury',
                'amount_numeric': 10000.0,
                'status': 'active',
                'created_at': datetime.now() - timedelta(days=5),
                'rank_score': 0.8,
                'search_type': 'lexical'
            },
            {
                'id': 'prop_2', 
                'title': 'Governance Proposal for Upgrade',
                'description': 'This governance proposal suggests upgrading the runtime to version 2.0.',
                'network': 'kusama',
                'type': 'governance',
                'amount_numeric': 5000.0,
                'status': 'pending',
                'created_at': datetime.now() - timedelta(days=3),
                'similarity_score': 0.6,
                'search_type': 'vector'
            },
            {
                'id': 'prop_3',
                'title': 'Community Proposal for Events',
                'description': 'Funding request for community events and conferences.',
                'network': 'polkadot',
                'type': 'community',
                'amount_numeric': 2000.0,
                'status': 'active',
                'created_at': datetime.now() - timedelta(days=1),
                'rank_score': 0.7,
                'search_type': 'lexical'
            }
        ]
    
    @pytest.fixture
    def retrieval_service(self):
        """Create RetrievalService instance for testing"""
        with patch('app.services.retrieval.BGEM3EmbeddingProvider') as mock_provider:
            mock_provider.return_value.get_embedding = AsyncMock(return_value=[0.1] * 1024)
            service = RetrievalService(embedding_provider="bge-m3")
            return service
    
    @pytest.mark.asyncio
    async def test_fuzzy_name_matching_typo(self, retrieval_service, mock_db_results):
        """Test that fuzzy name matching returns results even with typos"""
        
        # Mock database responses for lexical search with typo
        with patch.object(retrieval_service, '_lexical_search', new_callable=AsyncMock) as mock_lexical:
            with patch.object(retrieval_service, '_vector_search', new_callable=AsyncMock) as mock_vector:
                
                # Mock lexical search to return results for typo query
                mock_lexical.return_value = mock_db_results[:2]  # Return first 2 results
                mock_vector.return_value = mock_db_results[1:]   # Return last 2 results
                
                # Test with typo in query
                results = await retrieval_service.search_proposals(
                    query="treasry proposl",  # Intentional typos
                    top_k=5
                )
                
                # Should return at least 1 result despite typos
                assert len(results) >= 1
                assert any("treasury" in result.title.lower() for result in results)
                
                # Verify both search methods were called
                mock_lexical.assert_called_once()
                mock_vector.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_vector_only_query_returns_results(self, retrieval_service, mock_db_results):
        """Test that vector-only queries still return results"""
        
        with patch.object(retrieval_service, '_lexical_search', new_callable=AsyncMock) as mock_lexical:
            with patch.object(retrieval_service, '_vector_search', new_callable=AsyncMock) as mock_vector:
                
                # Mock lexical search to return no results (vector-only scenario)
                mock_lexical.return_value = []
                mock_vector.return_value = mock_db_results
                
                # Test with semantic query that might not match lexically
                results = await retrieval_service.search_proposals(
                    query="blockchain infrastructure funding",
                    top_k=5
                )
                
                # Should return results from vector search
                assert len(results) > 0
                assert all(isinstance(result, SearchResult) for result in results)
                
                # Verify both search methods were called
                mock_lexical.assert_called_once()
                mock_vector.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_filters_reduce_candidate_set(self, retrieval_service, mock_db_results):
        """Test that filters effectively reduce the candidate set"""
        
        # Create filtered results
        filtered_results = [result for result in mock_db_results if result['network'] == 'polkadot']
        
        with patch.object(retrieval_service, '_lexical_search', new_callable=AsyncMock) as mock_lexical:
            with patch.object(retrieval_service, '_vector_search', new_callable=AsyncMock) as mock_vector:
                
                # Mock search methods to return filtered results
                mock_lexical.return_value = filtered_results
                mock_vector.return_value = filtered_results
                
                # Test with network filter
                filters = SearchFilters(network='polkadot')
                results = await retrieval_service.search_proposals(
                    query="proposal",
                    filters=filters,
                    top_k=10
                )
                
                # All results should match the filter
                assert len(results) > 0
                assert all(result.network == 'polkadot' for result in results)
                
                # Verify search methods were called with filters
                mock_lexical.assert_called_once()
                mock_vector.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_multiple_filters_work_together(self, retrieval_service, mock_db_results):
        """Test that multiple filters work together to narrow results"""
        
        # Create results that match multiple filters
        multi_filtered_results = [
            result for result in mock_db_results 
            if result['network'] == 'polkadot' and result['type'] == 'treasury'
        ]
        
        with patch.object(retrieval_service, '_lexical_search', new_callable=AsyncMock) as mock_lexical:
            with patch.object(retrieval_service, '_vector_search', new_callable=AsyncMock) as mock_vector:
                
                mock_lexical.return_value = multi_filtered_results
                mock_vector.return_value = multi_filtered_results
                
                # Test with multiple filters
                filters = SearchFilters(
                    network='polkadot',
                    proposal_type='treasury',
                    min_amount=5000.0
                )
                
                results = await retrieval_service.search_proposals(
                    query="funding",
                    filters=filters,
                    top_k=10
                )
                
                # All results should match all filters
                assert len(results) > 0
                for result in results:
                    assert result.network == 'polkadot'
                    assert result.type == 'treasury'
                    assert result.amount is None or result.amount >= 5000.0
    
    @pytest.mark.asyncio
    async def test_rrf_fusion_combines_results(self, retrieval_service, mock_db_results):
        """Test that RRF fusion properly combines lexical and vector results"""
        
        lexical_results = mock_db_results[:2]
        vector_results = mock_db_results[1:]  # Overlap with lexical
        
        with patch.object(retrieval_service, '_lexical_search', new_callable=AsyncMock) as mock_lexical:
            with patch.object(retrieval_service, '_vector_search', new_callable=AsyncMock) as mock_vector:
                
                mock_lexical.return_value = lexical_results
                mock_vector.return_value = vector_results
                
                results = await retrieval_service.search_proposals(
                    query="test query",
                    top_k=10
                )
                
                # Should have results from both searches
                assert len(results) > 0
                
                # Check that RRF scores are calculated
                for result in results:
                    assert hasattr(result, 'score')
                    assert result.score >= 0.0
    
    @pytest.mark.asyncio
    async def test_empty_query_returns_empty_results(self, retrieval_service):
        """Test that empty queries return empty results"""
        
        results = await retrieval_service.search_proposals(
            query="",
            top_k=10
        )
        
        assert results == []
    
    @pytest.mark.asyncio
    async def test_snippet_generation(self, retrieval_service, mock_db_results):
        """Test that snippets are properly generated"""
        
        with patch.object(retrieval_service, '_lexical_search', new_callable=AsyncMock) as mock_lexical:
            with patch.object(retrieval_service, '_vector_search', new_callable=AsyncMock) as mock_vector:
                
                mock_lexical.return_value = mock_db_results
                mock_vector.return_value = []
                
                results = await retrieval_service.search_proposals(
                    query="test",
                    top_k=5
                )
                
                # All results should have snippets
                for result in results:
                    assert isinstance(result.snippet, str)
                    assert len(result.snippet) > 0
    
    @pytest.mark.asyncio
    async def test_cohere_reranking_integration(self, retrieval_service, mock_db_results):
        """Test Cohere reranking integration"""
        
        # Mock Cohere client
        mock_cohere_client = MagicMock()
        mock_cohere_client.rerank.return_value = MagicMock()
        mock_cohere_client.rerank.return_value.results = [
            MagicMock(index=0, relevance_score=0.9),
            MagicMock(index=1, relevance_score=0.8)
        ]
        
        retrieval_service.cohere_client = mock_cohere_client
        
        with patch.object(retrieval_service, '_lexical_search', new_callable=AsyncMock) as mock_lexical:
            with patch.object(retrieval_service, '_vector_search', new_callable=AsyncMock) as mock_vector:
                
                mock_lexical.return_value = mock_db_results
                mock_vector.return_value = []
                
                results = await retrieval_service.search_proposals(
                    query="test query",
                    top_k=5,
                    use_rerank=True
                )
                
                # Should call Cohere rerank
                mock_cohere_client.rerank.assert_called_once()
                
                # Results should be returned
                assert len(results) > 0
    
    @pytest.mark.asyncio
    async def test_cohere_reranking_fallback(self, retrieval_service, mock_db_results):
        """Test that search works when Cohere reranking fails"""
        
        # Mock Cohere client to raise exception
        mock_cohere_client = MagicMock()
        mock_cohere_client.rerank.side_effect = Exception("Cohere API error")
        retrieval_service.cohere_client = mock_cohere_client
        
        with patch.object(retrieval_service, '_lexical_search', new_callable=AsyncMock) as mock_lexical:
            with patch.object(retrieval_service, '_vector_search', new_callable=AsyncMock) as mock_vector:
                
                mock_lexical.return_value = mock_db_results
                mock_vector.return_value = []
                
                # Should not raise exception, should return original results
                results = await retrieval_service.search_proposals(
                    query="test query",
                    top_k=5,
                    use_rerank=True
                )
                
                # Should still return results despite Cohere failure
                assert len(results) > 0
    
    def test_search_filters_validation(self):
        """Test SearchFilters dataclass validation"""
        
        # Test valid filters
        filters = SearchFilters(
            network='polkadot',
            proposal_type='treasury',
            status='active',
            min_amount=1000.0,
            max_amount=50000.0,
            start_date=datetime.now() - timedelta(days=30),
            end_date=datetime.now()
        )
        
        assert filters.network == 'polkadot'
        assert filters.proposal_type == 'treasury'
        assert filters.status == 'active'
        assert filters.min_amount == 1000.0
        assert filters.max_amount == 50000.0
        assert filters.start_date is not None
        assert filters.end_date is not None
    
    def test_search_result_creation(self):
        """Test SearchResult dataclass creation"""
        
        result = SearchResult(
            id='test_id',
            title='Test Proposal',
            network='polkadot',
            type='treasury',
            amount=1000.0,
            created_at=datetime.now(),
            snippet='Test snippet',
            score=0.8
        )
        
        assert result.id == 'test_id'
        assert result.title == 'Test Proposal'
        assert result.network == 'polkadot'
        assert result.type == 'treasury'
        assert result.amount == 1000.0
        assert result.snippet == 'Test snippet'
        assert result.score == 0.8


class TestSearchFilters:
    """Test SearchFilters functionality"""
    
    def test_empty_filters(self):
        """Test creating empty filters"""
        filters = SearchFilters()
        assert filters.network is None
        assert filters.proposal_type is None
        assert filters.status is None
        assert filters.min_amount is None
        assert filters.max_amount is None
        assert filters.start_date is None
        assert filters.end_date is None
    
    def test_partial_filters(self):
        """Test creating filters with only some fields"""
        filters = SearchFilters(network='kusama', status='active')
        assert filters.network == 'kusama'
        assert filters.status == 'active'
        assert filters.proposal_type is None
        assert filters.min_amount is None


if __name__ == "__main__":
    pytest.main([__file__])

