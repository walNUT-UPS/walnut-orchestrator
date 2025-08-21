from datetime import datetime
from typing import List, Optional, Dict, Any
from enum import Enum

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import desc, and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from walnut.auth.deps import current_active_user
from walnut.auth.models import User
from walnut.database.connection import get_db_session_dependency
import anyio
from walnut.database.models import LegacyEvent


router = APIRouter()


class SeverityLevel(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class EventCreate(BaseModel):
    event_type: str = Field(..., min_length=1, max_length=100, description="Event type identifier")
    description: str = Field(..., min_length=1, description="Human-readable event description")
    severity: SeverityLevel = Field(..., description="Event severity level")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Optional event metadata")


class EventResponse(BaseModel):
    id: int
    timestamp: datetime
    event_type: str
    description: str
    severity: str
    metadata: Optional[Dict[str, Any]]
    
    class Config:
        from_attributes = True


class EventStats(BaseModel):
    total_count: int
    info_count: int
    warning_count: int
    critical_count: int
    recent_activity: List[Dict[str, Any]]


class SeverityColor(BaseModel):
    severity: str
    color: str
    text_color: str


def get_severity_colors() -> List[SeverityColor]:
    """Get color coding hints for severity levels"""
    return [
        SeverityColor(severity="INFO", color="#10b981", text_color="#ffffff"),
        SeverityColor(severity="WARNING", color="#f59e0b", text_color="#ffffff"),  
        SeverityColor(severity="CRITICAL", color="#ef4444", text_color="#ffffff")
    ]


@router.get("/events", response_model=List[EventResponse])
async def get_events(
    limit: int = Query(50, ge=1, le=1000, description="Number of events to return"),
    severity: Optional[SeverityLevel] = Query(None, description="Filter by severity level"),
    since: Optional[datetime] = Query(None, description="Filter events since this ISO8601 timestamp"),
    db: AsyncSession = Depends(get_db_session_dependency),
    current_user: User = Depends(current_active_user)
):
    """
    Get event timeline with optional filtering.
    
    Returns events sorted by timestamp descending (most recent first).
    Supports filtering by severity level and date range.
    """
    query = select(LegacyEvent)
    
    # Apply filters
    conditions = []
    if severity:
        conditions.append(LegacyEvent.severity == severity.value)
    if since:
        conditions.append(LegacyEvent.timestamp >= since)
    
    if conditions:
        query = query.where(and_(*conditions))
    
    # Sort by timestamp descending and limit
    query = query.order_by(desc(LegacyEvent.timestamp)).limit(limit)
    
    result = await anyio.to_thread.run_sync(db.execute, query)
    events = await anyio.to_thread.run_sync(result.scalars().all)
    
    return [EventResponse.model_validate(event) for event in events]


@router.post(
    "/events",
    response_model=EventResponse,
    status_code=status.HTTP_201_CREATED,
    responses={500: {"description": "Failed to create the event due to an internal error."}},
)
async def create_event(
    event: EventCreate,
    db: AsyncSession = Depends(get_db_session_dependency),
    current_user: User = Depends(current_active_user)
):
    """
    Create a manual event entry.
    
    Useful for testing or manual event logging.
    """
    try:
        # Create new event
        db_event = LegacyEvent(
            event_type=event.event_type,
            description=event.description,
            severity=event.severity.value,
            event_metadata=event.metadata
        )
        
        db.add(db_event)
        await db.commit()
        await db.refresh(db_event)
        
        return EventResponse.model_validate(db_event)
        
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create event: {str(e)}"
        )


@router.get(
    "/events/stats",
    response_model=EventStats,
    responses={500: {"description": "Failed to retrieve event statistics due to an internal error."}},
)
async def get_event_stats(
    days: int = Query(7, ge=1, le=365, description="Number of days to include in statistics"),
    db: AsyncSession = Depends(get_db_session_dependency),
    current_user: User = Depends(current_active_user)
):
    """
    Get event statistics including count by severity and recent activity.
    """
    try:
        # Calculate date threshold
        since_date = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        since_date = since_date.replace(day=since_date.day - days + 1)
        
        # Get total count
        total_query = select(func.count(LegacyEvent.id)).where(
            LegacyEvent.timestamp >= since_date
        )
        total_result = await db.execute(total_query)
        total_count = total_result.scalar() or 0
        
        # Get counts by severity
        severity_counts = {}
        for severity in ["INFO", "WARNING", "CRITICAL"]:
            count_query = select(func.count(LegacyEvent.id)).where(
                and_(
                    LegacyEvent.timestamp >= since_date,
                    LegacyEvent.severity == severity
                )
            )
            count_result = await db.execute(count_query)
            severity_counts[severity.lower() + "_count"] = count_result.scalar() or 0
        
        # Get recent activity (last 24 hours, grouped by hour)
        recent_query = select(
            func.strftime('%H', LegacyEvent.timestamp).label('hour'),
            func.count(LegacyEvent.id).label('count'),
            LegacyEvent.severity
        ).where(
            LegacyEvent.timestamp >= datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        ).group_by('hour', LegacyEvent.severity).order_by('hour')
        
        recent_results = await db.execute(recent_query)
        recent_activity = []
        for row in recent_results:
            recent_activity.append({
                "hour": int(row.hour),
                "count": row.count,
                "severity": row.severity
            })
        
        return EventStats(
            total_count=total_count,
            **severity_counts,
            recent_activity=recent_activity
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get event statistics: {str(e)}"
        )


@router.get("/events/severity-colors", response_model=List[SeverityColor])
async def get_severity_color_hints(
    current_user: User = Depends(current_active_user)
):
    """
    Get severity color coding hints for frontend display.
    """
    return get_severity_colors()
