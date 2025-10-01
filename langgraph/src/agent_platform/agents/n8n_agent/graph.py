"""n8n Agent Graph - Bridges LangGraph to n8n workflows with streaming support."""

import json
import uuid
from typing import Any, Dict

import aiohttp
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.config import get_stream_writer
from langgraph.graph import MessagesState, StateGraph, START, END

from agent_platform.agents.n8n_agent.configuration import GraphConfigPydantic


def parse_n8n_streaming_chunk(chunk_text: str) -> str | None:
    """
    Parse n8n streaming chunk and extract content, filtering out metadata.
    
    Args:
        chunk_text: Raw chunk text from n8n stream
        
    Returns:
        Extracted content string or None if chunk should be filtered out
    """
    if not chunk_text.strip():
        return None

    try:
        data = json.loads(chunk_text.strip())
        
        if isinstance(data, dict):
            chunk_type = data.get("type", "")
            metadata = data.get("metadata", {}) or {}
            node_name = metadata.get("nodeName")
            
            # Filter out n8n metadata chunks
            if chunk_type in ["begin", "end"]:
                return None
                
            # Extract content from item chunks
            if chunk_type == "item":
                # Skip the final echoed payload from the Respond to Webhook node to avoid duplication
                if node_name and str(node_name).lower() == "respond to webhook":
                    return None
                content = data.get("content")
                if content:
                    # Handle the final JSON response from "Respond to Webhook" node
                    if content.startswith('{"output":'):
                        try:
                            output_data = json.loads(content)
                            return output_data.get("output", content)
                        except json.JSONDecodeError:
                            return content
                    return content
                    
        return None
        
    except json.JSONDecodeError:
        # Ignore incomplete/invalid fragments; we'll reassemble at the stream layer
        return None
    
    return None


async def n8n_bridge_node(state: MessagesState, config: RunnableConfig) -> Dict[str, Any]:
    """
    Bridge node that forwards messages to n8n webhook and streams back responses.
    
    Args:
        state: Current graph state containing messages
        config: Runtime configuration containing webhook_url
        
    Returns:
        State update with AI response message
    """
    # Get configuration
    configurable = config.get("configurable", {})
    webhook_url = configurable.get("webhook_url")
    
    if not webhook_url:
        raise ValueError("webhook_url is required in configuration")
    
    # Extract the latest user message
    messages = state.get("messages", [])
    if not messages:
        raise ValueError("No messages found in state")
    
    # Find the last human message and normalise to plain text
    user_message = None
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            content = message.content
            if isinstance(content, str):
                user_message = content
            else:
                # content can be a list of segments (e.g., {type: 'text', text: ...})
                parts: list[str] = []
                if isinstance(content, list):
                    for part in content:
                        # dict-like segment
                        if isinstance(part, dict):
                            text_val = part.get("text") or part.get("content")
                            if isinstance(text_val, str):
                                parts.append(text_val)
                            else:
                                # fallback to string cast
                                parts.append(str(text_val) if text_val is not None else "")
                        else:
                            # object segment (e.g., TextContent); try attributes
                            text_val = getattr(part, "text", None) or getattr(part, "content", None)
                            if isinstance(text_val, str):
                                parts.append(text_val)
                            else:
                                parts.append(str(part))
                    user_message = "".join(parts).strip()
                else:
                    # Unexpected structure; fallback to string
                    user_message = str(content)
            break
    
    if not user_message:
        raise ValueError("No user message found in conversation")
    
    # Generate thread_id from config thread_id or create a new one
    thread_id = config.get("configurable", {}).get("thread_id", str(uuid.uuid4()))
    
    # Get the full configurable metadata object and filter to JSON-serializable values
    configurable = config.get("configurable", {})
    
    # Filter out non-JSON-serializable objects (like ProxyUser, functions, etc.)
    serializable_config = {}
    for key, value in configurable.items():
        try:
            # Test if the value is JSON serializable
            json.dumps(value)
            serializable_config[key] = value
        except (TypeError, ValueError):
            # Skip non-serializable values (e.g., user objects, functions)
            pass
    
    # Prepare n8n payload with both simplified fields and filtered config
    payload = {
        "thread_id": thread_id,
        "user_message": user_message,
        "config": serializable_config  # Include only JSON-serializable config data
    }
    
    # Get stream writer for custom streaming
    writer = get_stream_writer()
    
    # Collect full response for final message
    full_response = ""
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                webhook_url,
                json=payload,
                headers={"Content-Type": "application/json"}
            ) as response:
                
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"n8n webhook returned HTTP {response.status}: {error_text}")
                
                # Stream the response using brace-matching to extract complete JSON objects
                buffer = ""
                async for chunk in response.content.iter_any():
                    if not chunk:
                        continue
                    
                    buffer += chunk.decode(errors="ignore")
                    
                    # Extract complete JSON objects from the buffer
                    while True:
                        start_idx = buffer.find("{")
                        if start_idx == -1:
                            # No opening brace yet; drop any leading non-JSON noise
                            buffer = ""
                            break
                        
                        # Find matching closing brace
                        brace_count = 0
                        end_idx = -1
                        for i, ch in enumerate(buffer[start_idx:], start=start_idx):
                            if ch == "{":
                                brace_count += 1
                            elif ch == "}":
                                brace_count -= 1
                                if brace_count == 0:
                                    end_idx = i
                                    break
                        
                        if end_idx == -1:
                            # Incomplete JSON; wait for more data
                            # Trim any leading noise before start_idx
                            if start_idx > 0:
                                buffer = buffer[start_idx:]
                            break
                        
                        json_obj = buffer[start_idx : end_idx + 1]
                        buffer = buffer[end_idx + 1 :]
                        
                        content = parse_n8n_streaming_chunk(json_obj)
                        if content:
                            full_response += content
                            if writer:
                                writer({"n8n_chunk": content})
    
    except Exception as e:
        error_msg = f"Error calling n8n webhook: {str(e)}"
        if writer:
            writer({"n8n_error": error_msg})
        raise Exception(error_msg)
    
    # Return the complete AI message
    if not full_response:
        full_response = "No response received from n8n workflow"
    
    return {"messages": [AIMessage(content=full_response)]}


def create_graph(config: GraphConfigPydantic) -> StateGraph:
    """
    Create the n8n bridge graph.
    
    Args:
        config: Configuration containing webhook URL
        
    Returns:
        Compiled StateGraph ready for execution
    """
    # Create the graph with MessagesState
    graph = StateGraph(MessagesState, config_schema=GraphConfigPydantic)
    
    # Add the bridge node
    graph.add_node("n8n_bridge", n8n_bridge_node)
    
    # Set up the flow: START -> n8n_bridge -> END
    graph.add_edge(START, "n8n_bridge")
    graph.add_edge("n8n_bridge", END)
    
    return graph.compile()


async def graph(config: RunnableConfig):
    """
    Module entrypoint used by LangGraph runtime. Validates config and
    returns a compiled graph that bridges to n8n.
    """
    # Build and return compiled graph (schema registered for UI),
    # do not hard-validate at load time to allow schema introspection
    return create_graph(GraphConfigPydantic())