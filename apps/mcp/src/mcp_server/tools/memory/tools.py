"""Memory tools for Mem0 integration via LangConnect API."""

import json
from typing import Any, Dict, List, Optional, Union

import aiohttp

from ..base import CustomTool, ToolParameter
from ...config import LANGCONNECT_BASE_URL, settings
from ...utils.logging import get_logger
from ...utils.exceptions import ToolExecutionError

logger = get_logger(__name__)


class _MemoryBaseTool(CustomTool):
    """Base class for memory tools with common functionality."""
    
    def __init__(self):
        super().__init__()
        self.base_url = LANGCONNECT_BASE_URL.rstrip("/")
        self.toolkit_name = "memory"
        self.toolkit_display_name = "Memory Management"
    
    def _extract_context_from_args(self, arguments: Dict[str, Any]) -> tuple[Dict[str, Any], Optional[str]]:
        """Extract context information and JWT token from arguments."""
        context = {}
        jwt_token = None
        
        # Debug: log all arguments to see what we're receiving
        logger.info(f"Memory tool arguments received: {list(arguments.keys())}")
        for key, value in arguments.items():
            if key == '_jwt_token':
                logger.info(f"Found _jwt_token argument with length: {len(str(value)) if value else 0}")
            elif key.startswith('_context_'):
                logger.info(f"Found context argument '{key}': {type(value).__name__} = {str(value)[:50]}...")
            elif key.startswith('_'):
                logger.info(f"Found special argument '{key}': {type(value).__name__}")
        
        # Extract all context from universal context injection
        context_fields = [
            'user_id', 'agent_id', 'run_id', 'thread_id', 
            'assistant_id', 'graph_id'
        ]
        
        for field in context_fields:
            context_key = f'_context_{field}'
            if context_key in arguments:
                context[field] = arguments.pop(context_key)
                logger.info(f"Extracted context {field}: {context[field]}")
        
        # Legacy support: Extract from old memory-specific context arguments
        if '_context_user_id' in arguments:
            context['user_id'] = arguments.pop('_context_user_id')
        if '_context_agent_id' in arguments:
            context['agent_id'] = arguments.pop('_context_agent_id')
        if '_context_run_id' in arguments:
            context['run_id'] = arguments.pop('_context_run_id')
        
        # Extract JWT token for authentication
        if '_jwt_token' in arguments:
            jwt_token = arguments.pop('_jwt_token')
            logger.info(f"Successfully extracted JWT token from arguments, length: {len(jwt_token) if jwt_token else 0}")
        else:
            logger.warning("_jwt_token not found in arguments")
            
        return context, jwt_token
    
    async def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        context: Optional[Dict[str, Any]] = None,
        jwt_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """Make an authenticated HTTP request to LangConnect."""
        url = f"{self.base_url}{endpoint}"
        
        # Default headers
        request_headers = {"Content-Type": "application/json"}
        if headers:
            request_headers.update(headers)
            
        # Add JWT authentication header if token is provided
        if jwt_token:
            request_headers["Authorization"] = f"Bearer {jwt_token}"
            logger.info(f"Added JWT token to request headers for {endpoint}")
        else:
            logger.warning(f"No JWT token available for {endpoint} - this will likely fail authentication")
        
        # Inject context into request data if provided
        if context and data is not None:
            if 'agent_id' in context and context['agent_id']:
                data['agent_id'] = context['agent_id']
            if 'run_id' in context and context['run_id']:
                data['run_id'] = context['run_id']
        
        try:
            async with aiohttp.ClientSession() as session:
                if method.upper() == "GET":
                    # For GET requests, add query parameters
                    params = data if data else {}
                    if context:
                        if 'agent_id' in context and context['agent_id']:
                            params['agent_id'] = context['agent_id']
                        if 'run_id' in context and context['run_id']:
                            params['run_id'] = context['run_id']
                    
                    async with session.get(url, headers=request_headers, params=params) as response:
                        response_text = await response.text()
                        logger.info(f"LangConnect API response - status: {response.status}, body: {response_text}")
                        
                        try:
                            import json as json_module
                            response_data = json_module.loads(response_text)
                        except json_module.JSONDecodeError:
                            response_data = {"detail": f"Non-JSON response: {response_text}"}
                        
                        if response.status >= 400:
                            error_detail = response_data.get('detail', 'Unknown error')
                            logger.error(f"LangConnect API error - status: {response.status}, detail: {error_detail}")
                            raise ToolExecutionError("memory_api", f"API request failed: {error_detail}")
                        return response_data
                        
                else:
                    # For POST/PUT/DELETE requests, send data in body
                    json_data = json.dumps(data) if data else None
                    async with session.request(method, url, headers=request_headers, data=json_data) as response:
                        response_text = await response.text()
                        logger.info(f"LangConnect API response - status: {response.status}, body: {response_text}")
                        
                        try:
                            import json as json_module
                            response_data = json_module.loads(response_text)
                        except json_module.JSONDecodeError:
                            response_data = {"detail": f"Non-JSON response: {response_text}"}
                        
                        if response.status >= 400:
                            error_detail = response_data.get('detail', 'Unknown error')
                            logger.error(f"LangConnect API error - status: {response.status}, detail: {error_detail}")
                            raise ToolExecutionError("memory_api", f"API request failed: {error_detail}")
                        return response_data
                        
        except aiohttp.ClientError as e:
            logger.error(f"HTTP request failed: {e}")
            raise ToolExecutionError("memory_api", f"Failed to connect to LangConnect API: {e}")
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse API response: {e}")
            raise ToolExecutionError("memory_api", f"Invalid API response format: {e}")
        except Exception as e:
            logger.error(f"Unexpected error during API request: {e}")
            raise ToolExecutionError("memory_api", f"Unexpected error: {e}")


class AddMemoryTool(_MemoryBaseTool):
    """Tool for adding memories via Mem0."""
    
    @property
    def name(self) -> str:
        return "add_memory"
    
    @property
    def description(self) -> str:
        return "Add a new memory for the current user. Memories can store important facts, preferences, or context that should be remembered for future conversations."
    
    def get_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="content",
                type="string",
                description="The memory content to store. This should be a clear, factual statement that will be useful in future conversations.",
                required=True
            ),
            ToolParameter(
                name="metadata",
                type="object",
                description="Optional metadata to associate with this memory (e.g., category, importance level, tags).",
                required=False
            )
        ]
    
    async def _execute_impl(self, user_id: str, **arguments) -> str:
        """Execute the add memory operation."""
        # Extract context and JWT token from arguments
        context, jwt_token = self._extract_context_from_args(arguments)
        
        # Debug logging
        logger.info(f"AddMemoryTool execution - user_id: {user_id}")
        logger.info(f"AddMemoryTool execution - context: {context}")
        logger.info(f"AddMemoryTool execution - has jwt_token: {bool(jwt_token)}")
        logger.info(f"AddMemoryTool execution - base_url: {self.base_url}")
        
        content = arguments.get("content")
        metadata = arguments.get("metadata")
        
        if not content:
            raise ToolExecutionError("add_memory", "Content is required for adding a memory")
        
        # Prepare request data
        request_data = {
            "content": content,
            "metadata": metadata
        }
        
        try:
            logger.info(f"Making request to: {self.base_url}/memory/add")
            logger.info(f"Request data: {request_data}")
            logger.info(f"Has JWT token: {bool(jwt_token)}")
            response = await self._make_request("POST", "/memory/add", request_data, context=context, jwt_token=jwt_token)
            
            if response.get("success"):
                result_data = response.get("data", {})
                results = result_data.get("results", [])
                
                if results:
                    memory_info = []
                    for result in results:
                        memory_id = result.get("id", "Unknown")
                        memory_info.append(f"Memory ID: {memory_id}")
                    
                    return f"Memory added successfully. {', '.join(memory_info)}"
                else:
                    return "Memory added successfully."
            else:
                error_msg = response.get("error", "Unknown error")
                raise ToolExecutionError("add_memory", f"Failed to add memory: {error_msg}")
                
        except Exception as e:
            logger.error(f"Error adding memory: {e}")
            raise ToolExecutionError("add_memory", f"Failed to add memory: {e}")


class SearchMemoryTool(_MemoryBaseTool):
    """Tool for searching memories via Mem0."""
    
    @property
    def name(self) -> str:
        return "search_memory"
    
    @property
    def description(self) -> str:
        return "Search for memories based on a query. This will find memories that are semantically similar to the search query and can help recall relevant information from past conversations."
    
    def get_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="query",
                type="string",
                description="The search query to find relevant memories",
                required=True
            ),
            ToolParameter(
                name="limit",
                type="integer",
                description="Maximum number of memories to return (default: 10, max: 100)",
                required=False
            )
        ]
    
    async def _execute_impl(self, user_id: str, **arguments) -> str:
        """Execute the search memory operation."""
        _, jwt_token = self._extract_context_from_args(arguments)
        
        query = arguments.get("query")
        limit = arguments.get("limit", 10)
        
        if not query:
            raise ToolExecutionError("search_memory", "Query is required for searching memories")
        
        request_data = {
            "query": query,
            "limit": limit
        }

        logger.info(f"SearchMemoryTool executing with query='{query}', limit={limit}, user_id from context: {user_id}")

        try:
            # We don't pass context here to ensure search is across all user memories,
            # not just for the current agent/run.
            logger.info(f"Making search request to LangConnect API: {request_data}")
            response = await self._make_request("POST", "/memory/search", request_data, jwt_token=jwt_token)
            logger.info(f"LangConnect search response: {response}")
            
            if response.get("success"):
                result_data = response.get("data", {})
                results = result_data.get("results", [])
                
                if results:
                    memory_list = []
                    for i, result in enumerate(results, 1):
                        memory_content = result.get("memory", "No content")
                        score = result.get("score", 0.0)
                        memory_id = result.get("id", "Unknown")
                        memory_list.append(f"{i}. [{memory_id}] {memory_content} (relevance: {score:.3f})")
                    
                    return f"Found {len(results)} relevant memories:\n" + "\n".join(memory_list)
                else:
                    return "No memories found matching the search query."
            else:
                error_msg = response.get("error", "Unknown error")
                raise ToolExecutionError("search_memory", f"Failed to search memories: {error_msg}")
                
        except Exception as e:
            logger.error(f"Error searching memories: {e}")
            raise ToolExecutionError("search_memory", f"Failed to search memories: {e}")


class GetMemoryTool(_MemoryBaseTool):
    """Tool for retrieving a specific memory by ID."""
    
    @property
    def name(self) -> str:
        return "get_memory"
    
    @property
    def description(self) -> str:
        return "Retrieve a specific memory by its ID. This allows you to get the full details of a memory including its content, metadata, and timestamps."
    
    def get_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="memory_id",
                type="string",
                description="The ID of the memory to retrieve",
                required=True
            )
        ]
    
    async def _execute_impl(self, user_id: str, **arguments) -> str:
        """Execute the get memory operation."""
        context, jwt_token = self._extract_context_from_args(arguments)
        
        memory_id = arguments.get("memory_id")
        if not memory_id:
            raise ToolExecutionError("get_memory", "Memory ID is required")
        
        try:
            response = await self._make_request("GET", f"/memory/{memory_id}", context=context, jwt_token=jwt_token)
            
            if response.get("success"):
                memory_data = response.get("data", {})
                
                content = memory_data.get("memory", "No content")
                metadata = memory_data.get("metadata", {})
                created_at = memory_data.get("created_at", "Unknown")
                
                result = f"Memory ID: {memory_id}\n"
                result += f"Content: {content}\n"
                result += f"Created: {created_at}\n"
                
                if metadata:
                    result += f"Metadata: {json.dumps(metadata, indent=2)}"
                
                return result
            else:
                error_msg = response.get("error", "Memory not found")
                raise ToolExecutionError("get_memory", f"Failed to get memory: {error_msg}")
                
        except Exception as e:
            logger.error(f"Error getting memory: {e}")
            raise ToolExecutionError("get_memory", f"Failed to get memory: {e}")


class GetAllMemoriesTool(_MemoryBaseTool):
    """Tool for retrieving all memories for the user."""
    
    @property
    def name(self) -> str:
        return "get_all_memories"
    
    @property
    def description(self) -> str:
        return "Get all memories for the current user. This returns a list of all stored memories with their IDs, content, and timestamps."
    
    def get_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="limit",
                type="integer",
                description="Maximum number of memories to return (default: 50, max: 1000)",
                required=False
            ),
            ToolParameter(
                name="offset",
                type="integer",
                description="Number of memories to skip for pagination (default: 0)",
                required=False
            )
        ]
    
    async def _execute_impl(self, user_id: str, **arguments) -> str:
        """Execute the get all memories operation."""
        _, jwt_token = self._extract_context_from_args(arguments)
        
        limit = arguments.get("limit", 50)
        offset = arguments.get("offset", 0)
        
        request_data = {
            "limit": limit,
            "offset": offset
        }
        
        try:
            # We don't pass context here to ensure get all is across all user memories.
            response = await self._make_request("GET", "/memory/all", request_data, jwt_token=jwt_token)
            
            if response.get("success"):
                result_data = response.get("data", {})
                memories = result_data.get("results", [])
                
                if memories:
                    memory_list = []
                    for i, memory in enumerate(memories, offset + 1):
                        memory_id = memory.get("id", "Unknown")
                        content = memory.get("memory", "No content")
                        created_at = memory.get("created_at", "Unknown")
                        memory_list.append(f"{i}. [{memory_id}] {content} (created: {created_at})")
                    
                    return f"Found {len(memories)} memories:\n" + "\n".join(memory_list)
                else:
                    return "No memories found."
            else:
                error_msg = response.get("error", "Unknown error")
                raise ToolExecutionError("get_all_memories", f"Failed to get memories: {error_msg}")
                
        except Exception as e:
            logger.error(f"Error getting memories: {e}")
            raise ToolExecutionError("get_all_memories", f"Failed to get memories: {e}")


class UpdateMemoryTool(_MemoryBaseTool):
    """Tool for updating an existing memory."""
    
    @property
    def name(self) -> str:
        return "update_memory"
    
    @property
    def description(self) -> str:
        return "Update an existing memory by its ID. You can modify the content and/or metadata of a stored memory."
    
    def get_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="memory_id",
                type="string",
                description="The ID of the memory to update",
                required=True
            ),
            ToolParameter(
                name="content",
                type="string",
                description="New content for the memory",
                required=False
            ),
            ToolParameter(
                name="metadata",
                type="object",
                description="New metadata for the memory",
                required=False
            )
        ]
    
    async def _execute_impl(self, user_id: str, **arguments) -> str:
        """Execute the update memory operation."""
        context, jwt_token = self._extract_context_from_args(arguments)
        
        memory_id = arguments.get("memory_id")
        content = arguments.get("content")
        metadata = arguments.get("metadata")
        
        if not memory_id:
            raise ToolExecutionError("update_memory", "Memory ID is required")
        
        if not content and not metadata:
            raise ToolExecutionError("update_memory", "Either content or metadata must be provided for update")
        
        request_data = {}
        if content:
            request_data["content"] = content
        if metadata:
            request_data["metadata"] = metadata
        
        try:
            response = await self._make_request("PUT", f"/memory/{memory_id}", request_data, context=context, jwt_token=jwt_token)
            
            if response.get("success"):
                return f"Memory {memory_id} updated successfully."
            else:
                error_msg = response.get("error", "Unknown error")
                raise ToolExecutionError("update_memory", f"Failed to update memory: {error_msg}")
                
        except Exception as e:
            logger.error(f"Error updating memory: {e}")
            raise ToolExecutionError("update_memory", f"Failed to update memory: {e}")


class DeleteMemoryTool(_MemoryBaseTool):
    """Tool for deleting a specific memory."""
    
    @property
    def name(self) -> str:
        return "delete_memory"
    
    @property
    def description(self) -> str:
        return "Delete a specific memory by its ID. This permanently removes the memory from storage."
    
    def get_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="memory_id",
                type="string",
                description="The ID of the memory to delete",
                required=True
            )
        ]
    
    async def _execute_impl(self, user_id: str, **arguments) -> str:
        """Execute the delete memory operation."""
        context, jwt_token = self._extract_context_from_args(arguments)
        
        memory_id = arguments.get("memory_id")
        if not memory_id:
            raise ToolExecutionError("delete_memory", "Memory ID is required")
        
        try:
            response = await self._make_request("DELETE", f"/memory/{memory_id}", context=context, jwt_token=jwt_token)
            
            if response.get("success"):
                return f"Memory {memory_id} deleted successfully."
            else:
                error_msg = response.get("error", "Memory not found")
                raise ToolExecutionError("delete_memory", f"Failed to delete memory: {error_msg}")
                
        except Exception as e:
            logger.error(f"Error deleting memory: {e}")
            raise ToolExecutionError("delete_memory", f"Failed to delete memory: {e}")
