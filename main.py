"""Personal Knowledge Management System — FastAPI Main Entry."""

import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config import settings
from storage import db
from storage.vector_db import vector_db
from storage.graph_db import graph_db

# --- Logging ---
logging.basicConfig(
    level=logging.INFO if not settings.debug else logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# Suppress noisy third-party loggers
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("lark_oapi").setLevel(logging.WARNING)


# --- Lifespan ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    logger.info("=" * 50)
    logger.info("Personal Knowledge Management System starting...")
    logger.info(f"  Vector DB: {settings.vector_db_path}")
    logger.info(f"  Graph DB:  {settings.graph_db_path}")
    logger.info(f"  SQLite:    {settings.sqlite_path}")
    logger.info(f"  LLM:       {settings.deepseek_chat_model}")
    logger.info(f"  Embed:     {settings.deepseek_embed_model}")
    logger.info(f"  Feishu:    {'configured' if settings.feishu_app_id else 'not configured'}")

    stats = db.get_stats()
    logger.info(f"  Docs: {stats['documents']}, Entities: {stats['entities']}, Relations: {stats['relations']}")
    logger.info("=" * 50)
    yield
    logger.info("Shutting down...")


# --- App ---
app = FastAPI(
    title="Personal Knowledge Management System",
    description="AI-powered knowledge graph builder with Feishu interaction",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Routes ---
from api.collect import router as collect_router
from api.graph import router as graph_router
from api.qa import router as qa_router
from api.feishu import router as feishu_router
from api.review import router as review_router

app.include_router(collect_router)
app.include_router(graph_router)
app.include_router(qa_router)
app.include_router(feishu_router)
app.include_router(review_router)


# --- Root ---
@app.get("/")
async def root():
    return {
        "name": "Personal Knowledge Management System",
        "version": "1.0.0",
        "docs": "/docs",
        "endpoints": {
            "collection": "/api/collect/",
            "graph": "/api/graph/",
            "qa": "/api/qa/",
            "feishu": "/api/feishu/",
            "review": "/api/review/",
            "export": "/api/export",
            "health": "/api/health",
        },
    }


# --- Error handlers ---
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.error(f"Unhandled error: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"status": "error", "message": str(exc)},
    )


# --- Main ---
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level="info",
    )
