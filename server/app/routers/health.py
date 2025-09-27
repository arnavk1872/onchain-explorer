from fastapi import APIRouter, HTTPException
from app.db import test_connection
from app.logger import get_logger

logger = get_logger(__name__)

router = APIRouter()


@router.get("/healthz")
async def health_check():
    """Health check endpoint"""
    try:
        # Test database connection
        db_status = await test_connection()
        
        if db_status["status"] == "success":
            return {
                "status": "healthy",
                "database": "connected",
                "timestamp": "2024-01-01T00:00:00Z"
            }
        else:
            return {
                "status": "unhealthy",
                "database": "disconnected",
                "error": db_status["message"]
            }
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Health check failed")


@router.get("/dbcheck")
async def db_check():
    """Database check endpoint - runs SELECT 1 and returns ok"""
    try:
        from app.db import get_session
        
        async with get_session() as conn:
            result = await conn.fetchval("SELECT 1")
            
            if result == 1:
                return {
                    "status": "ok",
                    "message": "Database query successful",
                    "result": result
                }
            else:
                raise HTTPException(status_code=500, detail="Database query returned unexpected result")
                
    except Exception as e:
        logger.error(f"Database check failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Database check failed: {str(e)}")
