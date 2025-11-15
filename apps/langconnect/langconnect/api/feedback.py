"""
Feedback management endpoints for agent message feedback and app feedback.
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Annotated, Optional
from uuid import UUID as UUID_TYPE

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from langconnect.auth import AuthenticatedActor, resolve_user_or_service
from langconnect.database.connection import get_db_connection

# Set up logging
log = logging.getLogger(__name__)

# Create router
router = APIRouter(tags=["Feedback"])

# ============================================================================
# Pydantic Models
# ============================================================================


class MessageFeedbackCreate(BaseModel):
    """Request model for creating/updating message feedback."""

    thread_id: str = Field(..., description="Thread ID containing the message")
    message_id: str = Field(..., description="Message ID to provide feedback on")
    run_id: Optional[str] = Field(None, description="LangSmith run ID (optional, will be extracted from message_id if not provided)")
    score: int = Field(..., ge=-1, le=1, description="1=thumbs up, -1=thumbs down, 0=remove")
    category: Optional[str] = Field(None, max_length=50, description="Category of feedback")
    comment: Optional[str] = Field(None, description="Optional user comment")


class MessageFeedbackResponse(BaseModel):
    """Response model for message feedback operations."""

    id: str
    score: int
    category: Optional[str]
    comment: Optional[str]
    langsmith_synced: bool
    created_at: str
    updated_at: str


class AppFeedbackCreate(BaseModel):
    """Request model for creating app feedback."""

    feedback_type: str = Field(..., description="Type: 'bug' or 'feature'")
    title: str = Field(..., max_length=255, description="Feedback title")
    description: str = Field(..., description="Detailed description")
    screenshot_urls: Optional[list[str]] = Field(None, description="Array of screenshot URLs")
    page_url: Optional[str] = Field(None, description="Current page URL")
    user_agent: Optional[str] = Field(None, description="Browser user agent")
    metadata: Optional[dict] = Field(None, description="Additional context")


class AppFeedbackResponse(BaseModel):
    """Response model for app feedback operations."""

    id: str
    feedback_type: str
    title: str
    description: str
    status: str
    created_at: str


# ============================================================================
# Helper Functions
# ============================================================================


def extract_run_id_from_message_id(message_id: str) -> Optional[str]:
    """
    Extract LangSmith run_id from LangGraph message_id.

    LangGraph message IDs often follow the pattern: "run--<uuid>" or "run-<uuid>"
    This function attempts to extract the UUID portion and validates it.

    Examples:
        "run--9f1f8cac-7b36-4e1b-880b-d46dab8b3ffc" -> "9f1f8cac-7b36-4e1b-880b-d46dab8b3ffc"
        "run-3fdbf494-acce-402e-9b50-4eab46403859" -> "3fdbf494-acce-402e-9b50-4eab46403859"
        "9f1f8cac-7b36-4e1b-880b-d46dab8b3ffc" -> "9f1f8cac-7b36-4e1b-880b-d46dab8b3ffc"
    """
    if not message_id:
        return None

    extracted_id = None

    # Try to extract UUID from message_id
    # Pattern 1: "run--<uuid>" or "run-<uuid>"
    if message_id.startswith("run--"):
        extracted_id = message_id[5:]  # Strip "run--" prefix
    elif message_id.startswith("run-"):
        extracted_id = message_id[4:]  # Strip "run-" prefix
    # Pattern 2: Already a UUID (no prefix)
    elif len(message_id) == 36 and message_id.count("-") == 4:
        extracted_id = message_id
    else:
        log.warning(f"Could not extract run_id from message_id: {message_id}")
        return None

    # Validate that extracted_id is a valid UUID
    try:
        UUID_TYPE(extracted_id)
        return extracted_id
    except ValueError:
        log.warning(f"Invalid UUID format extracted from message_id {message_id}: {extracted_id}")
        return None


async def find_langsmith_run_id(thread_id: str, message_timestamp: datetime) -> Optional[str]:
    """
    Query LangSmith API to find run_id by correlating thread_id and timestamp.

    This searches for runs that:
    1. Match the thread_id
    2. Have a start_time close to the message timestamp (within 30 seconds)

    Returns the most recent matching run_id or None if not found.

    NOTE: This timestamp-based approach is a fallback and has limitations:
    - 30-second window may match wrong runs in high-traffic scenarios
    - Recommended to pass run_id directly or extract from message_id when possible
    """
    api_key = os.getenv("LANGSMITH_API_KEY")
    endpoint = os.getenv("LANGSMITH_ENDPOINT", "https://api.smith.langchain.com")

    if not api_key:
        log.warning("❌ LANGSMITH_API_KEY not configured, skipping run_id lookup")
        return None

    log.info(f"🔍 Searching for LangSmith run_id for thread: {thread_id}")

    try:
        # Format timestamp for LangSmith API query (Unix timestamp)
        message_ts = message_timestamp.timestamp()
        start_time = message_ts - 30  # 30s before
        end_time = message_ts + 30  # 30s after

        # Use json.dumps for safe JSON serialization (prevents injection)
        filter_query = json.dumps({
            "thread_id": thread_id,
            "start_time": {"$gte": start_time, "$lte": end_time}
        })
        log.debug(f"LangSmith filter query: {filter_query}")

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{endpoint}/runs",
                params={
                    "filter": filter_query,
                    "limit": 10,
                },
                headers={"x-api-key": api_key},
                timeout=10.0,
            )

            if response.status_code == 200:
                runs = response.json()
                if runs and len(runs) > 0:
                    # Return the most recent run
                    run_id = runs[0].get("id")
                    log.info(f"✅ Found LangSmith run_id: {run_id} for thread: {thread_id}")
                    return run_id
                else:
                    log.warning(f"⚠️ No LangSmith runs found for thread: {thread_id} in time window [{start_time}, {end_time}]")
            else:
                log.error(f"❌ LangSmith API error: {response.status_code} - {response.text}")

    except Exception as e:
        log.error(f"❌ Error querying LangSmith API: {e}", exc_info=True)

    return None


async def submit_feedback_to_langsmith(
    run_id: str,
    score: int,
    comment: Optional[str],
    category: Optional[str],
) -> Optional[str]:
    """
    Submit feedback to LangSmith API.

    Returns the LangSmith feedback_id if successful, None otherwise.
    """
    api_key = os.getenv("LANGSMITH_API_KEY")
    endpoint = os.getenv("LANGSMITH_ENDPOINT", "https://api.smith.langchain.com")

    if not api_key:
        log.warning("❌ LANGSMITH_API_KEY not configured, skipping LangSmith sync")
        return None

    log.info(f"📤 Submitting feedback to LangSmith for run_id: {run_id}")

    try:
        # LangSmith accepts any numerical score value
        # Our internal format: 1 = thumbs up, -1 = thumbs down, 0 = removed
        # We pass the score directly to LangSmith (1, -1, or None for removed)
        langsmith_score = None if score == 0 else float(score)

        payload = {
            "run_id": run_id,
            "key": "user_feedback",
            "score": langsmith_score,
        }

        log.info(f"📊 LangSmith payload: score={langsmith_score}, category={category}, comment={'[present]' if comment else '[none]'}")

        # Add optional fields
        if comment:
            payload["comment"] = comment
        if category:
            payload["value"] = category

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{endpoint}/feedback",
                json=payload,
                headers={"x-api-key": api_key},
                timeout=10.0,
            )

            if response.status_code in [200, 201]:
                feedback_data = response.json()
                feedback_id = feedback_data.get("id")
                log.info(f"✅ Submitted feedback to LangSmith: {feedback_id}")
                return feedback_id
            else:
                log.error(f"❌ LangSmith feedback error: {response.status_code} - {response.text}")

    except Exception as e:
        log.error(f"❌ Error submitting to LangSmith: {e}", exc_info=True)

    return None


# ============================================================================
# Message Feedback Endpoints
# ============================================================================

# TODO: Add rate limiting to prevent abuse
# Consider using slowapi or similar middleware to limit feedback submissions per user
# Suggested limits: 10 requests per minute per user


@router.post("/feedback/messages", response_model=MessageFeedbackResponse)
async def create_message_feedback(
    feedback: MessageFeedbackCreate,
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
) -> MessageFeedbackResponse:
    """
    Create or update feedback for an AI message.

    Workflow:
    1. Store feedback in database
    2. Query LangSmith API to find run_id using thread_id + timestamp
    3. Submit feedback to LangSmith if run_id found
    4. Update database with LangSmith feedback_id

    **Authorization:**
    - **All Users**: Can create feedback for their own messages

    **Note:** Rate limiting should be implemented to prevent abuse.
    """
    try:
        # Service accounts cannot create feedback
        if actor.actor_type == "service":
            raise HTTPException(
                status_code=403,
                detail="Service accounts cannot create feedback",
            )

        user_id = actor.identity

        # Upsert feedback in database
        async with get_db_connection() as conn:
            result = await conn.fetchrow(
                """
                INSERT INTO langconnect.message_feedback
                (user_id, thread_id, message_id, score, category, comment)
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (user_id, message_id) DO UPDATE SET
                    score = EXCLUDED.score,
                    category = EXCLUDED.category,
                    comment = EXCLUDED.comment,
                    updated_at = NOW()
                RETURNING id, score, category, comment, created_at, updated_at
                """,
                user_id,
                feedback.thread_id,
                feedback.message_id,
                feedback.score,
                feedback.category,
                feedback.comment,
            )

            feedback_id = result["id"]
            score = result["score"]
            category = result["category"]
            comment = result["comment"]
            created_at = result["created_at"]
            updated_at = result["updated_at"]

        log.info(f"Created message feedback: {feedback_id} for message: {feedback.message_id}")

        # Attempt to sync with LangSmith
        langsmith_synced = False

        if feedback.score != 0:  # Don't sync removed feedback
            # Determine run_id: use provided value, extract from message_id, or search by timestamp
            run_id = feedback.run_id

            if not run_id:
                # Try to extract run_id from message_id
                run_id = extract_run_id_from_message_id(feedback.message_id)
                if run_id:
                    log.info(f"Extracted run_id from message_id: {run_id}")
                else:
                    # Fallback: Try to find run_id using thread_id and timestamp (less reliable)
                    log.warning("Could not extract run_id from message_id, falling back to timestamp-based search")
                    run_id = await find_langsmith_run_id(feedback.thread_id, created_at)

            if run_id:
                # Submit to LangSmith
                langsmith_feedback_id = await submit_feedback_to_langsmith(
                    run_id=run_id,
                    score=feedback.score,
                    comment=feedback.comment,
                    category=feedback.category,
                )

                if langsmith_feedback_id:
                    # Update database with LangSmith info
                    async with get_db_connection() as conn:
                        await conn.execute(
                            """
                            UPDATE langconnect.message_feedback
                            SET run_id = $1,
                                langsmith_feedback_id = $2,
                                langsmith_synced_at = NOW()
                            WHERE id = $3
                            """,
                            run_id,
                            langsmith_feedback_id,
                            feedback_id,
                        )

                    langsmith_synced = True
                    log.info(f"Synced feedback {feedback_id} to LangSmith: {langsmith_feedback_id}")

        return MessageFeedbackResponse(
            id=str(feedback_id),
            score=score,
            category=category,
            comment=comment,
            langsmith_synced=langsmith_synced,
            created_at=created_at.isoformat(),
            updated_at=updated_at.isoformat(),
        )

    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Error creating message feedback: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create feedback: {str(e)}",
        )


@router.get("/feedback/messages/{message_id}", response_model=Optional[MessageFeedbackResponse])
async def get_message_feedback(
    message_id: str,
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
) -> Optional[MessageFeedbackResponse]:
    """
    Get feedback for a specific message from the authenticated user.

    **Authorization:**
    - **All Users**: Can view their own feedback
    """
    try:
        if actor.actor_type == "service":
            raise HTTPException(
                status_code=403,
                detail="Service accounts cannot access feedback",
            )

        user_id = actor.identity

        async with get_db_connection() as conn:
            result = await conn.fetchrow(
                """
                SELECT id, score, category, comment, langsmith_synced_at, created_at, updated_at
                FROM langconnect.message_feedback
                WHERE user_id = $1 AND message_id = $2
                """,
                user_id,
                message_id,
            )

            if not result:
                return None

            return MessageFeedbackResponse(
                id=str(result["id"]),
                score=result["score"],
                category=result["category"],
                comment=result["comment"],
                langsmith_synced=result["langsmith_synced_at"] is not None,
                created_at=result["created_at"].isoformat(),
                updated_at=result["updated_at"].isoformat(),
            )

    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Error fetching message feedback: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch feedback: {str(e)}",
        )


# ============================================================================
# App Feedback Endpoints
# ============================================================================


@router.post("/feedback/app", response_model=AppFeedbackResponse)
async def create_app_feedback(
    feedback: AppFeedbackCreate,
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
) -> AppFeedbackResponse:
    """
    Create app feedback (bug report or feature request).

    **Authorization:**
    - **All Users**: Can create app feedback
    """
    try:
        if actor.actor_type == "service":
            raise HTTPException(
                status_code=403,
                detail="Service accounts cannot create app feedback",
            )

        user_id = actor.identity

        # Validate feedback_type
        if feedback.feedback_type not in ["bug", "feature"]:
            raise HTTPException(
                status_code=400,
                detail="feedback_type must be 'bug' or 'feature'",
            )

        async with get_db_connection() as conn:
            result = await conn.fetchrow(
                """
                INSERT INTO langconnect.app_feedback
                (user_id, feedback_type, title, description, screenshot_urls,
                 page_url, user_agent, metadata)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb)
                RETURNING id, feedback_type, title, description, status, created_at
                """,
                user_id,
                feedback.feedback_type,
                feedback.title,
                feedback.description,
                feedback.screenshot_urls,
                feedback.page_url,
                feedback.user_agent,
                json.dumps(feedback.metadata or {}),
            )

            feedback_id = result["id"]
            fb_type = result["feedback_type"]
            title = result["title"]
            description = result["description"]
            status = result["status"]
            created_at = result["created_at"]

        log.info(f"Created app feedback: {feedback_id} ({fb_type}) by {user_id}")

        return AppFeedbackResponse(
            id=str(feedback_id),
            feedback_type=fb_type,
            title=title,
            description=description,
            status=status,
            created_at=created_at.isoformat(),
        )

    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Error creating app feedback: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create app feedback: {str(e)}",
        )


@router.get("/feedback/app/{feedback_id}", response_model=AppFeedbackResponse)
async def get_app_feedback(
    feedback_id: UUID_TYPE,
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
) -> AppFeedbackResponse:
    """
    Get a specific app feedback by ID.

    **Authorization:**
    - **All Users**: Can view their own feedback
    - **Admins**: Can view all feedback
    """
    try:
        if actor.actor_type == "service":
            raise HTTPException(
                status_code=403,
                detail="Service accounts cannot access app feedback",
            )

        user_id = actor.identity

        async with get_db_connection() as conn:
            # Users can only see their own feedback
            result = await conn.fetchrow(
                """
                SELECT id, feedback_type, title, description, status, created_at
                FROM langconnect.app_feedback
                WHERE id = $1 AND user_id = $2
                """,
                feedback_id,
                user_id,
            )

            if not result:
                raise HTTPException(
                    status_code=404,
                    detail="Feedback not found",
                )

            return AppFeedbackResponse(
                id=str(result["id"]),
                feedback_type=result["feedback_type"],
                title=result["title"],
                description=result["description"],
                status=result["status"],
                created_at=result["created_at"].isoformat(),
            )

    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Error fetching app feedback: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch app feedback: {str(e)}",
        )
