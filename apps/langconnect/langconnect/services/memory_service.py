"""
Memory service for Mem0 integration.

This service provides a secure interface to the mem0 library, handling all
memory operations with proper user isolation and database integration.
"""

import os
import traceback
from typing import Dict, List, Optional, Union, Any
from uuid import UUID
import logging

# Ensure mem0 writes under a writable home before importing it.
# mem0 initialises at import-time and creates ~/.mem0; on some images
# the default HOME (/home/<user>) is not writable.
logger = logging.getLogger(__name__)

try:
    preferred_home = (
        os.environ.get("LANGCONNECT_MEM0_HOME")
        or os.environ.get("MEM0_HOME")
        or "/app/data"
    )
    # Only set HOME if not already explicitly set
    os.environ.setdefault("HOME", preferred_home)
    # Also expose MEM0_HOME for future library support
    os.environ.setdefault("MEM0_HOME", preferred_home)
    # Best-effort create the directories; ignore if it fails
    os.makedirs(os.environ["HOME"], exist_ok=True)
    os.makedirs(os.path.join(os.environ["HOME"], ".mem0"), exist_ok=True)
except Exception as _mem0_home_err:
    # Do not crash service; mem0 import may still succeed if HOME is usable
    logger.warning("Failed to pre-create mem0 home directory", exc_info=False)

from mem0 import Memory

from ..config import (
    POSTGRES_HOST, POSTGRES_PORT, POSTGRES_USER, POSTGRES_PASSWORD, 
    POSTGRES_DB, POSTGRES_SCHEMA, IS_TESTING, DEFAULT_EMBEDDINGS
)

logger = logging.getLogger(__name__)


class MemoryService:
    """
    Service class for managing AI agent memories using mem0.
    
    This service provides a secure, user-centric interface to the mem0 library,
    ensuring all operations are properly isolated by user_id and integrated
    with the existing LangConnect database.
    """
    
    def __init__(self):
        """Initialize the memory service with mem0 configuration."""
        self._memory_client = None
        self._initialize_client()
    
    def _normalize_memory_format(self, memory_data: Any) -> Dict[str, Any]:
        """
        Normalize memory data format from PGVector provider to standard mem0 format.
        
        PGVector provider stores data in payload.data instead of memory field.
        This function converts it to the expected format for API responses.
        """
        if not memory_data:
            return None
            
        # If it's already in the correct format, return as-is
        if isinstance(memory_data, dict) and "memory" in memory_data:
            return memory_data
        
        # Handle PGVector format where content is in payload.data
        if isinstance(memory_data, dict):
            # Extract the actual memory content from payload structure
            payload = memory_data.get("payload", {})
            if payload and isinstance(payload, dict):
                return {
                    "id": memory_data.get("id"),
                    "memory": payload.get("data", ""),  # PGVector stores content in 'data' field
                    "user_id": payload.get("user_id"),
                    "hash": payload.get("hash"),
                    "metadata": payload.get("metadata", {}),
                    "created_at": payload.get("created_at"),
                    "updated_at": payload.get("updated_at")
                }
            
            # Fallback: if payload is not structured as expected
            return {
                "id": memory_data.get("id"),
                "memory": memory_data.get("data", memory_data.get("memory", "")),
                "user_id": memory_data.get("user_id"),
                "hash": memory_data.get("hash"),
                "metadata": memory_data.get("metadata", {}),
                "created_at": memory_data.get("created_at"),
                "updated_at": memory_data.get("updated_at")
            }
        
        return memory_data
    
    def _initialize_client(self) -> None:
        """
        Initialize the mem0 Memory client with our database configuration.
        
        This configures mem0 to use:
        - Our existing PostgreSQL database with pgvector
        - Our custom memory tables (memories, memory_embeddings)
        - OpenAI embeddings (or fake embeddings for testing)
        """
        try:
            logger.info("Initializing mem0 memory service...")
            logger.info(f"IS_TESTING: {IS_TESTING}")
            logger.info(f"Database config - Host: {POSTGRES_HOST}, Port: {POSTGRES_PORT}, DB: {POSTGRES_DB}, Schema: {POSTGRES_SCHEMA}")
            
            if IS_TESTING:
                # Use in-memory configuration for testing
                config = {
                    "vector_store": {
                        "provider": "memory",
                        "config": {
                            "collection_name": "test_memories"
                        }
                    },
                    "llm": {
                        "provider": "openai",
                        "config": {
                            "model": "gpt-4o-mini",
                            "api_key": "test-key"
                        }
                    },
                    "embedder": {
                        "provider": "openai", 
                        "config": {
                            "model": "text-embedding-3-small",
                            "api_key": "test-key"
                        }
                    }
                }
            else:
                # Production configuration using our PostgreSQL database with PGVector
                # Use connection string to set search_path to langconnect,public
                # This ensures PGVector creates tables in langconnect schema but can access vector extension in public
                connection_string = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}?options=-csearch_path%3D{POSTGRES_SCHEMA}%2Cpublic"
                logger.info(f"Using PGVector provider with connection string (search_path={POSTGRES_SCHEMA},public)")
                
                # Create configuration as a dictionary using mem0 PGVector provider
                config = {
                    "vector_store": {
                        "provider": "pgvector",
                        "config": {
                            "connection_string": connection_string,  # Use connection string with schema
                            "collection_name": "memories",  # Use the table we created in the schema
                            "embedding_model_dims": 1536,  # OpenAI text-embedding-3-small
                        }
                    },
                    "llm": {
                        "provider": "openai",
                        "config": {
                            "model": "gpt-4o-mini",
                            "temperature": 0.1,  # Low temperature for consistent memory processing
                            "max_tokens": 2000,  # Reasonable limit for memory operations
                            "api_key": os.environ.get("OPENAI_API_KEY"),
                        }
                    },
                    "embedder": {
                        "provider": "openai",
                        "config": {
                            "model": "text-embedding-3-small", 
                            "api_key": os.environ.get("OPENAI_API_KEY"),
                        }
                    }
                }
            
            logger.info("Creating Memory client with config...")
            
            # Check OpenAI API key availability
            openai_key = os.environ.get("OPENAI_API_KEY")
            if not openai_key:
                raise ValueError("OPENAI_API_KEY environment variable is not set")
            logger.info(f"OpenAI API key available: {openai_key[:10]}...{openai_key[-4:]}")
            
            self._memory_client = Memory.from_config(config)
            logger.info("Memory service initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize memory service: {e}")
            logger.error(f"Full traceback: {traceback.format_exc()}")
            logger.warning("Memory service will be disabled. Memory operations will not be available.")
            self._memory_client = None
            # Don't raise the exception - allow the service to start without memory functionality
    
    @property
    def client(self) -> Memory:
        """Get the mem0 client instance."""
        if self._memory_client is None:
            raise RuntimeError("Memory service is not available. Please check the logs for initialization errors.")
        return self._memory_client
    
    async def add_memory(
        self,
        user_id: str,
        content: Union[str, List[Dict[str, str]]],
        agent_id: Optional[str] = None,
        run_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Add a new memory for a user.
        
        Args:
            user_id: The user who owns this memory
            content: The memory content (string or list of message dicts)
            agent_id: Optional agent/assistant ID this memory relates to
            run_id: Optional conversation/run ID this memory is from
            metadata: Optional additional metadata
            
        Returns:
            Dict containing the operation results from mem0
            
        Raises:
            ValueError: If user_id is not provided
            RuntimeError: If memory creation fails
        """
        if not user_id:
            raise ValueError("user_id is required for all memory operations")
        
        logger.info(
            "Attempting to add memory", 
            extra={
                "user_id": user_id, 
                "agent_id": agent_id, 
                "run_id": run_id, 
                "content_type": type(content).__name__,
                "has_metadata": bool(metadata)
            }
        )
        
        try:
            # Prepare the memory data
            memory_kwargs = {
                "user_id": user_id,
                "metadata": metadata or {}
            }
            
            # Add optional context identifiers
            if agent_id:
                memory_kwargs["agent_id"] = agent_id
            if run_id:
                memory_kwargs["run_id"] = run_id
            
            # Add the memory using mem0
            result = self.client.add(content, **memory_kwargs)
            
            logger.info(f"Successfully added memory for user {user_id}", extra={"result": result})
            return result
            
        except Exception as e:
            logger.error(f"Failed to add memory for user {user_id}: {e}", exc_info=True)
            raise RuntimeError(f"Failed to add memory: {e}")
    
    async def search_memories(
        self,
        user_id: str,
        query: str,
        agent_id: Optional[str] = None,
        run_id: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 5,
        threshold: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Search for memories using semantic similarity.
        
        Args:
            user_id: The user whose memories to search
            query: The search query
            agent_id: Optional agent ID to filter by
            run_id: Optional run ID to filter by
            limit: Maximum number of results to return
            threshold: Minimum similarity threshold
            
        Returns:
            Dict containing search results from mem0
            
        Raises:
            ValueError: If user_id is not provided
            RuntimeError: If search fails
        """
        if not user_id:
            raise ValueError("user_id is required for all memory operations")
        
        logger.info(
            "Attempting to search memories", 
            extra={
                "user_id": user_id, 
                "query": query, 
                "agent_id": agent_id, 
                "run_id": run_id, 
                "filters": filters,
                "limit": limit
            }
        )
        
        try:
            # Prepare search parameters (mem0-specific)
            # Always scope by user but support optional filtering
            effective_threshold = threshold if threshold is not None else 0.25
            search_kwargs = {
                "user_id": user_id,   # keep for SDK compatibility
                "limit": limit,
                "threshold": effective_threshold,
            }
            
            # Note: For MCP tools, we intentionally don't pass agent_id/run_id to search ALL user memories
            # But the API supports optional filtering for direct API usage
            
            # Handle structured filters (advanced filtering)
            if filters:
                # Use structured filters format - try v2 API style first
                try:
                    # Ensure user_id is always included in structured filters
                    if "AND" not in filters:
                        filters = {"AND": [{"user_id": user_id}, filters]}
                    elif not any("user_id" in f for f in filters.get("AND", []) if isinstance(f, dict)):
                        filters["AND"].insert(0, {"user_id": user_id})
                    
                    search_kwargs["filters"] = filters
                    logger.info(f"Using structured filters: {filters}")
                except Exception as filter_error:
                    logger.warning(f"Failed to process structured filters: {filter_error}")
                    # Fallback to simple parameters
                    if agent_id:
                        search_kwargs["agent_id"] = agent_id
                    if run_id:
                        search_kwargs["run_id"] = run_id
            else:
                # Simple filtering for backwards compatibility
                if agent_id:
                    search_kwargs["agent_id"] = agent_id
                if run_id:
                    search_kwargs["run_id"] = run_id
            logger.info(
                "Calling mem0 client search",
                extra={"limit": limit, "threshold": effective_threshold, "search_kwargs": search_kwargs}
            )

            # Perform the search
            raw_results = self.client.search(query, **search_kwargs)

            logger.info("Received raw search results from mem0", extra={
                "raw_results": raw_results,
                "result_type": type(raw_results).__name__,
                "result_keys": list(raw_results.keys()) if isinstance(raw_results, dict) else None,
                "results_count": len(raw_results.get("results", [])) if isinstance(raw_results, dict) else 0
            })
            
            # Log individual results with scores for debugging
            if isinstance(raw_results, dict) and "results" in raw_results:
                for i, result in enumerate(raw_results.get("results", [])):
                    if isinstance(result, dict):
                        logger.info(f"Raw result {i}: score={result.get('score')}, data={result.get('payload', {}).get('data', 'N/A')[:50]}...")
                        
            # IMPORTANT: mem0 is returning distance scores instead of similarity scores
            # PGVector cosine distance: 0 = identical, higher = less similar
            # Expected similarity: 1.0 = identical, 0.0 = completely different
            # If scores are inverted (lower = more relevant), we need to convert distance to similarity

            # Normalize memory formats in the search results and preserve scores
            if raw_results and isinstance(raw_results, dict) and "results" in raw_results:
                normalized_memories = []
                raw_memories = raw_results.get("results", [])
                
                # Detect if scores are inverted (distance-based instead of similarity-based)
                # If the first result has a lower score than later results, scores are likely inverted
                scores_are_inverted = False
                if len(raw_memories) >= 2:
                    first_score = raw_memories[0].get("score") if isinstance(raw_memories[0], dict) else None
                    second_score = raw_memories[1].get("score") if isinstance(raw_memories[1], dict) else None
                    
                    if first_score is not None and second_score is not None:
                        # If first result (most relevant) has lower score than second, scores are inverted
                        if first_score < second_score:
                            scores_are_inverted = True
                            logger.info(f"Detected inverted scores (distance-based): first={first_score}, second={second_score}")
                        else:
                            logger.info(f"Scores appear correct (similarity-based): first={first_score}, second={second_score}")
                
                for memory in raw_memories:
                    score = None
                    if isinstance(memory, dict):
                        raw_score = memory.get("score")
                        if raw_score is not None:
                            if scores_are_inverted:
                                # Convert distance to similarity: similarity = 1 - distance
                                # But since we don't know the max distance, we'll use a simple inversion
                                # that maintains relative ranking but makes higher scores = more relevant
                                score = 1.0 - raw_score if raw_score <= 1.0 else 1.0 / (1.0 + raw_score)
                                logger.info(f"Converted score: {raw_score} -> {score}")
                            else:
                                score = raw_score
                    
                    normalized_memory = self._normalize_memory_format(memory)
                    if normalized_memory:
                        if score is not None:
                            normalized_memory["score"] = score
                        normalized_memories.append(normalized_memory)

                # Update results with normalized data
                results = raw_results.copy()
                results["results"] = normalized_memories
            else:
                results = raw_results

            logger.info(f"Searched memories for user {user_id}, found {len(results.get('results', []))} results")
            return results

        except Exception as e:
            logger.error(f"Failed to search memories for user {user_id}: {e}", exc_info=True)
            raise RuntimeError(f"Failed to search memories: {e}")
    
    async def get_memory(
        self,
        user_id: str,
        memory_id: str
    ) -> Dict[str, Any]:
        """
        Get a specific memory by ID.
        
        Args:
            user_id: The user who owns the memory (for security)
            memory_id: The memory ID to retrieve
            
        Returns:
            Dict containing the memory data
            
        Raises:
            ValueError: If user_id or memory_id is not provided
            RuntimeError: If retrieval fails
        """
        if not user_id:
            raise ValueError("user_id is required for all memory operations")
        if not memory_id:
            raise ValueError("memory_id is required")
        
        try:
            # Get the memory
            raw_memory = self.client.get(memory_id)
            
            # Normalize the memory format
            memory = self._normalize_memory_format(raw_memory)
            
            # Security check: ensure the memory belongs to the requesting user
            # Note: mem0 should handle this filtering, but we add an extra check
            if memory and memory.get("user_id") != user_id:
                raise RuntimeError(f"Memory {memory_id} does not belong to user {user_id}")
            
            logger.info(f"Retrieved memory {memory_id} for user {user_id}")
            return memory
            
        except Exception as e:
            logger.error(f"Failed to get memory {memory_id} for user {user_id}: {e}")
            raise RuntimeError(f"Failed to get memory: {e}")
    
    async def get_all_memories(
        self,
        user_id: str,
        agent_id: Optional[str] = None,
        run_id: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 100
    ) -> Dict[str, Any]:
        """
        Get all memories for a user with optional filtering.
        
        Args:
            user_id: The user whose memories to retrieve
            agent_id: Optional agent ID to filter by
            run_id: Optional run ID to filter by
            limit: Maximum number of memories to return
            
        Returns:
            Dict containing all matching memories
            
        Raises:
            ValueError: If user_id is not provided
            RuntimeError: If retrieval fails
        """
        if not user_id:
            raise ValueError("user_id is required for all memory operations")
        
        try:
            # Prepare get_all parameters with proper filtering
            get_kwargs = {
                "user_id": user_id,
                "limit": limit
            }
            
            # Handle structured filters (advanced filtering)
            if filters:
                # Use structured filters format - try v2 API style first
                try:
                    # Ensure user_id is always included in structured filters
                    if "AND" not in filters:
                        filters = {"AND": [{"user_id": user_id}, filters]}
                    elif not any("user_id" in f for f in filters.get("AND", []) if isinstance(f, dict)):
                        filters["AND"].insert(0, {"user_id": user_id})
                    
                    raw_results = self.client.get_all(filters=filters, limit=limit)
                    logger.info(f"Used structured filters: {filters}")
                except Exception as filter_error:
                    logger.info(f"Structured filters failed ({filter_error}), trying direct parameters")
                    # Fallback to simple parameters
                    if agent_id:
                        get_kwargs["agent_id"] = agent_id
                    if run_id:
                        get_kwargs["run_id"] = run_id
                    raw_results = self.client.get_all(**get_kwargs)
            elif agent_id or run_id:
                # Use structured filters for better compatibility
                structured_filters = {"AND": [{"user_id": user_id}]}
                
                if agent_id:
                    structured_filters["AND"].append({"agent_id": agent_id})
                if run_id:
                    structured_filters["AND"].append({"run_id": run_id})
                
                # Try with structured filters first (v2 style)
                try:
                    raw_results = self.client.get_all(filters=structured_filters, limit=limit)
                    logger.info(f"Used structured filters: {structured_filters}")
                except Exception as filter_error:
                    logger.info(f"Structured filters failed ({filter_error}), trying direct parameters")
                    # Fallback to direct parameters
                    if agent_id:
                        get_kwargs["agent_id"] = agent_id
                    if run_id:
                        get_kwargs["run_id"] = run_id
                    raw_results = self.client.get_all(**get_kwargs)
            else:
                # No additional filtering needed, just get all for user
                raw_results = self.client.get_all(**get_kwargs)
            
            # Normalize memory formats in the results
            if raw_results and isinstance(raw_results, dict) and "results" in raw_results:
                normalized_memories = []
                for memory in raw_results.get("results", []):
                    normalized_memory = self._normalize_memory_format(memory)
                    if normalized_memory:
                        normalized_memories.append(normalized_memory)
                
                # Update results with normalized data
                results = raw_results.copy()
                results["results"] = normalized_memories
            else:
                results = raw_results
            
            logger.info(f"Retrieved {len(results.get('results', []))} memories for user {user_id}")
            return results
            
        except Exception as e:
            logger.error(f"Failed to get all memories for user {user_id}: {e}")
            raise RuntimeError(f"Failed to get all memories: {e}")
    
    async def update_memory(
        self,
        user_id: str,
        memory_id: str,
        content: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Update an existing memory.
        
        Args:
            user_id: The user who owns the memory (for security)
            memory_id: The memory ID to update
            content: Optional new content for the memory
            metadata: Optional new metadata for the memory
            
        Returns:
            Dict containing the update result
            
        Raises:
            ValueError: If required parameters are missing
            RuntimeError: If update fails
        """
        if not user_id:
            raise ValueError("user_id is required for all memory operations")
        if not memory_id:
            raise ValueError("memory_id is required")
        if not content and not metadata:
            raise ValueError("Either content or metadata must be provided for update")
        
        try:
            # First verify the memory belongs to the user
            existing_memory = await self.get_memory(user_id, memory_id)
            if not existing_memory:
                raise RuntimeError(f"Memory {memory_id} not found for user {user_id}")
            
            # Update the memory using mem0 client's expected parameters
            if content and metadata:
                # Both content and metadata
                result = self.client.update(memory_id, data=content, metadata=metadata)
            elif content:
                # Only content
                result = self.client.update(memory_id, data=content)
            else:
                # Only metadata
                result = self.client.update(memory_id, metadata=metadata)
            
            logger.info(f"Updated memory {memory_id} for user {user_id}")
            return result
            
        except Exception as e:
            logger.error(f"Failed to update memory {memory_id} for user {user_id}: {e}")
            raise RuntimeError(f"Failed to update memory: {e}")
    
    async def delete_memory(
        self,
        user_id: str,
        memory_id: str
    ) -> Dict[str, Any]:
        """
        Delete a specific memory.
        
        Args:
            user_id: The user who owns the memory (for security)
            memory_id: The memory ID to delete
            
        Returns:
            Dict containing the deletion result
            
        Raises:
            ValueError: If required parameters are missing
            RuntimeError: If deletion fails
        """
        if not user_id:
            raise ValueError("user_id is required for all memory operations")
        if not memory_id:
            raise ValueError("memory_id is required")
        
        try:
            # First verify the memory belongs to the user
            existing_memory = await self.get_memory(user_id, memory_id)
            if not existing_memory:
                raise RuntimeError(f"Memory {memory_id} not found for user {user_id}")
            
            # Delete the memory
            result = self.client.delete(memory_id)
            
            logger.info(f"Deleted memory {memory_id} for user {user_id}")
            return result
            
        except Exception as e:
            logger.error(f"Failed to delete memory {memory_id} for user {user_id}: {e}")
            raise RuntimeError(f"Failed to delete memory: {e}")
    
    async def delete_all_memories(
        self,
        user_id: str,
        agent_id: Optional[str] = None,
        run_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Delete all memories for a user with optional filtering.
        
        Args:
            user_id: The user whose memories to delete
            agent_id: Optional agent ID to filter by
            run_id: Optional run ID to filter by
            
        Returns:
            Dict containing the deletion result
            
        Raises:
            ValueError: If user_id is not provided
            RuntimeError: If deletion fails
        """
        if not user_id:
            raise ValueError("user_id is required for all memory operations")
        
        try:
            # Prepare delete_all parameters
            delete_kwargs = {"user_id": user_id}
            
            # Add optional filters
            if agent_id:
                delete_kwargs["agent_id"] = agent_id
            if run_id:
                delete_kwargs["run_id"] = run_id
            
            # Delete all matching memories
            result = self.client.delete_all(**delete_kwargs)
            
            logger.info(f"Deleted all memories for user {user_id} (agent: {agent_id}, run: {run_id})")
            return result
            
        except Exception as e:
            logger.error(f"Failed to delete all memories for user {user_id}: {e}")
            raise RuntimeError(f"Failed to delete all memories: {e}")
    
    async def get_memory_history(
        self,
        user_id: str,
        memory_id: str
    ) -> List[Dict[str, Any]]:
        """
        Get the history of changes for a specific memory.
        
        Args:
            user_id: The user who owns the memory (for security)
            memory_id: The memory ID to get history for
            
        Returns:
            List of history entries
            
        Raises:
            ValueError: If required parameters are missing
            RuntimeError: If history retrieval fails
        """
        if not user_id:
            raise ValueError("user_id is required for all memory operations")
        if not memory_id:
            raise ValueError("memory_id is required")
        
        try:
            # First verify the memory belongs to the user
            existing_memory = await self.get_memory(user_id, memory_id)
            if not existing_memory:
                raise RuntimeError(f"Memory {memory_id} not found for user {user_id}")
            
            # Get the memory history
            history = self.client.history(memory_id)
            
            logger.info(f"Retrieved history for memory {memory_id} for user {user_id}")
            return history
            
        except Exception as e:
            logger.error(f"Failed to get history for memory {memory_id} for user {user_id}: {e}")
            raise RuntimeError(f"Failed to get memory history: {e}")


# Singleton instance for use across the application
memory_service = MemoryService()
