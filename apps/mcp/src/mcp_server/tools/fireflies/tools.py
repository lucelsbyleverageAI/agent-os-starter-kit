"""Fireflies AI tools implementation for the MCP server."""

from typing import Any, List
from datetime import datetime, timedelta, timezone

from ..base import CustomTool, ToolParameter
from ...utils.logging import get_logger
from ...utils.exceptions import ToolExecutionError

from .base import get_fireflies_client, handle_fireflies_error

logger = get_logger(__name__)


def format_duration(seconds: int) -> str:
    """Format duration in seconds to human-readable string."""
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        minutes = seconds // 60
        return f"{minutes}m"
    else:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        return f"{hours}h {minutes}m"


def format_timestamp(milliseconds: float) -> str:
    """Format milliseconds to MM:SS timestamp."""
    total_seconds = int(milliseconds // 1000)
    minutes = total_seconds // 60
    seconds = total_seconds % 60
    return f"{minutes:02d}:{seconds:02d}"


class ListMeetingsTool(CustomTool):
    """List meetings the user participated in with optional filtering."""

    toolkit_name = "fireflies"
    toolkit_display_name = "Fireflies AI"

    @property
    def name(self) -> str:
        return "list_meetings"

    @property
    def description(self) -> str:
        return (
            "List meetings you participated in from Fireflies AI. "
            "Returns meeting titles, dates, participants, and transcript IDs. "
            "\n\n"
            "SEARCH STRATEGY:\n"
            "- Broad search (finding meetings over longer period): Use high limit (up to 50), set include_summary=False, use skip for pagination\n"
            "- Narrow search (recent/specific meetings): Use low limit (5-10), set include_summary=True for context\n"
            "\n"
            "FILTERS:\n"
            "- Date range: Use from_date/to_date (ISO 8601 format) to narrow timeframe\n"
            "- Keyword: Searches meeting TITLES ONLY (note: meeting titles are often poorly named)\n"
            "- Participants: Filter by email addresses to find meetings with specific people. "
            "Uses AND logic - ALL specified participants must have attended the meeting. "
            "Your email is automatically included for security.\n"
            "- Organizers: Filter by meeting organizer emails\n"
            "\n"
            "Use transcript IDs with get_meeting_summary or get_meeting_transcript tools for details."
        )

    def get_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="from_date",
                type="string",
                description="Start date filter in ISO 8601 format (e.g., '2024-01-01T00:00:00Z'). Only meetings on or after this date will be returned.",
                required=False,
            ),
            ToolParameter(
                name="to_date",
                type="string",
                description="End date filter in ISO 8601 format (e.g., '2024-12-31T23:59:59Z'). Only meetings on or before this date will be returned.",
                required=False,
            ),
            ToolParameter(
                name="time_range",
                type="string",
                description="Convenient time range filter (e.g., 'day', 'week', 'month', 'year'). If provided, this overrides from_date/to_date parameters. Calculates dates from current time backwards.",
                required=False,
                enum=["day", "week", "month", "year"],
            ),
            ToolParameter(
                name="keyword",
                type="string",
                description="Search keyword to filter meetings by title or transcript content.",
                required=False,
            ),
            ToolParameter(
                name="participant_emails",
                type="array",
                description="Filter meetings by specific participant email addresses. Uses AND logic - only returns meetings where ALL specified participants attended (including your email, which is automatically added for security).",
                required=False,
                items={"type": "string"},
            ),
            ToolParameter(
                name="organizer_emails",
                type="array",
                description="Filter meetings by specific organizer email addresses.",
                required=False,
                items={"type": "string"},
            ),
            ToolParameter(
                name="limit",
                type="integer",
                description="Maximum number of meetings to return. Defaults to 10.",
                required=False,
                default=10,
            ),
            ToolParameter(
                name="skip",
                type="integer",
                description="Number of meetings to skip for pagination. Defaults to 0.",
                required=False,
                default=0,
            ),
            ToolParameter(
                name="include_summary",
                type="boolean",
                description="Include meeting summaries in the response. Defaults to true.",
                required=False,
                default=True,
            ),
        ]

    async def _execute_impl(self, user_id: str, **kwargs: Any) -> str:
        """Execute the list meetings tool."""
        try:
            # Get user email from context - REQUIRED for data scoping
            user_email = kwargs.get("_context_user_email")

            if not user_email:
                raise ToolExecutionError(
                    "list_meetings",
                    "User email is required for data scoping. Please ensure you are properly authenticated."
                )

            # Get parameters
            time_range = kwargs.get("time_range")

            # Calculate from_date/to_date based on time_range if provided
            if time_range:
                now = datetime.now(timezone.utc)
                if time_range == "day":
                    from_date = (now - timedelta(days=1)).isoformat()
                elif time_range == "week":
                    from_date = (now - timedelta(weeks=1)).isoformat()
                elif time_range == "month":
                    from_date = (now - timedelta(days=30)).isoformat()
                elif time_range == "year":
                    from_date = (now - timedelta(days=365)).isoformat()
                else:
                    # Invalid time_range, fall back to explicit dates
                    from_date = kwargs.get("from_date")
                    to_date = kwargs.get("to_date")
                to_date = now.isoformat()
            else:
                # Use explicit from_date/to_date if provided
                from_date = kwargs.get("from_date")
                to_date = kwargs.get("to_date")

            keyword = kwargs.get("keyword")
            participant_emails = kwargs.get("participant_emails", [])
            organizer_emails = kwargs.get("organizer_emails")
            limit = kwargs.get("limit", 10)
            skip = kwargs.get("skip", 0)
            include_summary = kwargs.get("include_summary", False)

            # SECURITY: Always add user email to participants for scoping
            # This ensures users can only see meetings they participated in
            if user_email not in participant_emails:
                participant_emails.append(user_email)

            # Get Fireflies client and query
            client = get_fireflies_client()
            response = await client.list_transcripts(
                from_date=from_date,
                to_date=to_date,
                keyword=keyword,
                participants=participant_emails if participant_emails else None,
                organizers=organizer_emails,
                limit=limit,
                skip=skip,
                include_summary=include_summary,
            )

            transcripts = response.get("data", {}).get("transcripts", [])

            # IMPORTANT: Fireflies API uses OR logic for participants filter (returns meetings
            # where ANY participant attended). We need AND logic (ALL participants must have attended).
            # Post-filter to ensure ALL specified participants are present in each meeting.
            if participant_emails and len(participant_emails) > 1:
                filtered_transcripts = []
                participant_set = set(email.lower() for email in participant_emails)

                for transcript in transcripts:
                    meeting_participants = transcript.get("participants", [])
                    # Normalize to lowercase for case-insensitive comparison
                    meeting_participants_lower = set(p.lower() for p in meeting_participants)

                    # Check if ALL specified participants are in this meeting
                    if participant_set.issubset(meeting_participants_lower):
                        filtered_transcripts.append(transcript)

                transcripts = filtered_transcripts
                logger.info(
                    f"Filtered meetings to require all participants: "
                    f"{len(response.get('data', {}).get('transcripts', []))} → {len(transcripts)} meetings"
                )

            if not transcripts:
                return "*No meetings found matching your criteria.*"

            # Format as markdown
            markdown_parts = [f"# Fireflies Meetings ({len(transcripts)} found)\n"]

            for transcript in transcripts:
                transcript_id = transcript.get("id", "")
                title = transcript.get("title", "Untitled Meeting")
                date_string = transcript.get("dateString", "")
                duration = transcript.get("duration", 0)
                organizer = transcript.get("organizer_email", "Unknown")
                participants = transcript.get("participants", [])
                transcript_url = transcript.get("transcript_url", "")

                markdown_parts.append(f"## {title}")
                markdown_parts.append(f"**Transcript ID:** `{transcript_id}`")
                markdown_parts.append(f"**Date:** {date_string}")
                markdown_parts.append(f"**Duration:** {format_duration(duration)}")
                markdown_parts.append(f"**Organizer:** {organizer}")

                if participants:
                    markdown_parts.append(
                        f"**Participants:** {', '.join(participants)}"
                    )

                if transcript_url:
                    markdown_parts.append(f"**URL:** {transcript_url}")

                # Include summary if requested (only overview or short_summary for brevity)
                if include_summary and "summary" in transcript:
                    summary = transcript["summary"]
                    if summary:
                        # Show overview (preferred) or short_summary as fallback
                        summary_text = summary.get("overview") or summary.get("short_summary")
                        if summary_text:
                            markdown_parts.append(f"\n**Summary:** {summary_text}")

                markdown_parts.append("")

            return "\n".join(markdown_parts)

        except Exception as e:
            error_msg = handle_fireflies_error(e)
            logger.error(f"Error in list_meetings: {error_msg}")
            raise ToolExecutionError("list_meetings", error_msg)


class GetMeetingSummaryTool(CustomTool):
    """Retrieve detailed AI-generated summary for a specific meeting."""

    toolkit_name = "fireflies"
    toolkit_display_name = "Fireflies AI"

    @property
    def name(self) -> str:
        return "get_meeting_summary"

    @property
    def description(self) -> str:
        return (
            "Get a detailed AI-generated summary for a specific meeting from Fireflies AI. "
            "Returns overview, key topics, action items, keywords, and meeting type. "
            "\n\n"
            "PREFERRED TOOL: Use this as your DEFAULT for understanding meeting content. "
            "It provides high signal-to-noise ratio compared to full transcripts. "
            "\n\n"
            "WHEN TO USE:\n"
            "- User asks 'what was the meeting about'\n"
            "- Finding action items or key decisions\n"
            "- Understanding topics discussed\n"
            "- Getting meeting overview without verbatim details\n"
            "\n"
            "Use the transcript ID from list_meetings tool."
        )

    def get_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="transcript_id",
                type="string",
                description="The transcript ID from list_meetings. This uniquely identifies the meeting.",
                required=True,
            ),
        ]

    async def _execute_impl(self, user_id: str, **kwargs: Any) -> str:
        """Execute the get meeting summary tool."""
        try:
            transcript_id = kwargs.get("transcript_id")

            if not transcript_id:
                raise ToolExecutionError(
                    "get_meeting_summary", "transcript_id is required"
                )

            # Get Fireflies client and query
            client = get_fireflies_client()
            response = await client.get_transcript(transcript_id)

            transcript = response.get("data", {}).get("transcript")

            if not transcript:
                return f"*No transcript found with ID: {transcript_id}*"

            # Extract details
            title = transcript.get("title", "Untitled Meeting")
            date_string = transcript.get("dateString", "")
            duration = transcript.get("duration", 0)
            organizer = transcript.get("organizer_email", "Unknown")
            participants = transcript.get("participants", [])
            summary = transcript.get("summary", {})

            # Format as markdown
            markdown_parts = [f"# Meeting Summary: {title}\n"]
            markdown_parts.append(f"**Date:** {date_string}")
            markdown_parts.append(f"**Duration:** {format_duration(duration)}")
            markdown_parts.append(f"**Organizer:** {organizer}")

            if participants:
                markdown_parts.append(
                    f"**Participants:** {', '.join(participants)}\n"
                )

            markdown_parts.append("---\n")

            # Overview
            if summary.get("overview"):
                markdown_parts.append("## Overview")
                markdown_parts.append(f"{summary['overview']}\n")

            # Topics Discussed
            if summary.get("topics_discussed"):
                topics = summary["topics_discussed"]
                if topics:
                    markdown_parts.append("## Topics Discussed")
                    for topic in topics:
                        markdown_parts.append(f"- {topic}")
                    markdown_parts.append("")

            # Action Items
            if summary.get("action_items"):
                action_items = summary["action_items"]
                if action_items:
                    markdown_parts.append("## Action Items")
                    for item in action_items:
                        markdown_parts.append(f"- {item}")
                    markdown_parts.append("")

            # Keywords
            if summary.get("keywords"):
                keywords = summary["keywords"]
                if keywords:
                    markdown_parts.append("## Keywords")
                    markdown_parts.append(f"{', '.join(keywords)}\n")

            # Meeting Type
            if summary.get("meeting_type"):
                markdown_parts.append(f"**Meeting Type:** {summary['meeting_type']}")

            # Bullet Gist
            if summary.get("bullet_gist"):
                markdown_parts.append("\n## Quick Summary")
                markdown_parts.append(summary["bullet_gist"])

            return "\n".join(markdown_parts)

        except Exception as e:
            error_msg = handle_fireflies_error(e)
            logger.error(f"Error in get_meeting_summary: {error_msg}")
            raise ToolExecutionError("get_meeting_summary", error_msg)


class GetMeetingTranscriptTool(CustomTool):
    """Retrieve full meeting transcript with speaker attribution."""

    toolkit_name = "fireflies"
    toolkit_display_name = "Fireflies AI"

    @property
    def name(self) -> str:
        return "get_meeting_transcript"

    @property
    def description(self) -> str:
        return (
            "Get the full transcript for a specific meeting from Fireflies AI. "
            "Returns speaker-attributed transcript with optional timestamps and AI-detected filters "
            "(tasks, questions, metrics, sentiment). "
            "\n\n"
            "⚠️ USE SPARINGLY: Transcripts consume significant context and contain low signal-to-noise ratio. "
            "Prefer get_meeting_summary for most use cases. "
            "\n\n"
            "WHEN TO USE:\n"
            "- User explicitly asks for 'exact words' or 'verbatim quotes'\n"
            "- Need specific phrasing or who said what exactly\n"
            "- Summary lacks sufficient detail for user's specific question\n"
            "\n"
            "Use the transcript ID from list_meetings tool."
        )

    def get_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="transcript_id",
                type="string",
                description="The transcript ID from list_meetings. This uniquely identifies the meeting.",
                required=True,
            ),
            ToolParameter(
                name="include_timestamps",
                type="boolean",
                description="Include start and end timestamps for each sentence. Defaults to false.",
                required=False,
                default=False,
            ),
            ToolParameter(
                name="include_ai_filters",
                type="boolean",
                description="Include AI-detected filters (tasks, questions, metrics, sentiment) for each sentence. Defaults to false.",
                required=False,
                default=False,
            ),
        ]

    async def _execute_impl(self, user_id: str, **kwargs: Any) -> str:
        """Execute the get meeting transcript tool."""
        try:
            transcript_id = kwargs.get("transcript_id")
            include_timestamps = kwargs.get("include_timestamps", False)
            include_ai_filters = kwargs.get("include_ai_filters", False)

            if not transcript_id:
                raise ToolExecutionError(
                    "get_meeting_transcript", "transcript_id is required"
                )

            # Get Fireflies client and query
            client = get_fireflies_client()
            response = await client.get_transcript(transcript_id)

            transcript = response.get("data", {}).get("transcript")

            if not transcript:
                return f"*No transcript found with ID: {transcript_id}*"

            # Extract details
            title = transcript.get("title", "Untitled Meeting")
            date_string = transcript.get("dateString", "")
            duration = transcript.get("duration", 0)
            sentences = transcript.get("sentences", [])

            if not sentences:
                return f"*No transcript content available for: {title}*"

            # Format as markdown
            markdown_parts = [f"# Meeting Transcript: {title}\n"]
            markdown_parts.append(f"**Date:** {date_string}")
            markdown_parts.append(f"**Duration:** {format_duration(duration)}\n")
            markdown_parts.append("---\n")

            # Group sentences by speaker
            current_speaker = None
            current_block = []

            for sentence in sentences:
                speaker_name = sentence.get("speaker_name", "Unknown")
                text = sentence.get("text", "")
                start_time = sentence.get("start_time", 0)
                end_time = sentence.get("end_time", 0)
                ai_filters = sentence.get("ai_filters", {})

                # If speaker changed, output previous block
                if current_speaker and current_speaker != speaker_name:
                    markdown_parts.append(f"**{current_speaker}:**")
                    markdown_parts.append(" ".join(current_block))
                    markdown_parts.append("")
                    current_block = []

                current_speaker = speaker_name

                # Build sentence text
                sentence_text = text

                # Add timestamp if requested
                if include_timestamps:
                    timestamp = format_timestamp(start_time)
                    sentence_text = f"[{timestamp}] {sentence_text}"

                # Add AI filter tags if requested
                if include_ai_filters and ai_filters:
                    tags = []
                    if ai_filters.get("task"):
                        tags.append("Task")
                    if ai_filters.get("question"):
                        tags.append("Question")
                    if ai_filters.get("metric"):
                        tags.append("Metric")
                    if ai_filters.get("sentiment"):
                        sentiment = ai_filters["sentiment"]
                        if sentiment:
                            tags.append(f"Sentiment: {sentiment}")

                    if tags:
                        sentence_text = f"{sentence_text} *[{', '.join(tags)}]*"

                current_block.append(sentence_text)

            # Output final block
            if current_speaker and current_block:
                markdown_parts.append(f"**{current_speaker}:**")
                markdown_parts.append(" ".join(current_block))

            return "\n".join(markdown_parts)

        except Exception as e:
            error_msg = handle_fireflies_error(e)
            logger.error(f"Error in get_meeting_transcript: {error_msg}")
            raise ToolExecutionError("get_meeting_transcript", error_msg)
