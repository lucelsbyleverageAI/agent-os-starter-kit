"""
Utility functions for graph discovery and metadata extraction.

This module provides helper functions to extract graph metadata from
LangGraph by querying graph template assistants and their configuration schemas.
"""

import logging
from typing import Dict, Optional, Tuple

log = logging.getLogger(__name__)


async def get_graph_metadata_from_api(langgraph_service, graph_id: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Extract template_name and template_description from a graph's template assistant schema.

    Makes API calls to LangGraph to:
    1. Search for the graph template assistant for this graph_id
    2. Fetch its config schema
    3. Parse template_name and template_description from schema defaults

    Args:
        langgraph_service: LangGraphService instance
        graph_id: The graph identifier (e.g., "tools_agent")

    Returns:
        Tuple of (name, description) or (None, None) if not found
    """
    try:
        # Search for graph template assistants with this graph_id
        log.info(f"Searching for graph template assistant for graph {graph_id}")

        search_response = await langgraph_service._make_request(
            method="POST",
            endpoint="assistants/search",
            data={
                "graph_id": graph_id,
                "limit": 100,  # Should only be 1 graph template assistant per graph
                "offset": 0
            }
        )

        assistants = search_response if isinstance(search_response, list) else search_response.get("assistants", [])

        # Find the graph template assistant (metadata.created_by == "system")
        template_assistant = None
        for assistant in assistants:
            metadata = assistant.get("metadata", {})
            if metadata.get("created_by") == "system":
                template_assistant = assistant
                break

        if not template_assistant:
            log.warning(f"No graph template assistant found for graph {graph_id}")
            return None, None

        assistant_id = template_assistant.get("assistant_id")
        log.info(f"Found graph template assistant {assistant_id} for graph {graph_id}")

        # Fetch the assistant's schemas
        schemas_response = await langgraph_service._make_request(
            method="GET",
            endpoint=f"assistants/{assistant_id}/schemas"
        )

        if not schemas_response:
            log.warning(f"No schemas returned for assistant {assistant_id}")
            return None, None

        # Extract config_schema
        config_schema = schemas_response.get("config_schema")
        if not config_schema:
            log.warning(f"No config_schema found for assistant {assistant_id}")
            return None, None

        # Parse template_name and template_description from schema properties
        properties = config_schema.get("properties", {})

        template_name_schema = properties.get("template_name", {})
        template_description_schema = properties.get("template_description", {})

        # Get default values
        template_name = template_name_schema.get("default")
        template_description = template_description_schema.get("default")

        if not template_name:
            log.warning(f"No template_name found in schema for {graph_id}")
            # Fallback to reasonable default
            template_name = graph_id.replace("_", " ").title()

        if not template_description:
            log.warning(f"No template_description found in schema for {graph_id}")
            # Fallback to reasonable default
            template_description = f"Agent graph: {template_name}"

        log.info(f"Extracted metadata for {graph_id}: name='{template_name}', description='{template_description[:50]}...'")
        return template_name, template_description

    except Exception as e:
        log.error(f"Failed to extract metadata for {graph_id}: {e}")
        # Fallback to reasonable defaults
        fallback_name = graph_id.replace("_", " ").title()
        fallback_description = f"Agent graph: {fallback_name}"
        return fallback_name, fallback_description


async def get_all_graph_metadata_from_api(langgraph_service) -> Dict[str, Dict[str, str]]:
    """
    Extract metadata for all graphs by discovering graph template assistants.

    This function:
    1. Searches for all graph template assistants in LangGraph
    2. Groups them by graph_id
    3. Extracts metadata from each graph's template assistant schema

    Args:
        langgraph_service: LangGraphService instance

    Returns:
        Dictionary mapping graph_id to {name, description}
    """
    try:
        log.info("Discovering all graphs from graph template assistants")

        # Search for all graph template assistants using metadata filtering
        # This filters server-side rather than fetching all assistants and filtering in Python
        search_response = await langgraph_service._make_request(
            method="POST",
            endpoint="assistants/search",
            data={
                "limit": 1000,  # Should only match graph template assistants (~5-10)
                "offset": 0,
                "metadata": {"created_by": "system"}  # Server-side filter for graph template assistants
            }
        )

        assistants = search_response if isinstance(search_response, list) else search_response.get("assistants", [])

        # Server-side metadata filtering returns only graph template assistants
        # No need for additional Python-side filtering
        template_assistants = assistants

        log.info(f"Found {len(template_assistants)} graph template assistants")

        # Extract unique graph_ids
        graph_ids = set()
        for assistant in template_assistants:
            graph_id = assistant.get("graph_id")
            if graph_id:
                graph_ids.add(graph_id)

        log.info(f"Found {len(graph_ids)} unique graphs: {sorted(graph_ids)}")

        # Extract metadata for each graph
        metadata = {}
        for graph_id in graph_ids:
            name, description = await get_graph_metadata_from_api(langgraph_service, graph_id)
            if name and description:
                metadata[graph_id] = {
                    "name": name,
                    "description": description
                }

        log.info(f"Successfully extracted metadata for {len(metadata)} graphs")
        return metadata

    except Exception as e:
        log.error(f"Failed to discover graphs: {e}")
        return {}


async def populate_graph_metadata_in_db(conn, graph_id: str, name: str, description: str) -> bool:
    """
    Populate or update graph metadata in graphs_mirror table.

    Args:
        conn: Database connection
        graph_id: Graph identifier
        name: Human-readable graph name
        description: Graph description

    Returns:
        True if successful, False otherwise
    """
    try:
        await conn.execute(
            """
            INSERT INTO langconnect.graphs_mirror (graph_id, name, description, schema_accessible)
            VALUES ($1, $2, $3, TRUE)
            ON CONFLICT (graph_id) DO UPDATE SET
                name = EXCLUDED.name,
                description = EXCLUDED.description,
                schema_accessible = TRUE,
                updated_at = NOW()
            """,
            graph_id,
            name,
            description
        )

        log.info(f"Updated graph metadata in DB for {graph_id}: {name}")
        return True

    except Exception as e:
        log.error(f"Failed to update graph metadata in DB for {graph_id}: {e}")
        return False
