"""
LangGraph Mirroring and Sync Service

This service maintains faithful mirrors of LangGraph data in LangConnect tables:
- graphs_mirror: Derived graph state from assistants by graph_id
- assistants_mirror: Exact copy of LangGraph assistants
- assistant_schemas: Cached schemas for fast UI decisions
- threads_mirror: Minimal thread metadata (no messages)

The sync service provides:
- Immediate targeted syncs after LangConnect-mediated mutations
- Background incremental sync to catch external changes
- Full reconciliation with cleanup of stale entries
"""

import logging
import time
import hashlib
import json
from typing import Dict, List, Set, Optional, Any, Tuple
from datetime import datetime, timezone
from uuid import UUID

from langconnect.database.connection import get_db_connection
from langconnect.services.langgraph_integration import LangGraphService

log = logging.getLogger(__name__)


def is_graph_template_assistant(assistant: Dict[str, Any]) -> bool:
    """
    Check if an assistant is a graph template assistant.

    Graph template assistants are created automatically by LangGraph to hold
    metadata and schemas for each graph template. They serve as the source of
    truth for graph configuration schemas and template information.

    They ARE synced to the mirror for template lookups and schema extraction,
    but won't appear in user-facing assistant lists due to permission filtering.

    Args:
        assistant: Assistant dictionary from LangGraph

    Returns:
        True if assistant is a graph template assistant (created_by === "system"), False otherwise
    """
    metadata = assistant.get("metadata", {})
    return metadata.get("created_by") == "system"


class LangGraphSyncService:
    """Service for synchronizing LangGraph data into mirror tables."""
    
    def __init__(self, langgraph_service: LangGraphService):
        self.langgraph_service = langgraph_service
    
    async def compute_assistant_hash(self, assistant: Dict[str, Any]) -> str:
        """Compute a stable hash of assistant fields for change detection."""
        # Extract significant fields that matter for sync
        name = assistant.get("name", "")
        config = assistant.get("config", {})
        metadata = assistant.get("metadata", {})
        description = assistant.get("description", metadata.get("description", ""))
        context = assistant.get("context", {})
        version = assistant.get("version", 1)
        created_at = assistant.get("created_at", "")
        updated_at = assistant.get("updated_at", "")
        
        # Create stable string representation
        hash_input = (
            str(name) +
            str(config) +
            str(metadata) +
            str(description) +
            str(context) +
            str(version) +
            str(created_at) +
            str(updated_at)
        )
        
        return hashlib.sha256(hash_input.encode()).hexdigest()
    
    async def sync_assistant_schemas(self, assistant_id: str, *, user_token: Optional[str] = None) -> bool:
        """
        Fetch and cache schemas for a specific assistant.

        Args:
            assistant_id: Assistant to fetch schemas for

        Returns:
            True if schemas were updated, False if unchanged or error
        """
        try:
            log.info(f"Syncing schemas for assistant {assistant_id}")

            # Fetch schemas from LangGraph
            schemas_data = await self.langgraph_service._make_request(
                "GET",
                f"assistants/{assistant_id}/schemas",
                user_token=user_token,
            )

            if not schemas_data:
                log.warning(f"No schemas returned for assistant {assistant_id}")
                return False

            # Extract schema components
            input_schema = schemas_data.get("input_schema")
            config_schema = schemas_data.get("config_schema")
            state_schema = schemas_data.get("state_schema")

            # Upsert schemas using database function
            async with get_db_connection() as conn:
                result = await conn.fetchval(
                    "SELECT langconnect.upsert_assistant_schemas($1, $2, $3, $4)",
                    assistant_id,
                    json.dumps(input_schema) if input_schema is not None else None,
                    json.dumps(config_schema) if config_schema is not None else None,
                    json.dumps(state_schema) if state_schema is not None else None
                )

                if result:
                    log.info(f"Updated schemas for assistant {assistant_id}")
                    return True
                else:
                    log.debug(f"Schemas unchanged for assistant {assistant_id}")
                    return False

        except Exception as e:
            log.error(f"Failed to sync schemas for assistant {assistant_id}: {e}")
            return False

    async def sync_graph_schemas(self, graph_id: str, *, user_token: Optional[str] = None) -> bool:
        """
        Fetch and cache schemas for a graph from its graph template assistant.

        Args:
            graph_id: Graph to fetch schemas for
            user_token: Optional user token for auth

        Returns:
            True if schemas were updated, False if unchanged or error
        """
        try:
            log.info(f"Syncing graph schemas for {graph_id}")

            # Find the graph template assistant for this graph
            async with get_db_connection() as conn:
                system_assistant_row = await conn.fetchrow(
                    """
                    SELECT assistant_id
                    FROM langconnect.assistants_mirror
                    WHERE graph_id = $1
                    AND metadata->>'created_by' = 'system'
                    LIMIT 1
                    """,
                    graph_id
                )

            if not system_assistant_row:
                log.warning(f"No graph template assistant found for graph {graph_id}")
                return False

            system_assistant_id = str(system_assistant_row["assistant_id"])

            # Fetch schemas from the graph template assistant
            schemas_data = await self.langgraph_service._make_request(
                "GET",
                f"assistants/{system_assistant_id}/schemas",
                user_token=user_token,
            )

            if not schemas_data:
                log.warning(f"No schemas returned for graph template assistant {system_assistant_id} (graph {graph_id})")
                return False

            # Extract schema components
            input_schema = schemas_data.get("input_schema")
            config_schema = schemas_data.get("config_schema")
            state_schema = schemas_data.get("state_schema")

            # Upsert graph schemas using database function
            async with get_db_connection() as conn:
                result = await conn.fetchval(
                    "SELECT langconnect.upsert_graph_schemas($1, $2, $3, $4)",
                    graph_id,
                    json.dumps(input_schema) if input_schema is not None else None,
                    json.dumps(config_schema) if config_schema is not None else None,
                    json.dumps(state_schema) if state_schema is not None else None
                )

                if result:
                    log.info(f"Updated graph schemas for {graph_id}")
                    return True
                else:
                    log.debug(f"Graph schemas unchanged for {graph_id}")
                    return False

        except Exception as e:
            log.error(f"Failed to sync graph schemas for {graph_id}: {e}")
            return False
    
    async def sync_all_schemas(self) -> Dict[str, Any]:
        """
        Sync schemas for all assistants in the mirror.
        
        Returns:
            Stats dictionary with sync results
        """
        try:
            log.info("Starting schema sync for all assistants")
            start_time = time.time()
            
            # Get all assistant IDs from mirror
            async with get_db_connection() as conn:
                assistant_ids = await conn.fetch(
                    "SELECT assistant_id FROM langconnect.assistants_mirror ORDER BY assistant_id"
                )
            
            total_assistants = len(assistant_ids)
            schema_updates = 0
            errors = []
            
            # Sync schemas for each assistant
            for row in assistant_ids:
                assistant_id = str(row['assistant_id'])
                try:
                    updated = await self.sync_assistant_schemas(assistant_id)
                    if updated:
                        schema_updates += 1
                except Exception as e:
                    error_msg = f"Failed to sync schemas for {assistant_id}: {e}"
                    log.error(error_msg)
                    errors.append(error_msg)
            
            duration_ms = int((time.time() - start_time) * 1000)
            
            stats = {
                "total_assistants": total_assistants,
                "schema_updates": schema_updates,
                "unchanged_schemas": total_assistants - schema_updates - len(errors),
                "errors": errors,
                "duration_ms": duration_ms,
                "sync_type": "schemas_only"
            }
            
            log.info(f"Schema sync completed: {schema_updates} updates, {len(errors)} errors in {duration_ms}ms")
            return stats
            
        except Exception as e:
            error_msg = f"Schema sync failed: {e}"
            log.error(error_msg)
            return {"error": error_msg}
    
    async def sync_assistant(self, assistant_id: str, *, user_token: Optional[str] = None) -> bool:
        """
        Sync a specific assistant from LangGraph to mirror.

        Args:
            assistant_id: Assistant to sync

        Returns:
            True if assistant was updated, False if unchanged or error
        """
        try:
            log.info(f"Syncing assistant {assistant_id}")

            # Fetch assistant from LangGraph
            assistant_data = await self.langgraph_service._make_request(
                "GET",
                f"assistants/{assistant_id}",
                user_token=user_token,
            )

            if not assistant_data:
                log.warning(f"Assistant {assistant_id} not found in LangGraph")
                return False

            # Parse timestamps
            created_at = datetime.fromisoformat(assistant_data.get("created_at", "").replace("Z", "+00:00"))
            updated_at = datetime.fromisoformat(assistant_data.get("updated_at", "").replace("Z", "+00:00"))
            
            # Upsert assistant directly with SQL (bypass function for now)
            async with get_db_connection() as conn:
                # Compute hash
                new_hash = await self.compute_assistant_hash(assistant_data)
                
                # Check if assistant exists
                existing_hash = await conn.fetchval(
                    "SELECT langgraph_hash FROM langconnect.assistants_mirror WHERE assistant_id = $1",
                    UUID(assistant_id)
                )
                
                assistant_updated = False
                
                # Only update if hash changed or assistant doesn't exist
                if existing_hash is None or existing_hash != new_hash:
                    # Ensure graph exists first
                    await conn.execute(
                        "INSERT INTO langconnect.graphs_mirror (graph_id) VALUES ($1) ON CONFLICT (graph_id) DO NOTHING",
                        assistant_data.get("graph_id")
                    )

                    # Extract tags from metadata (LangGraph workaround pattern)
                    # LangGraph SDK doesn't support native tags, so frontend stores them
                    # in metadata._x_oap_tags. We extract here and populate the database
                    # tags column for fast queries without hitting LangGraph API.
                    metadata = assistant_data.get("metadata", {})
                    tags = metadata.get("_x_oap_tags", [])

                    # Upsert assistant
                    await conn.execute(
                        """
                        INSERT INTO langconnect.assistants_mirror (
                            assistant_id, graph_id, name, description, tags, config, metadata, context, version,
                            langgraph_created_at, langgraph_updated_at, langgraph_hash, last_seen_at
                        ) VALUES (
                            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, NOW()
                        )
                        ON CONFLICT (assistant_id) DO UPDATE SET
                            graph_id = EXCLUDED.graph_id,
                            name = EXCLUDED.name,
                            description = EXCLUDED.description,
                            tags = EXCLUDED.tags,
                            config = EXCLUDED.config,
                            metadata = EXCLUDED.metadata,
                            context = EXCLUDED.context,
                            version = EXCLUDED.version,
                            langgraph_created_at = EXCLUDED.langgraph_created_at,
                            langgraph_updated_at = EXCLUDED.langgraph_updated_at,
                            langgraph_hash = EXCLUDED.langgraph_hash,
                            last_seen_at = EXCLUDED.last_seen_at,
                            mirror_updated_at = NOW(),
                            updated_at = NOW()
                        """,
                        UUID(assistant_id),
                        assistant_data.get("graph_id"),
                        assistant_data.get("name"),
                        assistant_data.get("description", assistant_data.get("metadata", {}).get("description")),
                        tags,  # Add tags
                        json.dumps(assistant_data.get("config", {})),
                        json.dumps(assistant_data.get("metadata", {})),
                        json.dumps(assistant_data.get("context", {})),
                        assistant_data.get("version", 1),
                        created_at,
                        updated_at,
                        new_hash
                    )
                    
                    # Increment assistants version
                    await conn.fetchval("SELECT langconnect.increment_cache_version('assistants')")
                    assistant_updated = True
                else:
                    # Just update last_seen_at
                    await conn.execute(
                        "UPDATE langconnect.assistants_mirror SET last_seen_at = NOW() WHERE assistant_id = $1",
                        UUID(assistant_id)
                    )
            
            # If assistant was updated, also sync schemas
            schemas_updated = False
            if assistant_updated:
                schemas_updated = await self.sync_assistant_schemas(assistant_id, user_token=user_token)
            
            # Refresh graph mirror for this graph
            graph_id = assistant_data.get("graph_id")
            if graph_id:
                async with get_db_connection() as conn:
                    await conn.fetchval(
                        "SELECT langconnect.refresh_graph_mirror($1)",
                        graph_id
                    )
            
            if assistant_updated:
                log.info(f"Successfully synced assistant {assistant_id} (schemas: {'updated' if schemas_updated else 'unchanged'})")
            
            return assistant_updated
            
        except Exception as e:
            log.error(f"Failed to sync assistant {assistant_id}: {e}")
            return False
    
    async def sync_assistants_incremental(self, limit: int = 1000, *, user_token: Optional[str] = None) -> Dict[str, Any]:
        """
        Perform incremental sync of assistants from LangGraph.
        
        Compares existing mirror data with LangGraph and only updates changed assistants.
        
        Args:
            limit: Maximum assistants to fetch from LangGraph
            
        Returns:
            Sync statistics
        """
        start_time = time.time()
        
        try:
            log.info(f"Starting incremental assistant sync (limit: {limit})")
            
            # Fetch all assistants from LangGraph
            assistants_data = await self.langgraph_service._make_request(
                "POST",
                "assistants/search",
                data={
                    "limit": limit,
                    "offset": 0,
                    "sort_by": "updated_at",
                    "sort_order": "desc"
                },
                user_token=user_token,
            )
            
            assistants = assistants_data if isinstance(assistants_data, list) else assistants_data.get("assistants", [])
            log.info(f"Found {len(assistants)} assistants in LangGraph")

            # Count graph template vs user assistants for logging
            template_count = sum(1 for a in assistants if is_graph_template_assistant(a))
            user_count = len(assistants) - template_count
            log.info(f"Breakdown: {user_count} user assistants, {template_count} graph template assistants")

            # Note: We sync ALL assistants (including graph templates) to the mirror
            # Graph template assistants are needed for template schema lookups and discovery
            # They won't appear in user-facing lists due to permission filtering

            # Get existing mirror data for comparison
            async with get_db_connection() as conn:
                existing_mirrors = await conn.fetch(
                    """
                    SELECT assistant_id, langgraph_hash, langgraph_updated_at
                    FROM langconnect.assistants_mirror
                    """
                )
            
            existing_map = {
                str(row["assistant_id"]): {
                    "hash": row["langgraph_hash"],
                    "updated_at": row["langgraph_updated_at"]
                }
                for row in existing_mirrors
            }
            
            # Track sync statistics
            stats = {
                "total_langgraph": len(assistants),
                "total_existing": len(existing_map),
                "new_assistants": 0,
                "updated_assistants": 0,
                "unchanged_assistants": 0,
                "schema_updates": 0,
                "graph_updates": 0,
                "errors": []
            }
            
            # Process each assistant
            seen_assistant_ids = set()
            graphs_to_refresh = set()
            
            for assistant in assistants:
                assistant_id = assistant.get("assistant_id")
                if not assistant_id:
                    continue
                    
                seen_assistant_ids.add(assistant_id)
                graph_id = assistant.get("graph_id")
                if graph_id:
                    graphs_to_refresh.add(graph_id)
                
                try:
                    # Compute hash for change detection
                    new_hash = await self.compute_assistant_hash(assistant)
                    existing = existing_map.get(assistant_id)
                    
                    # Check if update needed
                    needs_update = (
                        not existing or 
                        existing["hash"] != new_hash
                    )
                    
                    if needs_update:
                        # Parse timestamps
                        created_at = datetime.fromisoformat(assistant.get("created_at", "").replace("Z", "+00:00"))
                        updated_at = datetime.fromisoformat(assistant.get("updated_at", "").replace("Z", "+00:00"))
                        
                        # Upsert assistant directly
                        async with get_db_connection() as conn:
                            # Ensure graph exists first
                            await conn.execute(
                                "INSERT INTO langconnect.graphs_mirror (graph_id) VALUES ($1) ON CONFLICT (graph_id) DO NOTHING",
                                graph_id
                            )

                            # Extract tags from metadata (LangGraph workaround pattern)
                            # LangGraph SDK doesn't support native tags, so frontend stores them
                            # in metadata._x_oap_tags. We extract here and populate the database
                            # tags column for fast queries without hitting LangGraph API.
                            metadata = assistant.get("metadata", {})
                            tags = metadata.get("_x_oap_tags", [])

                            # Upsert assistant (include description; prefer top-level, fallback to metadata.description)
                            await conn.execute(
                                """
                                INSERT INTO langconnect.assistants_mirror (
                                    assistant_id, graph_id, name, description, tags, config, metadata, context, version,
                                    langgraph_created_at, langgraph_updated_at, langgraph_hash, last_seen_at
                                ) VALUES (
                                    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, NOW()
                                )
                                ON CONFLICT (assistant_id) DO UPDATE SET
                                    graph_id = EXCLUDED.graph_id,
                                    name = EXCLUDED.name,
                                    description = EXCLUDED.description,
                                    tags = EXCLUDED.tags,
                                    config = EXCLUDED.config,
                                    metadata = EXCLUDED.metadata,
                                    context = EXCLUDED.context,
                                    version = EXCLUDED.version,
                                    langgraph_created_at = EXCLUDED.langgraph_created_at,
                                    langgraph_updated_at = EXCLUDED.langgraph_updated_at,
                                    langgraph_hash = EXCLUDED.langgraph_hash,
                                    last_seen_at = EXCLUDED.last_seen_at,
                                    mirror_updated_at = NOW(),
                                    updated_at = NOW()
                                """,
                                UUID(assistant_id),
                                graph_id,
                                assistant.get("name"),
                                assistant.get("description", assistant.get("metadata", {}).get("description")),
                                tags,  # Add tags
                                json.dumps(assistant.get("config", {})),
                                json.dumps(assistant.get("metadata", {})),
                                json.dumps(assistant.get("context", {})),
                                assistant.get("version", 1),
                                created_at,
                                updated_at,
                                new_hash
                            )
                            
                            # Increment version
                            await conn.fetchval("SELECT langconnect.increment_cache_version('assistants')")
                            assistant_updated = True
                        
                        if assistant_updated:
                            if not existing:
                                stats["new_assistants"] += 1
                            else:
                                stats["updated_assistants"] += 1
                            
                            # Sync schemas for updated assistants
                            schema_updated = await self.sync_assistant_schemas(assistant_id, user_token=user_token)
                            if schema_updated:
                                stats["schema_updates"] += 1
                        else:
                            stats["unchanged_assistants"] += 1
                    else:
                        stats["unchanged_assistants"] += 1
                        
                        # Update last_seen_at for unchanged assistants
                        async with get_db_connection() as conn:
                            await conn.execute(
                                """
                                UPDATE langconnect.assistants_mirror 
                                SET last_seen_at = NOW() 
                                WHERE assistant_id = $1
                                """,
                                UUID(assistant_id)
                            )
                
                except Exception as e:
                    error_msg = f"Failed to sync assistant {assistant_id}: {str(e)}"
                    log.error(error_msg)
                    stats["errors"].append(error_msg)

            # Refresh graph mirrors for affected graphs and populate metadata
            for graph_id in graphs_to_refresh:
                try:
                    async with get_db_connection() as conn:
                        graph_updated = await conn.fetchval(
                            "SELECT langconnect.refresh_graph_mirror($1)",
                            graph_id
                        )
                        if graph_updated:
                            stats["graph_updates"] += 1

                    # Sync graph schemas from graph template assistant
                    try:
                        await self.sync_graph_schemas(graph_id, user_token=user_token)
                    except Exception as e:
                        log.warning(f"Failed to sync graph schemas for {graph_id}: {e}")

                    async with get_db_connection() as conn:
                        # Always try to populate graph metadata from LangGraph API
                        # This ensures metadata is populated on first sync and kept updated
                        try:
                            from langconnect.api.graph_actions.discovery_utils import get_graph_metadata_from_api

                            name, description = await get_graph_metadata_from_api(self.langgraph_service, graph_id)
                            if name and description:
                                # Check if graph has default/placeholder metadata that needs updating
                                # Default descriptions follow pattern "Agent graph: {Name}"
                                graph_row = await conn.fetchrow(
                                    "SELECT name, description FROM langconnect.graphs_mirror WHERE graph_id = $1",
                                    graph_id
                                )

                                should_update = False
                                if graph_row:
                                    # Update if description is missing or looks like a default placeholder
                                    current_desc = graph_row["description"]
                                    is_placeholder = (
                                        not current_desc or
                                        current_desc.startswith("Agent graph:")
                                    )
                                    if is_placeholder:
                                        should_update = True

                                if should_update:
                                    await conn.execute(
                                        """
                                        UPDATE langconnect.graphs_mirror
                                        SET name = $1,
                                            description = $2,
                                            schema_accessible = TRUE,
                                            updated_at = NOW()
                                        WHERE graph_id = $3
                                        """,
                                        name,
                                        description,
                                        graph_id
                                    )
                                    log.info(f"Populated metadata for graph {graph_id}: {name}")
                        except Exception as e:
                            log.warning(f"Failed to populate metadata for graph {graph_id}: {e}")

                except Exception as e:
                    error_msg = f"Failed to refresh graph mirror {graph_id}: {str(e)}"
                    log.error(error_msg)
                    stats["errors"].append(error_msg)
            
            # Mark unseen assistants (not in current LangGraph response)
            unseen_count = 0
            async with get_db_connection() as conn:
                if seen_assistant_ids:
                    # Update last_seen_at for assistants not in this sync
                    result = await conn.execute(
                        """
                        UPDATE langconnect.assistants_mirror 
                        SET last_seen_at = last_seen_at
                        WHERE assistant_id NOT IN (
                            SELECT unnest($1::uuid[])
                        )
                        """,
                        [UUID(aid) for aid in seen_assistant_ids]
                    )
                    # Note: We don't automatically delete unseen assistants - use cleanup endpoint
            
            duration_ms = int((time.time() - start_time) * 1000)
            stats["duration_ms"] = duration_ms
            
            log.info(f"Incremental sync completed: {stats['new_assistants']} new, {stats['updated_assistants']} updated, {stats['unchanged_assistants']} unchanged, {len(stats['errors'])} errors in {duration_ms}ms")
            
            return stats
            
        except Exception as e:
            log.error(f"Failed to perform incremental sync: {e}")
            return {
                "error": str(e),
                "duration_ms": int((time.time() - start_time) * 1000)
            }
    
    async def sync_all_full(self, limit: int = 1000, *, user_token: Optional[str] = None) -> Dict[str, Any]:
        """
        Perform full sync of all assistants and graphs from LangGraph.
        
        This is a more thorough sync that ensures completeness and can mark
        assistants/graphs as inactive if they haven't been seen.
        
        Args:
            limit: Maximum assistants to fetch from LangGraph
            
        Returns:
            Sync statistics
        """
        start_time = time.time()
        
        try:
            log.info(f"Starting full sync (limit: {limit})")
            
            # Use incremental sync as the base
            stats = await self.sync_assistants_incremental(limit, user_token=user_token)
            
            # Add full sync specific operations
            async with get_db_connection() as conn:
                # Mark graphs with zero assistants as potentially inactive
                # (but don't delete - let admin cleanup handle that)
                inactive_graphs = await conn.fetch(
                    """
                    UPDATE langconnect.graphs_mirror
                    SET assistants_count = 0,
                        mirror_updated_at = NOW(),
                        updated_at = NOW()
                    WHERE graph_id NOT IN (
                        SELECT DISTINCT graph_id 
                        FROM langconnect.assistants_mirror 
                        WHERE last_seen_at > NOW() - INTERVAL '1 hour'
                    )
                    AND assistants_count > 0
                    RETURNING graph_id
                    """
                )
                
                stats["inactive_graphs"] = len(inactive_graphs)
                if inactive_graphs:
                    inactive_graph_ids = [row["graph_id"] for row in inactive_graphs]
                    log.info(f"Marked {len(inactive_graphs)} graphs as having zero assistants: {inactive_graph_ids}")
            
            # Update sync timestamp
            async with get_db_connection() as conn:
                await conn.execute(
                    "UPDATE langconnect.cache_state SET last_synced_at = NOW() WHERE id = 1"
                )
            
            stats["sync_type"] = "full"
            stats["duration_ms"] = int((time.time() - start_time) * 1000)
            
            log.info(f"Full sync completed in {stats['duration_ms']}ms")
            return stats
            
        except Exception as e:
            log.error(f"Failed to perform full sync: {e}")
            return {
                "error": str(e),
                "sync_type": "full",
                "duration_ms": int((time.time() - start_time) * 1000)
            }
    
    async def sync_graph(self, graph_id: str, *, user_token: Optional[str] = None) -> Dict[str, Any]:
        """
        Sync all assistants for a specific graph.
        
        Args:
            graph_id: Graph to sync
            
        Returns:
            Sync statistics for the graph
        """
        start_time = time.time()
        
        try:
            log.info(f"Syncing graph {graph_id}")
            
            # Fetch assistants for this graph from LangGraph
            assistants_data = await self.langgraph_service._make_request(
                "POST",
                "assistants/search",
                data={
                    "graph_id": graph_id,
                    "limit": 1000,
                    "offset": 0
                },
                user_token=user_token,
            )
            
            assistants = assistants_data if isinstance(assistants_data, list) else assistants_data.get("assistants", [])
            log.info(f"Found {len(assistants)} assistants for graph {graph_id}")

            # Count graph template vs user assistants
            template_count = sum(1 for a in assistants if is_graph_template_assistant(a))
            user_count = len(assistants) - template_count
            log.info(f"Breakdown: {user_count} user assistants, {template_count} graph template assistants")

            stats = {
                "graph_id": graph_id,
                "assistants_found": len(assistants),
                "assistants_synced": 0,
                "schemas_synced": 0,
                "errors": []
            }

            # Sync each assistant
            for assistant in assistants:
                assistant_id = assistant.get("assistant_id")
                if not assistant_id:
                    continue
                
                try:
                    # Parse timestamps
                    created_at = datetime.fromisoformat(assistant.get("created_at", "").replace("Z", "+00:00"))
                    updated_at = datetime.fromisoformat(assistant.get("updated_at", "").replace("Z", "+00:00"))
                    
                    # Upsert assistant directly
                    async with get_db_connection() as conn:
                        # Compute hash
                        new_hash = await self.compute_assistant_hash(assistant)
                        
                        # Ensure graph exists first
                        await conn.execute(
                            "INSERT INTO langconnect.graphs_mirror (graph_id) VALUES ($1) ON CONFLICT (graph_id) DO NOTHING",
                            graph_id
                        )

                        # Extract tags from metadata (LangGraph workaround pattern)
                        # LangGraph SDK doesn't support native tags, so frontend stores them
                        # in metadata._x_oap_tags. We extract here and populate the database
                        # tags column for fast queries without hitting LangGraph API.
                        metadata = assistant.get("metadata", {})
                        tags = metadata.get("_x_oap_tags", [])

                        # Upsert assistant
                        await conn.execute(
                            """
                            INSERT INTO langconnect.assistants_mirror (
                                assistant_id, graph_id, name, description, tags, config, metadata, context, version,
                                langgraph_created_at, langgraph_updated_at, langgraph_hash, last_seen_at
                            ) VALUES (
                                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, NOW()
                            )
                            ON CONFLICT (assistant_id) DO UPDATE SET
                                graph_id = EXCLUDED.graph_id,
                                name = EXCLUDED.name,
                                description = EXCLUDED.description,
                                tags = EXCLUDED.tags,
                                config = EXCLUDED.config,
                                metadata = EXCLUDED.metadata,
                                context = EXCLUDED.context,
                                version = EXCLUDED.version,
                                langgraph_created_at = EXCLUDED.langgraph_created_at,
                                langgraph_updated_at = EXCLUDED.langgraph_updated_at,
                                langgraph_hash = EXCLUDED.langgraph_hash,
                                last_seen_at = EXCLUDED.last_seen_at,
                                mirror_updated_at = NOW(),
                                updated_at = NOW()
                            """,
                            UUID(assistant_id),
                            graph_id,
                            assistant.get("name"),
                            assistant.get("description", assistant.get("metadata", {}).get("description")),
                            tags,  # Add tags
                            json.dumps(assistant.get("config", {})),
                            json.dumps(assistant.get("metadata", {})),
                            json.dumps(assistant.get("context", {})),
                            assistant.get("version", 1),
                            created_at,
                            updated_at,
                            new_hash
                        )
                        
                        # Increment version
                        await conn.fetchval("SELECT langconnect.increment_cache_version('assistants')")
                        assistant_updated = True
                    
                    if assistant_updated:
                        stats["assistants_synced"] += 1
                        
                        # Sync schemas for updated assistant
                        schema_updated = await self.sync_assistant_schemas(assistant_id)
                        if schema_updated:
                            stats["schemas_synced"] += 1
                
                except Exception as e:
                    error_msg = f"Failed to sync assistant {assistant_id}: {str(e)}"
                    log.error(error_msg)
                    stats["errors"].append(error_msg)
            
            # Refresh graph mirror
            async with get_db_connection() as conn:
                graph_updated = await conn.fetchval(
                    "SELECT langconnect.refresh_graph_mirror($1)",
                    graph_id
                )
                stats["graph_updated"] = graph_updated

            # Sync graph schemas from graph template assistant
            try:
                graph_schema_updated = await self.sync_graph_schemas(graph_id, user_token=user_token)
                stats["graph_schema_updated"] = graph_schema_updated
            except Exception as e:
                log.warning(f"Failed to sync graph schemas for {graph_id}: {e}")

            async with get_db_connection() as conn:
                # Populate graph metadata from LangGraph API if missing or placeholder
                try:
                    from langconnect.api.graph_actions.discovery_utils import get_graph_metadata_from_api

                    name, description = await get_graph_metadata_from_api(self.langgraph_service, graph_id)
                    if name and description:
                        # Check if graph has default/placeholder metadata
                        graph_row = await conn.fetchrow(
                            "SELECT name, description FROM langconnect.graphs_mirror WHERE graph_id = $1",
                            graph_id
                        )

                        should_update = False
                        if graph_row:
                            current_desc = graph_row["description"]
                            is_placeholder = (
                                not current_desc or
                                current_desc.startswith("Agent graph:")
                            )
                            if is_placeholder:
                                should_update = True

                        if should_update:
                            await conn.execute(
                                """
                                UPDATE langconnect.graphs_mirror
                                SET name = $1,
                                    description = $2,
                                    schema_accessible = TRUE,
                                    updated_at = NOW()
                                WHERE graph_id = $3
                                """,
                                name,
                                description,
                                graph_id
                            )
                            log.info(f"Populated metadata for graph {graph_id}: {name}")
                            stats["metadata_populated"] = True
                except Exception as e:
                    log.warning(f"Failed to populate metadata for graph {graph_id}: {e}")
            
            stats["duration_ms"] = int((time.time() - start_time) * 1000)
            
            log.info(f"Graph {graph_id} sync completed: {stats['assistants_synced']}/{stats['assistants_found']} assistants synced in {stats['duration_ms']}ms")
            
            return stats
            
        except Exception as e:
            log.error(f"Failed to sync graph {graph_id}: {e}")
            return {
                "graph_id": graph_id,
                "error": str(e),
                "duration_ms": int((time.time() - start_time) * 1000)
            }
    
    async def get_cache_state(self) -> Dict[str, Any]:
        """Get current cache state for version-aware frontend caching."""
        try:
            async with get_db_connection() as conn:
                result = await conn.fetchrow(
                    """
                    SELECT graphs_version, assistants_version, schemas_version, 
                           threads_version, last_synced_at
                    FROM langconnect.cache_state
                    WHERE id = 1
                    """
                )
                
                if result:
                    return {
                        "graphs_version": result["graphs_version"],
                        "assistants_version": result["assistants_version"], 
                        "schemas_version": result["schemas_version"],
                        "threads_version": result["threads_version"],
                        "last_synced_at": result["last_synced_at"].isoformat()
                    }
                else:
                    # Fallback if no cache state exists
                    return {
                        "graphs_version": 1,
                        "assistants_version": 1,
                        "schemas_version": 1,
                        "threads_version": 1,
                        "last_synced_at": datetime.now(timezone.utc).isoformat()
                    }
                    
        except Exception as e:
            log.error(f"Failed to get cache state: {e}")
            return {
                "error": str(e)
            }
    
    async def cleanup_stale_mirrors(self, grace_period_days: int = 7) -> Dict[str, Any]:
        """
        Clean up assistants and graphs that haven't been seen in LangGraph.
        
        Args:
            grace_period_days: Days to wait before considering items stale
            
        Returns:
            Cleanup statistics
        """
        try:
            log.info(f"Cleaning up mirrors with {grace_period_days} day grace period")
            
            async with get_db_connection() as conn:
                # Remove assistants not seen recently
                stale_assistants = await conn.fetch(
                    """
                    DELETE FROM langconnect.assistants_mirror
                    WHERE last_seen_at < NOW() - make_interval(days => $1)
                    RETURNING assistant_id, graph_id, name
                    """,
                    grace_period_days
                )
                
                # Remove graphs with no assistants
                stale_graphs = await conn.fetch(
                    """
                    DELETE FROM langconnect.graphs_mirror
                    WHERE assistants_count = 0 
                    AND langgraph_last_seen_at < NOW() - make_interval(days => $1)
                    RETURNING graph_id
                    """,
                    grace_period_days
                )
                
                # Remove orphaned schemas
                orphaned_schemas = await conn.fetch(
                    """
                    DELETE FROM langconnect.assistant_schemas
                    WHERE assistant_id NOT IN (
                        SELECT assistant_id FROM langconnect.assistants_mirror
                    )
                    RETURNING assistant_id
                    """
                )
            
            stats = {
                "stale_assistants_removed": len(stale_assistants),
                "stale_graphs_removed": len(stale_graphs),
                "orphaned_schemas_removed": len(orphaned_schemas),
                "grace_period_days": grace_period_days
            }
            
            if stale_assistants:
                log.info(f"Removed {len(stale_assistants)} stale assistants")
            if stale_graphs:
                log.info(f"Removed {len(stale_graphs)} stale graphs")
            if orphaned_schemas:
                log.info(f"Removed {len(orphaned_schemas)} orphaned schemas")
            
            return stats
            
        except Exception as e:
            log.error(f"Failed to cleanup stale mirrors: {e}")
            return {
                "error": str(e)
            }
    
    async def backfill_mirrors(self) -> Dict[str, Any]:
        """
        Initial backfill of mirror tables from current LangGraph state.
        
        This should be run once after migration deployment to populate the mirrors.
        
        Returns:
            Backfill statistics
        """
        log.info("Starting mirror backfill from LangGraph")
        
        # Perform a full sync to populate mirrors
        stats = await self.sync_all_full(limit=1000)
        
        # Mark as backfill operation
        stats["operation"] = "backfill"
        
        log.info(f"Mirror backfill completed: {stats}")
        return stats


# Dependency injection helper
def get_sync_service() -> LangGraphSyncService:
    """Get sync service instance."""
    from langconnect.services.langgraph_integration import get_langgraph_service
    return LangGraphSyncService(get_langgraph_service())
