"""
Usage tracking endpoints for agent run cost data.

Provides APIs for:
- Recording usage data from agent runs
- Querying usage aggregated by agent, model, and user
- Time-series usage data for dashboards
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Annotated, Optional, List
from uuid import UUID as UUID_TYPE
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Header
from pydantic import BaseModel, Field

from langconnect.auth import AuthenticatedActor, ServiceAccount, resolve_user_or_service
from langconnect.database.connection import get_db_connection
from langconnect.database.user_roles import UserRoleManager

log = logging.getLogger(__name__)


async def is_admin_user(user_id: str) -> bool:
    """Check if a user has admin privileges (dev_admin or business_admin)."""
    role_manager = UserRoleManager(user_id)
    return await role_manager.can_manage_users()

router = APIRouter(prefix="/usage", tags=["Usage"])


# ============================================================================
# Pydantic Models
# ============================================================================


class UsageRecordCreate(BaseModel):
    """Request model for recording usage data from an agent run."""

    thread_id: str = Field(..., description="Thread ID for the conversation")
    run_id: str = Field(..., description="LangGraph run ID")
    assistant_id: Optional[str] = Field(None, description="Assistant instance ID")
    graph_name: Optional[str] = Field(None, description="Agent template name")
    model_name: str = Field(..., description="OpenRouter model ID")
    prompt_tokens: int = Field(..., ge=0, description="Number of prompt tokens")
    completion_tokens: int = Field(..., ge=0, description="Number of completion tokens")
    total_tokens: int = Field(..., ge=0, description="Total tokens used")
    cost: float = Field(..., ge=0, description="Cost in USD")


class UsageRecordResponse(BaseModel):
    """Response model for a single usage record."""

    id: str
    thread_id: str
    run_id: str
    assistant_id: Optional[str]
    graph_name: Optional[str]
    model_name: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost: float
    created_at: str


class UsageAggregateItem(BaseModel):
    """Aggregated usage for a single dimension (model, agent, or user)."""

    name: str
    display_name: Optional[str] = None
    run_count: int
    total_tokens: int
    prompt_tokens: int
    completion_tokens: int
    total_cost: float


class UsageSummaryResponse(BaseModel):
    """Summary of usage across different dimensions."""

    by_model: List[UsageAggregateItem]
    by_agent: List[UsageAggregateItem]
    by_user: Optional[List[UsageAggregateItem]] = None  # Only for admins
    total_cost: float
    total_tokens: int
    total_runs: int
    period_start: str
    period_end: str


class DailyUsageItem(BaseModel):
    """Daily usage data for time-series charts."""

    date: str
    cost: float
    tokens: int
    runs: int


class GroupedDailyUsageItem(BaseModel):
    """Daily usage data broken down by a grouping dimension."""

    date: str
    breakdown: dict[str, float]  # e.g., {"gpt-4": 0.05, "claude-3": 0.02}
    total_cost: float
    runs: int


class TimeSeriesResponse(BaseModel):
    """Time series usage data."""

    data: List[DailyUsageItem]
    period_start: str
    period_end: str


class GroupedTimeSeriesResponse(BaseModel):
    """Time series usage data with breakdown by model or agent."""

    data: List[GroupedDailyUsageItem]
    groups: List[str]  # List of unique group names for legend
    period_start: str
    period_end: str


# ============================================================================
# Helper Functions
# ============================================================================


def parse_period(period: str) -> tuple[datetime, datetime]:
    """
    Parse period string into start and end datetime.

    Args:
        period: One of 'day', 'week', 'month', 'all'

    Returns:
        Tuple of (start_datetime, end_datetime)
    """
    now = datetime.now(timezone.utc)
    end = now

    if period == "day":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "week":
        # Start of week (Monday)
        start = now - timedelta(days=now.weekday())
        start = start.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "month":
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    elif period == "all":
        # Far past date
        start = datetime(2020, 1, 1, tzinfo=timezone.utc)
    else:
        # Default to month
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    return start, end


def parse_date_range(
    start_date: Optional[str],
    end_date: Optional[str],
    period: str = "month",
) -> tuple[datetime, datetime]:
    """
    Parse date range from explicit start/end dates or fall back to period.

    Args:
        start_date: Optional ISO date string (e.g., "2025-11-14")
        end_date: Optional ISO date string (e.g., "2025-12-14")
        period: Fallback period if dates not provided

    Returns:
        Tuple of (start_datetime, end_datetime)
    """
    if start_date and end_date:
        # Parse date-only strings (YYYY-MM-DD) into datetime objects
        # date.fromisoformat is more reliable for date-only strings
        from datetime import date as date_type
        start_d = date_type.fromisoformat(start_date)
        end_d = date_type.fromisoformat(end_date)
        # Convert to datetime with timezone
        start = datetime(
            start_d.year, start_d.month, start_d.day,
            0, 0, 0, 0, tzinfo=timezone.utc
        )
        end = datetime(
            end_d.year, end_d.month, end_d.day,
            23, 59, 59, 999999, tzinfo=timezone.utc
        )
        return start, end

    # Fall back to period-based parsing
    return parse_period(period)


def generate_date_range(start: datetime, end: datetime) -> list[str]:
    """
    Generate a list of all dates between start and end (inclusive).

    Returns:
        List of ISO date strings (e.g., ["2025-12-10", "2025-12-11", ...])
    """
    dates = []
    current = start.replace(hour=0, minute=0, second=0, microsecond=0)
    end_date = end.replace(hour=0, minute=0, second=0, microsecond=0)

    while current <= end_date:
        dates.append(current.date().isoformat())
        current += timedelta(days=1)

    return dates


# ============================================================================
# Usage Recording Endpoints
# ============================================================================


@router.post("/record", response_model=UsageRecordResponse)
async def record_usage(
    usage: UsageRecordCreate,
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
    x_user_id: Annotated[Optional[str], Header(alias="X-User-Id")] = None,
) -> UsageRecordResponse:
    """
    Record usage data from an agent run.

    This endpoint is typically called by the LangGraph backend after a run completes,
    using a service account for authentication.

    **Authorization:**
    - **Service Accounts**: Can record usage for any user (user_id from X-User-Id header)
    - **Users**: Can record usage for their own runs
    """
    try:
        # Service accounts must provide user_id via X-User-Id header
        if isinstance(actor, ServiceAccount):
            if not x_user_id:
                raise HTTPException(
                    status_code=400,
                    detail="X-User-Id header required when using service account"
                )
            user_id = x_user_id
        else:
            user_id = actor.identity

        async with get_db_connection() as conn:
            # Upsert on (run_id, model_name) with ACCUMULATION for multi-call runs
            # Each model call within a run ADDS to the existing totals instead of overwriting.
            # This handles:
            # - Multi-model runs (e.g., deepagent with sub-agents using different models)
            # - Multiple calls of the same model within a run (e.g., ReAct loop)
            result = await conn.fetchrow(
                """
                INSERT INTO langconnect.agent_run_costs
                (thread_id, run_id, assistant_id, graph_name, user_id, model_name,
                 prompt_tokens, completion_tokens, total_tokens, cost)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                ON CONFLICT (run_id, model_name) DO UPDATE SET
                    prompt_tokens = agent_run_costs.prompt_tokens + EXCLUDED.prompt_tokens,
                    completion_tokens = agent_run_costs.completion_tokens + EXCLUDED.completion_tokens,
                    total_tokens = agent_run_costs.total_tokens + EXCLUDED.total_tokens,
                    cost = agent_run_costs.cost + EXCLUDED.cost
                RETURNING id, thread_id, run_id, assistant_id, graph_name, model_name,
                          prompt_tokens, completion_tokens, total_tokens, cost, created_at
                """,
                UUID_TYPE(usage.thread_id),
                usage.run_id,
                UUID_TYPE(usage.assistant_id) if usage.assistant_id else None,
                usage.graph_name,
                user_id,
                usage.model_name,
                usage.prompt_tokens,
                usage.completion_tokens,
                usage.total_tokens,
                Decimal(str(usage.cost)),
            )

        log.info(f"Recorded usage for run {usage.run_id}: {usage.total_tokens} tokens, ${usage.cost:.6f}")

        return UsageRecordResponse(
            id=str(result["id"]),
            thread_id=str(result["thread_id"]),
            run_id=result["run_id"],
            assistant_id=str(result["assistant_id"]) if result["assistant_id"] else None,
            graph_name=result["graph_name"],
            model_name=result["model_name"],
            prompt_tokens=result["prompt_tokens"],
            completion_tokens=result["completion_tokens"],
            total_tokens=result["total_tokens"],
            cost=float(result["cost"]),
            created_at=result["created_at"].isoformat(),
        )

    except Exception as e:
        log.error(f"Error recording usage: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to record usage: {str(e)}",
        )


# ============================================================================
# Usage Query Endpoints
# ============================================================================


@router.get("/summary", response_model=UsageSummaryResponse)
async def get_usage_summary(
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
    period: str = Query(default="month", description="Time period: day, week, month, all"),
    start_date: Optional[str] = Query(default=None, description="Start date (ISO format, e.g., 2025-11-14)"),
    end_date: Optional[str] = Query(default=None, description="End date (ISO format, e.g., 2025-12-14)"),
) -> UsageSummaryResponse:
    """
    Get aggregated usage summary with breakdowns by model, agent, and optionally user.

    **Authorization:**
    - **All Users**: Can view their own usage
    - **Admins**: Can view all users' usage with per-user breakdown
    """
    try:
        if actor.actor_type == "service":
            raise HTTPException(
                status_code=403,
                detail="Service accounts should use specific user queries",
            )

        user_id = actor.identity
        start_dt, end_dt = parse_date_range(start_date, end_date, period)

        # Check if user is admin (dev_admin or business_admin)
        is_admin = await is_admin_user(user_id)

        async with get_db_connection() as conn:
            # Build base query conditions
            if is_admin:
                user_filter = ""
                user_params = [start_dt, end_dt]
            else:
                user_filter = "AND user_id = $3"
                user_params = [start_dt, end_dt, user_id]

            # Get totals
            totals = await conn.fetchrow(
                f"""
                SELECT
                    COALESCE(SUM(cost), 0) as total_cost,
                    COALESCE(SUM(total_tokens), 0) as total_tokens,
                    COUNT(*) as total_runs
                FROM langconnect.agent_run_costs
                WHERE created_at >= $1 AND created_at <= $2 {user_filter}
                """,
                *user_params,
            )

            # Get by model
            by_model_rows = await conn.fetch(
                f"""
                SELECT
                    model_name as name,
                    COUNT(*) as run_count,
                    COALESCE(SUM(total_tokens), 0) as total_tokens,
                    COALESCE(SUM(prompt_tokens), 0) as prompt_tokens,
                    COALESCE(SUM(completion_tokens), 0) as completion_tokens,
                    COALESCE(SUM(cost), 0) as total_cost
                FROM langconnect.agent_run_costs
                WHERE created_at >= $1 AND created_at <= $2 {user_filter}
                GROUP BY model_name
                ORDER BY total_cost DESC
                """,
                *user_params,
            )

            # Get by agent (using graph_name and assistant_id)
            by_agent_rows = await conn.fetch(
                f"""
                SELECT
                    COALESCE(arc.graph_name, 'unknown') as name,
                    am.name as display_name,
                    COUNT(*) as run_count,
                    COALESCE(SUM(arc.total_tokens), 0) as total_tokens,
                    COALESCE(SUM(arc.prompt_tokens), 0) as prompt_tokens,
                    COALESCE(SUM(arc.completion_tokens), 0) as completion_tokens,
                    COALESCE(SUM(arc.cost), 0) as total_cost
                FROM langconnect.agent_run_costs arc
                LEFT JOIN langconnect.assistants_mirror am ON arc.assistant_id = am.assistant_id
                WHERE arc.created_at >= $1 AND arc.created_at <= $2 {user_filter.replace('user_id', 'arc.user_id')}
                GROUP BY arc.graph_name, am.name
                ORDER BY total_cost DESC
                """,
                *user_params,
            )

            # Get by user (admin only)
            by_user = None
            if is_admin:
                by_user_rows = await conn.fetch(
                    """
                    SELECT
                        arc.user_id as name,
                        ur.display_name,
                        COUNT(*) as run_count,
                        COALESCE(SUM(arc.total_tokens), 0) as total_tokens,
                        COALESCE(SUM(arc.prompt_tokens), 0) as prompt_tokens,
                        COALESCE(SUM(arc.completion_tokens), 0) as completion_tokens,
                        COALESCE(SUM(arc.cost), 0) as total_cost
                    FROM langconnect.agent_run_costs arc
                    LEFT JOIN langconnect.user_roles ur ON arc.user_id = ur.user_id
                    WHERE arc.created_at >= $1 AND arc.created_at <= $2
                    GROUP BY arc.user_id, ur.display_name
                    ORDER BY total_cost DESC
                    """,
                    start_dt,
                    end_dt,
                )
                by_user = [
                    UsageAggregateItem(
                        name=row["name"],
                        display_name=row["display_name"],
                        run_count=row["run_count"],
                        total_tokens=row["total_tokens"],
                        prompt_tokens=row["prompt_tokens"],
                        completion_tokens=row["completion_tokens"],
                        total_cost=float(row["total_cost"]),
                    )
                    for row in by_user_rows
                ]

        return UsageSummaryResponse(
            by_model=[
                UsageAggregateItem(
                    name=row["name"],
                    run_count=row["run_count"],
                    total_tokens=row["total_tokens"],
                    prompt_tokens=row["prompt_tokens"],
                    completion_tokens=row["completion_tokens"],
                    total_cost=float(row["total_cost"]),
                )
                for row in by_model_rows
            ],
            by_agent=[
                UsageAggregateItem(
                    name=row["name"],
                    display_name=row["display_name"],
                    run_count=row["run_count"],
                    total_tokens=row["total_tokens"],
                    prompt_tokens=row["prompt_tokens"],
                    completion_tokens=row["completion_tokens"],
                    total_cost=float(row["total_cost"]),
                )
                for row in by_agent_rows
            ],
            by_user=by_user,
            total_cost=float(totals["total_cost"]),
            total_tokens=totals["total_tokens"],
            total_runs=totals["total_runs"],
            period_start=start_dt.isoformat(),
            period_end=end_dt.isoformat(),
        )

    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Error getting usage summary: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get usage summary: {str(e)}",
        )


@router.get("/timeseries", response_model=TimeSeriesResponse)
async def get_usage_timeseries(
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
    period: str = Query(default="month", description="Time period: week, month, all"),
    start_date: Optional[str] = Query(default=None, description="Start date (ISO format, e.g., 2025-11-14)"),
    end_date: Optional[str] = Query(default=None, description="End date (ISO format, e.g., 2025-12-14)"),
) -> TimeSeriesResponse:
    """
    Get daily usage data for time-series charts.

    **Authorization:**
    - **All Users**: Can view their own usage
    - **Admins**: Can view all users' usage (aggregate)
    """
    try:
        if actor.actor_type == "service":
            raise HTTPException(
                status_code=403,
                detail="Service accounts should use specific user queries",
            )

        user_id = actor.identity
        start_dt, end_dt = parse_date_range(start_date, end_date, period)

        # Check if user is admin (dev_admin or business_admin)
        is_admin = await is_admin_user(user_id)

        async with get_db_connection() as conn:
            if is_admin:
                rows = await conn.fetch(
                    """
                    SELECT
                        DATE(created_at) as date,
                        COALESCE(SUM(cost), 0) as cost,
                        COALESCE(SUM(total_tokens), 0) as tokens,
                        COUNT(*) as runs
                    FROM langconnect.agent_run_costs
                    WHERE created_at >= $1 AND created_at <= $2
                    GROUP BY DATE(created_at)
                    ORDER BY date ASC
                    """,
                    start_dt,
                    end_dt,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT
                        DATE(created_at) as date,
                        COALESCE(SUM(cost), 0) as cost,
                        COALESCE(SUM(total_tokens), 0) as tokens,
                        COUNT(*) as runs
                    FROM langconnect.agent_run_costs
                    WHERE created_at >= $1 AND created_at <= $2 AND user_id = $3
                    GROUP BY DATE(created_at)
                    ORDER BY date ASC
                    """,
                    start_dt,
                    end_dt,
                    user_id,
                )

        return TimeSeriesResponse(
            data=[
                DailyUsageItem(
                    date=row["date"].isoformat(),
                    cost=float(row["cost"]),
                    tokens=row["tokens"],
                    runs=row["runs"],
                )
                for row in rows
            ],
            period_start=start_dt.isoformat(),
            period_end=end_dt.isoformat(),
        )

    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Error getting usage timeseries: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get usage timeseries: {str(e)}",
        )


@router.get("/timeseries/grouped", response_model=GroupedTimeSeriesResponse)
async def get_grouped_usage_timeseries(
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
    period: str = Query(default="month", description="Time period: week, month, all"),
    group_by: str = Query(default="model", description="Group by: model or agent"),
    start_date: Optional[str] = Query(default=None, description="Start date (ISO format, e.g., 2025-11-14)"),
    end_date: Optional[str] = Query(default=None, description="End date (ISO format, e.g., 2025-12-14)"),
) -> GroupedTimeSeriesResponse:
    """
    Get daily usage data grouped by model or agent for stacked bar charts.

    **Authorization:**
    - **All Users**: Can view their own usage
    - **Admins**: Can view all users' usage (aggregate)
    """
    try:
        if actor.actor_type == "service":
            raise HTTPException(
                status_code=403,
                detail="Service accounts should use specific user queries",
            )

        if group_by not in ("model", "agent"):
            raise HTTPException(
                status_code=400,
                detail="group_by must be 'model' or 'agent'",
            )

        user_id = actor.identity
        start_dt, end_dt = parse_date_range(start_date, end_date, period)

        # Check if user is admin (dev_admin or business_admin)
        is_admin = await is_admin_user(user_id)

        async with get_db_connection() as conn:
            # Build query based on group_by and admin status
            if group_by == "model":
                if is_admin:
                    rows = await conn.fetch(
                        """
                        SELECT
                            DATE(created_at) as date,
                            model_name as group_name,
                            COALESCE(SUM(cost), 0) as cost,
                            COUNT(*) as runs
                        FROM langconnect.agent_run_costs
                        WHERE created_at >= $1 AND created_at <= $2
                        GROUP BY DATE(created_at), model_name
                        ORDER BY date ASC, group_name ASC
                        """,
                        start_dt,
                        end_dt,
                    )
                else:
                    rows = await conn.fetch(
                        """
                        SELECT
                            DATE(created_at) as date,
                            model_name as group_name,
                            COALESCE(SUM(cost), 0) as cost,
                            COUNT(*) as runs
                        FROM langconnect.agent_run_costs
                        WHERE created_at >= $1 AND created_at <= $2 AND user_id = $3
                        GROUP BY DATE(created_at), model_name
                        ORDER BY date ASC, group_name ASC
                        """,
                        start_dt,
                        end_dt,
                        user_id,
                    )
            else:  # group_by == "agent"
                if is_admin:
                    rows = await conn.fetch(
                        """
                        SELECT
                            DATE(arc.created_at) as date,
                            COALESCE(am.name, arc.graph_name, 'unknown') as group_name,
                            COALESCE(SUM(arc.cost), 0) as cost,
                            COUNT(*) as runs
                        FROM langconnect.agent_run_costs arc
                        LEFT JOIN langconnect.assistants_mirror am ON arc.assistant_id = am.assistant_id
                        WHERE arc.created_at >= $1 AND arc.created_at <= $2
                        GROUP BY DATE(arc.created_at), COALESCE(am.name, arc.graph_name, 'unknown')
                        ORDER BY date ASC, group_name ASC
                        """,
                        start_dt,
                        end_dt,
                    )
                else:
                    rows = await conn.fetch(
                        """
                        SELECT
                            DATE(arc.created_at) as date,
                            COALESCE(am.name, arc.graph_name, 'unknown') as group_name,
                            COALESCE(SUM(arc.cost), 0) as cost,
                            COUNT(*) as runs
                        FROM langconnect.agent_run_costs arc
                        LEFT JOIN langconnect.assistants_mirror am ON arc.assistant_id = am.assistant_id
                        WHERE arc.created_at >= $1 AND arc.created_at <= $2 AND arc.user_id = $3
                        GROUP BY DATE(arc.created_at), COALESCE(am.name, arc.graph_name, 'unknown')
                        ORDER BY date ASC, group_name ASC
                        """,
                        start_dt,
                        end_dt,
                        user_id,
                    )

        # Collect unique groups and organize data by date
        all_groups: set[str] = set()
        date_data: dict[str, dict[str, float]] = {}
        date_runs: dict[str, int] = {}

        for row in rows:
            date_str = row["date"].isoformat()
            group_name = row["group_name"]
            cost = float(row["cost"])
            runs = row["runs"]

            all_groups.add(group_name)

            if date_str not in date_data:
                date_data[date_str] = {}
                date_runs[date_str] = 0

            date_data[date_str][group_name] = cost
            date_runs[date_str] += runs

        # Generate all dates in the range and fill missing with empty data
        all_dates = generate_date_range(start_dt, end_dt)
        grouped_data = []
        for date_str in all_dates:
            if date_str in date_data:
                grouped_data.append(
                    GroupedDailyUsageItem(
                        date=date_str,
                        breakdown=date_data[date_str],
                        total_cost=sum(date_data[date_str].values()),
                        runs=date_runs[date_str],
                    )
                )
            else:
                # No data for this date - add empty entry
                grouped_data.append(
                    GroupedDailyUsageItem(
                        date=date_str,
                        breakdown={},
                        total_cost=0,
                        runs=0,
                    )
                )

        return GroupedTimeSeriesResponse(
            data=grouped_data,
            groups=sorted(all_groups),
            period_start=start_dt.isoformat(),
            period_end=end_dt.isoformat(),
        )

    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Error getting grouped usage timeseries: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get grouped usage timeseries: {str(e)}",
        )
