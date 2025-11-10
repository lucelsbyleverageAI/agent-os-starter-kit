"""E18 Outlook email and calendar tools for the MCP server."""

from .tools import (
    ListEmailsTool,
    ListMailFoldersTool,
    ReadEmailTool,
    DownloadOutlookAttachmentTool,
    CreateEmailTool,
    EditEmailDraftTool,
    SendEmailDraftTool,
)

from .calendar_tools import (
    ListMyCalendarEventsTool,
    ListUserCalendarEventsTool,
    GetCalendarEventTool,
    GetUserAvailabilityTool,
    CreateCalendarEventTool,
    UpdateCalendarEventTool,
    DeleteCalendarEventTool,
    SearchUsersTool,
)

__all__ = [
    # Email tools
    "ListEmailsTool",
    "ListMailFoldersTool",
    "ReadEmailTool",
    "DownloadOutlookAttachmentTool",
    "CreateEmailTool",
    "EditEmailDraftTool",
    "SendEmailDraftTool",
    # Calendar tools
    "ListMyCalendarEventsTool",
    "ListUserCalendarEventsTool",
    "GetCalendarEventTool",
    "GetUserAvailabilityTool",
    "CreateCalendarEventTool",
    "UpdateCalendarEventTool",
    "DeleteCalendarEventTool",
    "SearchUsersTool",
]
