from datetime import datetime, timezone, timedelta
from typing import Optional, List, Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, desc, func
import anyio

from walnut.auth.deps import current_active_user
from walnut.auth.models import User
from walnut.database.connection import get_db_session
from walnut.database.models import UPSSample

router = APIRouter()


class UPSStatusResponse(BaseModel):
    timestamp: datetime
    battery_percent: Optional[float] = Field(None, description="Battery charge percentage (0-100)")
    runtime_seconds: Optional[int] = Field(None, description="Estimated runtime in seconds")
    load_percent: Optional[float] = Field(None, description="UPS load percentage (0-100)")
    input_voltage: Optional[float] = Field(None, description="Input voltage from mains")
    output_voltage: Optional[float] = Field(None, description="Output voltage to devices")
    status: Optional[str] = Field(None, description="UPS status string")


class UPSHealthSummary(BaseModel):
    period_hours: int = Field(description="Time period covered in hours")
    avg_battery: Optional[float] = Field(None, description="Average battery charge percentage")
    min_battery: Optional[float] = Field(None, description="Minimum battery charge percentage")
    max_battery: Optional[float] = Field(None, description="Maximum battery charge percentage")
    time_on_battery_seconds: Optional[int] = Field(None, description="Total time on battery power")
    samples_count: int = Field(description="Number of samples in this period")
    last_updated: datetime = Field(description="Timestamp of most recent sample")


class UPSSamplesResponse(BaseModel):
    samples: List[UPSStatusResponse]
    total_count: int
    limit: int
    offset: int
    has_more: bool


@router.get(
    "/ups/status",
    response_model=UPSStatusResponse,
    summary="Get current UPS status",
    responses={
        404: {"description": "No UPS data is available in the database."},
        500: {"description": "An internal error occurred while retrieving the status."},
    },
)
async def get_ups_status(
    user: User = Depends(current_active_user),
    session = Depends(get_db_session)
) -> UPSStatusResponse:
    """
    Get the most recent UPS status data.
    
    Returns the latest sample with battery charge, runtime, load, voltages, and status.
    Requires authentication.
    """
    try:
        # Get the most recent UPS sample
        stmt = select(UPSSample).order_by(desc(UPSSample.timestamp)).limit(1)
        result = await anyio.to_thread.run_sync(session.execute, stmt)
        sample = await anyio.to_thread.run_sync(result.scalar_one_or_none)
        
        if sample is None:
            raise HTTPException(
                status_code=404, 
                detail="No UPS data available"
            )
        
        return UPSStatusResponse(
            timestamp=sample.timestamp,
            battery_percent=sample.charge_percent,
            runtime_seconds=sample.runtime_seconds,
            load_percent=sample.load_percent,
            input_voltage=sample.input_voltage,
            output_voltage=sample.output_voltage,
            status=sample.status
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve UPS status: {str(e)}"
        )


@router.get(
    "/ups/samples",
    response_model=UPSSamplesResponse,
    summary="Get historical UPS samples",
    responses={500: {"description": "An internal error occurred while retrieving samples."}},
)
async def get_ups_samples(
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of samples to return"),
    offset: int = Query(0, ge=0, description="Number of samples to skip"),
    since: Optional[datetime] = Query(None, description="Return samples since this timestamp (ISO 8601)"),
    user: User = Depends(current_active_user),
    session = Depends(get_db_session)
) -> UPSSamplesResponse:
    """
    Get historical UPS samples with pagination.
    
    Supports filtering by timestamp and pagination. Results are ordered by timestamp descending (newest first).
    Requires authentication.
    """
    try:
        # Build base query
        query = select(UPSSample)
        
        # Apply time filter if provided
        if since:
            query = query.where(UPSSample.timestamp >= since)
        
        # Get total count for pagination info
        count_query = select(func.count(UPSSample.id))
        if since:
            count_query = count_query.where(UPSSample.timestamp >= since)
        
        total_count_result = await anyio.to_thread.run_sync(session.execute, count_query)
        total_count = await anyio.to_thread.run_sync(total_count_result.scalar)
        
        # Apply ordering, limit, and offset
        query = query.order_by(desc(UPSSample.timestamp)).limit(limit).offset(offset)
        
        # Execute query
        result = await anyio.to_thread.run_sync(session.execute, query)
        samples = await anyio.to_thread.run_sync(result.scalars().all)
        
        # Convert to response format
        sample_responses = [
            UPSStatusResponse(
                timestamp=sample.timestamp,
                battery_percent=sample.charge_percent,
                runtime_seconds=sample.runtime_seconds,
                load_percent=sample.load_percent,
                input_voltage=sample.input_voltage,
                output_voltage=sample.output_voltage,
                status=sample.status
            )
            for sample in samples
        ]
        
        return UPSSamplesResponse(
            samples=sample_responses,
            total_count=total_count,
            limit=limit,
            offset=offset,
            has_more=offset + len(samples) < total_count
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve UPS samples: {str(e)}"
        )


@router.get(
    "/ups/health",
    response_model=UPSHealthSummary,
    summary="Get 24-hour UPS health summary",
    responses={
        404: {"description": "No UPS data is available for the requested time period."},
        500: {"description": "An internal error occurred while calculating the health summary."},
    },
)
async def get_ups_health(
    hours: int = Query(24, ge=1, le=168, description="Number of hours to include in health summary"),
    user: User = Depends(current_active_user),
    session = Depends(get_db_session)
) -> UPSHealthSummary:
    """
    Get UPS health summary for the specified time period.
    
    Returns battery statistics, time on battery, and sample counts for health monitoring.
    Defaults to 24 hours but can be configured up to 168 hours (1 week).
    Requires authentication.
    """
    try:
        # Calculate time window
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(hours=hours)
        
        # Query samples in time window
        query = select(UPSSample).where(
            UPSSample.timestamp >= start_time,
            UPSSample.timestamp <= end_time
        )
        
        result = await anyio.to_thread.run_sync(session.execute, query)
        samples = await anyio.to_thread.run_sync(result.scalars().all)
        
        if not samples:
            raise HTTPException(
                status_code=404,
                detail=f"No UPS data available for the last {hours} hours"
            )
        
        # Calculate battery statistics
        battery_values = [s.charge_percent for s in samples if s.charge_percent is not None]
        
        avg_battery = sum(battery_values) / len(battery_values) if battery_values else None
        min_battery = min(battery_values) if battery_values else None
        max_battery = max(battery_values) if battery_values else None
        
        # Estimate time on battery by counting samples with status indicating battery power
        # Common NUT status values that indicate battery operation: "OB" (On Battery), "LB" (Low Battery)
        battery_samples = [
            s for s in samples 
            if s.status and ("OB" in s.status or "LB" in s.status)
        ]
        
        # Estimate time on battery (assuming samples are taken every ~30 seconds)
        # This is a rough estimate - in a production system you might track power events more precisely
        time_on_battery_seconds = len(battery_samples) * 30 if battery_samples else 0
        
        # Get the most recent sample timestamp
        latest_sample = max(samples, key=lambda s: s.timestamp)
        
        return UPSHealthSummary(
            period_hours=hours,
            avg_battery=round(avg_battery, 2) if avg_battery else None,
            min_battery=round(min_battery, 2) if min_battery else None,
            max_battery=round(max_battery, 2) if max_battery else None,
            time_on_battery_seconds=time_on_battery_seconds,
            samples_count=len(samples),
            last_updated=latest_sample.timestamp
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve UPS health summary: {str(e)}"
        )