"""FastAPI application entry point."""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .routers import (
    agents_router,
    budget_router,
    chat_router,
    projects_router,
    tasks_router,
    workflow_router,
)
from .websocket import get_connection_manager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan handler."""
    settings = get_settings()
    logger.info(f"Starting Conductor Dashboard API on port {settings.port}")
    logger.info(f"Conductor root: {settings.conductor_root}")
    logger.info(f"Projects directory: {settings.projects_path}")

    yield

    logger.info("Shutting down Conductor Dashboard API")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title="Conductor Dashboard API",
        description="REST API for the Conductor multi-agent orchestration dashboard",
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
    )

    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include routers
    app.include_router(projects_router, prefix="/api")
    app.include_router(workflow_router, prefix="/api")
    app.include_router(tasks_router, prefix="/api")
    app.include_router(agents_router, prefix="/api")
    app.include_router(budget_router, prefix="/api")
    app.include_router(chat_router, prefix="/api")

    # WebSocket endpoint for project events
    @app.websocket("/api/projects/{project_name}/events")
    async def project_events(websocket: WebSocket, project_name: str):
        """WebSocket endpoint for real-time project events."""
        manager = get_connection_manager()
        await manager.connect(websocket, project_name)

        try:
            while True:
                # Keep connection alive, receive pings
                data = await websocket.receive_text()
                # Could handle client messages here if needed
        except WebSocketDisconnect:
            await manager.disconnect(websocket, project_name)

    # Health check endpoint
    @app.get("/health")
    async def health_check():
        """Health check endpoint."""
        manager = get_connection_manager()
        return {
            "status": "healthy",
            "websocket_connections": manager.connection_count,
        }

    # Root endpoint
    @app.get("/")
    async def root():
        """Root endpoint with API info."""
        return {
            "name": "Conductor Dashboard API",
            "version": "1.0.0",
            "docs": "/docs" if settings.debug else None,
        }

    return app


# Create app instance
app = create_app()


def run_server():
    """Run the development server."""
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "dashboard.backend.app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.reload,
        log_level="debug" if settings.debug else "info",
    )


if __name__ == "__main__":
    run_server()
