"""
Thread Naming Service

AI-powered automatic thread naming and summarization using GPT-5 nano.
Generates concise names and detailed summaries from conversation history.
Features token limiting to prevent excessive costs on long conversations.
"""

import logging
from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field
from openai import AsyncOpenAI
import asyncpg
from starlette.config import Config
import tiktoken

from langconnect.services.langgraph_integration import LangGraphService

log = logging.getLogger(__name__)
env = Config()

# Configuration
THREAD_NAMING_ENABLED = env("THREAD_NAMING_ENABLED", cast=str, default="true").lower() == "true"
THREAD_NAMING_MODEL = env("THREAD_NAMING_MODEL", cast=str, default="gpt-5-nano")
MAX_TOKENS_FOR_NAMING = env("MAX_TOKENS_FOR_NAMING", cast=int, default=20000)
OPENAI_API_KEY = env("OPENAI_API_KEY", cast=str, default="")


class ThreadNamingSummary(BaseModel):
    """Structured output from LLM for thread naming."""

    name: str = Field(
        description="Concise thread name (3-5 words) summarizing the conversation topic"
    )
    summary: str = Field(
        description="Detailed paragraph-length summary of the conversation content and context"
    )


class ThreadNamingService:
    """
    Service for AI-powered thread naming and summarization.

    Uses GPT-5 nano (default) with structured output to generate:
    - Concise thread names (3-5 words)
    - Detailed conversation summaries (paragraph length)

    Features token limiting to prevent excessive costs on long conversations.
    Respects user rename intent via the user_renamed flag.
    """

    def __init__(
        self,
        db_pool: asyncpg.Pool,
        openai_api_key: Optional[str] = None,
        model: str = THREAD_NAMING_MODEL
    ):
        """
        Initialize the thread naming service.

        Args:
            db_pool: Database connection pool
            openai_api_key: OpenAI API key (defaults to env var)
            model: Model to use for naming (defaults to gpt-4o-mini)
        """
        self.db_pool = db_pool
        self.model = model
        self.langgraph_service = LangGraphService()

        # Initialize OpenAI client
        api_key = openai_api_key or OPENAI_API_KEY
        if not api_key:
            log.warning("OPENAI_API_KEY not configured - thread naming will fail")

        self.openai_client = AsyncOpenAI(api_key=api_key) if api_key else None

    async def fetch_thread_messages(
        self,
        thread_id: str,
        user_token: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Fetch conversation messages from LangGraph API.

        Filters to only human and AI messages (excludes tool calls).

        Args:
            thread_id: UUID of the thread
            user_token: Optional user JWT for scoped access

        Returns:
            List of message dictionaries with 'role' and 'content' keys

        Raises:
            RuntimeError: If LangGraph API request fails
        """
        try:
            # Fetch thread history from LangGraph
            # LangGraph stores messages in thread state
            response = await self.langgraph_service._make_request(
                method="GET",
                endpoint=f"/threads/{thread_id}/history",
                user_token=user_token
            )

            # Extract messages from response
            # LangGraph history format: Array of ThreadState objects
            # Each ThreadState: {values: {...}, next: [...], checkpoint: {...}, metadata: {...}, ...}
            thread_states = response if isinstance(response, list) else []
            all_messages = []

            for state in thread_states:
                # Extract values from each ThreadState
                state_values = state.get("values", {})
                messages = state_values.get("messages", [])
                for msg in messages:
                    # Only include human and AI messages
                    msg_type = msg.get("type", "")
                    if msg_type in ["human", "ai"]:
                        content = self._extract_message_content(msg)
                        if content:  # Skip empty messages
                            all_messages.append({
                                "role": "human" if msg_type == "human" else "ai",
                                "content": content
                            })

            log.info(f"Fetched {len(all_messages)} messages for thread {thread_id}")
            return all_messages

        except Exception as e:
            log.error(f"Failed to fetch messages for thread {thread_id}: {e}")
            raise RuntimeError(f"Failed to fetch thread messages: {e}")

    def _extract_message_content(self, message: Dict[str, Any]) -> str:
        """
        Extract text content from a LangGraph message.

        Handles both string content and structured content arrays.

        Args:
            message: Message dictionary from LangGraph

        Returns:
            Extracted text content
        """
        content = message.get("content", "")

        # Handle string content
        if isinstance(content, str):
            return content.strip()

        # Handle structured content (array of content blocks)
        if isinstance(content, list):
            text_parts = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    text_parts.append(block.get("text", ""))
                elif isinstance(block, str):
                    text_parts.append(block)
            return " ".join(text_parts).strip()

        return ""

    def _format_messages_for_llm(self, messages: List[Dict[str, Any]]) -> str:
        """
        Format messages as markdown for LLM input.

        Args:
            messages: List of message dictionaries

        Returns:
            Formatted markdown string
        """
        formatted_lines = []

        for msg in messages:
            role = msg["role"]
            content = msg["content"]

            # Format as markdown
            if role == "human":
                formatted_lines.append(f"**User**: {content}")
            elif role == "ai":
                formatted_lines.append(f"**Assistant**: {content}")

        return "\n\n".join(formatted_lines)

    def _trim_messages_to_token_limit(
        self,
        messages: List[Dict[str, Any]],
        max_tokens: int = MAX_TOKENS_FOR_NAMING
    ) -> List[Dict[str, Any]]:
        """
        Trim messages to stay under token limit by removing earliest messages.

        Strategy: Keep removing the oldest messages until we're under the limit.
        This preserves recent context which is more important for naming.

        Args:
            messages: List of message dictionaries
            max_tokens: Maximum tokens allowed (default: 20000)

        Returns:
            Trimmed list of messages
        """
        if not messages:
            return messages

        try:
            # Initialize tokenizer for gpt-5 (uses same encoding as gpt-4)
            encoding = tiktoken.encoding_for_model("gpt-4")
        except KeyError:
            # Fallback to cl100k_base encoding (used by GPT-4/GPT-5)
            encoding = tiktoken.get_encoding("cl100k_base")

        # Count tokens for all messages
        formatted = self._format_messages_for_llm(messages)
        total_tokens = len(encoding.encode(formatted))

        # If already under limit, return as-is
        if total_tokens <= max_tokens:
            log.info(f"Messages within token limit: {total_tokens}/{max_tokens} tokens")
            return messages

        # Trim from the start (earliest messages)
        trimmed_messages = messages.copy()
        while total_tokens > max_tokens and len(trimmed_messages) > 5:
            # Always keep at least 5 messages for context
            trimmed_messages.pop(0)  # Remove oldest message
            formatted = self._format_messages_for_llm(trimmed_messages)
            total_tokens = len(encoding.encode(formatted))

        removed_count = len(messages) - len(trimmed_messages)
        log.info(
            f"Trimmed {removed_count} messages to fit token limit: "
            f"{total_tokens}/{max_tokens} tokens ({len(trimmed_messages)} messages kept)"
        )

        return trimmed_messages

    async def generate_name_and_summary(
        self,
        messages: List[Dict[str, Any]]
    ) -> ThreadNamingSummary:
        """
        Generate thread name and summary using GPT-5 nano (or configured model).

        Uses OpenAI's structured output feature for reliable parsing.
        Automatically trims messages to stay within token limits.

        Args:
            messages: List of conversation messages

        Returns:
            ThreadNamingSummary with name and summary fields

        Raises:
            RuntimeError: If OpenAI API call fails or client not configured
        """
        if not self.openai_client:
            raise RuntimeError("OpenAI client not configured - check OPENAI_API_KEY")

        if not messages:
            raise RuntimeError("Cannot generate name/summary for empty conversation")

        # Trim messages to token limit to prevent excessive costs
        messages = self._trim_messages_to_token_limit(messages)

        # Format messages for LLM
        formatted_conversation = self._format_messages_for_llm(messages)

        try:
            # Call OpenAI with structured output
            # Note: GPT-5 models don't support temperature, top_p, or logprobs
            response = await self.openai_client.beta.chat.completions.parse(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a conversation summarizer. Your task is to analyze conversations "
                            "and generate:\n"
                            "1. A concise name (3-5 words) that captures the main topic\n"
                            "2. A detailed summary (1-2 paragraphs) covering key points and context\n\n"
                            "Make the name clear and specific. Make the summary comprehensive but concise."
                        )
                    },
                    {
                        "role": "user",
                        "content": f"Please analyze this conversation and provide a name and summary:\n\n{formatted_conversation}"
                    }
                ],
                response_format=ThreadNamingSummary,
                verbosity="low",  # Concise output for GPT-5 models
            )

            result = response.choices[0].message.parsed
            log.info(f"Generated name: '{result.name}' (summary length: {len(result.summary)} chars)")

            return result

        except Exception as e:
            log.error(f"OpenAI API call failed: {e}")
            raise RuntimeError(f"Failed to generate name/summary: {e}")

    async def update_thread_mirror(
        self,
        thread_id: str,
        name: str,
        summary: str
    ):
        """
        Update thread mirror with AI-generated name and summary.

        Args:
            thread_id: UUID of the thread
            name: Generated thread name
            summary: Generated thread summary
        """
        async with self.db_pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE langconnect.threads_mirror
                SET
                    name = $2,
                    summary = $3,
                    last_naming_at = NOW(),
                    needs_naming = false,
                    updated_at = NOW()
                WHERE thread_id = $1
                """,
                thread_id,
                name,
                summary
            )

            # Increment threads version for cache invalidation
            await conn.fetchval(
                "SELECT langconnect.increment_cache_version('threads')"
            )

            log.info(f"Updated thread {thread_id} with AI-generated name and summary")

    async def process_thread(
        self,
        thread_id: str,
        user_id: str,
        user_token: Optional[str] = None
    ) -> bool:
        """
        Main processing function for a single thread.

        Orchestrates the full naming workflow:
        1. Fetch messages from LangGraph
        2. Generate name and summary with LLM
        3. Update database

        Args:
            thread_id: UUID of the thread
            user_id: User ID who owns the thread
            user_token: Optional user JWT for scoped access

        Returns:
            True if successful, False if failed
        """
        try:
            log.info(f"Processing thread {thread_id} for naming")

            # 1. Fetch messages
            messages = await self.fetch_thread_messages(thread_id, user_token)

            if not messages:
                log.warning(f"No messages found for thread {thread_id}, skipping naming")
                return False

            # 2. Generate name and summary
            result = await self.generate_name_and_summary(messages)

            # 3. Update database
            await self.update_thread_mirror(
                thread_id=thread_id,
                name=result.name,
                summary=result.summary
            )

            log.info(f"Successfully named thread {thread_id}: '{result.name}'")
            return True

        except Exception as e:
            log.error(f"Failed to process thread {thread_id}: {e}", exc_info=True)
            return False

    async def process_batch(
        self,
        limit: int = 5,
        min_interval_seconds: int = 60
    ) -> Dict[str, int]:
        """
        Process a batch of threads needing naming.

        Used by background scheduler to process multiple threads efficiently.

        Args:
            limit: Maximum number of threads to process in this batch
            min_interval_seconds: Minimum seconds since last naming attempt

        Returns:
            Dictionary with counts: {'processed': N, 'succeeded': M, 'failed': K}
        """
        if not THREAD_NAMING_ENABLED:
            log.debug("Thread naming disabled via THREAD_NAMING_ENABLED=false")
            return {"processed": 0, "succeeded": 0, "failed": 0}

        async with self.db_pool.acquire() as conn:
            # Fetch threads needing naming
            threads = await conn.fetch(
                """
                SELECT thread_id, user_id
                FROM langconnect.threads_mirror
                WHERE needs_naming = true
                  AND user_renamed = false
                  AND (last_naming_at IS NULL
                       OR last_naming_at < NOW() - INTERVAL '1 second' * $2)
                ORDER BY last_message_at DESC
                LIMIT $1
                """,
                limit,
                min_interval_seconds
            )

            if not threads:
                log.debug("No threads needing naming found")
                return {"processed": 0, "succeeded": 0, "failed": 0}

            log.info(f"Processing {len(threads)} threads for naming")

            succeeded = 0
            failed = 0

            for thread in threads:
                try:
                    success = await self.process_thread(
                        thread_id=str(thread["thread_id"]),
                        user_id=thread["user_id"]
                    )

                    if success:
                        succeeded += 1
                    else:
                        failed += 1

                except Exception as e:
                    log.error(f"Error processing thread {thread['thread_id']}: {e}")
                    failed += 1
                    continue

            log.info(f"Batch complete: {succeeded} succeeded, {failed} failed")
            return {
                "processed": len(threads),
                "succeeded": succeeded,
                "failed": failed
            }


def get_thread_naming_service(db_pool: asyncpg.Pool) -> ThreadNamingService:
    """
    Get thread naming service instance (dependency injection).

    Args:
        db_pool: Database connection pool

    Returns:
        Configured ThreadNamingService instance
    """
    return ThreadNamingService(db_pool=db_pool)
