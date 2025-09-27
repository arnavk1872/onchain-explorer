"""
Orchestration service that wires together existing services with LangGraph
Provides streaming responses for query processing
"""
import asyncio
import time
from typing import Dict, Any, List, Generator, Optional
from dataclasses import dataclass, field
try:
    from langgraph.graph import StateGraph, END
except ImportError:
    # Fallback for when langgraph is not available
    StateGraph = None
    END = "END"
from app.logger import get_logger
from app.services.nlsql import get_nlsql_service, SQLSecurityError
from app.services.retrieval import get_retrieval_service, SearchFilters

logger = get_logger(__name__)


@dataclass
class OrchestrationState:
    """State for the orchestration workflow"""
    query: str
    route_decision: str = ""
    sql_query: str = ""
    sql_result: Optional[Dict[str, Any]] = None
    retrieval_hits: List[Dict[str, Any]] = field(default_factory=list)
    reranked_results: List[Dict[str, Any]] = field(default_factory=list)
    final_answer: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    processing_times: Dict[str, float] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for LangGraph compatibility"""
        return {
            "query": self.query,
            "route_decision": self.route_decision,
            "sql_query": self.sql_query,
            "sql_result": self.sql_result,
            "retrieval_hits": self.retrieval_hits,
            "reranked_results": self.reranked_results,
            "final_answer": self.final_answer,
            "metadata": self.metadata,
            "processing_times": self.processing_times
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'OrchestrationState':
        """Create from dict for LangGraph compatibility"""
        return cls(
            query=data.get("query", ""),
            route_decision=data.get("route_decision", ""),
            sql_query=data.get("sql_query", ""),
            sql_result=data.get("sql_result"),
            retrieval_hits=data.get("retrieval_hits", []),
            reranked_results=data.get("reranked_results", []),
            final_answer=data.get("final_answer", ""),
            metadata=data.get("metadata", {}),
            processing_times=data.get("processing_times", {})
        )


class OrchestrationService:
    """Orchestration service that coordinates different processing paths"""
    
    def __init__(self):
        self.nlsql_service = get_nlsql_service()
        self.retrieval_service = get_retrieval_service()
        self.graph = self._create_graph()
    
    def _create_graph(self):
        """Create the LangGraph workflow"""
        if StateGraph is None:
            logger.warning("LangGraph not available, using fallback implementation")
            return None
        
        workflow = StateGraph(dict)
        
        # Add nodes
        workflow.add_node("router", self._router_node)
        workflow.add_node("sql_agent", self._sql_agent_node)
        workflow.add_node("retrieval_agent", self._retrieval_agent_node)
        workflow.add_node("rerank_node", self._rerank_node)
        workflow.add_node("composer", self._composer_node)
        
        # Add conditional edges from router
        workflow.add_conditional_edges(
            "router",
            self._route_decision,
            {
                "sql_agent": "sql_agent",
                "retrieval_agent": "retrieval_agent",
                "composer": "composer"
            }
        )
        
        # Add edges from processing nodes
        workflow.add_edge("sql_agent", "rerank_node")
        workflow.add_edge("retrieval_agent", "rerank_node")
        workflow.add_edge("rerank_node", "composer")
        workflow.add_edge("composer", END)
        
        # Set entry point
        workflow.set_entry_point("router")
        
        # Compile the graph
        return workflow.compile()
    
    def _route_decision(self, state: Dict[str, Any]) -> str:
        """Determine the route based on query analysis"""
        return state.get("route_decision", "composer")
    
    async def _router_node(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Route the query to appropriate processing path using intelligent analysis"""
        start_time = time.time()
        query = state.get("query", "")
        logger.info(f"Routing query: {query}")
        
        query_lower = query.lower()
        route_decision = self._analyze_query_intent(query, query_lower)
        
        # Update state
        state["route_decision"] = route_decision
        state["processing_times"] = state.get("processing_times", {})
        state["processing_times"]["router"] = time.time() - start_time
        
        return state
    
    def _analyze_query_intent(self, query: str, query_lower: str) -> str:
        """Analyze query intent to determine the best processing path"""
        
        # 1. EXACT LOOKUPS - Use SQL agent for precise data retrieval
        if self._is_exact_lookup(query, query_lower):
            logger.info("Route decision: SQL agent (exact lookup)")
            return "sql_agent"
        
        # 2. MIXED QUERIES - Use SQL agent if it can handle both parts (check before analytical)
        if self._is_mixed_query(query_lower):
            logger.info("Route decision: SQL agent (mixed analytical + examples query)")
            return "sql_agent"
        
        # 3. ANALYTICAL QUERIES - Use SQL agent for aggregations and statistics
        if self._is_analytical_query(query_lower):
            logger.info("Route decision: SQL agent (analytical query)")
            return "sql_agent"
        
        # 4. DATE/TIME FILTERED QUERIES - Use SQL agent for structured filtering
        if self._is_date_filtered_query(query_lower):
            logger.info("Route decision: SQL agent (date-filtered query)")
            return "sql_agent"
        
        # 5. FILTERED QUERIES - Use SQL agent for structured filtering by type/network
        if self._is_filtered_query(query_lower):
            logger.info("Route decision: SQL agent (filtered query)")
            return "sql_agent"
        
        # 6. SEMANTIC SEARCH QUERIES - Use retrieval agent for fuzzy matching
        if self._is_semantic_search_query(query_lower):
            logger.info("Route decision: Retrieval agent (semantic search)")
            return "retrieval_agent"
        
        # 7. DEFAULT - Use composer for general queries
        logger.info("Route decision: Composer (general query)")
        return "composer"
    
    def _is_exact_lookup(self, query: str, query_lower: str) -> bool:
        """Check if query is asking for exact data lookup"""
        # Specific ID patterns
        id_patterns = [
            "proposal with id", "proposal id", "id is", "id =", "id:", 
            "proposal #", "proposal number", "specific proposal", "details of proposal"
        ]
        
        # Check for ID patterns
        if any(pattern in query_lower for pattern in id_patterns):
            return True
        
        # Check for proposal + number pattern (e.g., "proposal 123456")
        if "proposal" in query_lower and any(char.isdigit() for char in query):
            return True
        
        # Check for specific entity lookups that are likely exact
        if any(phrase in query_lower for phrase in [
            "give me the details", "show me the details", "get the details"
        ]):
            return True
        
        return False
    
    def _is_analytical_query(self, query_lower: str) -> bool:
        """Check if query is asking for analytical/statistical data"""
        analytical_keywords = [
            "how many", "count", "total", "number of", "amount", "amounts",
            "highest", "lowest", "average", "sum", "statistics",
            "most", "least", "maximum", "minimum", "show me proposal amounts"
        ]
        
        return any(keyword in query_lower for keyword in analytical_keywords)
    
    def _is_date_filtered_query(self, query_lower: str) -> bool:
        """Check if query involves date/time filtering"""
        date_keywords = [
            "recent", "after", "before", "between", "since", "until",
            "january", "february", "march", "april", "may", "june",
            "july", "august", "september", "october", "november", "december",
            "jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec",
            "2024", "2025", "2026", "2027", "2028", "2029", "2030"
        ]
        
        # Check for date patterns
        if any(keyword in query_lower for keyword in date_keywords):
            return True
        
        # Check for date format patterns (YYYY-MM-DD, MM/DD/YYYY, etc.)
        import re
        date_patterns = [
            r'\d{4}-\d{2}-\d{2}',  # YYYY-MM-DD
            r'\d{2}/\d{2}/\d{4}',  # MM/DD/YYYY
            r'\d{4}/\d{2}/\d{2}',  # YYYY/MM/DD
            r'\d{1,2}/\d{1,2}/\d{4}',  # M/D/YYYY or MM/DD/YYYY
        ]
        
        for pattern in date_patterns:
            if re.search(pattern, query_lower):
                return True
        
        return False
    
    def _is_mixed_query(self, query_lower: str) -> bool:
        """Check if query combines analytical and example requests"""
        # Queries that ask for both count/examples
        mixed_patterns = [
            "how many", "count", "total"
        ]
        
        example_patterns = [
            "show some", "name a few", "give examples", "show examples", 
            "and show", "and name", "and give", "and show some", "and name a few"
        ]
        
        has_analytical = any(pattern in query_lower for pattern in mixed_patterns)
        has_examples = any(pattern in query_lower for pattern in example_patterns)
        
        return has_analytical and has_examples
    
    def _is_filtered_query(self, query_lower: str) -> bool:
        """Check if query is asking for filtered results by structured criteria"""
        # Network filters
        network_filters = ["kusama", "polkadot", "westend", "rococo"]
        
        # Proposal type filters  
        type_filters = ["treasury", "council", "referendum", "bounty", "tip", "motion"]
        
        # Check for network filtering
        has_network_filter = any(network in query_lower for network in network_filters)
        
        # Check for type filtering
        has_type_filter = any(prop_type in query_lower for prop_type in type_filters)
        
        # Check for general filtering patterns
        filter_patterns = [
            "find", "what", "show me", "get", "list", "all"
        ]
        
        has_filter_pattern = any(pattern in query_lower for pattern in filter_patterns)
        
        # This is a filtered query if it has filtering criteria and patterns
        return (has_network_filter or has_type_filter) and has_filter_pattern
    
    def _is_semantic_search_query(self, query_lower: str) -> bool:
        """Check if query requires semantic search for fuzzy matching"""
        # General search patterns
        search_patterns = [
            "find", "search", "show me", "tell me about", "what", "which",
            "get", "look for", "discover"
        ]
        
        # Specific entity names that require semantic search
        entity_names = [
            "clarys", "subsquare", "polkadot", "kusama", "treasury", 
            "council", "referendum", "bounty", "tip"
        ]
        
        # Check for search patterns
        has_search_pattern = any(pattern in query_lower for pattern in search_patterns)
        
        # Check for entity names
        has_entity = any(entity in query_lower for entity in entity_names)
        
        # Check for general proposal queries without specific criteria
        is_general_proposal_query = (
            "proposal" in query_lower and 
            not any(char.isdigit() for char in query_lower) and
            not any(keyword in query_lower for keyword in ["how many", "count", "total", "amount"])
        )
        
        return has_search_pattern or has_entity or is_general_proposal_query
    
    async def _sql_agent_node(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Process query using NLSQL service"""
        start_time = time.time()
        query = state.get("query", "")
        logger.info("Processing with SQL agent")
        
        try:
            result = await self.nlsql_service.execute_nlsql(query)
            state["sql_query"] = result.get("sql", "")
            state["sql_result"] = result
            state["metadata"] = state.get("metadata", {})
            state["metadata"]["sql_plan"] = result.get("plan", "")
            logger.info(f"SQL agent completed: {result.get('count', 0)} results")
        except SQLSecurityError as e:
            logger.warning(f"SQL security error: {e}")
            state["sql_result"] = {"error": str(e), "count": 0, "examples": []}
        except Exception as e:
            logger.error(f"SQL agent failed: {e}")
            state["sql_result"] = {"error": str(e), "count": 0, "examples": []}
        
        state["processing_times"] = state.get("processing_times", {})
        state["processing_times"]["sql_agent"] = time.time() - start_time
        return state
    
    async def _retrieval_agent_node(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Process query using retrieval service"""
        start_time = time.time()
        query = state.get("query", "")
        logger.info("Processing with retrieval agent")
        
        try:
            results = await self.retrieval_service.search_proposals(
                query=query,
                top_k=10,
                use_rerank=True
            )
            state["retrieval_hits"] = [result.__dict__ for result in results]
            logger.info(f"Retrieval agent completed: {len(results)} results")
        except Exception as e:
            logger.error(f"Retrieval agent failed: {e}")
            state["retrieval_hits"] = []
        
        state["processing_times"] = state.get("processing_times", {})
        state["processing_times"]["retrieval_agent"] = time.time() - start_time
        return state
    
    async def _rerank_node(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Rerank results from either SQL or retrieval"""
        start_time = time.time()
        logger.info("Reranking results")
        
        sql_result = state.get("sql_result")
        retrieval_hits = state.get("retrieval_hits", [])
        
        if sql_result and not sql_result.get("error"):
            # Use SQL results as reranked results
            state["reranked_results"] = sql_result.get("examples", [])
        elif retrieval_hits:
            # Use retrieval results as reranked results
            state["reranked_results"] = retrieval_hits
        else:
            state["reranked_results"] = []
        
        state["processing_times"] = state.get("processing_times", {})
        state["processing_times"]["rerank"] = time.time() - start_time
        return state
    
    async def _composer_node(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Compose final answer from results"""
        start_time = time.time()
        logger.info("Composing final answer")
        
        route_decision = state.get("route_decision", "composer")
        sql_result = state.get("sql_result")
        reranked_results = state.get("reranked_results", [])
        
        if route_decision == "sql_agent" and sql_result:
            # Compose answer from SQL results
            count = sql_result.get("count", 0)
            examples = sql_result.get("examples", [])
            
            if count > 0:
                final_answer = f"Found {count} proposals"
                if examples:
                    final_answer += f". Here are some examples:\n\n"
                    for i, example in enumerate(examples[:5], 1):
                        title = example.get("title", "Untitled")
                        proposal_type = example.get("type", "Unknown")
                        network = example.get("network", "Unknown")
                        created_at = example.get("created_at", "Unknown")
                        proposal_id = example.get("id", "N/A")
                        proposer = example.get("proposer", "Unknown")
                        status = example.get("status", "Unknown")
                        description = example.get("description", "No description available")
                        amount = example.get("amount_numeric")
                        
                        final_answer += f"## Proposal {i}: {title}\n"
                        final_answer += f"**ID:** {proposal_id}\n"
                        final_answer += f"**Type:** {proposal_type}\n"
                        final_answer += f"**Network:** {network}\n"
                        final_answer += f"**Proposer:** {proposer}\n"
                        final_answer += f"**Status:** {status}\n"
                        final_answer += f"**Created:** {created_at}\n"
                        if amount:
                            final_answer += f"**Amount:** {amount}\n"
                        final_answer += f"**Description:** {description[:200]}{'...' if len(description) > 200 else ''}\n\n"
                state["final_answer"] = final_answer
            else:
                state["final_answer"] = "No proposals found matching your criteria."
                
        elif route_decision == "retrieval_agent" and reranked_results:
            # Much stricter filtering - only show results with meaningful relevance
            relevant_results = [r for r in reranked_results if r.get("score", 0.0) >= 0.015]
            
            # If still too many results, take only the top 3-5 most relevant
            if len(relevant_results) > 5:
                relevant_results = relevant_results[:5]
            
            # If no results meet threshold, show only top 2 most relevant
            if not relevant_results:
                relevant_results = reranked_results[:2]
            
            count = len(relevant_results)
            final_answer = f"Found {count} relevant proposals:\n\n"
            
            for i, result in enumerate(relevant_results, 1):
                title = result.get("title") or "Untitled"
                proposal_type = result.get("type") or "Unknown"
                network = result.get("network") or "Unknown"
                created_at = result.get("created_at") or "Unknown"
                proposal_id = result.get("id") or "N/A"
                proposer = result.get("proposer") or "Unknown"
                status = result.get("status") or "Unknown"
                description = result.get("description") or "No description available"
                amount = result.get("amount") or result.get("amount_numeric")
                
                final_answer += f"## Proposal {i}: {title}\n"
                final_answer += f"**ID:** {proposal_id}\n"
                final_answer += f"**Type:** {proposal_type}\n"
                final_answer += f"**Network:** {network}\n"
                final_answer += f"**Proposer:** {proposer}\n"
                final_answer += f"**Status:** {status}\n"
                final_answer += f"**Created:** {created_at}\n"
                if amount:
                    final_answer += f"**Amount:** {amount}\n"
                final_answer += f"**Description:** {description[:200]}{'...' if len(description) > 200 else ''}\n\n"
            
            state["final_answer"] = final_answer
            state["proposals_for_descriptions"] = relevant_results
        else:
            state["final_answer"] = "I couldn't find any relevant information for your query."
        
        state["metadata"] = state.get("metadata", {})
        state["metadata"]["processing_type"] = route_decision
        state["processing_times"] = state.get("processing_times", {})
        state["processing_times"]["composer"] = time.time() - start_time
        return state
    
    async def run_graph(self, user_query: str) -> Generator[Dict[str, Any], None, None]:
        """Run the graph and yield streaming events"""
        logger.info(f"Starting orchestration for query: {user_query}")
        
        # Create initial state as dict
        state = {
            "query": user_query,
            "route_decision": "",
            "sql_query": "",
            "sql_result": None,
            "retrieval_hits": [],
            "reranked_results": [],
            "final_answer": "",
            "metadata": {},
            "processing_times": {}
        }
        
        try:
            if self.graph is None:
                # Fallback implementation without LangGraph
                result = await self._run_fallback_workflow(state)
            else:
                # Execute the graph
                result = await self.graph.ainvoke(state)
            
            # Yield events in sequence
            yield {
                "stage": "router_decision",
                "payload": {
                    "decision": result.get("route_decision", "unknown"),
                    "processing_time": result.get("processing_times", {}).get("router", 0)
                }
            }
            
            route_decision = result.get("route_decision", "unknown")
            if route_decision == "sql_agent":
                yield {
                    "stage": "sql_result",
                    "payload": {
                        "sql": result.get("sql_query", ""),
                        "count": result.get("sql_result", {}).get("count", 0) if result.get("sql_result") else 0,
                        "examples": result.get("sql_result", {}).get("examples", []) if result.get("sql_result") else [],
                        "processing_time": result.get("processing_times", {}).get("sql_agent", 0)
                    }
                }
            elif route_decision == "retrieval_agent":
                # Filter results for display with stricter criteria
                retrieval_hits = result.get("retrieval_hits", [])
                relevant_hits = [r for r in retrieval_hits if r.get("score", 0.0) >= 0.015]
                
                # Limit to max 5 results
                if len(relevant_hits) > 5:
                    relevant_hits = relevant_hits[:5]
                
                # If no results meet threshold, show only top 2
                if not relevant_hits:
                    relevant_hits = retrieval_hits[:2]
                
                yield {
                    "stage": "retrieval_hits",
                    "payload": {
                        "hits": relevant_hits,
                        "count": len(relevant_hits),
                        "processing_time": result.get("processing_times", {}).get("retrieval_agent", 0)
                    }
                }
            
            yield {
                "stage": "final_answer",
                "payload": {
                    "answer": result.get("final_answer", "No answer generated"),
                    "metadata": result.get("metadata", {}),
                    "processing_times": result.get("processing_times", {})
                }
            }
            
            # If we have proposals for descriptions, send them as a separate event
            if result.get("proposals_for_descriptions"):
                yield {
                    "stage": "proposal_descriptions",
                    "payload": {
                        "proposals": result.get("proposals_for_descriptions", [])
                    }
                }
            
            # Also send the proposals data for the frontend to parse
            if result.get("proposals_for_descriptions"):
                yield {
                    "stage": "proposals_data",
                    "payload": {
                        "proposals": result.get("proposals_for_descriptions", [])
                    }
                }
            
        except Exception as e:
            logger.error(f"Orchestration failed: {e}")
            yield {
                "stage": "error",
                "payload": {
                    "error": str(e),
                    "message": "Failed to process query"
                }
            }
    
    async def _run_fallback_workflow(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Fallback workflow implementation without LangGraph"""
        logger.info("Using fallback workflow implementation")
        
        # Run the workflow steps manually
        state = await self._router_node(state)
        
        if state.get("route_decision") == "sql_agent":
            state = await self._sql_agent_node(state)
        elif state.get("route_decision") == "retrieval_agent":
            state = await self._retrieval_agent_node(state)
        
        state = await self._rerank_node(state)
        state = await self._composer_node(state)
        
        return state


def get_orchestration_service() -> OrchestrationService:
    """Get orchestration service instance"""
    return OrchestrationService()
