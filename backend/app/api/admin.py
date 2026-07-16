from fastapi import APIRouter, Depends, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime
from app.database.connection import get_db
from app.api.schemas import SystemStatsResponse, HealthResponse
from app.services.admin_service import AdminService
from app.auth.dependencies import get_current_admin
from app.models.user import User

router = APIRouter(tags=["Admin & Monitoring"])

@router.get("/stats", response_model=SystemStatsResponse)
async def get_stats(
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Retrieves aggregated statistics and analytics for the admin dashboard."""
    stats = await AdminService.get_system_stats(db)
    return stats

@router.get("/health", response_model=HealthResponse)
async def get_health(db: AsyncSession = Depends(get_db)):
    """Health check endpoint monitoring DB connections and vector store status."""
    # Test DB connection
    db_status = "unhealthy"
    try:
        from sqlalchemy import text
        await db.execute(text("SELECT 1"))
        db_status = "healthy"
    except Exception:
        db_status = "down"

    # Vector store state (database pgvector count)
    vector_store_status = "healthy"
    vector_store_size = 0
    try:
        from app.models.document import DocumentChunk
        from sqlalchemy import func
        stmt = select(func.count(DocumentChunk.id)).where(DocumentChunk.embedding.isnot(None))
        res = await db.execute(stmt)
        vector_store_size = res.scalar() or 0
    except Exception:
        vector_store_status = "down"

    services = {
        "database": db_status,
        "vector_store": vector_store_status
    }
    
    overall_status = "healthy" if all(v == "healthy" for v in services.values()) else "unhealthy"

    return HealthResponse(
        status=overall_status,
        timestamp=datetime.utcnow(),
        vector_store_size=vector_store_size,
        services=services
    )

@router.get("/logs")
async def get_logs(
    limit: int = Query(50, ge=1, le=500),
    current_user: User = Depends(get_current_admin)
):
    """Admin-only endpoint to view the latest application logs."""
    logs = await AdminService.get_system_logs(lines=limit)
    return {"logs": logs}
