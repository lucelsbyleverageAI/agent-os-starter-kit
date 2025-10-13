"""Permission utilities for collections, graphs, and assistants."""

from typing import Dict, Optional, List, Any
from langconnect.database.connection import get_db_connection


PERMISSION_HIERARCHY = {
    "viewer": 0,
    "editor": 1,
    "owner": 2
}


async def get_user_accessible_collections(
    user_id: str,
    min_permission: str = "viewer"
) -> Dict[str, str]:
    """
    Get all collections user can access with at least min_permission.
    
    Args:
        user_id: User ID to check permissions for
        min_permission: Minimum permission level required (viewer, editor, or owner)
    
    Returns:
        Dictionary mapping collection_id to permission_level
        Example: {"uuid-1": "owner", "uuid-2": "editor"}
    """
    min_level = PERMISSION_HIERARCHY.get(min_permission, 2)
    
    async with get_db_connection() as conn:
        query = """
            SELECT collection_id, permission_level
            FROM langconnect.collection_permissions
            WHERE user_id = $1
        """
        rows = await conn.fetch(query, user_id)
        
        result = {}
        for row in rows:
            perm_level = PERMISSION_HIERARCHY.get(row["permission_level"], 0)
            if perm_level >= min_level:
                result[str(row["collection_id"])] = row["permission_level"]
        
        return result


async def verify_collection_permission(
    user_id: str,
    collection_id: str,
    required_permission: str
) -> bool:
    """
    Verify user has required permission on a specific collection.
    
    Args:
        user_id: User ID to check
        collection_id: Collection UUID to check
        required_permission: Required permission level (viewer, editor, or owner)
    
    Returns:
        True if user has required permission or higher, False otherwise
    """
    async with get_db_connection() as conn:
        query = """
            SELECT permission_level
            FROM langconnect.collection_permissions
            WHERE user_id = $1 AND collection_id = $2
        """
        row = await conn.fetchrow(query, user_id, collection_id)
        
        if not row:
            return False
        
        user_level = PERMISSION_HIERARCHY.get(row["permission_level"], 0)
        required_level = PERMISSION_HIERARCHY.get(required_permission, 2)
        
        return user_level >= required_level


async def get_user_collection_permission(
    user_id: str,
    collection_id: str
) -> Optional[str]:
    """
    Get user's permission level for a specific collection.
    
    Args:
        user_id: User ID to check
        collection_id: Collection UUID to check
    
    Returns:
        Permission level string (viewer, editor, or owner) or None if no access
    """
    async with get_db_connection() as conn:
        query = """
            SELECT permission_level
            FROM langconnect.collection_permissions
            WHERE user_id = $1 AND collection_id = $2
        """
        row = await conn.fetchrow(query, user_id, collection_id)
        
        if not row:
            return None
        
        return row["permission_level"]


class GraphPermissionsManager:
    """Facade exposing graph permission operations used across the API."""

    @staticmethod
    async def get_user_role(user_id: str) -> Optional[str]:
        async with get_db_connection() as conn:
            row = await conn.fetchrow(
                "SELECT role FROM langconnect.user_roles WHERE user_id = $1",
                user_id,
            )
            return row["role"] if row else None

    @staticmethod
    async def get_all_dev_admins() -> List[Dict[str, Any]]:
        async with get_db_connection() as conn:
            rows = await conn.fetch(
                """
                SELECT user_id, email, display_name
                FROM langconnect.user_roles
                WHERE role = 'dev_admin'
                """
            )
            return [dict(r) for r in rows]

    @staticmethod
    async def get_user_by_id(user_id: str) -> Optional[Dict[str, Any]]:
        """Get user information by user ID."""
        async with get_db_connection() as conn:
            row = await conn.fetchrow(
                """
                SELECT user_id, email, display_name, role
                FROM langconnect.user_roles
                WHERE user_id = $1
                """,
                user_id,
            )
            return dict(row) if row else None

    @staticmethod
    async def has_graph_permission(user_id: str, graph_id: str, required_level: str) -> bool:
        role = await GraphPermissionsManager.get_user_role(user_id)
        if role == "dev_admin":
            return True
        async with get_db_connection() as conn:
            row = await conn.fetchrow(
                """
                SELECT permission_level
                FROM langconnect.graph_permissions
                WHERE user_id = $1 AND graph_id = $2
                """,
                user_id,
                graph_id,
            )
        if not row:
            return False
        level = row["permission_level"]
        if required_level == "admin":
            return level == "admin"
        return level in {"access", "admin"}

    @staticmethod
    async def grant_graph_permission(graph_id: str, user_id: str, permission_level: str, granted_by: str = "system") -> bool:
        async with get_db_connection() as conn:
            result = await conn.execute(
                """
                INSERT INTO langconnect.graph_permissions (graph_id, user_id, permission_level, granted_by)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (graph_id, user_id) DO UPDATE SET
                  permission_level = EXCLUDED.permission_level,
                  granted_by = EXCLUDED.granted_by,
                  updated_at = NOW()
                """,
                graph_id,
                user_id,
                permission_level,
                granted_by,
            )
            return True if isinstance(result, str) else False

    @staticmethod
    async def get_user_accessible_graphs(user_id: str) -> List[Dict[str, Any]]:
        # Check if user is dev_admin - they have implicit access to all graphs
        role = await GraphPermissionsManager.get_user_role(user_id)
        if role == "dev_admin":
            # Dev admins have implicit admin access to all graphs in the mirror
            async with get_db_connection() as conn:
                rows = await conn.fetch(
                    """
                    SELECT graph_id, 'admin' as permission_level
                    FROM langconnect.graphs_mirror
                    ORDER BY graph_id
                    """
                )
                return [dict(r) for r in rows]

        # Regular users only see graphs they have explicit permissions for
        async with get_db_connection() as conn:
            rows = await conn.fetch(
                """
                SELECT graph_id, permission_level
                FROM langconnect.graph_permissions
                WHERE user_id = $1
                ORDER BY graph_id
                """,
                user_id,
            )
            return [dict(r) for r in rows]

    @staticmethod
    async def get_graph_permissions(graph_id: str) -> List[Dict[str, Any]]:
        async with get_db_connection() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    gp.user_id,
                    gp.permission_level,
                    gp.granted_by,
                    gp.created_at,
                    ur.email,
                    ur.display_name
                FROM langconnect.graph_permissions gp
                LEFT JOIN langconnect.user_roles ur ON ur.user_id = gp.user_id
                WHERE gp.graph_id = $1
                ORDER BY gp.created_at ASC
                """,
                graph_id,
            )
            return [dict(r) for r in rows]

    @staticmethod
    async def revoke_graph_permission(graph_id: str, user_id: str) -> bool:
        """Revoke a user's permission for a specific graph."""
        async with get_db_connection() as conn:
            result = await conn.execute(
                """
                DELETE FROM langconnect.graph_permissions
                WHERE graph_id = $1 AND user_id = $2
                """,
                graph_id,
                user_id,
            )
            # Check if any rows were deleted
            if isinstance(result, str) and result.split()[-1].isdigit():
                return int(result.split()[-1]) > 0
            return False

    @staticmethod
    async def cleanup_graph_permissions(graph_id: str, dry_run: bool = True) -> int:
        async with get_db_connection() as conn:
            if dry_run:
                count = await conn.fetchval(
                    "SELECT COUNT(*) FROM langconnect.graph_permissions WHERE graph_id = $1",
                    graph_id,
                )
                return count or 0
            result = await conn.execute(
                "DELETE FROM langconnect.graph_permissions WHERE graph_id = $1",
                graph_id,
            )
            return int(result.split()[-1]) if isinstance(result, str) and result.split()[-1].isdigit() else 0

    @staticmethod
    async def cleanup_assistant_permissions_for_graph(graph_id: str, dry_run: bool = True) -> int:
        async with get_db_connection() as conn:
            if dry_run:
                count = await conn.fetchval(
                    """
                    SELECT COUNT(*)
                    FROM langconnect.assistant_permissions ap
                    WHERE ap.assistant_id = ANY(
                        SELECT assistant_id::text FROM langconnect.assistants_mirror WHERE graph_id = $1
                    )
                    """,
                    graph_id,
                )
                return count or 0
            result = await conn.execute(
                """
                DELETE FROM langconnect.assistant_permissions ap
                WHERE ap.assistant_id = ANY(
                    SELECT assistant_id::text FROM langconnect.assistants_mirror WHERE graph_id = $1
                )
                """,
                graph_id,
            )
            return int(result.split()[-1]) if isinstance(result, str) and result.split()[-1].isdigit() else 0

    @staticmethod
    async def cleanup_assistant_metadata_for_graph(graph_id: str, dry_run: bool = True) -> int:
        async with get_db_connection() as conn:
            if dry_run:
                count = await conn.fetchval(
                    "SELECT COUNT(*) FROM langconnect.assistants_mirror WHERE graph_id = $1",
                    graph_id,
                )
                return count or 0
            result = await conn.execute(
                "DELETE FROM langconnect.assistants_mirror WHERE graph_id = $1",
                graph_id,
            )
            return int(result.split()[-1]) if isinstance(result, str) and result.split()[-1].isdigit() else 0

    @staticmethod
    async def get_orphaned_assistants_for_graph(graph_id: str) -> List[Dict[str, Any]]:
        async with get_db_connection() as conn:
            rows = await conn.fetch(
                """
                SELECT assistant_id::text AS assistant_id, name AS display_name
                FROM langconnect.assistants_mirror
                WHERE graph_id = $1
                ORDER BY langgraph_created_at DESC NULLS LAST
                """,
                graph_id,
            )
            return [dict(r) for r in rows]


class AssistantPermissionsManager:
    """Facade exposing assistant permission operations."""

    @staticmethod
    async def get_assistant_metadata(assistant_id: str) -> Optional[Dict[str, Any]]:
        async with get_db_connection() as conn:
            row = await conn.fetchrow(
                """
                SELECT
                  am.assistant_id::text AS assistant_id,
                  am.graph_id,
                  am.name AS display_name,
                  am.description,
                  am.langgraph_created_at AS created_at,
                  am.langgraph_updated_at AS updated_at,
                  owner_perm.user_id AS owner_id,
                  ur.display_name AS owner_display_name
                FROM langconnect.assistants_mirror am
                LEFT JOIN LATERAL (
                  SELECT user_id
                  FROM langconnect.assistant_permissions p
                  WHERE p.assistant_id = am.assistant_id AND p.permission_level = 'owner'
                  ORDER BY p.created_at ASC
                  LIMIT 1
                ) AS owner_perm ON TRUE
                LEFT JOIN langconnect.user_roles ur ON owner_perm.user_id = ur.user_id
                WHERE am.assistant_id = $1::uuid
                """,
                assistant_id,
            )
            return dict(row) if row else None

    @staticmethod
    async def register_assistant(
        assistant_id: str,
        graph_id: str,
        owner_id: str,
        display_name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> bool:
        async with get_db_connection() as conn:
            await conn.execute(
                """
                INSERT INTO langconnect.assistant_permissions (assistant_id, user_id, permission_level, granted_by)
                VALUES ($1, $2, 'owner', 'system')
                ON CONFLICT (assistant_id, user_id) DO NOTHING
                """,
                assistant_id,
                owner_id,
            )
        return True

    @staticmethod
    async def get_user_permission_for_assistant(user_id: str, assistant_id: str) -> Optional[str]:
        async with get_db_connection() as conn:
            row = await conn.fetchrow(
                """
                SELECT permission_level
                FROM langconnect.assistant_permissions
                WHERE user_id = $1 AND assistant_id = $2
                """,
                user_id,
                assistant_id,
            )
        return row["permission_level"] if row else None

    @staticmethod
    async def grant_assistant_permission(
        assistant_id: str,
        user_id: str,
        permission_level: str,
        granted_by: str = "system:public",
    ) -> bool:
        async with get_db_connection() as conn:
            result = await conn.execute(
                """
                INSERT INTO langconnect.assistant_permissions (assistant_id, user_id, permission_level, granted_by)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (assistant_id, user_id) DO UPDATE SET
                  permission_level = EXCLUDED.permission_level,
                  granted_by = EXCLUDED.granted_by,
                  updated_at = NOW()
                """,
                assistant_id,
                user_id,
                permission_level,
                granted_by,
            )
            return True if isinstance(result, str) else False

    @staticmethod
    async def get_assistant_permissions(assistant_id: str) -> List[Dict[str, Any]]:
        """Get all permissions for a specific assistant (no auth check - for admin/mirror use)."""
        async with get_db_connection() as conn:
            query = """
                SELECT 
                    ap.id,
                    ap.assistant_id::text as assistant_id,
                    ap.user_id,
                    ur.email,
                    ur.display_name,
                    ap.permission_level,
                    ap.granted_by,
                    ap.created_at,
                    ap.updated_at
                FROM langconnect.assistant_permissions ap
                LEFT JOIN langconnect.user_roles ur ON ap.user_id = ur.user_id
                WHERE ap.assistant_id = $1::uuid
                ORDER BY ap.permission_level DESC, ap.created_at ASC
            """
            results = await conn.fetch(query, assistant_id)
            return [dict(result) for result in results]

    @staticmethod
    async def get_user_accessible_assistants(user_id: str) -> List[Dict[str, Any]]:
        """Get all assistants a user has access to with metadata."""
        async with get_db_connection() as conn:
            query = """
                SELECT 
                    ap.assistant_id::text as assistant_id,
                    am.graph_id,
                    am.name AS display_name,
                    am.description,
                    ap.permission_level,
                    owner_perm.user_id AS owner_id,
                    ur.email AS owner_email,
                    ur.display_name AS owner_display_name,
                    am.langgraph_created_at AS assistant_created_at,
                    am.langgraph_updated_at AS assistant_updated_at
                FROM langconnect.assistant_permissions ap
                JOIN langconnect.assistants_mirror am ON ap.assistant_id = am.assistant_id
                LEFT JOIN LATERAL (
                    SELECT user_id
                    FROM langconnect.assistant_permissions p
                    WHERE p.assistant_id = am.assistant_id AND p.permission_level = 'owner'
                    ORDER BY p.created_at ASC
                    LIMIT 1
                ) AS owner_perm ON TRUE
                LEFT JOIN langconnect.user_roles ur ON owner_perm.user_id = ur.user_id
                WHERE ap.user_id = $1
                ORDER BY am.langgraph_created_at DESC NULLS LAST
            """
            results = await conn.fetch(query, user_id)
            return [dict(result) for result in results]

    @staticmethod
    async def revoke_assistant_permission(assistant_id: str, user_id: str) -> bool:
        """Revoke a specific user's permission for an assistant."""
        async with get_db_connection() as conn:
            result = await conn.execute(
                """
                DELETE FROM langconnect.assistant_permissions
                WHERE assistant_id = $1::uuid AND user_id = $2
                """,
                assistant_id,
                user_id
            )
            # Check if any rows were deleted
            if isinstance(result, str) and result.split()[-1].isdigit():
                return int(result.split()[-1]) > 0
            return False

    @staticmethod
    async def delete_assistant_permissions(assistant_id: str) -> bool:
        """Delete all permissions for an assistant."""
        async with get_db_connection() as conn:
            result = await conn.execute(
                "DELETE FROM langconnect.assistant_permissions WHERE assistant_id = $1::uuid",
                assistant_id
            )
            # Check if any rows were deleted
            if isinstance(result, str) and result.split()[-1].isdigit():
                return int(result.split()[-1]) > 0
            return False

    @staticmethod
    async def delete_assistant_metadata(assistant_id: str) -> bool:
        """Delete assistant metadata from mirror."""
        async with get_db_connection() as conn:
            result = await conn.execute(
                "DELETE FROM langconnect.assistants_mirror WHERE assistant_id = $1::uuid",
                assistant_id
            )
            # Check if any rows were deleted
            if isinstance(result, str) and result.split()[-1].isdigit():
                return int(result.split()[-1]) > 0
            return False

    @staticmethod
    async def get_all_public_assistant_permissions() -> List[Dict[str, Any]]:
        """Get all public assistant permissions, including revoked ones."""
        async with get_db_connection() as conn:
            query = """
                SELECT 
                    pap.id,
                    pap.assistant_id,
                    pap.permission_level,
                    pap.created_at,
                    pap.revoked_at,
                    pap.revoke_mode,
                    pap.notes,
                    ur.email AS created_by_email,
                    ur.display_name AS created_by_display_name
                FROM langconnect.public_assistant_permissions pap
                LEFT JOIN langconnect.user_roles ur ON pap.created_by::text = ur.user_id
                ORDER BY pap.created_at DESC
            """
            results = await conn.fetch(query)
            return [dict(row) for row in results]

    @staticmethod
    async def revoke_public_assistant_permission(assistant_id: str, mode: str) -> Dict[str, Any]:
        """Revoke a public permission for an assistant.

        Args:
            assistant_id: The ID of the assistant.
            mode: The revocation mode ('revoke_all' or 'future_only').

        Returns:
            A dictionary with a summary of the revocation.
        """
        if mode not in ['revoke_all', 'future_only']:
            raise ValueError("Invalid revocation mode. Must be 'revoke_all' or 'future_only'.")

        async with get_db_connection() as conn:
            async with conn.transaction():
                update_query = """
                    UPDATE langconnect.public_assistant_permissions
                    SET revoked_at = NOW(), revoke_mode = $1
                    WHERE assistant_id = $2 AND revoked_at IS NULL
                    RETURNING id
                """
                result = await conn.fetchrow(update_query, mode, assistant_id)

                if not result:
                    raise ValueError(f"No active public permission found for assistant_id: {assistant_id}")

                revoked_count = 0
                if mode == 'revoke_all':
                    delete_query = """
                        DELETE FROM langconnect.assistant_permissions
                        WHERE assistant_id = $1 AND granted_by = 'system:public'
                    """
                    delete_result = await conn.execute(delete_query, assistant_id)
                    if hasattr(delete_result, 'split'):
                        revoked_count = int(delete_result.split()[-1]) if delete_result.split()[-1].isdigit() else 0
                    else:
                        revoked_count = 0
                
                return {
                    "assistant_id": assistant_id,
                    "status": "revoked",
                    "mode": mode,
                    "revoked_user_count": revoked_count
                }
