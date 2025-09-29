"""
Graph presentation endpoints: editable name and description on graphs_mirror.
"""

import logging
from typing import Annotated, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException

from langconnect.auth import resolve_user_or_service, AuthenticatedActor
from langconnect.database.connection import get_db_connection
from langconnect.database.permissions import GraphPermissionsManager

log = logging.getLogger(__name__)

router = APIRouter()


def _sanitize_name(name: Optional[str]) -> Optional[str]:
    if name is None:
        return None
    trimmed = name.strip()
    if trimmed == "":
        return None
    # Limit length to avoid abuse
    return trimmed[:120]


def _sanitize_description(description: Optional[str]) -> Optional[str]:
    if description is None:
        return None
    trimmed = description.strip()
    # Allow empty to mean NULL (clear)
    if trimmed == "":
        return None
    return trimmed[:2000]


@router.patch("/graphs/{graph_id}")
async def update_graph_presentation(
    graph_id: str,
    body: Dict[str, Any],
    actor: Annotated[AuthenticatedActor, Depends(resolve_user_or_service)],
):
    """
    Update graph name/description (admin only).
    Bumps graphs_version for cache invalidation.
    """
    try:
        log.info(f"[graphs:presentation] update graph={graph_id} actor={actor.actor_type}:{actor.identity}")

        # Authorisation: only dev_admin users or service accounts
        if actor.actor_type == "user":
            user_role = await GraphPermissionsManager.get_user_role(actor.identity)
            if user_role != "dev_admin":
                raise HTTPException(status_code=403, detail="Only dev_admin users can edit graph details")

        desired_name = _sanitize_name(body.get("name")) if isinstance(body, dict) else None
        desired_description = _sanitize_description(body.get("description")) if isinstance(body, dict) else None

        if desired_name is None and desired_description is None:
            raise HTTPException(status_code=400, detail="No valid fields provided. Provide 'name' and/or 'description'.")

        async with get_db_connection() as conn:
            # Ensure graph exists
            exists = await conn.fetchval(
                "SELECT 1 FROM langconnect.graphs_mirror WHERE graph_id = $1",
                graph_id,
            )
            if not exists:
                raise HTTPException(status_code=404, detail="Graph not found")

            # Build dynamic update
            sets = []
            params = []
            idx = 1
            if desired_name is not None:
                sets.append(f"name = ${idx}")
                params.append(desired_name)
                idx += 1
            if desired_description is not None:
                sets.append(f"description = ${idx}")
                params.append(desired_description)
                idx += 1
            sets.append("mirror_updated_at = NOW()")
            sets.append("updated_at = NOW()")

            params.append(graph_id)

            query = f"""
                UPDATE langconnect.graphs_mirror
                SET {', '.join(sets)}
                WHERE graph_id = ${idx}
                RETURNING graph_id, name, description, assistants_count, has_default_assistant, schema_accessible
            """

            row = await conn.fetchrow(query, *params)

            # Bump graphs cache version
            await conn.execute("SELECT langconnect.increment_cache_version('graphs')")

            return {
                "graph_id": row["graph_id"],
                "name": row["name"],
                "description": row["description"],
                "assistants_count": row["assistants_count"],
                "has_default_assistant": row["has_default_assistant"],
                "schema_accessible": row["schema_accessible"],
            }
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Failed to update graph presentation for {graph_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update graph details: {str(e)}")


