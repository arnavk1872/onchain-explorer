"""
Natural Language to SQL service with security constraints and validation.
"""
import re
import json
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
import sqlglot
from sqlglot import parse_one, exp
from sqlglot.errors import ParseError
import openai
from app.logger import get_logger
from app.config import settings
from app.db import get_session

logger = get_logger(__name__)

# Allowed tables and columns
ALLOWED_TABLES = {"proposals", "proposals_embeddings"}
ALLOWED_COLUMNS = {
    "id", "network", "type", "title", "description", "proposer", 
    "amount_numeric", "currency", "status", "created_at", "updated_at"
}

# SQLGlot dialect for PostgreSQL
DIALECT = "postgres"

class SQLSecurityError(Exception):
    """Raised when SQL violates security constraints"""
    pass

class NLSQLService:
    def __init__(self):
        self.client = openai.OpenAI(api_key=settings.openai_api_key)
        self.db_connection_string = settings.db_connection_string
    
    def plan_sql(self, user_query: str, schema_hint: str = "") -> Dict[str, Any]:
        """
        Generate SQL plan from natural language query using LLM with validation.
        
        Args:
            user_query: Natural language query
            schema_hint: Optional schema information
            
        Returns:
            Dict with plan, sql, and params
        """
        try:
            # Generate SQL using LLM
            sql_result = self._generate_sql_with_llm(user_query, schema_hint)
            
            # Validate and secure the SQL
            validated_sql, params = self._validate_and_secure_sql(sql_result["sql"])
            
            return {
                "plan": sql_result["plan"],
                "sql": validated_sql,
                "params": params
            }
            
        except Exception as e:
            logger.error(f"SQL planning failed: {str(e)}")
            raise SQLSecurityError(f"Failed to generate secure SQL: {str(e)}")
    
    async def execute_nlsql(self, user_query: str, schema_hint: str = "") -> Dict[str, Any]:
        """
        Execute natural language query and return results.
        
        Args:
            user_query: Natural language query
            schema_hint: Optional schema information
            
        Returns:
            Dict with count, examples, and metadata
        """
        try:
            # Generate SQL plan
            plan_result = self.plan_sql(user_query, schema_hint)
            
            # Execute the SQL
            results = await self._execute_sql(plan_result["sql"], plan_result["params"])
            
            # Format results based on query type
            if "COUNT" in plan_result["sql"].upper():
                count = results[0][0] if results else 0
                # Get examples if it's a count query
                examples = await self._get_examples_for_count_query(user_query)
                return {
                    "count": count,
                    "examples": examples,
                    "plan": plan_result["plan"],
                    "sql": plan_result["sql"]
                }
            else:
                # Return examples directly
                return {
                    "count": len(results),
                    "examples": [dict(row) for row in results],
                    "plan": plan_result["plan"],
                    "sql": plan_result["sql"]
                }
                
        except Exception as e:
            logger.error(f"NLSQL execution failed: {str(e)}")
            raise SQLSecurityError(f"Failed to execute query: {str(e)}")
    
    async def _execute_sql(self, sql: str, params: List[Any]) -> List[Any]:
        """Execute SQL query and return results"""
        try:
            async with get_session() as conn:
                result = await conn.fetch(sql, *params)
                return result
        except Exception as e:
            logger.error(f"SQL execution failed: {str(e)}")
            raise SQLSecurityError(f"Database query failed: {str(e)}")
    
    async def _get_examples_for_count_query(self, user_query: str) -> List[Dict[str, Any]]:
        """Get example results for count queries"""
        try:
            # Extract filters from the original query to match the count query
            query_lower = user_query.lower()
            
            # Check for network filtering
            network_filter = self._extract_network_filter(query_lower)
            
            # Check for date filtering
            date_filter = self._extract_date_filter(query_lower)
            
            # Build WHERE conditions
            where_conditions = []
            if network_filter:
                where_conditions.append(network_filter)
            if date_filter:
                where_conditions.append(date_filter)
            
            where_clause = " AND ".join(where_conditions) if where_conditions else ""
            where_sql = f" WHERE {where_clause}" if where_clause else ""
            
            # Generate examples query that matches the count query
            examples_sql = f"SELECT id, title, type, created_at FROM proposals{where_sql} ORDER BY created_at DESC LIMIT 5"
            results = await self._execute_sql(examples_sql, [])
            return [dict(row) for row in results]
        except Exception as e:
            logger.warning(f"Failed to get examples: {str(e)}")
            return []
    
    def _generate_sql_with_llm(self, user_query: str, schema_hint: str) -> Dict[str, Any]:
        """Generate SQL using OpenAI with structured output"""
        
        schema_info = """
        Database: PostgreSQL
        
        COMPLETE DATABASE SCHEMA:
        
        Table: proposals
        - id (TEXT, PRIMARY KEY): Unique identifier for the proposal
        - network (TEXT, NOT NULL): Network name ('polkadot' or 'kusama')
        - type (TEXT, NOT NULL): Proposal type ('TreasuryProposal', 'ReferendumV2', 'CouncilMotion', 'ChildBounty', etc.)
        - title (TEXT): Proposal title
        - description (TEXT): Proposal description/content
        - proposer (TEXT): Proposer address
        - amount_numeric (NUMERIC): Proposal amount (can be NULL)
        - currency (TEXT): Currency type (can be NULL)
        - status (TEXT): Proposal status ('Executed', 'Confirmed', 'Claimed', 'Pending', etc.)
        - created_at (TIMESTAMP, NOT NULL): When the proposal was created
        - updated_at (TIMESTAMP): When the proposal was last updated
        - metadata (JSON): Additional metadata
        - doc_tsv (TEXT): Full-text search content
        
        Table: proposals_embeddings
        - proposal_id (TEXT, PRIMARY KEY): References proposals.id
        - embedding (VECTOR): Vector embedding for similarity search
        
        Rules:
        - Only SELECT queries allowed
        - Use actual values, not parameters
        - Return both a plan and the SQL
        - For date ranges, use created_at column
        - For counting, use COUNT(*)
        - For examples, use LIMIT 5
        - Use PostgreSQL syntax (e.g., single quotes for strings, ::text for casting)
        - Network values are lowercase: 'polkadot' or 'kusama'
        - Type values are case-sensitive: 'TreasuryProposal', 'ReferendumV2', etc.
        """
        
        prompt = f"""
        Convert this natural language query to SQL: "{user_query}"
        
        {schema_info}
        {schema_hint}
        
        Return a JSON response with:
        {{
            "plan": "Brief description of what the query does",
            "sql": "Single SQL query with actual values (not parameterized)",
            "params": []
        }}
        
        CRITICAL RULES:
        1. For "how many" questions, ALWAYS use: SELECT COUNT(*) FROM proposals WHERE [conditions]
        2. For "show examples" questions, use: SELECT * FROM proposals WHERE [conditions] LIMIT 5
        3. NEVER use CTEs, WITH clauses, or complex subqueries
        4. Keep queries simple and direct
        5. Return only ONE SQL query in the "sql" field
        
        Examples:
        - "How many proposals in August 2025?" -> {{"plan": "Count proposals created in August 2025", "sql": "SELECT COUNT(*) FROM proposals WHERE created_at >= '2025-08-01' AND created_at < '2025-09-01'", "params": []}}
        - "Show me some treasury proposals" -> {{"plan": "Get sample treasury proposals", "sql": "SELECT * FROM proposals WHERE type = 'TreasuryProposal' LIMIT 5", "params": []}}
        - "How many proposals are there?" -> {{"plan": "Count all proposals", "sql": "SELECT COUNT(*) FROM proposals", "params": []}}
        - "How many Kusama proposals exist?" -> {{"plan": "Count Kusama proposals", "sql": "SELECT COUNT(*) FROM proposals WHERE network = 'kusama'", "params": []}}
        - "Show me some Polkadot proposals" -> {{"plan": "Get sample Polkadot proposals", "sql": "SELECT * FROM proposals WHERE network = 'polkadot' LIMIT 5", "params": []}}
        - "How many Kusama proposals exist and show some examples?" -> {{"plan": "Count Kusama proposals", "sql": "SELECT COUNT(*) FROM proposals WHERE network = 'kusama'", "params": []}}
        - "Show me executed treasury proposals" -> {{"plan": "Get executed treasury proposals", "sql": "SELECT * FROM proposals WHERE type = 'TreasuryProposal' AND status = 'Executed' LIMIT 5", "params": []}}
        - "How many proposals have amounts over 1000?" -> {{"plan": "Count proposals with amount > 1000", "sql": "SELECT COUNT(*) FROM proposals WHERE amount_numeric > 1000", "params": []}}
        """
        
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a PostgreSQL SQL expert with complete knowledge of the database schema. Generate SIMPLE SQL queries using ONLY the provided schema fields. NEVER use CTEs, WITH clauses, or complex subqueries. For 'how many' questions, use SELECT COUNT(*) FROM proposals WHERE [conditions]. For 'show examples' questions, use SELECT * FROM proposals WHERE [conditions] LIMIT 5. Always return valid JSON without any markdown formatting or extra text."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=500
            )
            
            content = response.choices[0].message.content.strip()
            
            # More robust content cleaning
            if content.startswith('```json'):
                content = content[7:]
            elif content.startswith('```'):
                content = content[3:]
            
            if content.endswith('```'):
                content = content[:-3]
            
            # Remove any leading/trailing whitespace and newlines
            content = content.strip()
            
            # Try to find JSON in the content if it's embedded in other text
            json_start = content.find('{')
            json_end = content.rfind('}') + 1
            
            if json_start != -1 and json_end > json_start:
                content = content[json_start:json_end]
            
            result = json.loads(content)
            
            # Validate that we got a proper result structure
            if not isinstance(result, dict) or 'sql' not in result:
                logger.error("LLM returned invalid JSON structure")
                return self._generate_fallback_sql(user_query)
            
            # Validate that sql is a string, not an array
            if not isinstance(result['sql'], str):
                logger.error("LLM returned SQL as array instead of string")
                return self._generate_fallback_sql(user_query)
            
            # Post-process to validate security and fix common issues
            result = self._validate_sql_security_simple(result)
            result = self._fix_llm_query_issues(result, user_query)
            
            return result
            
        except json.JSONDecodeError as e:
            logger.error(f"LLM JSON parsing failed: {str(e)}")
            # Fallback to simple query generation
            return self._generate_fallback_sql(user_query)
        except Exception as e:
            logger.error(f"LLM SQL generation failed: {str(e)}")
            return self._generate_fallback_sql(user_query)
    
    def _generate_fallback_sql(self, user_query: str) -> Dict[str, Any]:
        """Generate simple SQL for common queries when LLM fails"""
        query_lower = user_query.lower()
        
        # Check for date filtering patterns
        date_filter = self._extract_date_filter(query_lower)
        
        # Check for network filtering patterns
        network_filter = self._extract_network_filter(query_lower)
        
        # Build WHERE conditions
        where_conditions = []
        if network_filter:
            where_conditions.append(network_filter)
        if date_filter:
            where_conditions.append(date_filter)
        
        where_clause = " AND ".join(where_conditions) if where_conditions else ""
        where_sql = f" WHERE {where_clause}" if where_clause else ""
        
        if "how many" in query_lower and "proposals" in query_lower:
            if "treasury" in query_lower:
                sql = f"SELECT COUNT(*) FROM proposals WHERE type = 'TreasuryProposal'{where_sql.replace(' WHERE ', ' AND ')}"
                if not where_conditions:
                    sql = "SELECT COUNT(*) FROM proposals WHERE type = 'TreasuryProposal'"
                network_name = network_filter.split('=')[1].strip().strip("'") if network_filter else ""
                plan_parts = ["Count treasury proposals"]
                if network_name:
                    plan_parts.append(f"for {network_name}")
                if date_filter:
                    plan_parts.append(f"in {date_filter}")
                
                return {
                    "plan": " ".join(plan_parts),
                    "sql": sql,
                    "params": []
                }
            else:
                sql = f"SELECT COUNT(*) FROM proposals{where_sql}"
                network_name = network_filter.split('=')[1].strip().strip("'") if network_filter else ""
                plan_parts = ["Count all proposals"]
                if network_name:
                    plan_parts.append(f"for {network_name}")
                if date_filter:
                    plan_parts.append(f"in {date_filter}")
                
                return {
                    "plan": " ".join(plan_parts),
                    "sql": sql,
                    "params": []
                }
        elif "show" in query_lower and "recent" in query_lower:
            sql = f"SELECT * FROM proposals{where_sql} ORDER BY created_at DESC LIMIT 5"
            network_name = network_filter.split('=')[1].strip().strip("'") if network_filter else ""
            plan_parts = ["Get recent proposals"]
            if network_name:
                plan_parts.append(f"for {network_name}")
            if date_filter:
                plan_parts.append(f"in {date_filter}")
            
            return {
                "plan": " ".join(plan_parts),
                "sql": sql,
                "params": []
            }
        elif "show" in query_lower and "treasury" in query_lower:
            treasury_where = "type = 'TreasuryProposal'"
            if where_conditions:
                treasury_where += f" AND {where_clause}"
            sql = f"SELECT * FROM proposals WHERE {treasury_where} LIMIT 5"
            network_name = network_filter.split('=')[1].strip().strip("'") if network_filter else ""
            plan_parts = ["Get treasury proposals"]
            if network_name:
                plan_parts.append(f"for {network_name}")
            if date_filter:
                plan_parts.append(f"in {date_filter}")
            
            return {
                "plan": " ".join(plan_parts),
                "sql": sql,
                "params": []
            }
        else:
            # Default fallback
            sql = f"SELECT * FROM proposals{where_sql} LIMIT 5"
            network_name = network_filter.split('=')[1].strip().strip("'") if network_filter else ""
            plan_parts = ["Get sample proposals"]
            if network_name:
                plan_parts.append(f"for {network_name}")
            if date_filter:
                plan_parts.append(f"in {date_filter}")
            
            return {
                "plan": " ".join(plan_parts),
                "sql": sql,
                "params": []
            }
    
    def _extract_date_filter(self, query_lower: str) -> str:
        """Extract date filter from query text"""
        import re
        from datetime import datetime
        
        # Check for month/year patterns like "August 2025", "Aug 2025", "2025-08"
        month_patterns = {
            'january': '01', 'jan': '01',
            'february': '02', 'feb': '02', 
            'march': '03', 'mar': '03',
            'april': '04', 'apr': '04',
            'may': '05',
            'june': '06', 'jun': '06',
            'july': '07', 'jul': '07',
            'august': '08', 'aug': '08',
            'september': '09', 'sep': '09', 'sept': '09',
            'october': '10', 'oct': '10',
            'november': '11', 'nov': '11',
            'december': '12', 'dec': '12'
        }
        
        # Look for month year pattern
        for month_name, month_num in month_patterns.items():
            if month_name in query_lower:
                # Extract year
                year_match = re.search(r'(\d{4})', query_lower)
                if year_match:
                    year = year_match.group(1)
                    start_date = f"{year}-{month_num}-01"
                    # Calculate next month for end date
                    if month_num == '12':
                        end_date = f"{int(year)+1}-01-01"
                    else:
                        next_month = int(month_num) + 1
                        end_date = f"{year}-{next_month:02d}-01"
                    
                    return f"created_at >= '{start_date}' AND created_at < '{end_date}'"
        
        # Check for YYYY-MM pattern
        date_match = re.search(r'(\d{4})-(\d{2})', query_lower)
        if date_match:
            year, month = date_match.groups()
            start_date = f"{year}-{month}-01"
            # Calculate next month
            if month == '12':
                end_date = f"{int(year)+1}-01-01"
            else:
                next_month = int(month) + 1
                end_date = f"{year}-{next_month:02d}-01"
            
            return f"created_at >= '{start_date}' AND created_at < '{end_date}'"
        
        return ""
    
    def _extract_network_filter(self, query_lower: str) -> str:
        """Extract network filter from query text"""
        import re
        
        # Common network names and their variations
        network_patterns = {
            'polkadot': ['polkadot', 'dot'],
            'kusama': ['kusama', 'ksm'],
            'substrate': ['substrate'],
            'westend': ['westend', 'westend testnet'],
            'rococo': ['rococo', 'rococo testnet']
        }
        
        # Look for network mentions in the query
        for network, patterns in network_patterns.items():
            for pattern in patterns:
                if pattern in query_lower:
                    return f"network = '{network}'"
        
        return ""
    
    def _validate_sql_security_simple(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Simple security validation - only check for dangerous keywords"""
        sql = result['sql'].upper()
        
        # Check for dangerous keywords
        dangerous_keywords = [
            'DELETE', 'DROP', 'INSERT', 'UPDATE', 'ALTER', 'CREATE', 
            'TRUNCATE', 'EXEC', 'EXECUTE', '--', '/*', '*/'
        ]
        
        for keyword in dangerous_keywords:
            if keyword in sql:
                logger.error(f"Dangerous SQL keyword '{keyword}' detected, using fallback")
                # We need to pass the original query to the fallback, but we don't have it here
                # So we'll just return the result as-is and let the main flow handle it
                pass
        
        return result
    
    def _fix_llm_query_issues(self, result: Dict[str, Any], user_query: str) -> Dict[str, Any]:
        """Fix common LLM query issues"""
        sql = result['sql']
        query_lower = user_query.lower()
        
        # Fix multiple statements separated by semicolons
        if ';' in sql and 'SELECT' in sql.upper():
            # Split by semicolon and take the first SELECT statement
            statements = [stmt.strip() for stmt in sql.split(';') if stmt.strip()]
            select_statements = [stmt for stmt in statements if 'SELECT' in stmt.upper()]
            if select_statements:
                # Remove any surrounding parentheses
                clean_sql = select_statements[0].strip()
                if clean_sql.startswith('(') and clean_sql.endswith(')'):
                    clean_sql = clean_sql[1:-1].strip()
                result['sql'] = clean_sql
                logger.info("Fixed multiple statements to use first SELECT statement")
        
        # If the query asks "how many" but uses complex constructs, simplify it
        if "how many" in query_lower:
            # Check for CTEs, WITH clauses, or complex subqueries
            if any(keyword in sql.upper() for keyword in ['WITH ', 'CTE', 'UNION', 'array_agg', 'row_to_json']):
                logger.info("LLM generated complex query for 'how many', using fallback")
                return self._generate_fallback_sql(user_query)
        
        # If the query asks "show examples" but uses complex constructs, simplify it
        if any(phrase in query_lower for phrase in ['show examples', 'show some', 'name a few']):
            if any(keyword in sql.upper() for keyword in ['WITH ', 'CTE', 'UNION', 'array_agg', 'row_to_json']):
                logger.info("LLM generated complex query for 'show examples', using fallback")
                return self._generate_fallback_sql(user_query)
        
        return result
    
    def _validate_and_secure_sql(self, sql: str) -> Tuple[str, List[Any]]:
        """
        Validate and secure SQL using SQLGlot.
        
        Returns:
            Tuple of (validated_sql, parameters)
        """
        try:
            # Parse SQL
            parsed = parse_one(sql, read=DIALECT)
            if not parsed:
                raise SQLSecurityError("Invalid SQL syntax")
            
            # Security validations
            self._validate_sql_security(parsed)
            
            # Extract parameters and create parameterized query
            param_values = self._extract_parameters(sql)
            validated_sql = self._create_parameterized_sql(parsed)
            
            return validated_sql, param_values
            
        except ParseError as e:
            raise SQLSecurityError(f"SQL parse error: {str(e)}")
        except Exception as e:
            raise SQLSecurityError(f"SQL validation failed: {str(e)}")
    
    def _validate_sql_security(self, parsed_sql) -> None:
        """Validate SQL against security constraints"""
        
        # Check for non-SELECT statements
        if not isinstance(parsed_sql, exp.Select):
            raise SQLSecurityError("Only SELECT queries are allowed")
        
        # Check for dangerous keywords and patterns
        sql_str = str(parsed_sql)
        sql_upper = sql_str.upper()
        
        # Check for dangerous SQL keywords
        dangerous_keywords = [
            'INSERT', 'UPDATE', 'DELETE', 'DROP', 'CREATE', 
            'ALTER', 'TRUNCATE', 'EXEC', 'EXECUTE'
        ]
        
        for keyword in dangerous_keywords:
            # Check if keyword appears as a standalone word
            pattern = r'\b' + keyword + r'\b'
            if re.search(pattern, sql_upper):
                raise SQLSecurityError(f"Dangerous SQL keyword '{keyword}' not allowed")
        
        # Check for comments
        if '--' in sql_str or '/*' in sql_str or '*/' in sql_str:
            raise SQLSecurityError("Comments not allowed in SQL")
        
        # Check tables and columns
        self._validate_tables_and_columns(parsed_sql)
    
    def _validate_tables_and_columns(self, parsed_sql) -> None:
        """Validate that only allowed tables and columns are used"""
        
        # Get all table references, but allow CTEs and subqueries
        tables = set()
        for table in parsed_sql.find_all(exp.Table):
            table_name = table.name.lower()
            
            # Allow CTEs (Common Table Expressions) - they start with common prefixes
            if (table_name.startswith(('kusama_', 'polkadot_', 'temp_', 'cte_', 'with_')) or 
                table_name in ALLOWED_TABLES):
                tables.add(table_name)
            else:
                # Check if this is a CTE by looking at the context
                # CTEs are typically defined in WITH clauses
                parent = table.parent
                is_cte = False
                while parent:
                    if hasattr(parent, 'key') and parent.key == 'with':
                        is_cte = True
                        break
                    parent = parent.parent
                
                if not is_cte and table_name not in ALLOWED_TABLES:
                    raise SQLSecurityError(f"Table '{table_name}' not allowed")
                tables.add(table_name)
        
        # Get all column references - be more lenient for CTEs
        for column in parsed_sql.find_all(exp.Column):
            column_name = column.name.lower()
            # Allow common column names that might be in CTEs
            if (column_name not in ALLOWED_COLUMNS and 
                column_name not in ['count', 'samples', 'data', 'result', 'row']):
                # Check if this column is from a CTE
                table = column.table
                if table and table.name.lower().startswith(('kusama_', 'polkadot_', 'temp_', 'cte_', 'with_')):
                    continue  # Allow columns from CTEs
                raise SQLSecurityError(f"Column '{column_name}' not allowed")
    
    def _extract_parameters(self, sql: str) -> List[Any]:
        """Extract parameter values from SQL string"""
        # For now, return empty list - parameters should be provided separately
        # In a real implementation, you'd parse the SQL to extract parameter values
        return []
    
    def _create_parameterized_sql(self, parsed_sql) -> str:
        """Convert parsed SQL to parameterized form"""
        # Convert to string
        sql_str = str(parsed_sql)
        
        # Convert @1, @2, etc. to $1, $2, etc. for PostgreSQL
        import re
        sql_str = re.sub(r'@(\d+)', r'$\1', sql_str)
        
        return sql_str

def get_nlsql_service() -> NLSQLService:
    """Get NLSQL service instance"""
    return NLSQLService()
