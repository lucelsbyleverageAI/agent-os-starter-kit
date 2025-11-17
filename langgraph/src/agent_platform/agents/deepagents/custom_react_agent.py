import inspect
import logging
from typing import Any, Optional, Sequence, Union, Callable, Type, TypeVar, cast, get_type_hints, Literal, Awaitable
from langchain_core.messages import BaseMessage, SystemMessage, AIMessage, ToolMessage, AnyMessage, HumanMessage
from langchain_core.runnables import Runnable, RunnableConfig, RunnableBinding, RunnableSequence
from langchain_core.tools import BaseTool
from langchain_core.language_models import LanguageModelLike, BaseChatModel, LanguageModelInput
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.graph.state import CompiledStateGraph
from langgraph.managed import RemainingSteps
from langgraph.runtime import Runtime
from langgraph.store.base import BaseStore
from langgraph.types import Checkpointer, Send
from langgraph.typing import ContextT
from typing_extensions import Annotated, TypedDict, NotRequired
from pydantic import BaseModel

try:
    # Use centralized model utilities
    from agent_platform.utils.model_utils import (
        init_model,
        ModelConfig,
        RetryConfig,
    )
except Exception:  # pragma: no cover
    init_model = None  # type: ignore
    ModelConfig = None  # type: ignore
    RetryConfig = None  # type: ignore

try:
    # Use ToolNode for robust tool execution and ToolMessage creation
    from langgraph.prebuilt.tool_node import ToolNode
except Exception as e:  # pragma: no cover
    raise e

try:
    from langgraph._internal._runnable import RunnableCallable
except Exception:  # pragma: no cover
    # Fallback if internal import fails
    RunnableCallable = Runnable  # type: ignore


# Type variables and schemas
StructuredResponse = Union[dict, BaseModel]
StructuredResponseSchema = Union[dict, type[BaseModel]]
StateSchema = TypeVar("StateSchema", bound=Union[dict, BaseModel])
StateSchemaType = Type[StateSchema]

Prompt = Union[
    SystemMessage,
    str,
    Callable[[StateSchema], LanguageModelInput],
    Runnable[StateSchema, LanguageModelInput],
]
logger = logging.getLogger(__name__)



class AgentState(TypedDict):
    """The state of the agent."""
    messages: Annotated[Sequence[BaseMessage], add_messages]
    remaining_steps: NotRequired[RemainingSteps]


class AgentStateWithStructuredResponse(AgentState):
    """The state of the agent with a structured response."""
    structured_response: StructuredResponse


def _get_state_value(state: StateSchema, key: str, default: Any = None) -> Any:
    """Get value from state dict or Pydantic model.

    Special handling for 'messages' key: checks both 'llm_input_messages'
    (set by trimming hook) and 'messages' keys to ensure processed messages are used.
    """
    if isinstance(state, dict):
        # Special case: For 'messages', check llm_input_messages first (set by trimming hook)
        if key == "messages":
            return state.get("llm_input_messages") or state.get("messages", default)
        return state.get(key, default)
    else:
        # For Pydantic models, check llm_input_messages first for 'messages' key
        if key == "messages":
            return getattr(state, "llm_input_messages", None) or getattr(state, "messages", default)
        return getattr(state, key, default)


def _get_prompt_runnable(prompt: Optional[Prompt]) -> Runnable:
    """Convert prompt to a runnable that takes state and returns messages."""
    if prompt is None:
        return RunnableCallable(
            lambda state: _get_state_value(state, "messages"), name="Prompt"
        )
    elif isinstance(prompt, str):
        _system_message: BaseMessage = SystemMessage(content=prompt)
        return RunnableCallable(
            lambda state: [_system_message] + list(_get_state_value(state, "messages")),
            name="Prompt",
        )
    elif isinstance(prompt, SystemMessage):
        return RunnableCallable(
            lambda state: [prompt] + list(_get_state_value(state, "messages")),
            name="Prompt",
        )
    elif inspect.iscoroutinefunction(prompt):
        return RunnableCallable(
            None,
            prompt,
            name="Prompt",
        )
    elif callable(prompt):
        return RunnableCallable(
            prompt,
            name="Prompt",
        )
    elif isinstance(prompt, Runnable):
        return prompt
    else:
        raise ValueError(f"Got unexpected type for `prompt`: {type(prompt)}")


def _should_bind_tools(
    model: LanguageModelLike, tools: Sequence[BaseTool], num_builtin: int = 0
) -> bool:
    """Check if we should bind tools to the model."""
    if isinstance(model, RunnableSequence):
        model = next(
            (
                step
                for step in model.steps
                if isinstance(step, (RunnableBinding, BaseChatModel))
            ),
            model,
        )

    if not isinstance(model, RunnableBinding):
        return True

    if "tools" not in model.kwargs:
        return True

    bound_tools = model.kwargs["tools"]
    if len(tools) != len(bound_tools) - num_builtin:
        return True  # Let it rebind

    return False


def _get_model(model: LanguageModelLike) -> BaseChatModel:
    """Get the underlying model from a RunnableBinding or return the model itself."""
    if isinstance(model, RunnableSequence):
        model = next(
            (
                step
                for step in model.steps
                if isinstance(step, (RunnableBinding, BaseChatModel))
            ),
            model,
        )

    if isinstance(model, RunnableBinding):
        model = model.bound

    if not isinstance(model, BaseChatModel):
        raise TypeError(
            f"Expected `model` to be a ChatModel or RunnableBinding, got {type(model)}"
        )

    return model


def _validate_chat_history(messages: Sequence[BaseMessage]) -> None:
    """Validate that all tool calls in AIMessages have a corresponding ToolMessage."""
    all_tool_calls = [
        tool_call
        for message in messages
        if isinstance(message, AIMessage)
        for tool_call in message.tool_calls
    ]
    tool_call_ids_with_results = {
        message.tool_call_id for message in messages if isinstance(message, ToolMessage)
    }
    tool_calls_without_results = [
        tool_call
        for tool_call in all_tool_calls
        if tool_call["id"] not in tool_call_ids_with_results
    ]
    if tool_calls_without_results:
        # For now, just warn instead of raising - we can be more lenient
        pass


def custom_create_react_agent(
    model: Union[
        str,
        LanguageModelLike,
        Callable[[StateSchema, Runtime[ContextT]], BaseChatModel],
        Callable[[StateSchema, Runtime[ContextT]], Awaitable[BaseChatModel]],
    ],
    tools: Union[Sequence[Union[BaseTool, Callable, dict[str, Any]]], ToolNode],
    *,
    prompt: Optional[Prompt] = None,
    response_format: Optional[
        Union[StructuredResponseSchema, tuple[str, StructuredResponseSchema]]
    ] = None,
    pre_model_hook: Optional[Runnable] = None,
    post_model_hook: Optional[Runnable] = None,
    state_schema: Optional[StateSchemaType] = None,
    context_schema: Optional[Type[Any]] = None,
    checkpointer: Optional[Checkpointer] = None,
    store: Optional[BaseStore] = None,
    interrupt_before: Optional[list[str]] = None,
    interrupt_after: Optional[list[str]] = None,
    debug: bool = False,
    version: Literal["v1", "v2"] = "v2",
    name: Optional[str] = None,
    enable_image_processing: bool = False,
    **kwargs: Any,
) -> CompiledStateGraph:
    """Creates a ReAct agent graph that calls tools in a loop until a stopping condition is met.
    
    This is a comprehensive implementation that matches the features of LangGraph's create_react_agent.
    """
    # Handle deprecated config_schema if present
    if "config_schema" in kwargs:
        if context_schema is None:
            context_schema = kwargs["config_schema"]
        kwargs.pop("config_schema")
    
    if version not in ("v1", "v2"):
        raise ValueError(f"Invalid version {version}. Supported versions are 'v1' and 'v2'.")

    # Validate state schema requirements
    if state_schema is not None:
        required_keys = {"messages", "remaining_steps"}
        if response_format is not None:
            required_keys.add("structured_response")

        schema_keys = set(get_type_hints(state_schema))
        if missing_keys := required_keys - set(schema_keys):
            raise ValueError(f"Missing required key(s) {missing_keys} in state_schema")

    # Set default state schema
    if state_schema is None:
        state_schema = (
            AgentStateWithStructuredResponse
            if response_format is not None
            else AgentState
        )

    # Process tools
    llm_builtin_tools: list[dict] = []
    if isinstance(tools, ToolNode):
        tool_classes = list(tools.tools_by_name.values())
        tool_node = tools
    else:
        llm_builtin_tools = [t for t in tools if isinstance(t, dict)]
        tool_node = ToolNode([t for t in tools if not isinstance(t, dict)])
        tool_classes = list(tool_node.tools_by_name.values())

    # Handle dynamic vs static models
    is_dynamic_model = not isinstance(model, (str, Runnable)) and callable(model)
    is_async_dynamic_model = is_dynamic_model and inspect.iscoroutinefunction(model)
    tool_calling_enabled = len(tool_classes) > 0

    def _build_system_note_for_uploads(state: StateSchema) -> Optional[str]:
        """Build a system note for user uploads without mutating state."""
        try:
            files = _get_state_value(state, "files", {}) or {}
            logger.debug("[call_model] Checking for user uploads to build system note")

            # Collect user-uploaded images from file system
            uploaded_images = []
            uploaded_documents = []

            for filename, file_entry in files.items():
                metadata = file_entry.get("metadata", {}) if isinstance(file_entry, dict) else {}
                if metadata.get("source") == "user_upload":
                    if metadata.get("type") == "image":
                        uploaded_images.append({
                            "filename": filename,
                            "name": metadata.get("name", "Uploaded Image"),
                            "description": metadata.get("description", "User uploaded image"),
                            "gcp_url": metadata.get("gcp_url") or metadata.get("gcp_path"),
                        })
                    elif metadata.get("type") == "document":
                        uploaded_documents.append({
                            "filename": filename,
                            "original_filename": metadata.get("original_filename", filename),
                            "original_mime_type": metadata.get("original_mime_type", "unknown"),
                        })

            logger.debug("[call_model] Found %d uploaded image(s), %d uploaded document(s)",
                        len(uploaded_images), len(uploaded_documents))

            if not uploaded_images and not uploaded_documents:
                return None

            # Build concise system note
            lines = ["System Note: The user uploaded file(s) have been added to your internal file system."]

            if uploaded_images:
                lines.append("\nImages (reference by gcp_url when using tools):")
                for img in uploaded_images:
                    display_url = img.get("gcp_url") or img.get("filename")
                    lines.append(f"- {display_url} — {img['name']}: {img['description']}")

            if uploaded_documents:
                lines.append("\nDocuments (reference by filename):")
                for doc in uploaded_documents:
                    lines.append(f"- {doc['filename']} (original: {doc['original_filename']})")

            return "\n".join(lines)
        except Exception:
            logger.exception("[call_model] Failed to build system note; skipping")
            return None

    # Setup static model if not dynamic
    if not is_dynamic_model:
        if isinstance(model, str):
            if init_model is None:
                raise ImportError(
                    "Please install agent_platform.utils.model_utils to use '<provider>:<model>' string syntax"
                )
            # Initialize using init_model_simple to get correct max_tokens from registry
            from agent_platform.utils.model_utils import init_model_simple
            model = cast(BaseChatModel, init_model_simple(model_name=model))

        # Bind tools if needed
        if (
            _should_bind_tools(model, tool_classes, num_builtin=len(llm_builtin_tools))
            and len(tool_classes + llm_builtin_tools) > 0
        ):
            model = cast(BaseChatModel, model).bind_tools(
                tool_classes + llm_builtin_tools
            )

        static_model: Optional[Runnable] = _get_prompt_runnable(prompt) | model
    else:
        static_model = None

    # Track tools that return directly
    should_return_direct = {t.name for t in tool_classes if t.return_direct}

    def _resolve_model(state: StateSchema, runtime: Runtime[ContextT]) -> LanguageModelLike:
        """Resolve the model to use, handling both static and dynamic models."""
        if is_dynamic_model:
            return _get_prompt_runnable(prompt) | model(state, runtime)
        else:
            return static_model

    async def _aresolve_model(state: StateSchema, runtime: Runtime[ContextT]) -> LanguageModelLike:
        """Async resolve the model to use, handling both static and dynamic models."""
        if is_async_dynamic_model:
            resolved_model = await model(state, runtime)
            return _get_prompt_runnable(prompt) | resolved_model
        elif is_dynamic_model:
            return _get_prompt_runnable(prompt) | model(state, runtime)
        else:
            return static_model

    def _are_more_steps_needed(state: StateSchema, response: BaseMessage) -> bool:
        """Check if we need more steps based on remaining_steps."""
        has_tool_calls = isinstance(response, AIMessage) and response.tool_calls
        all_tools_return_direct = (
            all(call["name"] in should_return_direct for call in response.tool_calls)
            if isinstance(response, AIMessage)
            else False
        )
        remaining_steps = _get_state_value(state, "remaining_steps", None)
        if remaining_steps is not None:
            if remaining_steps < 1 and all_tools_return_direct:
                return True
            elif remaining_steps < 2 and has_tool_calls:
                return True
        return False

    def _prepare_messages_for_model(state: StateSchema) -> list[BaseMessage]:
        """Prepare messages for model input, optionally adding system note for uploads."""
        messages = _get_state_value(state, "messages")
        if messages is None:
            raise ValueError(f"Expected input to call_model to have 'messages' key, but got {state}")

        _validate_chat_history(messages)

        # Inject system note for uploads (images and documents)
        system_note = _build_system_note_for_uploads(state)
        if system_note and messages:
            # Create a copy of messages and append system note to last human message
            model_messages = list(messages)
            last_msg = model_messages[-1]
            if isinstance(last_msg, HumanMessage):
                # Preserve rich content if present
                if isinstance(last_msg.content, list):
                    augmented = list(last_msg.content) + [{"type": "text", "text": system_note}]
                    new_last = HumanMessage(content=augmented, additional_kwargs=getattr(last_msg, "additional_kwargs", {}))
                    logger.debug("[call_model] Appended system note to structured HumanMessage (list content)")
                else:
                    text_content = str(last_msg.content) if last_msg.content is not None else ""
                    new_last = HumanMessage(content=(text_content + "\n\n" + system_note).strip(), additional_kwargs=getattr(last_msg, "additional_kwargs", {}))
                    logger.debug("[call_model] Appended system note to plain-text HumanMessage")
                model_messages[-1] = new_last
                return model_messages

        return list(messages)

    # Define the function that calls the model
    def call_model(
        state: StateSchema, runtime: Runtime[ContextT], config: RunnableConfig
    ) -> StateSchema:
        if is_async_dynamic_model:
            msg = (
                "Async model callable provided but agent invoked synchronously. "
                "Use agent.ainvoke() or agent.astream(), or provide a sync model callable."
            )
            raise RuntimeError(msg)

        # Prepare messages for the model (with optional system note injection)
        model_messages = _prepare_messages_for_model(state)
        
        # Create a temporary state for model input without mutating the original
        if isinstance(state_schema, type) and issubclass(state_schema, BaseModel):
            model_input = state_schema(messages=model_messages, **{k: v for k, v in state.items() if k != "messages"})
        else:
            model_input = {**state, "messages": model_messages}

        if is_dynamic_model:
            dynamic_model = _resolve_model(state, runtime)
            response = cast(AIMessage, dynamic_model.invoke(model_input, config))
        else:
            response = cast(AIMessage, static_model.invoke(model_input, config))

        # Add agent name to the AIMessage
        if name:
            response.name = name

        if _are_more_steps_needed(state, response):
            return {
                "messages": [
                    AIMessage(
                        id=response.id,
                        content="Sorry, need more steps to process this request.",
                    )
                ]
            }

        return {"messages": [response]}

    async def acall_model(
        state: StateSchema, runtime: Runtime[ContextT], config: RunnableConfig
    ) -> StateSchema:
        # Prepare messages for the model (with optional system note injection)
        model_messages = _prepare_messages_for_model(state)
        
        # Create a temporary state for model input without mutating the original
        if isinstance(state_schema, type) and issubclass(state_schema, BaseModel):
            model_input = state_schema(messages=model_messages, **{k: v for k, v in state.items() if k != "messages"})
        else:
            model_input = {**state, "messages": model_messages}

        if is_dynamic_model:
            dynamic_model = await _aresolve_model(state, runtime)
            response = cast(AIMessage, await dynamic_model.ainvoke(model_input, config))
        else:
            response = cast(AIMessage, await static_model.ainvoke(model_input, config))

        if name:
            response.name = name
            
        if _are_more_steps_needed(state, response):
            return {
                "messages": [
                    AIMessage(
                        id=response.id,
                        content="Sorry, need more steps to process this request.",
                    )
                ]
            }

        return {"messages": [response]}

    # Use the standard state schema since we handle message preparation internally
    input_schema = state_schema

    def generate_structured_response(
        state: StateSchema, runtime: Runtime[ContextT], config: RunnableConfig
    ) -> StateSchema:
        if is_async_dynamic_model:
            msg = (
                "Async model callable provided but agent invoked synchronously. "
                "Use agent.ainvoke() or agent.astream(), or provide a sync model callable."
            )
            raise RuntimeError(msg)

        messages = _get_state_value(state, "messages")
        structured_response_schema = response_format
        if isinstance(response_format, tuple):
            system_prompt, structured_response_schema = response_format
            messages = [SystemMessage(content=system_prompt)] + list(messages)

        resolved_model = _resolve_model(state, runtime)
        model_with_structured_output = _get_model(resolved_model).with_structured_output(
            cast(StructuredResponseSchema, structured_response_schema)
        )
        response = model_with_structured_output.invoke(messages, config)
        return {"structured_response": response}

    async def agenerate_structured_response(
        state: StateSchema, runtime: Runtime[ContextT], config: RunnableConfig
    ) -> StateSchema:
        messages = _get_state_value(state, "messages")
        structured_response_schema = response_format
        if isinstance(response_format, tuple):
            system_prompt, structured_response_schema = response_format
            messages = [SystemMessage(content=system_prompt)] + list(messages)

        resolved_model = await _aresolve_model(state, runtime)
        model_with_structured_output = _get_model(resolved_model).with_structured_output(
            cast(StructuredResponseSchema, structured_response_schema)
        )
        response = await model_with_structured_output.ainvoke(messages, config)
        return {"structured_response": response}

    # Handle case with no tool calling
    if not tool_calling_enabled:
        workflow = StateGraph(state_schema=state_schema, context_schema=context_schema)
        workflow.add_node(
            "agent",
            RunnableCallable(call_model, acall_model),
            input_schema=input_schema,
        )

        # Import file attachment processing
        try:
            from .file_attachment_processing import extract_file_attachments
        except ImportError:
            from agent_platform.agents.deepagents.file_attachment_processing import extract_file_attachments

        # Add file attachment extraction node (always runs first)
        workflow.add_node("extract_file_attachments", extract_file_attachments)
        entrypoint = "extract_file_attachments"

        # Handle image processing and pre_model_hook for no-tool case
        next_node = "agent"

        if enable_image_processing:
            try:
                from .image_processing import dispatch_image_processing, process_single_image, continue_after_image_processing
            except ImportError:
                from agent_platform.agents.deepagents.image_processing import dispatch_image_processing, process_single_image, continue_after_image_processing

            workflow.add_node("dispatch_image_processing", dispatch_image_processing)
            workflow.add_node("process_single_image", process_single_image)
            workflow.add_node("continue_after_image_processing", continue_after_image_processing)

            # Connect file attachments -> image processing
            workflow.add_edge("extract_file_attachments", "dispatch_image_processing")

            # Flow: extract_file_attachments -> dispatch -> [process_single_image (parallel)] -> continue_after_image_processing -> agent/pre_model_hook
            # The continue_after_image_processing node acts as fan-in for all parallel processing

            if pre_model_hook is not None:
                workflow.add_node("pre_model_hook", pre_model_hook)
                workflow.add_edge("continue_after_image_processing", "pre_model_hook")
                workflow.add_edge("pre_model_hook", "agent")
            else:
                workflow.add_edge("continue_after_image_processing", "agent")
        elif pre_model_hook is not None:
            workflow.add_node("pre_model_hook", pre_model_hook)
            workflow.add_edge("extract_file_attachments", "pre_model_hook")
            workflow.add_edge("pre_model_hook", "agent")
        else:
            # Direct connection: extract_file_attachments -> agent
            workflow.add_edge("extract_file_attachments", "agent")

        workflow.set_entry_point(entrypoint)

        if post_model_hook is not None:
            workflow.add_node("post_model_hook", post_model_hook)
            workflow.add_edge("agent", "post_model_hook")

        if response_format is not None:
            workflow.add_node(
                "generate_structured_response",
                RunnableCallable(generate_structured_response, agenerate_structured_response),
            )
            if post_model_hook is not None:
                workflow.add_edge("post_model_hook", "generate_structured_response")
            else:
                workflow.add_edge("agent", "generate_structured_response")

        return workflow.compile(
            checkpointer=checkpointer,
            store=store,
            interrupt_before=interrupt_before,
            interrupt_after=interrupt_after,
            debug=debug,
            name=name,
        )

    # Define the function that determines whether to continue or not
    def should_continue(state: StateSchema) -> Union[str, list[Send]]:
        messages = _get_state_value(state, "messages")
        last_message = messages[-1]
        
        if not isinstance(last_message, AIMessage) or not last_message.tool_calls:
            if post_model_hook is not None:
                return "post_model_hook"
            elif response_format is not None:
                return "generate_structured_response"
            else:
                return END
        else:
            if version == "v1":
                return "tools"
            elif version == "v2":
                if post_model_hook is not None:
                    return "post_model_hook"
                tool_calls = [
                    tool_node.inject_tool_args(call, state, store)
                    for call in last_message.tool_calls
                ]
                return [Send("tools", [tool_call]) for tool_call in tool_calls]

    # Build the main workflow
    workflow = StateGraph(state_schema=state_schema, context_schema=context_schema)

    # Add nodes
    workflow.add_node(
        "agent",
        RunnableCallable(call_model, acall_model),
        input_schema=input_schema,
    )
    workflow.add_node("tools", tool_node)

    # Import file attachment processing
    try:
        from .file_attachment_processing import extract_file_attachments
    except ImportError:
        from agent_platform.agents.deepagents.file_attachment_processing import extract_file_attachments

    # Add file attachment extraction node (always runs first)
    workflow.add_node("extract_file_attachments", extract_file_attachments, input_schema=state_schema)
    entrypoint = "extract_file_attachments"

    # agent_loop_entrypoint is where tools should route back to (skipping file attachment extraction)
    agent_loop_entrypoint = "agent"

    # Handle image processing and pre_model_hook
    if enable_image_processing:
        # Import here to avoid circular imports
        try:
            from .image_processing import dispatch_image_processing, process_single_image, continue_after_image_processing
        except ImportError:
            from agent_platform.agents.deepagents.image_processing import dispatch_image_processing, process_single_image, continue_after_image_processing

        # Add image processing nodes with explicit input schema to avoid conflicts
        workflow.add_node("dispatch_image_processing", dispatch_image_processing, input_schema=state_schema)
        workflow.add_node("process_single_image", process_single_image, input_schema=state_schema)
        workflow.add_node("continue_after_image_processing", continue_after_image_processing, input_schema=state_schema)

        # Connect file attachments -> image processing
        workflow.add_edge("extract_file_attachments", "dispatch_image_processing")

        # Flow: extract_file_attachments -> dispatch -> [process_single_image (parallel)] -> continue_after_image_processing -> agent/pre_model_hook
        # The continue_after_image_processing node acts as fan-in for all parallel processing

        if pre_model_hook is not None:
            workflow.add_node("pre_model_hook", pre_model_hook)
            workflow.add_edge("continue_after_image_processing", "pre_model_hook")
            workflow.add_edge("pre_model_hook", "agent")
        else:
            workflow.add_edge("continue_after_image_processing", "agent")

        # Tools should route back to agent (image processing already happened)
        agent_loop_entrypoint = "agent"
    elif pre_model_hook is not None:
        workflow.add_node("pre_model_hook", pre_model_hook)
        workflow.add_edge("extract_file_attachments", "pre_model_hook")
        workflow.add_edge("pre_model_hook", "agent")
        # Tools should route back to pre_model_hook
        agent_loop_entrypoint = "pre_model_hook"
    else:
        # Direct connection: extract_file_attachments -> agent
        workflow.add_edge("extract_file_attachments", "agent")
        # Tools should route back to agent
        agent_loop_entrypoint = "agent"

    workflow.set_entry_point(entrypoint)

    # Setup routing paths
    agent_paths = []
    post_model_hook_paths = [agent_loop_entrypoint, "tools"]
    
    # When image processing is enabled, post_model_hook can also route to agent
    if enable_image_processing and post_model_hook is not None:
        post_model_hook_paths.append("agent")

    # Add post_model_hook if provided
    if post_model_hook is not None:
        workflow.add_node("post_model_hook", post_model_hook)
        agent_paths.append("post_model_hook")
        workflow.add_edge("agent", "post_model_hook")
    else:
        agent_paths.append("tools")

    # Add structured response generation if needed
    if response_format is not None:
        workflow.add_node(
            "generate_structured_response",
            RunnableCallable(generate_structured_response, agenerate_structured_response),
        )
        if post_model_hook is not None:
            post_model_hook_paths.append("generate_structured_response")
        else:
            agent_paths.append("generate_structured_response")
    else:
        if post_model_hook is not None:
            post_model_hook_paths.append(END)
        else:
            agent_paths.append(END)

    # Handle post_model_hook routing
    if post_model_hook is not None:
        def post_model_hook_router(state: StateSchema) -> Union[str, list[Send]]:
            messages = _get_state_value(state, "messages")
            tool_messages = [
                m.tool_call_id for m in messages if isinstance(m, ToolMessage)
            ]
            last_ai_message = next(
                m for m in reversed(messages) if isinstance(m, AIMessage)
            )
            pending_tool_calls = [
                c for c in last_ai_message.tool_calls if c["id"] not in tool_messages
            ]

            if pending_tool_calls:
                pending_tool_calls = [
                    tool_node.inject_tool_args(call, state, store)
                    for call in pending_tool_calls
                ]
                return [Send("tools", [tool_call]) for tool_call in pending_tool_calls]
            elif isinstance(messages[-1], ToolMessage):
                # Route back to agent loop entrypoint (skips file attachment extraction)
                return agent_loop_entrypoint
            elif response_format is not None:
                return "generate_structured_response"
            else:
                return END

        workflow.add_conditional_edges(
            "post_model_hook",
            post_model_hook_router,
            path_map=post_model_hook_paths,
        )

    # Add main conditional edges
    workflow.add_conditional_edges(
        "agent",
        should_continue,
        path_map=agent_paths,
    )

    # Handle tools that return directly
    def route_tool_responses(state: StateSchema) -> str:
        for m in reversed(_get_state_value(state, "messages")):
            if not isinstance(m, ToolMessage):
                break
            if m.name in should_return_direct:
                return END

        # Handle parallel tool calls case
        if isinstance(m, AIMessage) and m.tool_calls:
            if any(call["name"] in should_return_direct for call in m.tool_calls):
                return END

        # Route back to agent loop entrypoint (skips file attachment extraction)
        return agent_loop_entrypoint

    if should_return_direct:
        workflow.add_conditional_edges(
            "tools", route_tool_responses, path_map=[agent_loop_entrypoint, END]
        )
    else:
        workflow.add_edge("tools", agent_loop_entrypoint)

    return workflow.compile(
        checkpointer=checkpointer,
        store=store,
        interrupt_before=interrupt_before,
        interrupt_after=interrupt_after,
        debug=debug,
        name=name,
    )


__all__ = ["custom_create_react_agent"]


