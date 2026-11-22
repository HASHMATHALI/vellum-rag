import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import HealthResponse, SystemStatsResponse
from app.auth.dependencies import get_current_admin
from app.database.connection import get_db, set_rls_context
from app.models.document import DocumentChunk
from app.models.user import User
from app.services.admin_service import AdminService

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Admin & Monitoring"])


@router.get("/stats", response_model=SystemStatsResponse)
async def get_stats(current_user: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)):
    await set_rls_context(db, current_user.id, is_admin=True, system=True)  # aggregate counts only
    return await AdminService.get_system_stats(db)


@router.get("/health/live")
async def liveness():
    return {"status": "alive"}


@router.get("/health", response_model=HealthResponse)
async def get_health(db: AsyncSession = Depends(get_db)):
    """Readiness: database reachable and pgvector usable. Returns 503 when unhealthy."""
    services = {"database": "down", "vector_store": "down"}
    size = 0
    try:
        await db.execute(text("SELECT 1"))
        services["database"] = "healthy"
        await set_rls_context(db, None, system=True)
        size = (await db.execute(select(func.count(DocumentChunk.id)).where(DocumentChunk.embedding.isnot(None)))).scalar() or 0
        services["vector_store"] = "healthy"
    except Exception as e:  # report unhealthy instead of failing the probe
        logger.warning("Health check failed: %s", type(e).__name__)
    healthy = all(v == "healthy" for v in services.values())
    body = HealthResponse(status="healthy" if healthy else "unhealthy", timestamp=datetime.now(timezone.utc),
                          vector_store_size=size, services=services)
    return JSONResponse(body.model_dump(mode="json"), status_code=200 if healthy else 503)


@router.get("/logs")
async def get_logs(limit: int = Query(50, ge=1, le=500), current_user: User = Depends(get_current_admin)):
    return {"logs": await AdminService.get_system_logs(lines=limit)}
