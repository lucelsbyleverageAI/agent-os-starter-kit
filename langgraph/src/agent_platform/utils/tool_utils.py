from typing import Annotated, Optional, List
from langchain_core.tools import StructuredTool, ToolException, tool
from langchain_core.messages import AIMessage, ToolCall, ToolMessage
import aiohttp
import re
from mcp.client.streamable_http import streamablehttp_client
from mcp import ClientSession, Tool, McpError
from langgraph.types import interrupt

# Import human interrupt schema
from agent_platform.types.human_interrupt import (
    HumanInterrupt, 
    HumanResponse, 
    ActionRequest,
    HumanInterruptConfig,
    DEFAULT_FULL_CONFIG
)
from agent_platform.sentry import get_logger
logger = get_logger(__name__)


def create_langchain_mcp_tool(
    mcp_tool: Tool, mcp_server_url: str = "", headers: dict[str, str] = {}
) -> StructuredTool:
    """
    Create a LangChain StructuredTool from an MCP tool.
    
    Args:
        mcp_tool: MCP tool definition with name, description, and inputSchema
        mcp_server_url: Base URL of the MCP server
        headers: HTTP headers for authentication
    
    Returns:
        StructuredTool: LangChain-compatible tool
    """

    @tool(
        mcp_tool.name,
        description=mcp_tool.description,
        args_schema=mcp_tool.inputSchema,
    )
    async def new_tool(**kwargs):
        """Execute MCP tool via official Streamable HTTP client."""
        import json
        
        # Debug: log the headers we're using
        logger.info("[MCP_TOOL_DEBUG] Creating MCP tool %s with headers: %s", mcp_tool.name, list(headers.keys()))
        for key, value in headers.items():
            if key.lower() == 'authorization':
                masked = f"***{value[-10:]}" if isinstance(value, str) and len(value) > 10 else "***"
                logger.info("[MCP_TOOL_DEBUG] Authorization header: %s = Bearer %s", key, masked)
        
        # Use official MCP client with Streamable HTTP transport
        async with streamablehttp_client(mcp_server_url, headers=headers) as streams:
            read_stream, write_stream, _ = streams
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                # Call the tool
                call_result = await session.call_tool(name=mcp_tool.name, arguments=kwargs)
                
                # call_result.content is a list of Content objects; extract text if present
                try:
                    contents = getattr(call_result, 'content', None) or []
                    for item in contents:
                        # item may have .type and .text
                        text = getattr(item, 'text', None)
                        if text:
                            return text
                    # Fallback: dump JSON
                    return json.dumps([item.__dict__ for item in contents], indent=2, default=str)
                except Exception:
                    # As a last resort, stringify the result
                    return str(call_result)

    return new_tool


def create_langchain_mcp_tool_with_auth_data(
    mcp_tool: Tool, 
    mcp_server_url: str, 
    auth_data: dict
) -> StructuredTool:
    """
    Create a LangChain StructuredTool from an MCP tool with authentication data.
    
    This function creates the appropriate headers based on the authentication mode
    and then calls the standard create_langchain_mcp_tool function.
    
    Args:
        mcp_tool: The MCP tool definition
        mcp_server_url: Base URL of the MCP server
        auth_data: Authentication data from fetch_tokens containing either:
            - OAuth mode: {"auth_type": "oauth", "access_token": "...", ...}
            - Custom mode: {"auth_type": "custom", "user_id": "...", "email": "..."}
    
    Returns:
        StructuredTool: A LangChain tool configured with proper authentication
    """
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    
    if auth_data:
        auth_type = auth_data.get("auth_type")
        
        if auth_type == "mcp_access_token":
            # Use MCP access token as Bearer token (preferred)
            access_token = auth_data.get("access_token")
            if access_token:
                headers["Authorization"] = f"Bearer {access_token}"
                
        elif auth_type == "service_account":
            # Service account authentication - use service account key
            access_token = auth_data.get("access_token")
            if access_token:
                headers["Authorization"] = f"Bearer {access_token}"
    
    return create_langchain_mcp_tool(mcp_tool, mcp_server_url, headers)


def wrap_mcp_authenticate_tool(tool: StructuredTool) -> StructuredTool:
    """
    Wrap an MCP tool to handle authentication and interaction requirements.
    
    This wrapper intercepts MCP errors, specifically the "interaction_required" error
    (code -32003), and converts them into user-friendly ToolExceptions that can
    include authentication URLs for user interaction.
    
    Args:
        tool: The LangChain StructuredTool to wrap
        
    Returns:
        StructuredTool: The same tool with enhanced error handling
        
    Error Handling:
        - Catches MCP interaction_required errors (code -32003)
        - Extracts authentication URLs from error data
        - Converts to ToolException with user-friendly message
        - Preserves original exceptions for non-authentication errors
        
    Example Error Flow:
        1. MCP server returns interaction_required error
        2. Wrapper extracts authentication URL
        3. Raises ToolException: "Required interaction https://auth.example.com/login"
        4. LLM can present this URL to the user for authentication
    """

    # Store reference to original tool coroutine
    old_coroutine = tool.coroutine

    async def wrapped_mcp_coroutine(**kwargs):
        """
        Enhanced coroutine that handles MCP authentication errors.
        
        This wrapper function intercepts exceptions from the original tool
        and provides special handling for MCP interaction requirements.
        """
        
        def _find_first_mcp_error_nested(exc: BaseException) -> McpError | None:
            """
            Recursively search for MCP errors in exception chains.
            
            MCP errors can be nested within ExceptionGroups or other exception
            wrappers, so we need to search the entire exception tree.
            
            Args:
                exc: The exception to search
                
            Returns:
                McpError if found, None otherwise
            """
            # Direct MCP error
            if isinstance(exc, McpError):
                return exc
                
            # Search within exception groups (Python 3.11+)
            if isinstance(exc, ExceptionGroup):
                for sub_exc in exc.exceptions:
                    if found := _find_first_mcp_error_nested(sub_exc):
                        return found
                        
            return None

        try:
            # Execute the original tool function
            return await old_coroutine(**kwargs)
            
        except BaseException as e_orig:
            # Search for MCP errors in the exception chain
            mcp_error = _find_first_mcp_error_nested(e_orig)

            # If no MCP error found, re-raise original exception
            if not mcp_error:
                raise e_orig

            # Extract error details from MCP error
            error_details = mcp_error.error
            is_interaction_required = getattr(error_details, "code", None) == -32003
            error_data = getattr(error_details, "data", None) or {}

            # Handle interaction required errors (authentication/authorization)
            if is_interaction_required:
                # Extract user-friendly message from error data
                message_payload = error_data.get("message", {})
                error_message_text = "Required interaction"
                
                if isinstance(message_payload, dict):
                    error_message_text = (
                        message_payload.get("text") or error_message_text
                    )

                # Append authentication URL if available
                if url := error_data.get("url"):
                    error_message_text = f"{error_message_text} {url}"
                    
                # Raise user-friendly ToolException
                raise ToolException(error_message_text) from e_orig

            # For other MCP errors, re-raise original exception
            raise e_orig

    # Replace the tool's coroutine with our wrapped version
    tool.coroutine = wrapped_mcp_coroutine
    return tool


async def create_hybrid_search_tool(
    langconnect_api_url: str,
    access_token: str,
    scoped_collections: List[str]
) -> StructuredTool:
    """
    Create a collection-agnostic hybrid search tool.
    
    This tool can search across all configured collections or filter to a specific one.
    Works consistently with other file system tools by accepting optional collection_id.
    
    Args:
        langconnect_api_url: Base URL of the LangConnect API server
        access_token: Bearer token for API authentication
        scoped_collections: List of collection IDs the agent is allowed to access
        
    Returns:
        StructuredTool: A hybrid search tool that works across collections
    """
    # Normalize API URL
    if langconnect_api_url.endswith("/"):
        langconnect_api_url = langconnect_api_url[:-1]
    
    @tool
    async def hybrid_search(
        query: Annotated[str, "Semantic query (natural language)"],
        keywords: Annotated[Optional[list[str]], "Optional keywords/phrases to combine with semantic search"] = None,
        collection_id: Annotated[Optional[str], "Optional collection filter; if omitted, search all accessible" ] = None,
        limit: Annotated[int, "Result chunk count (1-20). Default: 5"] = 5,
        max_context_characters: Annotated[int, "Context characters per chunk (amount of characters to return before and after the matched chunk). Default: 2500"] = 2500,
        semantic_weight: Annotated[float, "Semantic vs keyword weight (0.0-1.0). Default: 0.6"] = 0.6,
        **kwargs  # Accept context arguments injected by universal context wrapper
    ) -> str:
        """Search across your scoped collections using a hybrid (semantic + keyword) ranker.

        Optionally limit to a specific `collection_id`. The response contains
        LLM‑ready formatted content plus a compact citation list of unique
        documents. Use `limit`, `max_context_characters`, and `semantic_weight`
        to balance breadth, context size, and semantic vs keyword emphasis.
        """
        import json
        import httpx
        
        logger.info(f"[HYBRID_SEARCH] query={query!r}, keywords={keywords!r}, collection_id={collection_id!r}, limit={limit}, semantic_weight={semantic_weight}")
        
        # Normalize keywords input
        try:
            if isinstance(keywords, str):
                keywords = [keywords]
            if keywords is None:
                keywords = []
        except Exception:
            keywords = []
        if not isinstance(keywords, list):
            keywords = []
        
        # Validate and clamp parameters
        limit = max(1, min(20, limit))
        max_context_characters = max(500, min(5000, max_context_characters))
        semantic_weight = max(0.0, min(1.0, semantic_weight))
        
        # Validate collection_id if provided
        if collection_id and collection_id not in scoped_collections:
            error_response = {
                "formatted_content": f"Error: You don't have access to collection {collection_id}. Available collections can be found using fs_list_collections.",
                "documents": []
            }
            return json.dumps(error_response, indent=2)
        
        # Prepare search payload
        payload = {
            "query": query,
            "keywords": keywords,
            "limit": limit,
            "return_surrounding_context": True,
            "max_context_characters": max_context_characters,
            "format_chunks_for_llm": True,
            "semantic_weight": semantic_weight,
            "scoped_collections": scoped_collections  # Enforce permissions at backend
        }
        
        # If specific collection requested, add to payload
        if collection_id:
            payload["collection_id"] = collection_id
        
        try:
            # Call unified search endpoint
            search_endpoint = f"{langconnect_api_url}/agent-filesystem/search"
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    search_endpoint,
                    json=payload,
                    headers={"Authorization": f"Bearer {access_token}"},
                    timeout=30.0
                )
                response.raise_for_status()
                search_data = response.json()
            
            # Extract formatted text and structured results
            formatted_text = search_data.get("formatted_text", "")
            structured_results = search_data.get("structured_results", [])
            
            # Extract unique document information for citations
            unique_documents = {}
            for result in structured_results:
                doc_id = result.get("document_id")
                if doc_id and doc_id not in unique_documents:
                    doc_metadata = result.get("document_metadata", {})
                    unique_documents[doc_id] = {
                        "document_id": doc_id,
                        "collection_name": result.get("collection_name", "Unknown"),
                        "title": doc_metadata.get("title", "Untitled"),
                        "source_name": doc_metadata.get("source_name") or doc_metadata.get("original_filename", "Unknown source"),
                    }
            
            # Create optimized response for LLM
            response_data = {
                "formatted_content": formatted_text,
                "documents": list(unique_documents.values())
            }
            
            return json.dumps(response_data, indent=2)
            
        except Exception as e:
            logger.exception(f"[HYBRID_SEARCH] Error searching documents")
            error_response = {
                "formatted_content": f"Error searching documents: {str(e)}",
                "documents": []
            }
            return json.dumps(error_response, indent=2)
    
    return hybrid_search


async def create_rag_tool(langconnect_api_url: str, collection_id: str, access_token: str):
    """
    DEPRECATED: Create a collection-specific RAG tool.
    
    This function is kept for backward compatibility but is deprecated in favor of
    create_hybrid_search_tool() which works across collections.
    
    Use create_hybrid_search_tool() instead for new implementations.
    """
    # Normalize RAG URL by removing trailing slash
    if langconnect_api_url.endswith("/"):
        langconnect_api_url = langconnect_api_url[:-1]

    # Construct collection metadata endpoint
    collection_endpoint = f"{langconnect_api_url}/collections/{collection_id}"
    logger.debug(f"[RAG] Fetching collection metadata from {collection_endpoint}")
    
    try:
        # Fetch collection metadata to configure the tool
        async with aiohttp.ClientSession() as session:
            async with session.get(
                collection_endpoint, 
                headers={"Authorization": f"Bearer {access_token}"}
            ) as response:
                response.raise_for_status()
                collection_data = await response.json()
                logger.debug(f"[RAG] Metadata fetch status={response.status}; keys={list(collection_data.keys())}")

        # Extract and sanitize collection name for tool naming
        raw_collection_name = collection_data.get("name", f"collection_{collection_id}")

        # Sanitize name to meet LangChain tool naming requirements
        # Tool names must match regex: ^[a-zA-Z0-9_-]+$
        sanitized_name = re.sub(r"[^a-zA-Z0-9_-]", "_", raw_collection_name)

        # Ensure name is valid and within length limits
        if not sanitized_name:
            sanitized_name = f"collection_{collection_id}"
        collection_name = sanitized_name[:64]  # Limit to 64 characters

        # Create tool description from collection metadata
        raw_description = collection_data.get("metadata", {}).get("description")

        if not raw_description:
            collection_description = "Search your collection of documents with contextual expansion for comprehensive results semantically similar to the input query"
        else:
            collection_description = f"Search your collection of documents with contextual expansion for comprehensive results semantically similar to the input query. Collection description: {raw_description}"

        logger.info(f"[RAG] Registered search tool: search_collection_{collection_name} (collection_id={collection_id})")

        @tool(f"search_collection_{collection_name}", description=collection_description)
        async def get_documents(
            query: Annotated[str, "Semantic query (natural language)"],
            keywords: Annotated[Optional[list[str]], "Optional keywords/phrases to combine with semantic search" ] = None,
            **kwargs  # Accept context arguments injected by universal context wrapper
        ) -> str:
            """Search within this collection using hybrid (semantic + keyword) ranking.

            Best for focused lookups when you already know the target collection.
            Returns LLM‑formatted content plus a concise citation list.
            """

            logger.info(f"[RAG] Tool 'search_collection_{collection_name}' called! query={query!r}, keywords={keywords!r}, context_keys={list(kwargs.keys())}")

            # Normalize inputs (make keywords optional & robust)
            try:
                if isinstance(keywords, str):
                    keywords = [keywords]
                if keywords is None:
                    keywords = []
            except Exception:
                keywords = []
            if not isinstance(keywords, list):
                keywords = []

            # Construct hybrid search endpoint URL
            search_endpoint = f"{langconnect_api_url}/collections/{collection_id}/hybrid_search"
            
            # Prepare hybrid search payload with fixed optimal parameters
            payload = {
                "query": query,                       # Semantic component
                "keywords": keywords,                 # Keyword component provided by LLM
                "limit": 5,                          # Limit results to prevent overwhelming the LLM
                "return_surrounding_context": True,  # Always include context
                "max_context_characters": 2500,     # Comprehensive context
                "format_chunks_for_llm": True,       # LLM-optimized formatting
                "semantic_weight": 0.6               # Favor semantic slightly over keywords
            }

            try:
                logger.info(
                    f"[RAG] Calling hybrid_search: endpoint={search_endpoint}; query_len={len(query) if query else 0}; "
                    f"keywords_count={len(keywords)}"
                )
                # Execute contextual search request
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        search_endpoint,
                        json=payload,
                        headers={"Authorization": f"Bearer {access_token}"},
                    ) as search_response:
                        # Do not raise immediately; capture body for better diagnostics
                        status_code = search_response.status
                        try:
                            search_data = await search_response.json()
                        except Exception as parse_err:
                            # Fallback to raw text for diagnostics
                            raw_text = await search_response.text()
                            logger.error(
                                f"[RAG] Failed to parse search response as JSON: status={status_code}; body_starts={raw_text[:200]!r}"
                            )
                            raise
                        if status_code >= 400:
                            logger.error(
                                f"[RAG] Search responded with error status={status_code}; body_keys={list(search_data.keys())}"
                            )
                            raise aiohttp.ClientResponseError(
                                request_info=search_response.request_info,
                                history=search_response.history,
                                status=status_code,
                                message=f"LangConnect search error {status_code}",
                                headers=search_response.headers,
                            )
                        logger.info(
                            f"[RAG] Search response status={status_code}; keys={list(search_data.keys())}"
                        )

                # Extract formatted text and structured results from LLMSearchResponse
                formatted_text = search_data.get("formatted_text", "")
                structured_results = search_data.get("structured_results", [])

                # Extract unique document information for citations
                unique_documents = {}
                
                for result in structured_results:
                    doc_id = result.get("document_id")
                    if doc_id and doc_id not in unique_documents:
                        doc_metadata = result.get("document_metadata", {})
                        
                        # Extract only key citation information (title and source only)
                        unique_documents[doc_id] = {
                            "document_id": doc_id,
                            "title": doc_metadata.get("title", "Untitled"),
                            "source_name": doc_metadata.get("source_name") or doc_metadata.get("original_filename", "Unknown source"),
                        }

                # Create optimized response for LLM
                response_data = {
                    "formatted_content": formatted_text,
                    "documents": list(unique_documents.values())
                }

                # Return as JSON string for LLM processing
                import json
                return json.dumps(response_data, indent=2)
                
            except Exception as e:
                # Return error in consistent JSON format
                logger.exception(f"[RAG] Error searching documents for collection_id={collection_id}")
                import json
                error_response = {
                    "formatted_content": f"Error searching documents: {str(e)}",
                    "documents": []
                }
                logger.error(f"[RAG] Returning error response: {error_response}")
                return json.dumps(error_response, indent=2)

        return get_documents

    except Exception as e:
        # Re-raise with context about tool creation failure
        logger.exception(f"[RAG] Failed to create RAG tool for collection_id={collection_id}")
        raise Exception(f"Failed to create RAG tool: {str(e)}")


def wrap_tool_with_human_approval(
    tool: StructuredTool, 
    interrupt_config: HumanInterruptConfig = None
) -> StructuredTool:
    """
    Wrap any LangChain tool to require human approval before execution.
    
    This function creates a wrapper around an existing tool that intercepts
    tool calls and pauses execution for human review via the Agent Inbox UI.
    The human can approve, edit, ignore, or provide feedback on the tool call.
    
    Args:
        tool: The LangChain StructuredTool to wrap
        interrupt_config: Configuration for allowed human response types
        
    Returns:
        StructuredTool: A new tool that requires human approval before execution
        
    Example:
        ```python
        # Wrap an existing tool
        approval_tool = wrap_tool_with_human_approval(
            my_tool,
            interrupt_config={
                "allow_accept": True,
                "allow_edit": True,
                "allow_ignore": True,
                "allow_respond": True
            }
        )
        ```
    """
    
    if interrupt_config is None:
        interrupt_config = DEFAULT_FULL_CONFIG
    
    # Store reference to original tool function
    old_coroutine = tool.coroutine
    
    async def tool_with_approval(**tool_args):
        """
        Enhanced tool function that requires human approval before execution.
        
        This wrapper function intercepts tool calls, creates a human interrupt
        request, and handles the human's response appropriately.
        """
        
        logger.info("[HITL EXECUTION] Tool '%s' called", tool.name)
        
        # Create human interrupt request
        request: HumanInterrupt = {
            "action_request": {
                "action": tool.name,
                "args": tool_args
            },
            "config": interrupt_config,
            "description": f"**Tool:** {tool.name}\n\n**Description:** {tool.description}\n\n**Arguments:** ```json\n{tool_args}\n```\n\nPlease review this tool call and choose how to proceed."
        }
        
        logger.info("[HITL EXECUTION] Requesting human approval for '%s'...", tool.name)
        
        # Send interrupt and get human response
        response: HumanResponse = interrupt([request])[0]
        
        logger.info("[HITL EXECUTION] Human response for '%s': %s", tool.name, response["type"]) 
        
        # Handle human response
        if response["type"] == "accept":
            logger.info("[HITL EXECUTION] Executing '%s' with original arguments", tool.name)
            # Execute tool with original arguments
            result = await old_coroutine(**tool_args)
            logger.info("[HITL EXECUTION] Tool '%s' completed successfully", tool.name)
            return result
            
        elif response["type"] == "edit":
            logger.info("[HITL EXECUTION] Executing '%s' with edited arguments", tool.name)
            # Execute tool with edited arguments
            edited_args = response["args"]["args"]
            result = await old_coroutine(**edited_args)
            logger.info("[HITL EXECUTION] Tool '%s' completed with edited args", tool.name)
            return result
            
        elif response["type"] == "ignore":
            logger.info("[HITL EXECUTION] Tool '%s' was ignored by human", tool.name)
            # Skip tool execution
            return f"Tool call to {tool.name} was ignored by human reviewer."
            
        elif response["type"] == "response":
            logger.info("[HITL EXECUTION] Tool '%s' replaced with human feedback", tool.name)
            # Return human feedback instead of executing tool
            return f"Human feedback: {response['args']}"
            
        else:
            logger.error("[HITL EXECUTION] Unknown response type for '%s': %s", tool.name, response["type"]) 
            raise ValueError(f"Unsupported human response type: {response['type']}")
    
    # Create the tool using StructuredTool.from_function 
    # This is the correct way to create a tool from an async function
    from langchain_core.tools import StructuredTool
    
    approval_tool = StructuredTool.from_function(
        func=tool_with_approval,
        name=tool.name,
        description=tool.description,
        args_schema=tool.args_schema,
        coroutine=tool_with_approval  # For async functions
    )
    
    return approval_tool


async def create_rag_tool_with_universal_context(
    langconnect_api_url: str, 
    collection_id: str, 
    access_token: str,
    config_getter: callable = None
):
    """
    Create a RAG tool with universal context injection.
    
    This function creates a RAG search tool that automatically receives
    LangGraph execution context (user_id, assistant_id, thread_id, etc.)
    for better tracking and analytics.
    
    Args:
        langconnect_api_url: Base URL of the LangConnect API server
        collection_id: Unique identifier for the document collection
        access_token: Bearer token for API authentication
        config_getter: Optional callable to extract RunnableConfig
        
    Returns:
        StructuredTool: A RAG search tool with universal context injection
        
    Example:
        ```python
        rag_tool = await create_rag_tool_with_universal_context(
            "https://langconnect-api.example.com",
            "docs-collection-123",
            "bearer-token-xyz",
            config_getter
        )
        ```
    """
    
    # First create the standard RAG tool
    rag_tool = await create_rag_tool(langconnect_api_url, collection_id, access_token)
    
    # Then wrap it with universal context injection
    context_tool = wrap_tool_with_context_injection(rag_tool, config_getter)
    
    return context_tool


async def create_rag_tool_with_human_approval(
    langconnect_api_url: str, 
    collection_id: str, 
    access_token: str,
    interrupt_config: HumanInterruptConfig = None
):
    """
    Create a RAG tool with human-in-the-loop approval for searches.
    
    This function creates a RAG search tool that requires human approval
    before executing any document searches. Useful for sensitive or
    regulated document collections.
    
    Args:
        langconnect_api_url: Base URL of the LangConnect API server
        collection_id: Unique identifier for the document collection
        access_token: Bearer token for API authentication
        interrupt_config: Configuration for allowed human response types
        
    Returns:
        StructuredTool: A RAG search tool with human approval workflow
        
    Example:
        ```python
        rag_tool = await create_rag_tool_with_human_approval(
            "https://langconnect-api.example.com",
            "docs-collection-123",
            "bearer-token-xyz"
        )
        ```
    """
    
    # First create the standard RAG tool
    rag_tool = await create_rag_tool(langconnect_api_url, collection_id, access_token)
    
    # Then wrap it with human approval
    wrapped_tool = wrap_tool_with_human_approval(rag_tool, interrupt_config)
    
    return wrapped_tool


def create_langchain_mcp_tool_with_human_approval(
    mcp_tool: Tool, 
    mcp_server_url: str, 
    auth_data: dict,
    interrupt_config: HumanInterruptConfig = None
) -> StructuredTool:
    """
    Create an MCP tool with human-in-the-loop approval.
    
    This function creates an MCP tool wrapper that requires human approval
    before executing any MCP tool calls. Provides oversight for external
    tool integrations.
    
    Args:
        mcp_tool: The MCP tool definition
        mcp_server_url: Base URL of the MCP server
        auth_data: Authentication data for MCP server
        interrupt_config: Configuration for allowed human response types
        
    Returns:
        StructuredTool: An MCP tool with human approval workflow
        
    Example:
        ```python
        mcp_tool = create_langchain_mcp_tool_with_human_approval(
            mcp_tool_def,
            "https://mcp-server.example.com",
            auth_data
        )
        ```
    """
    # First create the standard MCP tool with auth
    mcp_tool_with_auth = create_langchain_mcp_tool_with_auth_data(
        mcp_tool, mcp_server_url, auth_data
    )
    
    # Then wrap it with authentication error handling
    mcp_tool_with_auth_handling = wrap_mcp_authenticate_tool(mcp_tool_with_auth)
    
    # Finally wrap with human approval
    return wrap_tool_with_human_approval(mcp_tool_with_auth_handling, interrupt_config)


def wrap_memory_tool_with_context(
    tool: StructuredTool, 
    state_getter: callable = None
) -> StructuredTool:
    """
    Wrap a memory tool to automatically inject context from LangGraph state.
    
    This wrapper automatically injects user_id, agent_id, and run_id into memory
    tool calls when they are executed within a LangGraph agent. This ensures
    memories are properly scoped and isolated without requiring the LLM to
    manually provide these context parameters.
    
    Args:
        tool: The memory tool to wrap (must be a memory-related tool)
        state_getter: Optional callable to extract state context (defaults to thread-local)
        
    Returns:
        StructuredTool: Enhanced tool with automatic context injection
        
    Context Injection:
        - user_id: Extracted from LangGraph state or authentication context
        - agent_id: Extracted from current assistant/agent configuration
        - run_id: Extracted from current thread/conversation ID
        
    Example:
        ```python
        # Wrap memory tools with context injection
        add_memory_tool = wrap_memory_tool_with_context(base_add_memory_tool)
        search_memory_tool = wrap_memory_tool_with_context(base_search_memory_tool)
        ```
    """
    
    # List of memory tool names that should receive context injection
    MEMORY_TOOL_NAMES = {
        'add_memory', 'search_memory', 'get_memory', 'get_all_memories',
        'update_memory', 'delete_memory', 'delete_all_memories', 'get_memory_history'
    }
    
    # Only wrap memory tools
    if tool.name not in MEMORY_TOOL_NAMES:
        return tool
    
    # Store reference to original tool coroutine
    old_coroutine = tool.coroutine
    
    async def memory_tool_with_context(**tool_args):
        """
        Enhanced memory tool function with automatic context injection.
        
        This wrapper extracts context from the current LangGraph execution
        environment and injects it into memory tool calls automatically.
        """
        
        # Extract context from LangGraph state or environment
        context = {}
        
        if state_getter:
            # Use provided state getter
            try:
                state = state_getter()
                context = _extract_context_from_state(state)
            except Exception as e:
                # If state getter fails, continue without context
                logger.warning("[MEMORY CONTEXT] Failed to get state context: %s", e)
        else:
            # Try to get context from thread-local storage or environment
            context = _get_default_context()
        
        # Inject context into tool arguments for API requests
        if context:
            # For memory tools, we need to modify the HTTP request that will be made
            # We'll inject the context as headers that the MCP tool can use
            
            # Store context in tool arguments for the MCP tool to access
            if 'user_id' in context and context['user_id']:
                tool_args['_context_user_id'] = context['user_id']
            if 'agent_id' in context and context['agent_id']:
                tool_args['_context_agent_id'] = context['agent_id']  
            if 'run_id' in context and context['run_id']:
                tool_args['_context_run_id'] = context['run_id']
        
        # Execute the original tool with injected context
        return await old_coroutine(**tool_args)
    
    # Create new tool with context injection
    from langchain_core.tools import StructuredTool
    
    context_tool = StructuredTool.from_function(
        func=memory_tool_with_context,
        name=tool.name,
        description=tool.description,
        args_schema=tool.args_schema,
        coroutine=memory_tool_with_context
    )
    
    return context_tool


def extract_context_from_config(config: dict) -> dict:
    """
    Extract execution context from LangGraph RunnableConfig.
    
    This function standardizes context extraction across all tools by pulling
    user_id, assistant_id/graph_id, thread_id, and other relevant context
    from the LangGraph configuration.
    
    Args:
        config: LangGraph RunnableConfig dictionary containing:
            - configurable: Request-level config (thread_id, tokens, etc.)
            - metadata: Thread metadata (owner, assistant_id, graph_id, etc.)
            
    Returns:
        dict: Standardized context dictionary with:
            - user_id: User who owns the thread
            - agent_id: Assistant/agent ID (from assistant_id or graph_id)  
            - thread_id: Current thread identifier
            - graph_id: Graph identifier if available
            - assistant_id: Assistant identifier if available
    """
    context = {}
    
    # Extract configurable values
    configurable = config.get("configurable", {})
    metadata = config.get("metadata", {})
    
    # Extract user_id (from metadata.owner set by auth system)
    if 'owner' in metadata:
        context['user_id'] = metadata['owner']
    elif 'user_id' in metadata:
        context['user_id'] = metadata['user_id']
    
    # Extract thread_id (from configurable)
    if 'thread_id' in configurable:
        context['thread_id'] = configurable['thread_id']
    
    # Extract agent identifiers (from metadata set by frontend)
    if 'assistant_id' in metadata:
        context['assistant_id'] = metadata['assistant_id']
        context['agent_id'] = metadata['assistant_id']  # Unified field
    elif 'graph_id' in metadata:
        context['graph_id'] = metadata['graph_id']
        context['agent_id'] = metadata['graph_id']  # Unified field
    
    # Extract run_id - use thread_id as run_id for now
    # In LangGraph, each thread represents a conversation/run
    if 'thread_id' in configurable:
        context['run_id'] = configurable['thread_id']
    
    return context


def _extract_context_from_state(state: dict) -> dict:
    """
    DEPRECATED: Extract memory context from LangGraph state.
    
    Use extract_context_from_config() instead for standardized context extraction.
    This function is kept for backward compatibility.
    
    Args:
        state: LangGraph state dictionary
        
    Returns:
        dict: Context dictionary with user_id, agent_id, run_id
    """
    context = {}
    
    # Extract user_id from state
    if 'user_id' in state:
        context['user_id'] = state['user_id']
    elif 'user' in state and isinstance(state['user'], dict):
        context['user_id'] = state['user'].get('id')
    elif 'auth' in state and isinstance(state['auth'], dict):
        context['user_id'] = state['auth'].get('user_id')
    
    # Extract agent_id from state
    if 'agent_id' in state:
        context['agent_id'] = state['agent_id']
    elif 'assistant_id' in state:
        context['agent_id'] = state['assistant_id']
    elif 'config' in state and isinstance(state['config'], dict):
        context['agent_id'] = state['config'].get('assistant_id')
    
    # Extract run_id from state
    if 'run_id' in state:
        context['run_id'] = state['run_id']
    elif 'thread_id' in state:
        context['run_id'] = state['thread_id']
    elif 'conversation_id' in state:
        context['run_id'] = state['conversation_id']
    
    return context


def wrap_tool_with_context_injection(
    tool: StructuredTool,
    config_getter: callable = None
) -> StructuredTool:
    """
    Universal wrapper that injects LangGraph execution context into any tool.
    
    This wrapper automatically injects user_id, assistant_id/graph_id, thread_id,
    and run_id into tool calls when they are executed within a LangGraph agent.
    This ensures all tools have access to proper context without requiring the LLM
    to manually provide these parameters.
    
    Args:
        tool: Any LangChain StructuredTool to wrap with context injection
        config_getter: Optional callable to extract RunnableConfig (defaults to thread-local)
        
    Returns:
        StructuredTool: Enhanced tool with automatic context injection
        
    Context Injection:
        - user_id: Extracted from metadata.owner (set by LangGraph auth)
        - assistant_id: Extracted from metadata.assistant_id (set by frontend)
        - graph_id: Extracted from metadata.graph_id (set by frontend) 
        - agent_id: Unified field (assistant_id or graph_id)
        - thread_id: Extracted from configurable.thread_id
        - run_id: Same as thread_id (each thread is a conversation/run)
        
    Usage:
        ```python
        # Wrap any tool with context injection
        context_tool = wrap_tool_with_context_injection(my_tool)
        
        # Tool will automatically receive context as _context_* arguments
        # - _context_user_id
        # - _context_agent_id  
        # - _context_thread_id
        # - _context_run_id
        # - _context_assistant_id (if available)
        # - _context_graph_id (if available)
        ```
    """
    
    # Store reference to original tool coroutine
    old_coroutine = tool.coroutine
    
    async def tool_with_context(**tool_args):
        """
        Enhanced tool function with automatic context injection.
        
        This wrapper extracts context from the current LangGraph execution
        environment and injects it into tool calls automatically.
        """
        
        # Extract context from LangGraph config
        context = {}
        
        if config_getter:
            # Use provided config getter
            try:
                config = config_getter()
                context = extract_context_from_config(config)
            except Exception as e:
                # If config getter fails, continue without context
                logger.warning("[CONTEXT INJECTION] Failed to get config context: %s", e)
        else:
            # Try to get context from thread-local storage or environment
            context = _get_default_context()
        
        # Inject context into tool arguments
        if context:
            # Inject all available context fields as _context_* arguments
            for key, value in context.items():
                if value:  # Only inject non-empty values
                    context_key = f'_context_{key}'
                    tool_args[context_key] = value
        
        # Execute the original tool with injected context
        return await old_coroutine(**tool_args)
    
    # Create new tool with context injection
    from langchain_core.tools import StructuredTool
    
    context_tool = StructuredTool.from_function(
        func=tool_with_context,
        name=tool.name,
        description=tool.description,
        args_schema=tool.args_schema,
        coroutine=tool_with_context
    )
    
    return context_tool


def _get_default_context() -> dict:
    """
    Get default context from environment or thread-local storage.
    
    This is a fallback method when RunnableConfig is not available.
    
    Returns:
        dict: Context dictionary with available context information
    """
    context = {}
    
    # Try to get context from thread-local storage (if available)
    try:
        import threading
        thread_local = getattr(threading.current_thread(), 'langgraph_context', None)
        if thread_local:
            context.update(thread_local)
    except Exception:
        pass
    
    # Try to get context from environment variables (fallback)
    import os
    if os.getenv('LANGGRAPH_USER_ID'):
        context['user_id'] = os.getenv('LANGGRAPH_USER_ID')
    if os.getenv('LANGGRAPH_AGENT_ID'):
        context['agent_id'] = os.getenv('LANGGRAPH_AGENT_ID')
    if os.getenv('LANGGRAPH_ASSISTANT_ID'):
        context['assistant_id'] = os.getenv('LANGGRAPH_ASSISTANT_ID')
    if os.getenv('LANGGRAPH_GRAPH_ID'):
        context['graph_id'] = os.getenv('LANGGRAPH_GRAPH_ID')
    if os.getenv('LANGGRAPH_THREAD_ID'):
        context['thread_id'] = os.getenv('LANGGRAPH_THREAD_ID')
    if os.getenv('LANGGRAPH_RUN_ID'):
        context['run_id'] = os.getenv('LANGGRAPH_RUN_ID')
    
    return context


def create_langchain_mcp_tool_with_universal_context(
    mcp_tool: Tool, 
    mcp_server_url: str, 
    auth_data: dict,
    config_getter: callable = None
) -> StructuredTool:
    """
    Create an MCP tool with universal context injection.
    
    This function creates an MCP tool that automatically injects all available
    LangGraph context (user_id, assistant_id, graph_id, thread_id, run_id) into
    tool calls. This is the recommended way to create MCP tools for LangGraph agents.
    
    Args:
        mcp_tool: The MCP tool definition
        mcp_server_url: Base URL of the MCP server
        auth_data: Authentication data for MCP server
        config_getter: Optional callable to extract RunnableConfig
        
    Returns:
        StructuredTool: MCP tool with universal context injection
        
    Example:
        ```python
        # Create MCP tools with automatic context injection
        mcp_tools = []
        for mcp_tool in available_mcp_tools:
            tool = create_langchain_mcp_tool_with_universal_context(
                mcp_tool, mcp_server_url, auth_data, config_getter
            )
            mcp_tools.append(tool)
        ```
    """
    # First create the standard MCP tool with auth
    mcp_tool_with_auth = create_langchain_mcp_tool_with_auth_data(
        mcp_tool, mcp_server_url, auth_data
    )
    
    # Then wrap it with authentication error handling
    mcp_tool_with_auth_handling = wrap_mcp_authenticate_tool(mcp_tool_with_auth)
    
    # Finally wrap with universal context injection
    return wrap_tool_with_context_injection(mcp_tool_with_auth_handling, config_getter)


def create_langchain_mcp_tool_with_memory_context(
    mcp_tool: Tool, 
    mcp_server_url: str, 
    auth_data: dict,
    state_getter: callable = None
) -> StructuredTool:
    """
    DEPRECATED: Create an MCP tool with automatic memory context injection.
    
    Use create_langchain_mcp_tool_with_universal_context() instead for 
    standardized context injection across all tools.
    
    This function is kept for backward compatibility.
    """
    # First create the standard MCP tool with auth
    mcp_tool_with_auth = create_langchain_mcp_tool_with_auth_data(
        mcp_tool, mcp_server_url, auth_data
    )
    
    # Then wrap it with authentication error handling
    mcp_tool_with_auth_handling = wrap_mcp_authenticate_tool(mcp_tool_with_auth)
    
    # Finally wrap with memory context injection (legacy)
    return wrap_memory_tool_with_context(mcp_tool_with_auth_handling, state_getter)


# ==================== File System Tool Factories ====================

async def create_fs_list_collections_tool(
    langconnect_api_url: str,
    access_token: str,
    scoped_collections: List[str]
) -> StructuredTool:
    """Create tool to list all accessible collections (scoped to agent config)."""
    
    @tool
    async def fs_list_collections() -> str:
        """List collections accessible to this agent with key metadata.

        Returns each collection's id, name, description, document count,
        total size, and your permission level (viewer/editor/owner).
        """
        import json
        import httpx
        
        url = f"{langconnect_api_url}/agent-filesystem/collections"
        headers = {"Authorization": f"Bearer {access_token}"}
        params = {"scoped_collections": ",".join(scoped_collections)}
        
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers, params=params, timeout=10.0)
            response.raise_for_status()
            data = response.json()
        
        return json.dumps(data, indent=2)
    
    return fs_list_collections


async def create_fs_list_files_tool(
    langconnect_api_url: str,
    access_token: str,
    scoped_collections: List[str]
) -> StructuredTool:
    """Create tool to list files across collections (scoped to agent config)."""
    
    @tool
    async def fs_list_files(
        collection_id: Annotated[Optional[str], "Optional collection filter; otherwise list across all accessible"] = None,
        limit: Annotated[int, "Max files to return (1-500). Default: 100"] = 100,
        sort_by: Annotated[str, "Sort by: 'updated_at' | 'created_at' | 'name' | 'size'"] = "updated_at"
    ) -> str:
        """List files across your scoped collections or a specific collection.

        Useful for discovery before reading or editing. Returns id, collection,
        name, description, sizes (bytes/lines), chunk_count, and timestamps.
        Use descriptions to understand file contents at a glance.
        """
        import json
        import httpx
        
        # Validate collection_id if provided
        if collection_id and collection_id not in scoped_collections:
            error_response = {
                "error": f"You don't have access to collection {collection_id}. Available collections can be found using fs_list_collections."
            }
            return json.dumps(error_response, indent=2)
        
        url = f"{langconnect_api_url}/agent-filesystem/files"
        headers = {"Authorization": f"Bearer {access_token}"}
        params = {
            "limit": min(limit, 500),
            "sort_by": sort_by,
            "scoped_collections": ",".join(scoped_collections)
        }
        if collection_id:
            params["collection_id"] = collection_id
        
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers, params=params, timeout=10.0)
            response.raise_for_status()
            data = response.json()
        
        return json.dumps(data, indent=2)
    
    return fs_list_files


async def create_fs_read_file_tool(
    langconnect_api_url: str,
    access_token: str,
    scoped_collections: List[str]
) -> StructuredTool:
    """Create tool to read file contents (scoped to agent config)."""
    
    @tool
    async def fs_read_file(
        document_id: Annotated[str, "Document UUID"],
        offset: Annotated[int, "Start line (0-based)"] = 0,
        limit: Annotated[int, "Lines to return (1-5000). Default: 2000"] = 2000
    ) -> str:
        """Read document content with line numbers; page using offset/limit.

        Returns `content` plus metadata: document_name, total_lines, line_range,
        and truncated (to indicate more content is available).
        """
        import json
        import httpx
        
        url = f"{langconnect_api_url}/agent-filesystem/files/{document_id}"
        headers = {"Authorization": f"Bearer {access_token}"}
        params = {
            "offset": offset,
            "limit": min(limit, 5000),
            "include_line_numbers": True,
            "scoped_collections": ",".join(scoped_collections)
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers, params=params, timeout=30.0)
            response.raise_for_status()
            data = response.json()
        
        # Return content with metadata
        result = {
            "content": data["content"],
            "metadata": {
                "document_name": data["document_name"],
                "total_lines": data["total_lines"],
                "line_range": data["line_range"],
                "truncated": data["truncated"]
            }
        }
        
        return json.dumps(result, indent=2)
    
    return fs_read_file


async def create_fs_grep_tool(
    langconnect_api_url: str,
    access_token: str,
    scoped_collections: List[str]
) -> StructuredTool:
    """Create tool to search for patterns across files (scoped to agent config)."""
    
    @tool
    async def fs_grep_files(
        pattern: Annotated[str, "Text or regex to search for"],
        collection_id: Annotated[Optional[str], "Optional collection filter"] = None,
        case_sensitive: Annotated[bool, "Case‑sensitive search"] = False,
        max_results: Annotated[int, "Max matches to return (1-500). Default: 100"] = 100
    ) -> str:
        """Find lines matching a text/regex across files; optionally filter by collection.

        Returns matches with document name, line number, line content, and small
        before/after context. Start simple, then add regex as needed.
        """
        import json
        import httpx
        
        # Validate collection_id if provided
        if collection_id and collection_id not in scoped_collections:
            error_response = {
                "error": f"You don't have access to collection {collection_id}. Available collections can be found using fs_list_collections."
            }
            return json.dumps(error_response, indent=2)
        
        url = f"{langconnect_api_url}/agent-filesystem/files/search"
        headers = {"Authorization": f"Bearer {access_token}"}
        payload = {
            "pattern": pattern,
            "case_sensitive": case_sensitive,
            "max_results": min(max_results, 500),
            "context_lines": 2,
            "scoped_collections": scoped_collections
        }
        if collection_id:
            payload["collection_id"] = collection_id
        
        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=headers, json=payload, timeout=30.0)
            response.raise_for_status()
            data = response.json()
        
        return json.dumps(data, indent=2)
    
    return fs_grep_files


async def create_fs_write_file_tool(
    langconnect_api_url: str,
    access_token: str,
    scoped_collections: List[str]
) -> StructuredTool:
    """Create tool to create new files (scoped to agent config)."""
    
    @tool
    async def fs_write_file(
        collection_id: Annotated[str, "Target collection UUID"],
        name: Annotated[str, "Document name/title"],
        content: Annotated[str, "Document content (markdown format unless otherwise specified)"],
        metadata: Annotated[Optional[dict], "Optional extra metadata"] = None
    ) -> str:
        """Create a new document in a collection using markdown format unless otherwise specified.
        Provide a clear title and well‑formatted content for best retrieval quality.
        """
        import json
        import httpx
        
        # Validate collection_id
        if collection_id not in scoped_collections:
            error_response = {
                "error": f"You don't have access to collection {collection_id}. Available collections can be found using fs_list_collections."
            }
            return json.dumps(error_response, indent=2)
        
        url = f"{langconnect_api_url}/agent-filesystem/collections/{collection_id}/files"
        headers = {"Authorization": f"Bearer {access_token}"}
        payload = {
            "name": name,
            "content": content,
            "metadata": metadata or {},
            "scoped_collections": scoped_collections
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=headers, json=payload, timeout=30.0)
            response.raise_for_status()
            data = response.json()
        
        return json.dumps(data, indent=2)
    
    return fs_write_file


async def create_fs_edit_file_tool(
    langconnect_api_url: str,
    access_token: str,
    scoped_collections: List[str]
) -> StructuredTool:
    """Create tool to edit file contents (scoped to agent config)."""
    
    @tool
    async def fs_edit_file(
        document_id: Annotated[str, "Document UUID"],
        old_string: Annotated[str, "Exact text to replace; include unique surrounding context"],
        new_string: Annotated[str, "Replacement text (empty to delete)"],
        replace_all: Annotated[bool, "Replace all occurrences instead of a single unique match"] = False
    ) -> str:
        """Replace exact text in a document using markdown format unless otherwise specified.

        Read the file first and include unique surrounding context in `old_string`
        to avoid ambiguous matches. Returns a diff preview and change counts.
        """
        import json
        import httpx
        
        url = f"{langconnect_api_url}/agent-filesystem/files/{document_id}"
        headers = {"Authorization": f"Bearer {access_token}"}
        payload = {
            "old_string": old_string,
            "new_string": new_string,
            "replace_all": replace_all,
            "scoped_collections": scoped_collections
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.patch(url, headers=headers, json=payload, timeout=30.0)
            response.raise_for_status()
            data = response.json()
        
        return json.dumps(data, indent=2)
    
    return fs_edit_file


async def create_fs_delete_file_tool(
    langconnect_api_url: str,
    access_token: str,
    scoped_collections: List[str]
) -> StructuredTool:
    """Create tool to delete files (scoped to agent config)."""
    
    @tool
    async def fs_delete_file(
        document_id: Annotated[str, "Document UUID"]
    ) -> str:
        """Permanently delete a document and its chunks (irreversible).

        Confirm the target before use; consider archiving when deletion isn't required.
        """
        import json
        import httpx
        
        url = f"{langconnect_api_url}/agent-filesystem/files/{document_id}"
        headers = {"Authorization": f"Bearer {access_token}"}
        params = {"scoped_collections": ",".join(scoped_collections)}
        
        async with httpx.AsyncClient() as client:
            response = await client.delete(url, headers=headers, params=params, timeout=10.0)
            response.raise_for_status()
            data = response.json()
        
        return json.dumps(data, indent=2)
    
    return fs_delete_file


async def create_collection_tools(
    langconnect_api_url: str,
    collection_ids: List[str],
    enabled_tools: List[str],
    access_token: str,
    config_getter: Optional[callable] = None
) -> List[StructuredTool]:
    """
    Create file system tools for document collections.
    
    This is the main orchestrator function that creates all enabled tools based on
    the agent's configuration. All tools are now scoped to the agent's configured
    collections for consistent permission enforcement.
    
    Args:
        langconnect_api_url: Base URL of LangConnect API
        collection_ids: List of collection UUIDs agent can access (scoped permissions)
        enabled_tools: List of tool names to create (from agent config)
        access_token: Supabase JWT for authentication
        config_getter: Optional callable to get RunnableConfig for context injection
        
    Returns:
        List of enabled and instantiated tools
        
    Tool Types:
        - hybrid_search: Collection-agnostic search with optional collection_id filter
        - File system tools: All work across configured collections with permission checks
    """
    tools = []
    
    # Normalize API URL
    if langconnect_api_url.endswith("/"):
        langconnect_api_url = langconnect_api_url[:-1]
    
    # Map of tool names to factory functions (all now receive scoped_collections)
    tool_factories = {
        # Search tool (collection-agnostic with optional filter)
        "hybrid_search": lambda: create_hybrid_search_tool(
            langconnect_api_url, access_token, collection_ids
        ),
        
        # File system tools (all scoped to configured collections)
        "fs_list_collections": lambda: create_fs_list_collections_tool(
            langconnect_api_url, access_token, collection_ids
        ),
        "fs_list_files": lambda: create_fs_list_files_tool(
            langconnect_api_url, access_token, collection_ids
        ),
        "fs_read_file": lambda: create_fs_read_file_tool(
            langconnect_api_url, access_token, collection_ids
        ),
        "fs_grep_files": lambda: create_fs_grep_tool(
            langconnect_api_url, access_token, collection_ids
        ),
        "fs_write_file": lambda: create_fs_write_file_tool(
            langconnect_api_url, access_token, collection_ids
        ),
        "fs_edit_file": lambda: create_fs_edit_file_tool(
            langconnect_api_url, access_token, collection_ids
        ),
        "fs_delete_file": lambda: create_fs_delete_file_tool(
            langconnect_api_url, access_token, collection_ids
        ),
    }
    
    for tool_name in enabled_tools:
        if tool_name not in tool_factories:
            logger.warning(f"[TOOL_CREATE] Unknown tool: {tool_name}")
            continue
            
        try:
            # All tools now created once (no per-collection duplication)
            tool = await tool_factories[tool_name]()
            
            # Wrap with context injection if config_getter provided
            if config_getter and tool_name == "hybrid_search":
                tool = wrap_tool_with_context_injection(tool, config_getter)
            
            tools.append(tool)
            logger.info(f"[TOOL_CREATE] Created {tool_name} (scoped to {len(collection_ids)} collections)")
                
        except Exception as e:
            logger.exception(f"[TOOL_CREATE] Failed to create {tool_name}: {e}")
            continue
    
    logger.info(f"[TOOL_CREATE] Successfully created {len(tools)} tools for {len(collection_ids)} collections")
    return tools