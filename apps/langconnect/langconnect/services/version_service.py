"""
Assistant Version History Service

This service manages version history for assistants:
- Fetches versions from LangGraph SDK
- Mirrors versions to local database for fast reads
- Stores optional commit messages (local-only metadata)
- Restores previous versions by creating new versions with old config
"""

import logging
import json
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone
from uuid import UUID

from langconnect.database.connection import get_db_connection
from langconnect.services.langgraph_integration import LangGraphService
from langconnect.models.agent import (
    AssistantVersionInfo,
    AssistantVersionsResponse,
    AssistantRestoreResponse,
)

log = logging.getLogger(__name__)


class VersionService:
    """Service for managing assistant version history."""

    def __init__(self, langgraph_service: LangGraphService):
        self.langgraph_service = langgraph_service

    async def get_versions(
        self,
        assistant_id: str,
        *,
        user_token: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> AssistantVersionsResponse:
        """
        Fetch version history for an assistant.

        First tries to fetch from LangGraph Cloud (if available), then falls back
        to local-only version history. Local development servers don't support
        the versioning API.

        Args:
            assistant_id: Assistant to get versions for
            user_token: User JWT for LangGraph auth
            limit: Max versions to return
            offset: Pagination offset

        Returns:
            AssistantVersionsResponse with version list
        """
        try:
            log.info(f"Fetching versions for assistant {assistant_id}")

            # Get current assistant info for name and latest version
            current_assistant = await self.langgraph_service._make_request(
                "GET",
                f"assistants/{assistant_id}",
                user_token=user_token,
            )

            current_name = current_assistant.get("name", "Unknown") if current_assistant else "Unknown"
            current_version = current_assistant.get("version", 1) if current_assistant else 1

            # Try to fetch versions from LangGraph Cloud (may not be available in dev)
            langgraph_versions = []
            try:
                versions_data = await self.langgraph_service._make_request(
                    "GET",
                    f"assistants/{assistant_id}/versions",
                    user_token=user_token,
                )
                if versions_data:
                    if isinstance(versions_data, dict):
                        langgraph_versions = [versions_data]
                    else:
                        langgraph_versions = versions_data
                log.info(f"Got {len(langgraph_versions)} versions from LangGraph API")
            except Exception as lg_error:
                # LangGraph versioning API not available (e.g., local dev server)
                log.info(f"LangGraph versioning API not available, using local-only history: {lg_error}")

            # Get versions from local DB (may include versions not in LangGraph)
            enriched_versions = await self._get_local_versions_with_current(
                assistant_id,
                langgraph_versions,
                current_assistant,
                current_version,
            )

            # Apply pagination
            paginated_versions = enriched_versions[offset:offset + limit]

            return AssistantVersionsResponse(
                assistant_id=assistant_id,
                assistant_name=current_name,
                versions=paginated_versions,
                total_versions=len(enriched_versions),
                latest_version=current_version,
            )

        except Exception as e:
            log.error(f"Failed to get versions for assistant {assistant_id}: {e}")
            raise RuntimeError(f"Failed to get version history: {e}")

    async def _get_local_versions_with_current(
        self,
        assistant_id: str,
        langgraph_versions: List[Dict[str, Any]],
        current_assistant: Dict[str, Any],
        current_version: int,
    ) -> List[AssistantVersionInfo]:
        """
        Get versions from local DB, merging with LangGraph versions if available.
        Always includes the current version from the assistant.

        Args:
            assistant_id: Assistant ID
            langgraph_versions: Versions from LangGraph API (may be empty)
            current_assistant: Current assistant data
            current_version: Current version number

        Returns:
            List of AssistantVersionInfo sorted by version descending
        """
        versions_dict: Dict[int, AssistantVersionInfo] = {}

        async with get_db_connection() as conn:
            # Get all local versions with commit messages
            local_versions = await conn.fetch(
                """
                SELECT
                    av.version,
                    av.name,
                    av.description,
                    av.config,
                    av.metadata,
                    av.tags,
                    av.commit_message,
                    av.created_by,
                    av.langgraph_created_at,
                    ur.display_name as created_by_display_name
                FROM langconnect.assistant_versions av
                LEFT JOIN langconnect.user_roles ur ON av.created_by = ur.user_id
                WHERE av.assistant_id = $1
                ORDER BY av.version DESC
                """,
                UUID(assistant_id)
            )

            # Add local versions to dict
            for row in local_versions:
                version_num = row["version"]
                config = row["config"]
                if isinstance(config, str):
                    config = json.loads(config) if config else {}

                metadata = row["metadata"]
                if isinstance(metadata, str):
                    metadata = json.loads(metadata) if metadata else {}

                created_at = row["langgraph_created_at"]
                if created_at:
                    created_at_str = created_at.isoformat()
                else:
                    created_at_str = datetime.now(timezone.utc).isoformat()

                # Get tags from tags column first, fall back to metadata._x_oap_tags
                tags = row["tags"] if row["tags"] else []
                if not tags and config:
                    # Try to get from metadata if tags column is empty
                    row_metadata = row["metadata"]
                    if isinstance(row_metadata, str):
                        try:
                            row_metadata = json.loads(row_metadata) if row_metadata else {}
                        except:
                            row_metadata = {}
                    if row_metadata:
                        tags = row_metadata.get("_x_oap_tags", [])

                versions_dict[version_num] = AssistantVersionInfo(
                    version=version_num,
                    name=row["name"] or "",
                    description=row["description"],
                    config=config,
                    metadata=metadata,
                    tags=tags,
                    commit_message=row["commit_message"],
                    created_by=row["created_by"],
                    created_by_display_name=row["created_by_display_name"],
                    created_at=created_at_str,
                    is_latest=(version_num == current_version),
                )

            # Merge LangGraph versions (if any)
            for v in langgraph_versions:
                version_num = v.get("version", 1)
                if version_num not in versions_dict:
                    created_at_raw = v.get("created_at") or v.get("updated_at", "")
                    try:
                        if created_at_raw:
                            created_at = datetime.fromisoformat(created_at_raw.replace("Z", "+00:00"))
                        else:
                            created_at = datetime.now(timezone.utc)
                    except ValueError:
                        created_at = datetime.now(timezone.utc)

                    # Extract tags from metadata._x_oap_tags (LangGraph SDK workaround)
                    lg_tags = v.get("metadata", {}).get("_x_oap_tags", []) if v.get("metadata") else []

                    versions_dict[version_num] = AssistantVersionInfo(
                        version=version_num,
                        name=v.get("name", ""),
                        description=v.get("description"),
                        config=v.get("config", {}),
                        metadata=v.get("metadata"),
                        tags=lg_tags,
                        commit_message=None,
                        created_by=None,
                        created_by_display_name=None,
                        created_at=created_at.isoformat(),
                        is_latest=(version_num == current_version),
                    )

            # Always ensure current version is included AND saved to DB
            if current_version not in versions_dict and current_assistant:
                created_at_raw = current_assistant.get("created_at") or current_assistant.get("updated_at", "")
                try:
                    if created_at_raw:
                        created_at = datetime.fromisoformat(created_at_raw.replace("Z", "+00:00"))
                    else:
                        created_at = datetime.now(timezone.utc)
                except ValueError:
                    created_at = datetime.now(timezone.utc)

                # Get tags from metadata (stored with _x_oap_tags prefix - LangGraph SDK workaround)
                current_tags = current_assistant.get("metadata", {}).get("_x_oap_tags", []) if current_assistant.get("metadata") else []

                # Save this version to DB so it persists for future lookups and restores
                try:
                    await conn.execute(
                        """
                        INSERT INTO langconnect.assistant_versions (
                            assistant_id, version, name, description, config, metadata, tags,
                            langgraph_created_at, commit_message, created_by
                        ) VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb, $7, $8, $9, $10)
                        ON CONFLICT (assistant_id, version) DO NOTHING
                        """,
                        UUID(assistant_id),
                        current_version,
                        current_assistant.get("name", ""),
                        current_assistant.get("description"),
                        json.dumps(current_assistant.get("config", {})),
                        json.dumps(current_assistant.get("metadata") or {}),
                        current_tags,
                        created_at,
                        None,  # No commit message for auto-saved versions
                        None,  # No user for auto-saved versions
                    )
                    log.info(f"Auto-saved current version {current_version} for assistant {assistant_id}")
                except Exception as save_error:
                    log.warning(f"Failed to auto-save version {current_version}: {save_error}")

                versions_dict[current_version] = AssistantVersionInfo(
                    version=current_version,
                    name=current_assistant.get("name", ""),
                    description=current_assistant.get("description"),
                    config=current_assistant.get("config", {}),
                    metadata=current_assistant.get("metadata"),
                    tags=current_tags,
                    commit_message=None,
                    created_by=None,
                    created_by_display_name=None,
                    created_at=created_at.isoformat(),
                    is_latest=True,
                )

        # Sort by version descending
        return sorted(versions_dict.values(), key=lambda x: x.version, reverse=True)

    async def _sync_and_enrich_versions(
        self,
        assistant_id: str,
        langgraph_versions: List[Dict[str, Any]],
        current_version: int,
    ) -> List[AssistantVersionInfo]:
        """
        Sync versions to local DB and enrich with local metadata.

        Args:
            assistant_id: Assistant ID
            langgraph_versions: Versions from LangGraph
            current_version: Current/latest version number

        Returns:
            List of enriched AssistantVersionInfo
        """
        enriched = []

        async with get_db_connection() as conn:
            # Get existing local versions with commit messages
            local_versions = await conn.fetch(
                """
                SELECT
                    av.version,
                    av.commit_message,
                    av.created_by,
                    ur.display_name as created_by_display_name
                FROM langconnect.assistant_versions av
                LEFT JOIN langconnect.user_roles ur ON av.created_by = ur.user_id
                WHERE av.assistant_id = $1
                """,
                UUID(assistant_id)
            )

            # Create lookup dict for local metadata
            local_metadata = {
                row["version"]: {
                    "commit_message": row["commit_message"],
                    "created_by": row["created_by"],
                    "created_by_display_name": row["created_by_display_name"],
                }
                for row in local_versions
            }

            # Process each LangGraph version
            for v in langgraph_versions:
                version_num = v.get("version", 1)

                # Parse created_at timestamp
                created_at_raw = v.get("created_at") or v.get("updated_at", "")
                try:
                    if created_at_raw:
                        created_at = datetime.fromisoformat(created_at_raw.replace("Z", "+00:00"))
                    else:
                        created_at = datetime.now(timezone.utc)
                except ValueError:
                    created_at = datetime.now(timezone.utc)

                # Get tags from metadata (stored with _x_oap_tags prefix - LangGraph SDK workaround)
                version_tags = v.get("metadata", {}).get("_x_oap_tags", []) if v.get("metadata") else []

                # Upsert to local DB (only inserts if not exists)
                await conn.execute(
                    """
                    INSERT INTO langconnect.assistant_versions (
                        assistant_id, version, name, description, config, metadata, tags, langgraph_created_at
                    ) VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb, $7, $8)
                    ON CONFLICT (assistant_id, version) DO NOTHING
                    """,
                    UUID(assistant_id),
                    version_num,
                    v.get("name", ""),
                    v.get("description"),
                    json.dumps(v.get("config", {})),
                    json.dumps(v.get("metadata", {})),
                    version_tags,
                    created_at,
                )

                # Get local metadata if exists
                local = local_metadata.get(version_num, {})

                enriched.append(AssistantVersionInfo(
                    version=version_num,
                    name=v.get("name", ""),
                    description=v.get("description"),
                    config=v.get("config", {}),
                    metadata=v.get("metadata"),
                    tags=version_tags,
                    commit_message=local.get("commit_message"),
                    created_by=local.get("created_by"),
                    created_by_display_name=local.get("created_by_display_name"),
                    created_at=created_at.isoformat(),
                    is_latest=(version_num == current_version),
                ))

        # Sort by version descending (newest first)
        enriched.sort(key=lambda x: x.version, reverse=True)

        return enriched

    async def restore_version(
        self,
        assistant_id: str,
        target_version: int,
        *,
        user_id: str,
        commit_message: Optional[str] = None,
        user_token: Optional[str] = None,
    ) -> AssistantRestoreResponse:
        """
        Restore an assistant to a previous version.

        Creates a NEW version with the old config (doesn't use set_latest).
        This preserves complete version history.

        Args:
            assistant_id: Assistant to restore
            target_version: Version number to restore to
            user_id: User performing the restore
            commit_message: Optional message for the restore
            user_token: User JWT for LangGraph auth

        Returns:
            AssistantRestoreResponse with new version info
        """
        try:
            log.info(f"Restoring assistant {assistant_id} to version {target_version}")

            # First try to get target version from local DB
            target_data = None
            async with get_db_connection() as conn:
                local_version = await conn.fetchrow(
                    """
                    SELECT name, description, config, metadata, tags
                    FROM langconnect.assistant_versions
                    WHERE assistant_id = $1 AND version = $2
                    """,
                    UUID(assistant_id),
                    target_version,
                )

                if local_version:
                    config = local_version["config"]
                    if isinstance(config, str):
                        config = json.loads(config) if config else {}

                    metadata = local_version["metadata"]
                    if isinstance(metadata, str):
                        metadata = json.loads(metadata) if metadata else {}

                    # Get tags from tags column first, fall back to metadata._x_oap_tags
                    tags = local_version["tags"] if local_version["tags"] else []
                    if not tags and metadata:
                        tags = metadata.get("_x_oap_tags", [])

                    target_data = {
                        "name": local_version["name"],
                        "description": local_version["description"],
                        "config": config,
                        "metadata": metadata,
                        "tags": tags,
                    }

            if not target_data:
                raise RuntimeError(f"Version {target_version} not found for assistant {assistant_id}. Make sure you have saved at least one version before trying to restore.")

            log.info(f"Restoring with target_data: name={target_data.get('name')}, description={target_data.get('description')[:50] if target_data.get('description') else None}..., config_keys={list(target_data.get('config', {}).keys())}, tags={target_data.get('tags', [])}")

            # Build update payload from target version
            # Always include all fields to ensure complete restore
            update_payload = {
                "name": target_data.get("name"),
                "config": target_data.get("config", {}),
                "description": target_data.get("description") or "",  # Always include, even if empty
            }

            # Include tags in metadata (using _x_oap_tags convention)
            restored_tags = target_data.get("tags", [])
            existing_metadata = target_data.get("metadata", {}) or {}
            update_payload["metadata"] = {
                **existing_metadata,
                "_x_oap_tags": restored_tags,
            }

            log.info(f"Sending PATCH to LangGraph with payload keys: {list(update_payload.keys())}, config_keys: {list(update_payload.get('config', {}).keys())}")

            # Call LangGraph update to create new version
            updated_assistant = await self.langgraph_service._make_request(
                "PATCH",
                f"assistants/{assistant_id}",
                data=update_payload,
                user_token=user_token,
            )

            log.info(f"LangGraph PATCH response: version={updated_assistant.get('version')}, config_keys={list(updated_assistant.get('config', {}).keys())}")

            new_version = updated_assistant.get("version", target_version + 1)

            # Build commit message for restore
            restore_message = commit_message or f"Restored from version {target_version}"

            # Save full version snapshot (not just commit message)
            await self.save_version_snapshot(
                assistant_id=assistant_id,
                version=new_version,
                name=updated_assistant.get("name", ""),
                description=updated_assistant.get("description"),
                config=updated_assistant.get("config", {}),
                metadata=updated_assistant.get("metadata"),
                commit_message=restore_message,
                user_id=user_id,
                tags=restored_tags,
            )

            # Sync the new version to local DB (mirror)
            from langconnect.services.langgraph_sync import LangGraphSyncService
            sync_service = LangGraphSyncService(self.langgraph_service)
            await sync_service.sync_assistant(assistant_id, user_token=user_token)

            log.info(f"Successfully restored assistant {assistant_id} from v{target_version} to v{new_version}")

            return AssistantRestoreResponse(
                assistant_id=assistant_id,
                restored_from_version=target_version,
                new_version=new_version,
                success=True,
                message=f"Successfully restored from version {target_version}",
            )

        except Exception as e:
            log.error(f"Failed to restore assistant {assistant_id} to version {target_version}: {e}")
            raise RuntimeError(f"Failed to restore version: {e}")

    async def store_commit_message(
        self,
        assistant_id: str,
        version: int,
        commit_message: str,
        user_id: str,
    ) -> bool:
        """
        Store a commit message for a specific version.

        Used when:
        - User saves with a commit message
        - User restores to a previous version

        Args:
            assistant_id: Assistant ID
            version: Version number
            commit_message: Message to store
            user_id: User who made the change

        Returns:
            True if message was stored
        """
        try:
            async with get_db_connection() as conn:
                # Try to update existing version record
                result = await conn.execute(
                    """
                    UPDATE langconnect.assistant_versions
                    SET commit_message = $3, created_by = $4
                    WHERE assistant_id = $1 AND version = $2
                    """,
                    UUID(assistant_id),
                    version,
                    commit_message,
                    user_id,
                )

                # Check if we updated anything
                if result == "UPDATE 0":
                    # Version record doesn't exist yet, create it with placeholder data
                    # It will be properly populated when versions are fetched
                    await conn.execute(
                        """
                        INSERT INTO langconnect.assistant_versions (
                            assistant_id, version, name, config, langgraph_created_at,
                            commit_message, created_by
                        ) VALUES ($1, $2, '', '{}'::jsonb, NOW(), $3, $4)
                        ON CONFLICT (assistant_id, version) DO UPDATE SET
                            commit_message = EXCLUDED.commit_message,
                            created_by = EXCLUDED.created_by
                        """,
                        UUID(assistant_id),
                        version,
                        commit_message,
                        user_id,
                    )

                log.info(f"Stored commit message for assistant {assistant_id} v{version}")
                return True

        except Exception as e:
            log.error(f"Failed to store commit message: {e}")
            return False


    async def save_version_snapshot(
        self,
        assistant_id: str,
        version: int,
        name: str,
        description: Optional[str],
        config: Dict[str, Any],
        metadata: Optional[Dict[str, Any]],
        commit_message: Optional[str],
        user_id: str,
        tags: Optional[List[str]] = None,
    ) -> bool:
        """
        Save a version snapshot to local DB.

        Called when an assistant is updated to record the new version.

        Args:
            assistant_id: Assistant ID
            version: Version number
            name: Assistant name
            description: Assistant description
            config: Assistant config
            metadata: Assistant metadata
            commit_message: Optional commit message
            user_id: User who made the change
            tags: Optional list of tags (if not provided, extracted from metadata)

        Returns:
            True if saved successfully
        """
        try:
            # Extract tags from metadata if not provided directly
            # Tags are stored in metadata with _x_oap_tags prefix (LangGraph SDK workaround)
            if tags is None:
                tags = metadata.get("_x_oap_tags", []) if metadata else []

            async with get_db_connection() as conn:
                await conn.execute(
                    """
                    INSERT INTO langconnect.assistant_versions (
                        assistant_id, version, name, description, config, metadata, tags,
                        langgraph_created_at, commit_message, created_by
                    ) VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb, $7, $8, $9, $10)
                    ON CONFLICT (assistant_id, version) DO UPDATE SET
                        name = EXCLUDED.name,
                        description = EXCLUDED.description,
                        config = EXCLUDED.config,
                        metadata = EXCLUDED.metadata,
                        tags = EXCLUDED.tags,
                        commit_message = COALESCE(EXCLUDED.commit_message, langconnect.assistant_versions.commit_message),
                        created_by = COALESCE(EXCLUDED.created_by, langconnect.assistant_versions.created_by)
                    """,
                    UUID(assistant_id),
                    version,
                    name,
                    description,
                    json.dumps(config) if config else "{}",
                    json.dumps(metadata) if metadata else "{}",
                    tags,
                    datetime.now(timezone.utc),
                    commit_message,
                    user_id,
                )

                log.info(f"Saved version snapshot for assistant {assistant_id} v{version}")
                return True

        except Exception as e:
            log.error(f"Failed to save version snapshot: {e}")
            return False


def get_version_service(langgraph_service: LangGraphService) -> VersionService:
    """Get the version service instance (dependency injection)."""
    return VersionService(langgraph_service)
