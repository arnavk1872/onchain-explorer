"""
Unit tests for search API endpoint
Tests request validation, response format, and error handling
"""

import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from datetime import datetime, timedelta

from app.main import app
from app.services.retrieval import SearchResult


class TestSearchEndpoint:
    """Test cases for POST /search endpoint"""
    
    @pytest.fixture
    def client(self):
        """Create test client"""
        return TestClient(app)
    
    @pytest.fixture
    def mock_search_results(self):
        """Mock search results for testing"""
        return [
            SearchResult(
                id='prop_1',
                title='Treasury Proposal for Development',
                network='polkadot',
                type='treasury',
                amount=10000.0,
                created_at=datetime.now() - timedelta(days=5),
                snippet='This proposal requests funding for core development work.',
                score=0.8
            ),
            SearchResult(
                id='prop_2',
                title='Governance Proposal for Upgrade',
                network='kusama',
                type='governance',
                amount=5000.0,
                created_at=datetime.now() - timedelta(days=3),
                snippet='This governance proposal suggests upgrading the runtime.',
                score=0.7
            )
        ]
    
    @patch('app.api.endpoints.get_retrieval_service')
    def test_search_endpoint_success(self, mock_get_service, client, mock_search_results):
        """Test successful search request"""
        
        # Mock retrieval service
        mock_service = AsyncMock()
        mock_service.search_proposals.return_value = mock_search_results
        mock_get_service.return_value = mock_service
        
        # Test request
        request_data = {
            "query": "treasury proposal",
            "filters": {
                "network": "polkadot",
                "proposal_type": "treasury"
            },
            "top_k": 10,
            "use_rerank": True
        }
        
        response = client.post("/api/v1/search", json=request_data)
        
        # Verify response
        assert response.status_code == 200
        data = response.json()
        
        assert data["query"] == "treasury proposal"
        assert data["total_found"] == 2
        assert len(data["results"]) == 2
        assert data["filters_applied"]["network"] == "polkadot"
        assert data["filters_applied"]["proposal_type"] == "treasury"
        
        # Verify result structure
        result = data["results"][0]
        assert "id" in result
        assert "title" in result
        assert "network" in result
        assert "type" in result
        assert "amount" in result
        assert "created_at" in result
        assert "snippet" in result
        assert "score" in result
    
    @patch('app.api.endpoints.get_retrieval_service')
    def test_search_endpoint_minimal_request(self, mock_get_service, client, mock_search_results):
        """Test search request with minimal data"""
        
        # Mock retrieval service
        mock_service = AsyncMock()
        mock_service.search_proposals.return_value = mock_search_results[:1]
        mock_get_service.return_value = mock_service
        
        # Test minimal request
        request_data = {
            "query": "test query"
        }
        
        response = client.post("/api/v1/search", json=request_data)
        
        # Verify response
        assert response.status_code == 200
        data = response.json()
        
        assert data["query"] == "test query"
        assert data["total_found"] == 1
        assert data["filters_applied"] is None
    
    def test_search_endpoint_validation_error(self, client):
        """Test search request with validation errors"""
        
        # Test missing query
        request_data = {
            "filters": {"network": "polkadot"}
        }
        
        response = client.post("/api/v1/search", json=request_data)
        assert response.status_code == 422  # Validation error
    
    def test_search_endpoint_invalid_filters(self, client):
        """Test search request with invalid filter types"""
        
        # Test invalid filter types
        request_data = {
            "query": "test",
            "filters": {
                "min_amount": "invalid_number",  # Should be number
                "start_date": "invalid_date"    # Should be datetime
            }
        }
        
        response = client.post("/api/v1/search", json=request_data)
        assert response.status_code == 422  # Validation error
    
    @patch('app.api.endpoints.get_retrieval_service')
    def test_search_endpoint_service_error(self, mock_get_service, client):
        """Test search endpoint when service raises exception"""
        
        # Mock service to raise exception
        mock_service = AsyncMock()
        mock_service.search_proposals.side_effect = Exception("Database connection failed")
        mock_get_service.return_value = mock_service
        
        request_data = {
            "query": "test query"
        }
        
        response = client.post("/api/v1/search", json=request_data)
        
        # Should return 500 error
        assert response.status_code == 500
        data = response.json()
        assert "Search failed" in data["detail"]
    
    @patch('app.api.endpoints.get_retrieval_service')
    def test_search_endpoint_empty_results(self, mock_get_service, client):
        """Test search endpoint with empty results"""
        
        # Mock service to return empty results
        mock_service = AsyncMock()
        mock_service.search_proposals.return_value = []
        mock_get_service.return_value = mock_service
        
        request_data = {
            "query": "nonexistent query"
        }
        
        response = client.post("/api/v1/search", json=request_data)
        
        # Verify response
        assert response.status_code == 200
        data = response.json()
        
        assert data["query"] == "nonexistent query"
        assert data["total_found"] == 0
        assert data["results"] == []
    
    @patch('app.api.endpoints.get_retrieval_service')
    def test_search_endpoint_with_date_filters(self, mock_get_service, client, mock_search_results):
        """Test search endpoint with date filters"""
        
        # Mock retrieval service
        mock_service = AsyncMock()
        mock_service.search_proposals.return_value = mock_search_results
        mock_get_service.return_value = mock_service
        
        # Test with date filters
        request_data = {
            "query": "test query",
            "filters": {
                "start_date": "2024-01-01T00:00:00Z",
                "end_date": "2024-12-31T23:59:59Z"
            }
        }
        
        response = client.post("/api/v1/search", json=request_data)
        
        # Verify response
        assert response.status_code == 200
        data = response.json()
        
        assert data["filters_applied"]["start_date"] == "2024-01-01T00:00:00Z"
        assert data["filters_applied"]["end_date"] == "2024-12-31T23:59:59Z"
    
    @patch('app.api.endpoints.get_retrieval_service')
    def test_search_endpoint_with_amount_filters(self, mock_get_service, client, mock_search_results):
        """Test search endpoint with amount filters"""
        
        # Mock retrieval service
        mock_service = AsyncMock()
        mock_service.search_proposals.return_value = mock_search_results
        mock_get_service.return_value = mock_service
        
        # Test with amount filters
        request_data = {
            "query": "funding",
            "filters": {
                "min_amount": 1000.0,
                "max_amount": 50000.0
            }
        }
        
        response = client.post("/api/v1/search", json=request_data)
        
        # Verify response
        assert response.status_code == 200
        data = response.json()
        
        assert data["filters_applied"]["min_amount"] == 1000.0
        assert data["filters_applied"]["max_amount"] == 50000.0
    
    def test_search_endpoint_request_validation(self, client):
        """Test various request validation scenarios"""
        
        # Test valid requests
        valid_requests = [
            {"query": "simple query"},
            {"query": "query", "top_k": 5},
            {"query": "query", "use_rerank": False},
            {"query": "query", "filters": {}},
            {"query": "query", "filters": {"network": "polkadot"}},
        ]
        
        for request_data in valid_requests:
            response = client.post("/api/v1/search", json=request_data)
            # Should not be validation error (might be 500 due to missing service, but not 422)
            assert response.status_code != 422
        
        # Test invalid requests
        invalid_requests = [
            {},  # Missing query
            {"query": ""},  # Empty query
            {"query": "test", "top_k": -1},  # Negative top_k
            {"query": "test", "top_k": "invalid"},  # Invalid top_k type
        ]
        
        for request_data in invalid_requests:
            response = client.post("/api/v1/search", json=request_data)
            assert response.status_code == 422  # Validation error


if __name__ == "__main__":
    pytest.main([__file__])
