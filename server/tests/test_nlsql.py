"""
Unit tests for NLSQL service
"""
import pytest
from unittest.mock import Mock, patch
from app.services.nlsql import NLSQLService, SQLSecurityError, get_nlsql_service


class TestNLSQLService:
    def setup_method(self):
        """Setup test instance"""
        with patch('app.services.nlsql.get_settings') as mock_settings:
            mock_settings.return_value.openai_api_key = "test-key"
            self.service = NLSQLService()
    
    def test_valid_date_range_query(self):
        """Test valid date range query generation"""
        with patch.object(self.service, '_generate_sql_with_llm') as mock_llm:
            mock_llm.return_value = {
                "plan": "Count proposals created in August 2025",
                "sql": "SELECT COUNT(*) FROM proposals WHERE created_at >= $1 AND created_at < $2"
            }
            
            result = self.service.plan_sql("How many proposals in August 2025?")
            
            assert result["plan"] == "Count proposals created in August 2025"
            assert "COUNT(*)" in result["sql"]
            assert "proposals" in result["sql"]
            assert "$1" in result["sql"] and "$2" in result["sql"]
    
    def test_invalid_column_rejected(self):
        """Test that invalid columns are rejected"""
        with patch.object(self.service, '_generate_sql_with_llm') as mock_llm:
            mock_llm.return_value = {
                "plan": "Invalid query",
                "sql": "SELECT invalid_column FROM proposals"
            }
            
            with pytest.raises(SQLSecurityError, match="Column 'invalid_column' not allowed"):
                self.service.plan_sql("Show me invalid data")
    
    def test_ddl_rejected(self):
        """Test that DDL statements are rejected"""
        with patch.object(self.service, '_generate_sql_with_llm') as mock_llm:
            mock_llm.return_value = {
                "plan": "Create table",
                "sql": "CREATE TABLE test (id INT)"
            }
            
            with pytest.raises(SQLSecurityError, match="Only SELECT queries are allowed"):
                self.service.plan_sql("Create a table")
    
    def test_dml_rejected(self):
        """Test that DML statements are rejected"""
        with patch.object(self.service, '_generate_sql_with_llm') as mock_llm:
            mock_llm.return_value = {
                "plan": "Insert data",
                "sql": "INSERT INTO proposals (id) VALUES ('test')"
            }
            
            with pytest.raises(SQLSecurityError, match="Only SELECT queries are allowed"):
                self.service.plan_sql("Insert some data")
    
    def test_sql_injection_attempt_rejected(self):
        """Test that SQL injection attempts are rejected"""
        with patch.object(self.service, '_generate_sql_with_llm') as mock_llm:
            mock_llm.return_value = {
                "plan": "Malicious query",
                "sql": "SELECT * FROM proposals; DROP TABLE proposals; --"
            }
            
            with pytest.raises(SQLSecurityError, match="Comments, DDL, DML, or UNION statements not allowed"):
                self.service.plan_sql("'; DROP TABLE proposals; --")
    
    def test_union_rejected(self):
        """Test that UNION statements are rejected"""
        with patch.object(self.service, '_generate_sql_with_llm') as mock_llm:
            mock_llm.return_value = {
                "plan": "Union query",
                "sql": "SELECT * FROM proposals UNION SELECT * FROM proposals_embeddings"
            }
            
            with pytest.raises(SQLSecurityError, match="Comments, DDL, DML, or UNION statements not allowed"):
                self.service.plan_sql("Show me everything")
    
    def test_invalid_table_rejected(self):
        """Test that invalid tables are rejected"""
        with patch.object(self.service, '_generate_sql_with_llm') as mock_llm:
            mock_llm.return_value = {
                "plan": "Invalid table query",
                "sql": "SELECT * FROM users"
            }
            
            with pytest.raises(SQLSecurityError, match="Table 'users' not allowed"):
                self.service.plan_sql("Show me users")
    
    def test_comments_rejected(self):
        """Test that comments are rejected"""
        with patch.object(self.service, '_generate_sql_with_llm') as mock_llm:
            mock_llm.return_value = {
                "plan": "Query with comment",
                "sql": "SELECT * FROM proposals -- this is a comment"
            }
            
            with pytest.raises(SQLSecurityError, match="Comments, DDL, DML, or UNION statements not allowed"):
                self.service.plan_sql("Show me proposals with comment")
    
    def test_valid_examples_query(self):
        """Test valid examples query generation"""
        with patch.object(self.service, '_generate_sql_with_llm') as mock_llm:
            mock_llm.return_value = {
                "plan": "Get sample treasury proposals",
                "sql": "SELECT * FROM proposals WHERE type = $1 LIMIT 5"
            }
            
            result = self.service.plan_sql("Show me some treasury proposals")
            
            assert result["plan"] == "Get sample treasury proposals"
            assert "LIMIT 5" in result["sql"]
            assert "type = $1" in result["sql"]
    
    def test_parameterization_required(self):
        """Test that parameterized queries are required"""
        with patch.object(self.service, '_generate_sql_with_llm') as mock_llm:
            mock_llm.return_value = {
                "plan": "Non-parameterized query",
                "sql": "SELECT * FROM proposals WHERE type = 'TreasuryProposal'"
            }
            
            with pytest.raises(SQLSecurityError, match="SQL must use parameterized queries"):
                self.service.plan_sql("Show treasury proposals")
    
    def test_get_nlsql_service(self):
        """Test service factory function"""
        with patch('app.services.nlsql.get_settings') as mock_settings:
            mock_settings.return_value.openai_api_key = "test-key"
            service = get_nlsql_service()
            assert isinstance(service, NLSQLService)


class TestNLSQLIntegration:
    """Integration tests for NLSQL service"""
    
    def test_complete_workflow(self):
        """Test complete workflow from query to validated SQL"""
        with patch('app.services.nlsql.get_settings') as mock_settings:
            mock_settings.return_value.openai_api_key = "test-key"
            
            service = NLSQLService()
            
            with patch.object(service, '_generate_sql_with_llm') as mock_llm:
                mock_llm.return_value = {
                    "plan": "Count proposals by status",
                    "sql": "SELECT status, COUNT(*) FROM proposals GROUP BY status"
                }
                
                result = service.plan_sql("How many proposals by status?")
                
                assert "plan" in result
                assert "sql" in result
                assert "params" in result
                assert result["plan"] == "Count proposals by status"
                assert "COUNT(*)" in result["sql"]
                assert "GROUP BY" in result["sql"]
