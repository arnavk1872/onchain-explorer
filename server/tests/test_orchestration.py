"""
Unit tests for orchestration service
"""
import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock
from app.services.orchestration import OrchestrationService, OrchestrationState, get_orchestration_service


class TestOrchestrationService:
    def setup_method(self):
        """Setup test instance"""
        with patch('app.services.orchestration.get_nlsql_service') as mock_nlsql, \
             patch('app.services.orchestration.get_retrieval_service') as mock_retrieval:
            
            # Mock NLSQL service
            self.mock_nlsql = AsyncMock()
            self.mock_nlsql.execute_nlsql.return_value = {
                "count": 100,
                "examples": [{"id": "1", "title": "Test Proposal", "type": "TreasuryProposal"}],
                "sql": "SELECT COUNT(*) FROM proposals",
                "plan": "Count all proposals"
            }
            mock_nlsql.return_value = self.mock_nlsql
            
            # Mock retrieval service
            self.mock_retrieval = AsyncMock()
            self.mock_retrieval.search_proposals.return_value = [
                Mock(id="1", title="Test Proposal", type="TreasuryProposal", score=0.95)
            ]
            mock_retrieval.return_value = self.mock_retrieval
            
            self.service = OrchestrationService()
    
    @pytest.mark.asyncio
    async def test_route_sql_query(self):
        """Test routing to SQL agent for analytical queries"""
        state = OrchestrationState(query="highest amount in Aug 2025")
        
        result = await self.service._router_node(state)
        
        assert result.route_decision == "sql_agent"
        assert "router" in result.processing_times
    
    @pytest.mark.asyncio
    async def test_route_retrieval_query(self):
        """Test routing to retrieval agent for search queries"""
        state = OrchestrationState(query="clarys proposal")
        
        result = await self.service._router_node(state)
        
        assert result.route_decision == "retrieval_agent"
        assert "router" in result.processing_times
    
    @pytest.mark.asyncio
    async def test_route_general_query(self):
        """Test routing to composer for general queries"""
        state = OrchestrationState(query="hello world")
        
        result = await self.service._router_node(state)
        
        assert result.route_decision == "composer"
        assert "router" in result.processing_times
    
    @pytest.mark.asyncio
    async def test_sql_agent_node(self):
        """Test SQL agent processing"""
        state = OrchestrationState(query="how many proposals", route_decision="sql_agent")
        
        result = await self.service._sql_agent_node(state)
        
        assert result.sql_query == "SELECT COUNT(*) FROM proposals"
        assert result.sql_result["count"] == 100
        assert len(result.sql_result["examples"]) == 1
        assert "sql_agent" in result.processing_times
    
    @pytest.mark.asyncio
    async def test_retrieval_agent_node(self):
        """Test retrieval agent processing"""
        state = OrchestrationState(query="find proposals", route_decision="retrieval_agent")
        
        result = await self.service._retrieval_agent_node(state)
        
        assert len(result.retrieval_hits) == 1
        assert result.retrieval_hits[0]["id"] == "1"
        assert "retrieval_agent" in result.processing_times
    
    @pytest.mark.asyncio
    async def test_rerank_node_with_sql(self):
        """Test rerank node with SQL results"""
        state = OrchestrationState(
            query="test",
            route_decision="sql_agent",
            sql_result={"count": 5, "examples": [{"id": "1", "title": "Test"}]}
        )
        
        result = await self.service._rerank_node(state)
        
        assert len(result.reranked_results) == 1
        assert result.reranked_results[0]["id"] == "1"
        assert "rerank" in result.processing_times
    
    @pytest.mark.asyncio
    async def test_rerank_node_with_retrieval(self):
        """Test rerank node with retrieval results"""
        state = OrchestrationState(
            query="test",
            route_decision="retrieval_agent",
            retrieval_hits=[{"id": "1", "title": "Test", "score": 0.9}]
        )
        
        result = await self.service._rerank_node(state)
        
        assert len(result.reranked_results) == 1
        assert result.reranked_results[0]["id"] == "1"
        assert "rerank" in result.processing_times
    
    @pytest.mark.asyncio
    async def test_composer_node_sql_path(self):
        """Test composer with SQL path"""
        state = OrchestrationState(
            query="how many proposals",
            route_decision="sql_agent",
            sql_result={"count": 100, "examples": [{"title": "Test", "type": "TreasuryProposal"}]},
            reranked_results=[{"title": "Test", "type": "TreasuryProposal"}]
        )
        
        result = await self.service._composer_node(state)
        
        assert "Found 100 proposals" in result.final_answer
        assert "Test (TreasuryProposal)" in result.final_answer
        assert result.metadata["processing_type"] == "sql_agent"
        assert "composer" in result.processing_times
    
    @pytest.mark.asyncio
    async def test_composer_node_retrieval_path(self):
        """Test composer with retrieval path"""
        state = OrchestrationState(
            query="find proposals",
            route_decision="retrieval_agent",
            reranked_results=[{"title": "Test", "type": "TreasuryProposal", "score": 0.95}]
        )
        
        result = await self.service._composer_node(state)
        
        assert "Found 1 relevant proposals" in result.final_answer
        assert "Test (TreasuryProposal)" in result.final_answer
        assert "Score: 0.95" in result.final_answer
        assert result.metadata["processing_type"] == "retrieval_agent"
        assert "composer" in result.processing_times
    
    @pytest.mark.asyncio
    async def test_run_graph_sql_path(self):
        """Test full graph execution for SQL path"""
        events = []
        async for event in self.service.run_graph("highest amount in Aug 2025"):
            events.append(event)
        
        # Check that we get the expected events
        assert len(events) >= 3  # router_decision, sql_result, final_answer
        
        # Check router decision
        router_event = next(e for e in events if e["stage"] == "router_decision")
        assert router_event["payload"]["decision"] == "sql_agent"
        
        # Check SQL result
        sql_event = next(e for e in events if e["stage"] == "sql_result")
        assert sql_event["payload"]["count"] == 100
        assert "SELECT" in sql_event["payload"]["sql"]
        
        # Check final answer
        final_event = next(e for e in events if e["stage"] == "final_answer")
        assert "Found 100 proposals" in final_event["payload"]["answer"]
    
    @pytest.mark.asyncio
    async def test_run_graph_retrieval_path(self):
        """Test full graph execution for retrieval path"""
        events = []
        async for event in self.service.run_graph("clarys proposal"):
            events.append(event)
        
        # Check that we get the expected events
        assert len(events) >= 3  # router_decision, retrieval_hits, final_answer
        
        # Check router decision
        router_event = next(e for e in events if e["stage"] == "router_decision")
        assert router_event["payload"]["decision"] == "retrieval_agent"
        
        # Check retrieval hits
        retrieval_event = next(e for e in events if e["stage"] == "retrieval_hits")
        assert retrieval_event["payload"]["count"] == 1
        assert len(retrieval_event["payload"]["hits"]) == 1
        
        # Check final answer
        final_event = next(e for e in events if e["stage"] == "final_answer")
        assert "Found 1 relevant proposals" in final_event["payload"]["answer"]


class TestOrchestrationIntegration:
    """Integration tests for orchestration service"""
    
    @pytest.mark.asyncio
    async def test_get_orchestration_service(self):
        """Test service factory function"""
        with patch('app.services.orchestration.get_nlsql_service') as mock_nlsql, \
             patch('app.services.orchestration.get_retrieval_service') as mock_retrieval:
            
            service = get_orchestration_service()
            assert isinstance(service, OrchestrationService)
    
    @pytest.mark.asyncio
    async def test_error_handling(self):
        """Test error handling in orchestration"""
        with patch('app.services.orchestration.get_nlsql_service') as mock_nlsql, \
             patch('app.services.orchestration.get_retrieval_service') as mock_retrieval:
            
            # Mock service that raises exception
            mock_nlsql.return_value.execute_nlsql.side_effect = Exception("Test error")
            mock_retrieval.return_value.search_proposals.return_value = []
            
            service = OrchestrationService()
            events = []
            
            async for event in service.run_graph("test query"):
                events.append(event)
            
            # Should get error event
            error_event = next((e for e in events if e["stage"] == "error"), None)
            assert error_event is not None
            assert "Test error" in error_event["payload"]["error"]
