"""Outlook calendar tools for the MCP server."""

from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta, timezone

import mistune

from ..base import CustomTool, ToolParameter
from ...utils.logging import get_logger
from ...utils.exceptions import ToolExecutionError

from .base import get_outlook_client, handle_outlook_error

logger = get_logger(__name__)


def markdown_to_html(markdown_text: str) -> str:
    """Convert markdown to HTML for calendar event body using mistune."""
    return mistune.html(markdown_text)


class ListMyCalendarEventsTool(CustomTool):
    """List the authenticated user's own calendar events."""

    toolkit_name = "outlook"
    toolkit_display_name = "E18 Outlook"

    @property
    def name(self) -> str:
        return "list_my_calendar_events"

    @property
    def description(self) -> str:
        return (
            "List YOUR OWN calendar events within a date range. "
            "\n\n"
            "Use this to check your personal schedule, see your upcoming meetings, "
            "or review your calendar. This tool only shows your own calendar events."
            "\n\n"
            "Returns event details including subject, time, location, attendees, and Teams meeting links."
            "\n\n"
            "PARAMETERS:\n"
            "- start_date: Start of date range (ISO 8601 format)\n"
            "- end_date: End of date range (ISO 8601 format)\n"
            "- limit: Maximum events to return (default 50, max 1000)\n"
            "\n"
            "To view OTHER users' calendars, use list_user_calendar_events instead."
        )

    def get_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="start_date",
                type="string",
                description="Start date/time in ISO 8601 format (e.g., '2025-11-15T00:00:00Z')",
                required=True,
            ),
            ToolParameter(
                name="end_date",
                type="string",
                description="End date/time in ISO 8601 format (e.g., '2025-11-15T23:59:59Z')",
                required=True,
            ),
            ToolParameter(
                name="limit",
                type="integer",
                description="Maximum number of events to return. Defaults to 50, max 1000.",
                required=False,
                default=50,
            ),
            ToolParameter(
                name="user_email",
                type="string",
                description="Email of the authenticated user (auto-populated from context)",
                required=False,
            ),
        ]

    async def _execute_impl(self, user_id: str, **kwargs: Any) -> str:
        """Execute list my calendar events tool."""
        try:
            # Get user's email from context
            user_email = kwargs.get("user_email")
            if not user_email:
                raise ToolExecutionError(
                    "list_my_calendar_events",
                    "User email is required. This should be auto-populated from authentication context."
                )

            start_date = kwargs.get("start_date")
            end_date = kwargs.get("end_date")
            limit = kwargs.get("limit", 50)

            if not all([start_date, end_date]):
                raise ToolExecutionError(
                    "list_my_calendar_events",
                    "start_date and end_date are required"
                )

            # Use calendarView for better recurring event handling
            client = get_outlook_client()
            endpoint = f"/users/{user_email}/calendar/calendarView"

            params = {
                "startDateTime": start_date,
                "endDateTime": end_date,
                "$select": "id,subject,start,end,attendees,location,isOnlineMeeting,onlineMeeting,body,organizer,sensitivity",
                "$orderby": "start/dateTime",
                "$top": min(limit, 1000),
            }

            response = await client._graph_request(
                method="GET",
                endpoint=endpoint,
                user_email=user_email,
                params=params,
            )

            events = response.get("value", [])

            if not events:
                return f"*No calendar events found for your calendar between {start_date} and {end_date}.*"

            # Format as markdown
            markdown_parts = [
                f"# Your Calendar Events",
                f"**Period:** {start_date} to {end_date}",
                f"**Total Events:** {len(events)}\n",
            ]

            for event in events:
                event_id = event.get("id", "")
                subject = event.get("subject", "No Subject")
                start = event.get("start", {})
                end = event.get("end", {})
                start_dt = start.get("dateTime", "")
                end_dt = end.get("dateTime", "")
                location = event.get("location", {}).get("displayName", "Not specified")
                is_online = event.get("isOnlineMeeting", False)

                # Parse datetime for better formatting
                try:
                    start_parsed = datetime.fromisoformat(start_dt.replace("Z", "+00:00"))
                    end_parsed = datetime.fromisoformat(end_dt.replace("Z", "+00:00"))
                    start_str = start_parsed.strftime("%Y-%m-%d %H:%M")
                    end_str = end_parsed.strftime("%H:%M")
                    duration_mins = int((end_parsed - start_parsed).total_seconds() / 60)
                except:
                    start_str = start_dt
                    end_str = end_dt
                    duration_mins = 0

                markdown_parts.append(f"## {subject}")
                markdown_parts.append(f"**Event ID:** `{event_id}`")
                markdown_parts.append(f"**Time:** {start_str} - {end_str} ({duration_mins} min)")
                markdown_parts.append(f"**Location:** {location}")

                if is_online:
                    online_meeting = event.get("onlineMeeting", {})
                    join_url = online_meeting.get("joinUrl", "")
                    if join_url:
                        markdown_parts.append(f"**Teams Meeting:** [Join Meeting]({join_url})")

                # Attendees
                attendees = event.get("attendees", [])
                if attendees:
                    attendee_details = []
                    for a in attendees:
                        email_info = a.get("emailAddress", {})
                        name = email_info.get("name", "")
                        email = email_info.get("address", "")
                        if name and email:
                            attendee_details.append(f"{name} ({email})")
                        elif email:
                            attendee_details.append(email)
                        elif name:
                            attendee_details.append(name)
                    markdown_parts.append(f"**Attendees:** {', '.join(attendee_details)}")

                markdown_parts.append("")

            return "\n".join(markdown_parts)

        except Exception as e:
            error_msg = handle_outlook_error(e)
            logger.error(f"Error in list_my_calendar_events: {error_msg}")
            raise ToolExecutionError("list_my_calendar_events", error_msg)


class ListUserCalendarEventsTool(CustomTool):
    """List another user's calendar events (requires admin permissions)."""

    toolkit_name = "outlook"
    toolkit_display_name = "E18 Outlook"

    @property
    def name(self) -> str:
        return "list_user_calendar_events"

    @property
    def description(self) -> str:
        return (
            "List calendar events for ANOTHER USER within a date range. "
            "\n\n"
            "Use this to check someone else's schedule, see what meetings they have, "
            "or find available time slots. Requires admin permissions or shared calendar access."
            "\n\n"
            "Returns event details including subject, time, location, attendees, and Teams meeting links."
            "\n\n"
            "PARAMETERS:\n"
            "- target_email: Email of the user whose calendar to check (e.g., 'ben@company.com')\n"
            "- start_date: Start of date range (ISO 8601 format)\n"
            "- end_date: End of date range (ISO 8601 format)\n"
            "- limit: Maximum events to return (default 50, max 1000)\n"
            "\n"
            "To view YOUR OWN calendar, use list_my_calendar_events instead."
        )

    def get_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="target_email",
                type="string",
                description="Email address of the user whose calendar to check (e.g., 'ben@company.com')",
                required=True,
            ),
            ToolParameter(
                name="start_date",
                type="string",
                description="Start date/time in ISO 8601 format (e.g., '2025-11-15T00:00:00Z')",
                required=True,
            ),
            ToolParameter(
                name="end_date",
                type="string",
                description="End date/time in ISO 8601 format (e.g., '2025-11-15T23:59:59Z')",
                required=True,
            ),
            ToolParameter(
                name="limit",
                type="integer",
                description="Maximum number of events to return. Defaults to 50, max 1000.",
                required=False,
                default=50,
            ),
        ]

    async def _execute_impl(self, user_id: str, **kwargs: Any) -> str:
        """Execute list user calendar events tool."""
        try:
            target_email = kwargs.get("target_email")
            start_date = kwargs.get("start_date")
            end_date = kwargs.get("end_date")
            limit = kwargs.get("limit", 50)

            if not all([target_email, start_date, end_date]):
                raise ToolExecutionError(
                    "list_user_calendar_events",
                    "target_email, start_date, and end_date are required"
                )

            # Use calendarView for better recurring event handling
            client = get_outlook_client()
            endpoint = f"/users/{target_email}/calendar/calendarView"

            params = {
                "startDateTime": start_date,
                "endDateTime": end_date,
                "$select": "id,subject,start,end,attendees,location,isOnlineMeeting,onlineMeeting,body,organizer,sensitivity",
                "$orderby": "start/dateTime",
                "$top": min(limit, 1000),
            }

            response = await client._graph_request(
                method="GET",
                endpoint=endpoint,
                user_email=target_email,
                params=params,
            )

            events = response.get("value", [])

            # For privacy, when viewing other users' calendars, only show busy/free status
            # Do not return any event details (subject, attendees, location, etc.)

            if not events:
                return f"*No calendar events found for {target_email} between {start_date} and {end_date}. User appears to be completely free during this period.*"

            # Format as markdown - only show time blocks when user is busy
            markdown_parts = [
                f"# Calendar Availability for {target_email}",
                f"**Period:** {start_date} to {end_date}",
                f"**Total Busy Slots:** {len(events)}",
                f"\n*For privacy, only busy/free status is shown. Event details are not available.*\n",
            ]

            for i, event in enumerate(events, 1):
                start = event.get("start", {})
                end = event.get("end", {})
                start_dt = start.get("dateTime", "")
                end_dt = end.get("dateTime", "")

                # Parse datetime for better formatting
                try:
                    start_parsed = datetime.fromisoformat(start_dt.replace("Z", "+00:00"))
                    end_parsed = datetime.fromisoformat(end_dt.replace("Z", "+00:00"))
                    start_str = start_parsed.strftime("%Y-%m-%d %H:%M")
                    end_str = end_parsed.strftime("%H:%M")
                    duration_mins = int((end_parsed - start_parsed).total_seconds() / 60)
                except:
                    start_str = start_dt
                    end_str = end_dt
                    duration_mins = 0

                markdown_parts.append(f"**{i}.** Busy: {start_str} - {end_str} ({duration_mins} min)")

            return "\n".join(markdown_parts)

        except Exception as e:
            error_msg = handle_outlook_error(e)
            logger.error(f"Error in list_user_calendar_events: {error_msg}")
            raise ToolExecutionError("list_user_calendar_events", error_msg)


class GetCalendarEventTool(CustomTool):
    """Get details of a single calendar event."""

    toolkit_name = "outlook"
    toolkit_display_name = "E18 Outlook"

    @property
    def name(self) -> str:
        return "get_calendar_event"

    @property
    def description(self) -> str:
        return (
            "Get detailed information about a specific calendar event. "
            "\n\n"
            "Use this to retrieve full details of a calendar event before updating or deleting it, "
            "or to check specific event information."
            "\n\n"
            "Returns complete event details including subject, time, description, location, attendees, "
            "organizer, Teams meeting link, and all other event properties."
            "\n\n"
            "PARAMETERS:\n"
            "- event_id: The ID of the calendar event (obtained from list_calendar_events)\n"
            "- user_email: Email of the user whose calendar contains the event"
        )

    def get_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="event_id",
                type="string",
                description="The ID of the calendar event to retrieve",
                required=True,
            ),
            ToolParameter(
                name="user_email",
                type="string",
                description="Email address of the user whose calendar contains the event",
                required=True,
            ),
            ToolParameter(
                name="requesting_user_email",
                type="string",
                description="Email of the user making the request (auto-populated from context). Used to determine if viewing own event or another user's event.",
                required=False,
            ),
        ]

    async def _execute_impl(self, user_id: str, **kwargs: Any) -> str:
        """Execute get calendar event tool."""
        try:
            event_id = kwargs.get("event_id")
            user_email = kwargs.get("user_email")
            requesting_user_email = kwargs.get("requesting_user_email")

            if not all([event_id, user_email]):
                raise ToolExecutionError(
                    "get_calendar_event",
                    "event_id and user_email are required"
                )

            client = get_outlook_client()
            endpoint = f"/users/{user_email}/events/{event_id}"

            event = await client._graph_request(
                method="GET",
                endpoint=endpoint,
                user_email=user_email,
            )

            # Extract basic event details
            start = event.get("start", {})
            end = event.get("end", {})
            start_dt = start.get("dateTime", "")
            end_dt = end.get("dateTime", "")
            start_tz = start.get("timeZone", "UTC")

            # Parse datetime for better formatting
            try:
                start_parsed = datetime.fromisoformat(start_dt.replace("Z", "+00:00"))
                end_parsed = datetime.fromisoformat(end_dt.replace("Z", "+00:00"))
                start_str = start_parsed.strftime("%Y-%m-%d %H:%M")
                end_str = end_parsed.strftime("%H:%M")
                duration_mins = int((end_parsed - start_parsed).total_seconds() / 60)
            except:
                start_str = start_dt
                end_str = end_dt
                duration_mins = 0

            # Check if viewing own event or another user's event
            is_own_event = requesting_user_email and requesting_user_email.lower() == user_email.lower()

            # If viewing another user's event, hide details for privacy
            if not is_own_event:
                markdown_parts = [
                    f"# Calendar Event (Privacy Protected)",
                    f"\n**Event ID:** `{event_id}`",
                    f"**Owner:** {user_email}",
                    f"**Time:** {start_str} - {end_str} ({duration_mins} min)",
                    f"**Timezone:** {start_tz}",
                    f"\n*For privacy, event details (subject, attendees, location, description) are not available when viewing other users' calendar events.*",
                ]
                return "\n".join(markdown_parts)

            # Show full details for own events
            subject = event.get("subject", "No Subject")
            location = event.get("location", {}).get("displayName", "Not specified")
            is_online = event.get("isOnlineMeeting", False)
            body = event.get("body", {}).get("content", "")
            body_type = event.get("body", {}).get("contentType", "HTML")
            organizer = event.get("organizer", {}).get("emailAddress", {})
            organizer_name = organizer.get("name", "Unknown")
            organizer_email = organizer.get("address", "Unknown")

            # Format as markdown
            markdown_parts = [
                f"# Calendar Event: {subject}",
                f"\n**Event ID:** `{event_id}`",
                f"**Time:** {start_str} - {end_str} ({duration_mins} min)",
                f"**Timezone:** {start_tz}",
                f"**Location:** {location}",
                f"**Organizer:** {organizer_name} ({organizer_email})",
            ]

            if is_online:
                online_meeting = event.get("onlineMeeting", {})
                join_url = online_meeting.get("joinUrl", "")
                if join_url:
                    markdown_parts.append(f"**Teams Meeting:** [Join Meeting]({join_url})")

            # Attendees
            attendees = event.get("attendees", [])
            if attendees:
                markdown_parts.append(f"\n## Attendees ({len(attendees)})")
                for attendee in attendees:
                    email_info = attendee.get("emailAddress", {})
                    name = email_info.get("name", "Unknown")
                    email = email_info.get("address", "Unknown")
                    attendee_type = attendee.get("type", "unknown")
                    status = attendee.get("status", {}).get("response", "none")
                    markdown_parts.append(f"- **{name}** ({email}) - {attendee_type} - Response: {status}")

            # Body
            if body:
                markdown_parts.append(f"\n## Description")
                # Truncate if too long
                if len(body) > 1000:
                    markdown_parts.append(f"{body[:1000]}...\n\n*(Description truncated)*")
                else:
                    markdown_parts.append(body)

            return "\n".join(markdown_parts)

        except Exception as e:
            error_msg = handle_outlook_error(e)
            logger.error(f"Error in get_calendar_event: {error_msg}")
            raise ToolExecutionError("get_calendar_event", error_msg)


class GetUserAvailabilityTool(CustomTool):
    """Get free/busy availability for multiple users."""

    toolkit_name = "outlook"
    toolkit_display_name = "E18 Outlook"

    @property
    def name(self) -> str:
        return "get_user_availability"

    @property
    def description(self) -> str:
        return (
            "Check free/busy availability for multiple users to find meeting times. "
            "\n\n"
            "Uses Microsoft Graph getSchedule API to return availability information "
            "for up to 20 users at once. Returns a detailed breakdown of when each "
            "user is free, busy, out of office, or working elsewhere."
            "\n\n"
            "Perfect for finding optimal meeting times across team members. The tool "
            "automatically identifies time slots where all attendees are available."
            "\n\n"
            "PARAMETERS:\n"
            "- user_emails: Array of email addresses to check (max 20)\n"
            "- start_time: Start of time window (ISO 8601)\n"
            "- end_time: End of time window (ISO 8601, max 62 days from start)\n"
            "- time_slot_minutes: Granularity in minutes (default 30)"
            "\n\n"
            "AVAILABILITY CODES:\n"
            "- Free: Available for meetings\n"
            "- Busy: Has scheduled events\n"
            "- Tentative: Tentatively scheduled\n"
            "- Out of Office: Not available\n"
            "- Working Elsewhere: Available but not in usual location"
        )

    def get_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="user_emails",
                type="array",
                description="Array of email addresses to check availability for (e.g., ['ben@company.com', 'john@company.com']). Max 20 users.",
                required=True,
                items={"type": "string"},
            ),
            ToolParameter(
                name="start_time",
                type="string",
                description="Start date/time in ISO 8601 format (e.g., '2025-11-15T09:00:00Z')",
                required=True,
            ),
            ToolParameter(
                name="end_time",
                type="string",
                description="End date/time in ISO 8601 format (e.g., '2025-11-15T17:00:00Z'). Max 62 days from start.",
                required=True,
            ),
            ToolParameter(
                name="time_slot_minutes",
                type="integer",
                description="Time slot granularity in minutes (default: 30). Smaller values = more detail.",
                required=False,
                default=30,
            ),
            ToolParameter(
                name="requesting_user_email",
                type="string",
                description="Email of the user making the request (for authentication). If not provided, will use the first email from user_emails.",
                required=False,
            ),
        ]

    async def _execute_impl(self, user_id: str, **kwargs: Any) -> str:
        """Execute get user availability tool."""
        try:
            user_emails = kwargs.get("user_emails", [])
            start_time = kwargs.get("start_time")
            end_time = kwargs.get("end_time")
            time_slot_minutes = kwargs.get("time_slot_minutes", 30)

            # Get requesting user email (for authentication context)
            requesting_user_email = kwargs.get("requesting_user_email")
            if not requesting_user_email and user_emails:
                requesting_user_email = user_emails[0]

            if not all([user_emails, start_time, end_time]):
                raise ToolExecutionError(
                    "get_user_availability",
                    "user_emails, start_time, and end_time are required"
                )

            if len(user_emails) > 20:
                raise ToolExecutionError(
                    "get_user_availability",
                    "Maximum 20 users allowed per request"
                )

            # Build request
            client = get_outlook_client()
            endpoint = "/users/{userPrincipalName}/calendar/getSchedule"

            json_body = {
                "schedules": user_emails,
                "startTime": {
                    "dateTime": start_time,
                    "timeZone": "UTC"
                },
                "endTime": {
                    "dateTime": end_time,
                    "timeZone": "UTC"
                },
                "availabilityViewInterval": time_slot_minutes
            }

            response = await client._graph_request(
                method="POST",
                endpoint=endpoint,
                user_email=requesting_user_email,
                json_body=json_body,
            )

            schedules = response.get("value", [])

            if not schedules:
                return "*No availability data returned.*"

            # Format as markdown
            markdown_parts = [
                f"# Availability Report",
                f"**Period:** {start_time} to {end_time}",
                f"**Users Checked:** {len(schedules)}\n",
            ]

            # Status mapping
            status_map = {
                "0": "Free",
                "1": "Tentative",
                "2": "Busy",
                "3": "Out of Office",
                "4": "Working Elsewhere"
            }

            for schedule in schedules:
                user_email = schedule.get("scheduleId", "Unknown")
                availability_view = schedule.get("availabilityView", "")
                schedule_items = schedule.get("scheduleItems", [])

                markdown_parts.append(f"## {user_email}")

                # Show busy periods (without subjects for privacy)
                if schedule_items:
                    markdown_parts.append(f"\n**Busy Periods:**")
                    for item in schedule_items:
                        status = item.get("status", "unknown")
                        start = item.get("start", {}).get("dateTime", "")
                        end = item.get("end", {}).get("dateTime", "")

                        try:
                            start_parsed = datetime.fromisoformat(start.replace("Z", "+00:00"))
                            end_parsed = datetime.fromisoformat(end.replace("Z", "+00:00"))
                            time_str = f"{start_parsed.strftime('%H:%M')} - {end_parsed.strftime('%H:%M')}"
                        except:
                            time_str = f"{start} - {end}"

                        markdown_parts.append(f"- {time_str}: **{status.title()}**")
                else:
                    markdown_parts.append(f"\n*No scheduled events - completely free*")

                markdown_parts.append("")

            # Find common free time slots
            markdown_parts.append("\n## Suggested Meeting Times")
            markdown_parts.append("*Times when all attendees are available:*\n")

            # Simple algorithm: find time slots where all users are "0" (free)
            if schedules:
                # Get the availability view strings
                views = [s.get("availabilityView", "") for s in schedules]
                min_len = min(len(v) for v in views) if views else 0

                free_slots = []
                for i in range(min_len):
                    if all(view[i] == "0" for view in views):
                        free_slots.append(i)

                if free_slots:
                    # Group consecutive slots
                    slot_groups = []
                    current_group = [free_slots[0]]

                    for slot in free_slots[1:]:
                        if slot == current_group[-1] + 1:
                            current_group.append(slot)
                        else:
                            slot_groups.append(current_group)
                            current_group = [slot]
                    slot_groups.append(current_group)

                    # Format time slots
                    try:
                        start_dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
                        for group in slot_groups[:10]:  # Show max 10 suggestions
                            slot_start = start_dt + timedelta(minutes=group[0] * time_slot_minutes)
                            slot_end = start_dt + timedelta(minutes=(group[-1] + 1) * time_slot_minutes)
                            duration = len(group) * time_slot_minutes
                            markdown_parts.append(
                                f"- {slot_start.strftime('%H:%M')} - {slot_end.strftime('%H:%M')} "
                                f"({duration} min available)"
                            )
                    except:
                        markdown_parts.append(f"- {len(free_slots)} free time slots available")
                else:
                    markdown_parts.append("*No common free time found - consider partial availability*")

            return "\n".join(markdown_parts)

        except Exception as e:
            error_msg = handle_outlook_error(e)
            logger.error(f"Error in get_user_availability: {error_msg}")
            raise ToolExecutionError("get_user_availability", error_msg)


class CreateCalendarEventTool(CustomTool):
    """Create a calendar event with attendees and send invitations."""

    toolkit_name = "outlook"
    toolkit_display_name = "E18 Outlook"

    @property
    def name(self) -> str:
        return "create_calendar_event"

    @property
    def description(self) -> str:
        return (
            "Create a new calendar event with attendees and automatically send meeting invitations. "
            "\n\n"
            "Can create in-person meetings with location, online Teams meetings, or hybrid meetings. "
            "Invitations are automatically sent to all attendees via email."
            "\n\n"
            "Returns the created event details including event ID and Teams meeting link (if applicable)."
            "\n\n"
            "PARAMETERS:\n"
            "- organizer_email: Email of the meeting organizer\n"
            "- subject: Meeting title\n"
            "- start_time: Start datetime (ISO 8601)\n"
            "- end_time: End datetime (ISO 8601)\n"
            "- attendees: Array of attendee email addresses\n"
            "- body: Optional meeting description (markdown format)\n"
            "- location: Optional physical location\n"
            "- create_teams_meeting: If true, creates Teams meeting with join link"
        )

    def get_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="organizer_email",
                type="string",
                description="Email of the person organizing the meeting (appears as organizer)",
                required=True,
            ),
            ToolParameter(
                name="subject",
                type="string",
                description="Meeting subject/title",
                required=True,
            ),
            ToolParameter(
                name="start_time",
                type="string",
                description="Start date/time in ISO 8601 format (e.g., '2025-11-15T14:00:00Z')",
                required=True,
            ),
            ToolParameter(
                name="end_time",
                type="string",
                description="End date/time in ISO 8601 format (e.g., '2025-11-15T15:00:00Z')",
                required=True,
            ),
            ToolParameter(
                name="attendees",
                type="array",
                description="Array of attendee email addresses",
                required=True,
                items={"type": "string"},
            ),
            ToolParameter(
                name="body",
                type="string",
                description="Meeting description/agenda in markdown format (will be converted to HTML)",
                required=False,
            ),
            ToolParameter(
                name="location",
                type="string",
                description="Physical location or conference room name",
                required=False,
            ),
            ToolParameter(
                name="create_teams_meeting",
                type="boolean",
                description="If true, creates a Teams online meeting with join link. Default: false",
                required=False,
                default=False,
            ),
        ]

    async def _execute_impl(self, user_id: str, **kwargs: Any) -> str:
        """Execute create calendar event tool."""
        try:
            organizer_email = kwargs.get("organizer_email")
            subject = kwargs.get("subject")
            start_time = kwargs.get("start_time")
            end_time = kwargs.get("end_time")
            attendee_emails = kwargs.get("attendees", [])
            body_markdown = kwargs.get("body")
            location = kwargs.get("location")
            create_teams_meeting = kwargs.get("create_teams_meeting", False)

            if not all([organizer_email, subject, start_time, end_time, attendee_emails]):
                raise ToolExecutionError(
                    "create_calendar_event",
                    "organizer_email, subject, start_time, end_time, and attendees are required"
                )

            # Format attendees
            attendees = [
                {
                    "emailAddress": {"address": email},
                    "type": "required"
                }
                for email in attendee_emails
            ]

            # Build event data
            event_data = {
                "subject": subject,
                "start": {
                    "dateTime": start_time,
                    "timeZone": "UTC"
                },
                "end": {
                    "dateTime": end_time,
                    "timeZone": "UTC"
                },
                "attendees": attendees,
            }

            # Add optional fields
            if body_markdown:
                body_html = markdown_to_html(body_markdown)
                event_data["body"] = {
                    "contentType": "HTML",
                    "content": body_html
                }

            if location:
                event_data["location"] = {
                    "displayName": location
                }

            if create_teams_meeting:
                event_data["isOnlineMeeting"] = True
                event_data["onlineMeetingProvider"] = "teamsForBusiness"

            # Create event
            client = get_outlook_client()
            endpoint = "/users/{userPrincipalName}/events"

            result = await client._graph_request(
                method="POST",
                endpoint=endpoint,
                user_email=organizer_email,
                json_body=event_data,
            )

            # Extract response details
            event_id = result.get("id", "")
            web_link = result.get("webLink", "")
            online_meeting = result.get("onlineMeeting", {})
            join_url = online_meeting.get("joinUrl", "")

            # Format response
            markdown_parts = [
                f"# Calendar Event Created Successfully",
                f"\n**Subject:** {subject}",
                f"**Organizer:** {organizer_email}",
                f"**Start:** {start_time}",
                f"**End:** {end_time}",
                f"**Attendees:** {', '.join(attendee_emails)}",
            ]

            if location:
                markdown_parts.append(f"**Location:** {location}")

            if join_url:
                markdown_parts.append(f"\n**Teams Meeting Link:** {join_url}")

            markdown_parts.append(f"\n**Event ID:** `{event_id}`")
            markdown_parts.append(f"\n*Meeting invitations have been sent to all attendees.*")

            return "\n".join(markdown_parts)

        except Exception as e:
            error_msg = handle_outlook_error(e)
            logger.error(f"Error in create_calendar_event: {error_msg}")
            raise ToolExecutionError("create_calendar_event", error_msg)


class UpdateCalendarEventTool(CustomTool):
    """Update an existing calendar event."""

    toolkit_name = "outlook"
    toolkit_display_name = "E18 Outlook"

    @property
    def name(self) -> str:
        return "update_calendar_event"

    @property
    def description(self) -> str:
        return (
            "Update an existing calendar event. "
            "\n\n"
            "Use this to reschedule meetings, change attendees, update location or description, "
            "or modify any other event details. Updated invitations are automatically sent to attendees."
            "\n\n"
            "You can update any combination of fields - only provide the fields you want to change. "
            "Fields not provided will remain unchanged."
            "\n\n"
            "PARAMETERS:\n"
            "- event_id: The ID of the event to update (from list_calendar_events)\n"
            "- organizer_email: Email of the event organizer\n"
            "- subject: New meeting title (optional)\n"
            "- start_time: New start time (optional, ISO 8601)\n"
            "- end_time: New end time (optional, ISO 8601)\n"
            "- attendees: Updated attendee list (optional, replaces all attendees)\n"
            "- body: Updated description (optional, markdown)\n"
            "- location: Updated location (optional)"
            "\n\n"
            "TIP: Use get_calendar_event first to see current values before updating."
        )

    def get_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="event_id",
                type="string",
                description="The ID of the calendar event to update",
                required=True,
            ),
            ToolParameter(
                name="organizer_email",
                type="string",
                description="Email of the event organizer (whose calendar contains the event)",
                required=True,
            ),
            ToolParameter(
                name="subject",
                type="string",
                description="New meeting subject/title (optional - only updates if provided)",
                required=False,
            ),
            ToolParameter(
                name="start_time",
                type="string",
                description="New start date/time in ISO 8601 format (optional - only updates if provided)",
                required=False,
            ),
            ToolParameter(
                name="end_time",
                type="string",
                description="New end date/time in ISO 8601 format (optional - only updates if provided)",
                required=False,
            ),
            ToolParameter(
                name="attendees",
                type="array",
                description="Updated array of attendee email addresses (optional - replaces all attendees if provided)",
                required=False,
                items={"type": "string"},
            ),
            ToolParameter(
                name="body",
                type="string",
                description="Updated meeting description in markdown format (optional - only updates if provided)",
                required=False,
            ),
            ToolParameter(
                name="location",
                type="string",
                description="Updated physical location or conference room name (optional - only updates if provided)",
                required=False,
            ),
        ]

    async def _execute_impl(self, user_id: str, **kwargs: Any) -> str:
        """Execute update calendar event tool."""
        try:
            event_id = kwargs.get("event_id")
            organizer_email = kwargs.get("organizer_email")

            if not all([event_id, organizer_email]):
                raise ToolExecutionError(
                    "update_calendar_event",
                    "event_id and organizer_email are required"
                )

            # Build update payload with only provided fields
            update_data = {}

            if "subject" in kwargs and kwargs["subject"] is not None:
                update_data["subject"] = kwargs["subject"]

            if "start_time" in kwargs and kwargs["start_time"] is not None:
                update_data["start"] = {
                    "dateTime": kwargs["start_time"],
                    "timeZone": "UTC"
                }

            if "end_time" in kwargs and kwargs["end_time"] is not None:
                update_data["end"] = {
                    "dateTime": kwargs["end_time"],
                    "timeZone": "UTC"
                }

            if "attendees" in kwargs and kwargs["attendees"] is not None:
                attendee_emails = kwargs["attendees"]
                update_data["attendees"] = [
                    {
                        "emailAddress": {"address": email},
                        "type": "required"
                    }
                    for email in attendee_emails
                ]

            if "body" in kwargs and kwargs["body"] is not None:
                body_html = markdown_to_html(kwargs["body"])
                update_data["body"] = {
                    "contentType": "HTML",
                    "content": body_html
                }

            if "location" in kwargs and kwargs["location"] is not None:
                update_data["location"] = {
                    "displayName": kwargs["location"]
                }

            if not update_data:
                return "*No fields provided to update. Please specify at least one field to change.*"

            # Update event
            client = get_outlook_client()
            endpoint = f"/users/{{userPrincipalName}}/events/{event_id}"

            result = await client._graph_request(
                method="PATCH",
                endpoint=endpoint,
                user_email=organizer_email,
                json_body=update_data,
            )

            # Extract updated details
            subject = result.get("subject", "")
            start = result.get("start", {}).get("dateTime", "")
            end = result.get("end", {}).get("dateTime", "")
            location = result.get("location", {}).get("displayName", "")

            # Format response
            markdown_parts = [
                f"# Calendar Event Updated Successfully",
                f"\n**Event ID:** `{event_id}`",
                f"**Subject:** {subject}",
                f"**Start:** {start}",
                f"**End:** {end}",
            ]

            if location:
                markdown_parts.append(f"**Location:** {location}")

            markdown_parts.append(f"\n**Updated Fields:** {', '.join(update_data.keys())}")
            markdown_parts.append(f"\n*Updated invitations have been sent to all attendees.*")

            return "\n".join(markdown_parts)

        except Exception as e:
            error_msg = handle_outlook_error(e)
            logger.error(f"Error in update_calendar_event: {error_msg}")
            raise ToolExecutionError("update_calendar_event", error_msg)


class DeleteCalendarEventTool(CustomTool):
    """Delete/cancel a calendar event."""

    toolkit_name = "outlook"
    toolkit_display_name = "E18 Outlook"

    @property
    def name(self) -> str:
        return "delete_calendar_event"

    @property
    def description(self) -> str:
        return (
            "Delete or cancel a calendar event. "
            "\n\n"
            "Use this to cancel meetings and remove events from calendars. "
            "Cancellation notices are automatically sent to all attendees."
            "\n\n"
            "**WARNING:** This action cannot be undone. The event will be permanently deleted "
            "from the organizer's calendar and cancellation emails will be sent to attendees."
            "\n\n"
            "PARAMETERS:\n"
            "- event_id: The ID of the event to delete (from list_calendar_events)\n"
            "- organizer_email: Email of the event organizer\n"
            "\n"
            "TIP: Use get_calendar_event first to confirm you're deleting the correct event."
        )

    def get_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="event_id",
                type="string",
                description="The ID of the calendar event to delete",
                required=True,
            ),
            ToolParameter(
                name="organizer_email",
                type="string",
                description="Email of the event organizer (whose calendar contains the event)",
                required=True,
            ),
        ]

    async def _execute_impl(self, user_id: str, **kwargs: Any) -> str:
        """Execute delete calendar event tool."""
        try:
            event_id = kwargs.get("event_id")
            organizer_email = kwargs.get("organizer_email")

            if not all([event_id, organizer_email]):
                raise ToolExecutionError(
                    "delete_calendar_event",
                    "event_id and organizer_email are required"
                )

            # Delete event
            client = get_outlook_client()
            endpoint = f"/users/{{userPrincipalName}}/events/{event_id}"

            await client._graph_request(
                method="DELETE",
                endpoint=endpoint,
                user_email=organizer_email,
            )

            # Format response
            markdown_parts = [
                f"# Calendar Event Deleted Successfully",
                f"\n**Event ID:** `{event_id}`",
                f"**Organizer:** {organizer_email}",
                f"\n*The event has been permanently deleted and cancellation notices have been sent to all attendees.*"
            ]

            return "\n".join(markdown_parts)

        except Exception as e:
            error_msg = handle_outlook_error(e)
            logger.error(f"Error in delete_calendar_event: {error_msg}")
            raise ToolExecutionError("delete_calendar_event", error_msg)


class SearchUsersTool(CustomTool):
    """Search for users in the organization directory by name or email."""

    toolkit_name = "outlook"
    toolkit_display_name = "E18 Outlook"

    @property
    def name(self) -> str:
        return "search_users"

    @property
    def description(self) -> str:
        return (
            "Search for users in the organization directory or list all users. "
            "\n\n"
            "Use this when you need to:\n"
            "- Find someone's email address from their name\n"
            "- Discover users matching a search term\n"
            "- List all users in the organization (omit search_query)\n"
            "\n\n"
            "Supports fuzzy/partial matching for searches. For example, 'ben wall' finds 'Benjamin Wall', "
            "or 'john m' finds 'John Miller', 'John Mason', etc."
            "\n\n"
            "Searches across display name, first name, last name, and email address. "
            "Returns user details including email, job title, and department."
            "\n\n"
            "PARAMETERS:\n"
            "- search_query: (Optional) Name or email to search for. Omit to list all users.\n"
            "- limit: Maximum number of results to return (default 20, max 50)\n"
            "\n"
            "EXAMPLES:\n"
            "- No search query → lists all users (up to limit)\n"
            "- 'ben wall' → finds Benjamin Wall, Ben Wallace, etc.\n"
            "- 'hannah s' → finds Hannah Smith, Hannah Simpson, etc.\n"
            "- 'john@company.com' → finds exact email match"
        )

    def get_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="search_query",
                type="string",
                description="Name or email to search for. Supports partial matching (e.g., 'ben wall', 'hannah s'). Omit to list all users.",
                required=False,
            ),
            ToolParameter(
                name="limit",
                type="integer",
                description="Maximum number of results to return. Defaults to 20, max 50.",
                required=False,
                default=20,
            ),
        ]

    async def _execute_impl(self, user_id: str, **kwargs: Any) -> str:
        """Execute search users tool."""
        try:
            search_query = kwargs.get("search_query", "").strip()
            limit = min(kwargs.get("limit", 20), 50)

            # Get user email from context (auto-populated by MCP)
            # Note: Even though this is an org-level query, we validate auth context
            user_email = kwargs.get("_context_user_email")

            if not user_email:
                raise ToolExecutionError(
                    "search_users",
                    "User email is required for authentication. Please ensure you are properly authenticated."
                )

            client = get_outlook_client()

            # Build parameters for Microsoft Graph
            # NOTE: /users is an organization-level endpoint that doesn't require
            # a specific user context. We make the request directly rather than
            # using _graph_request which is designed for user-scoped endpoints.

            params = {
                "$select": "id,displayName,mail,givenName,surname,jobTitle,department,officeLocation",
                "$top": limit,
            }

            headers = {
                "Authorization": "",  # Will be set below
                "Content-Type": "application/json",
            }

            # If search_query provided, build $search filter
            # Microsoft Graph requires property:value format for $search queries
            # Each property:value clause must be wrapped in double quotes
            # OR operators must be OUTSIDE quotes and in UPPERCASE
            if search_query:
                # Build OR search across multiple properties
                # displayName supports fuzzy/tokenized matching (e.g., "ben wall" matches "Benjamin Wall")
                # givenName, surname, mail default to startswith behavior
                search_parts = []
                search_parts.append(f'"displayName:{search_query}"')
                search_parts.append(f'"givenName:{search_query}"')
                search_parts.append(f'"surname:{search_query}"')
                search_parts.append(f'"mail:{search_query}"')

                params["$search"] = " OR ".join(search_parts)
                params["$count"] = "true"  # Required for $search
                headers["ConsistencyLevel"] = "eventual"  # Required for $search
            else:
                # No search query - list all users
                # Add orderby for consistent results
                params["$orderby"] = "displayName"

            # Make direct request to organization-level /users endpoint
            token = await client._ensure_access_token()
            url = f"{client.graph_base_url}/users"
            headers["Authorization"] = f"Bearer {token}"

            import httpx
            async with httpx.AsyncClient() as http_client:
                response = await http_client.request(
                    method="GET",
                    url=url,
                    params=params,
                    headers=headers,
                    timeout=60.0,
                )

                if response.status_code == 401:
                    raise ToolExecutionError(
                        "search_users",
                        "Invalid Graph API credentials"
                    )

                if response.status_code == 403:
                    raise ToolExecutionError(
                        "search_users",
                        "Insufficient permissions to search users. The application needs User.Read.All or Directory.Read.All permissions."
                    )

                if response.status_code not in (200, 201):
                    raise ToolExecutionError(
                        "search_users",
                        f"Microsoft Graph API error: HTTP {response.status_code}: {response.text}"
                    )

                response = response.json() if response.content else {}

            users = response.get("value", [])

            if not users:
                if search_query:
                    return f"*No users found matching '{search_query}'.*\n\nTry:\n- Using a shorter search term\n- Checking spelling\n- Searching by first or last name separately"
                else:
                    return "*No users found in the organization.*"

            # Format as markdown
            markdown_parts = []
            if search_query:
                markdown_parts.append(f"# User Search Results")
                markdown_parts.append(f"**Search Query:** {search_query}")
                markdown_parts.append(f"**Results Found:** {len(users)}\n")
            else:
                markdown_parts.append(f"# Organization Users")
                markdown_parts.append(f"**Total Users Returned:** {len(users)} (limit: {limit})\n")

            for i, user in enumerate(users, 1):
                display_name = user.get("displayName", "Unknown")
                email = user.get("mail") or user.get("userPrincipalName", "No email")
                job_title = user.get("jobTitle", "")
                department = user.get("department", "")
                office = user.get("officeLocation", "")

                markdown_parts.append(f"## {i}. {display_name}")
                markdown_parts.append(f"**Email:** {email}")

                if job_title:
                    markdown_parts.append(f"**Job Title:** {job_title}")

                if department:
                    markdown_parts.append(f"**Department:** {department}")

                if office:
                    markdown_parts.append(f"**Office:** {office}")

                markdown_parts.append("")

            return "\n".join(markdown_parts)

        except Exception as e:
            error_msg = handle_outlook_error(e)
            logger.error(f"Error in search_users: {error_msg}")
            raise ToolExecutionError("search_users", error_msg)
