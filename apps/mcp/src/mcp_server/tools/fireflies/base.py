"""Fireflies AI API client, authentication, and GraphQL helpers."""

import os
from typing import Any, Dict, Optional
import dotenv

dotenv.load_dotenv()

import httpx
from ...utils.logging import get_logger
from ...utils.exceptions import ToolExecutionError, AuthorizationError

logger = get_logger(__name__)


class FirefliesAPIError(Exception):
    """Fireflies API specific error."""
    pass


class FirefliesClient:
    """Fireflies AI API client."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("FIREFLIES_API_KEY")
        if not self.api_key:
            raise AuthorizationError(
                "Fireflies API key not found. Please set FIREFLIES_API_KEY environment variable."
            )

        self.base_url = "https://api.fireflies.ai/graphql"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def graphql_query(
        self, query: str, variables: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Execute a GraphQL query against Fireflies AI API."""
        payload = {
            "query": query,
            "variables": variables or {}
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.base_url,
                    json=payload,
                    headers=self.headers,
                    timeout=30.0
                )

                if response.status_code == 401:
                    raise AuthorizationError("Invalid Fireflies API key")

                if response.status_code != 200:
                    raise FirefliesAPIError(
                        f"HTTP {response.status_code}: {response.text}"
                    )

                data = response.json()

                # Check for GraphQL errors
                if "errors" in data:
                    error_messages = []
                    for error in data["errors"]:
                        error_messages.append(error.get("message", "Unknown error"))
                    raise FirefliesAPIError(
                        f"GraphQL errors: {', '.join(error_messages)}"
                    )

                return data

        except httpx.TimeoutException:
            raise ToolExecutionError(
                "fireflies_api_client", "Request to Fireflies API timed out"
            )
        except httpx.RequestError as e:
            raise ToolExecutionError(
                "fireflies_api_client", f"Request to Fireflies API failed: {str(e)}"
            )

    async def list_transcripts(
        self,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        keyword: Optional[str] = None,
        scope: Optional[str] = None,
        participants: Optional[list[str]] = None,
        organizers: Optional[list[str]] = None,
        limit: int = 10,
        skip: int = 0,
        include_summary: bool = False,
    ) -> Dict[str, Any]:
        """List transcripts with filtering options.

        Args:
            from_date: Start date filter in ISO 8601 format
            to_date: End date filter in ISO 8601 format
            keyword: Search keyword
            scope: Keyword search scope - 'title', 'sentences', or 'all'
            participants: Filter by participant emails
            organizers: Filter by organizer emails
            limit: Maximum number of results
            skip: Number of results to skip
            include_summary: Include summary fields in response
        """
        # Build summary fields conditionally
        summary_fields = """
            keywords
            action_items
            overview
            bullet_gist
            short_summary
        """ if include_summary else ""

        query = f"""
        query Transcripts(
            $fromDate: DateTime
            $toDate: DateTime
            $keyword: String
            $scope: String
            $participants: [String!]
            $organizers: [String!]
            $limit: Int
            $skip: Int
        ) {{
            transcripts(
                fromDate: $fromDate
                toDate: $toDate
                keyword: $keyword
                scope: $scope
                participants: $participants
                organizers: $organizers
                limit: $limit
                skip: $skip
            ) {{
                id
                title
                date
                dateString
                duration
                organizer_email
                participants
                transcript_url
                {"summary {" + summary_fields + "}" if include_summary else ""}
            }}
        }}
        """

        variables = {
            "fromDate": from_date,
            "toDate": to_date,
            "keyword": keyword,
            "scope": scope,
            "participants": participants,
            "organizers": organizers,
            "limit": limit,
            "skip": skip,
        }

        # Remove None values
        variables = {k: v for k, v in variables.items() if v is not None}

        return await self.graphql_query(query, variables)

    async def get_transcript(self, transcript_id: str) -> Dict[str, Any]:
        """Get a specific transcript by ID with full details."""
        query = """
        query Transcript($transcriptId: String!) {
            transcript(id: $transcriptId) {
                id
                title
                date
                dateString
                duration
                organizer_email
                participants
                transcript_url
                audio_url
                speakers {
                    id
                    name
                }
                summary {
                    keywords
                    action_items
                    overview
                    bullet_gist
                    short_summary
                    meeting_type
                    topics_discussed
                }
                sentences {
                    index
                    speaker_name
                    speaker_id
                    text
                    start_time
                    end_time
                    ai_filters {
                        task
                        question
                        metric
                        sentiment
                    }
                }
            }
        }
        """

        variables = {"transcriptId": transcript_id}
        return await self.graphql_query(query, variables)


# Global client instance
_fireflies_client: Optional[FirefliesClient] = None


def get_fireflies_client() -> FirefliesClient:
    """Get or create Fireflies API client instance."""
    global _fireflies_client
    if _fireflies_client is None:
        _fireflies_client = FirefliesClient()
    return _fireflies_client


def handle_fireflies_error(error: Exception) -> str:
    """Standardize error messages for MCP."""
    if isinstance(error, AuthorizationError):
        return f"Authorization error: {str(error)}"
    elif isinstance(error, FirefliesAPIError):
        return f"Fireflies API error: {str(error)}"
    elif isinstance(error, ToolExecutionError):
        return f"Execution error: {str(error)}"
    else:
        return f"Unexpected error: {str(error)}"
