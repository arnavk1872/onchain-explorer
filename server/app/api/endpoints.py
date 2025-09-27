from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, field_validator
from typing import Dict, Any, Optional, List
from datetime import datetime
import json
from app.db import test_connection
# LangGraph imports removed due to circular import issues
from app.logger import get_logger
from app.services.retrieval import get_retrieval_service, SearchFilters, SearchResult
from app.services.nlsql import get_nlsql_service, SQLSecurityError
from app.services.orchestration import get_orchestration_service

logger = get_logger(__name__)

router = APIRouter()


class QueryRequest(BaseModel):
    query: str
    user_id: Optional[str] = None


class QueryResponse(BaseModel):
    response: str
    sql_query: Optional[str] = None
    results: Optional[list] = None
    metadata: Dict[str, Any] = {}


class SearchFiltersRequest(BaseModel):
    """Search filters with proper validation"""
    network: Optional[str] = None
    proposal_type: Optional[str] = None
    status: Optional[str] = None
    min_amount: Optional[float] = None
    max_amount: Optional[float] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None

class SearchRequest(BaseModel):
    query: str
    filters: Optional[SearchFiltersRequest] = None
    top_k: int = 10
    use_rerank: bool = True
    
    @field_validator('query')
    @classmethod
    def validate_query(cls, v):
        if not v or not v.strip():
            raise ValueError('Query cannot be empty')
        return v.strip()
    
    @field_validator('top_k')
    @classmethod
    def validate_top_k(cls, v):
        if v <= 0:
            raise ValueError('top_k must be positive')
        return v


class SearchResponse(BaseModel):
    results: List[SearchResult]
    total_found: int
    query: str
    filters_applied: Optional[Dict[str, Any]] = None


class NLSQLRequest(BaseModel):
    user_query: str
    schema_hint: Optional[str] = None


class NLSQLResponse(BaseModel):
    count: Optional[int] = None
    examples: Optional[List[Dict[str, Any]]] = None
    plan: str
    sql: str
    error: Optional[str] = None




@router.post("/query", response_model=QueryResponse)
async def process_query(request: QueryRequest):
    """Process query using orchestration service"""
    try:
        logger.info(f"Processing query: {request.query}")
        
        # Get orchestration service
        orchestration_service = get_orchestration_service()
        
        # Collect all events from the stream
        events = []
        async for event in orchestration_service.run_graph(request.query):
            events.append(event)
        
        # Extract final answer and metadata
        final_event = next((e for e in events if e["stage"] == "final_answer"), None)
        sql_event = next((e for e in events if e["stage"] == "sql_result"), None)
        retrieval_event = next((e for e in events if e["stage"] == "retrieval_hits"), None)
        
        # Build response
        response_data = {
            "response": final_event["payload"]["answer"] if final_event else "No response generated",
            "sql_query": sql_event["payload"]["sql"] if sql_event else None,
            "results": retrieval_event["payload"]["hits"] if retrieval_event else None,
            "count": retrieval_event["payload"]["count"] if retrieval_event else 0,
            "metadata": final_event["payload"]["metadata"] if final_event else {}
        }
        
        logger.info(f"Query processed successfully: {response_data['metadata'].get('processing_type', 'unknown')}")
        return QueryResponse(**response_data)
        
    except Exception as e:
        logger.error(f"Query processing failed: {str(e)}")
        raise HTTPException(
            status_code=500, 
            detail=f"Query processing failed: {str(e)}"
        )


@router.post("/search", response_model=SearchResponse)
async def search_proposals(request: SearchRequest):
    """Search proposals using hybrid search with RRF fusion and optional reranking"""
    try:
        logger.info(f"Search request: query='{request.query}', filters={request.filters}, top_k={request.top_k}")
        
        # Convert validated filters to SearchFilters
        search_filters = None
        if request.filters:
            # Map frontend proposal types to database types
            proposal_type_mapping = {
                'treasury': 'TreasuryProposal',
                'democracy': 'DemocracyProposal', 
                'referendum': 'Referendum',
                'bounty': 'Bounty',
                'tip': 'Tip',
                'council': 'CouncilMotion',
                'tech': 'TechCommitteeProposal'
            }
            
            mapped_proposal_type = request.filters.proposal_type
            if request.filters.proposal_type and request.filters.proposal_type.lower() in proposal_type_mapping:
                mapped_proposal_type = proposal_type_mapping[request.filters.proposal_type.lower()]
            
            search_filters = SearchFilters(
                network=request.filters.network,
                proposal_type=mapped_proposal_type,
                status=request.filters.status,
                min_amount=request.filters.min_amount,
                max_amount=request.filters.max_amount,
                start_date=request.filters.start_date,
                end_date=request.filters.end_date
            )
        
        # Get retrieval service and search
        retrieval_service = get_retrieval_service()
        results = await retrieval_service.search_proposals(
            query=request.query,
            filters=search_filters,
            top_k=request.top_k,
            use_rerank=request.use_rerank
        )
        
        logger.info(f"Search completed: found {len(results)} results")
        
        return SearchResponse(
            results=results,
            total_found=len(results),
            query=request.query,
            filters_applied=request.filters.model_dump() if request.filters else None
        )
        
    except Exception as e:
        logger.error(f"Search failed: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Search failed: {str(e)}"
        )


@router.post("/nlsql", response_model=NLSQLResponse)
async def process_nlsql(request: NLSQLRequest):
    """Convert natural language to SQL with security validation and execute"""
    try:
        logger.info(f"Processing NLSQL query: {request.user_query}")
        
        # Get NLSQL service
        nlsql_service = get_nlsql_service()
        
        # Execute the natural language query
        result = await nlsql_service.execute_nlsql(
            user_query=request.user_query,
            schema_hint=request.schema_hint or ""
        )
        
        logger.info(f"NLSQL executed successfully: {result['plan']}")
        
        return NLSQLResponse(
            count=result.get("count"),
            examples=result.get("examples"),
            plan=result["plan"],
            sql=result["sql"]
        )
        
    except SQLSecurityError as e:
        logger.warning(f"NLSQL security error: {str(e)}")
        return NLSQLResponse(
            plan="",
            sql="",
            error=f"Security error: {str(e)}"
        )
        
    except Exception as e:
        logger.error(f"NLSQL processing failed: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"NLSQL processing failed: {str(e)}"
        )


@router.post("/query/stream")
async def process_query_stream(request: QueryRequest):
    """Process query using orchestration service with streaming response"""
    
    async def generate_stream():
        try:
            logger.info(f"Processing streaming query: {request.query}")
            
            # Get orchestration service
            orchestration_service = get_orchestration_service()
            
            # Stream events
            async for event in orchestration_service.run_graph(request.query):
                # Format as Server-Sent Events
                event_data = json.dumps(event, default=str)
                yield f"data: {event_data}\n\n"
            
            # Send end event
            yield "data: [DONE]\n\n"
            
        except Exception as e:
            logger.error(f"Streaming query failed: {str(e)}")
            error_event = {
                "stage": "error",
                "payload": {
                    "error": str(e),
                    "message": "Failed to process query"
                }
            }
            yield f"data: {json.dumps(error_event)}\n\n"
            yield "data: [DONE]\n\n"
    
    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type"
        }
    )


@router.post("/query/stream-raw")
async def process_query_stream_raw(request: Request):
    """Process query using orchestration service with streaming response (raw JSON)"""
    
    async def generate_stream():
        try:
            # Parse raw JSON from request body
            body = await request.json()
            query = body.get("query", "")
            
            if not query:
                error_event = {
                    "stage": "error",
                    "payload": {
                        "error": "Missing query parameter",
                        "message": "Query parameter is required"
                    }
                }
                yield f"data: {json.dumps(error_event)}\n\n"
                yield "data: [DONE]\n\n"
                return
            
            logger.info(f"Processing streaming query: {query}")
            
            # Get orchestration service
            orchestration_service = get_orchestration_service()
            
            # Stream events
            async for event in orchestration_service.run_graph(query):
                # Format as Server-Sent Events
                event_data = json.dumps(event, default=str)
                yield f"data: {event_data}\n\n"
            
            # Send end event
            yield "data: [DONE]\n\n"
            
        except Exception as e:
            logger.error(f"Streaming query failed: {str(e)}")
            error_event = {
                "stage": "error",
                "payload": {
                    "error": str(e),
                    "message": "Failed to process query"
                }
            }
            yield f"data: {json.dumps(error_event)}\n\n"
            yield "data: [DONE]\n\n"
    
    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type"
        }
    )
