from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.endpoints import router as api_router
from app.routers.health import router as health_router
from app.logger import setup_logging
from app.db import init_db, close_pool

# Setup logging
setup_logging()

# Create FastAPI app
app = FastAPI(
    title="Onchain Explorer Server",
    description="Server with FastAPI and LangGraph for onchain data exploration",
    version="0.1.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health_router, prefix="/api/v1")
app.include_router(api_router, prefix="/api/v1")


@app.on_event("startup")
async def startup_event():
    """Initialize application on startup"""
    try:
        # Initialize database and run migrations
        if await init_db():
            print("✅ Server started successfully with database initialized")
        else:
            print("⚠️  Server started but database initialization failed")
    except Exception as e:
        print(f"❌ Failed to initialize server: {e}")
        raise


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    await close_pool()
    print("🔄 Server shutdown complete")


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "Onchain Explorer Server",
        "version": "0.1.0",
        "endpoints": {
            "health": "/api/v1/healthz",
            "dbcheck": "/api/v1/dbcheck",
            "query": "/api/v1/query"
        }
    }
