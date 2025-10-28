"""Custom tools implementation for the MCP server."""


from .tavily import (
    TavilySearchTool,
    TavilyExtractTool,
    TavilyCrawlTool,
    TavilyMapTool,
)

from .e2b_code_sandbox import (
    E2BExecuteCodeTool,
)

from .memory import (
    AddMemoryTool,
    SearchMemoryTool,
    GetMemoryTool,
    GetAllMemoriesTool,
    UpdateMemoryTool,
    DeleteMemoryTool
)

from .monday import (
    ListBoardsTool,
    GetBoardColumnsTool,
    ListBoardItemsTool,
    GetItemTool,
    GetCustomersTool,
    GetCustomerInfoTool,
    ListProcessesTool,
    GetUniqueFilterValuesTool,
)

from .fireflies import (
    ListMeetingsTool,
    GetMeetingSummaryTool,
    GetMeetingTranscriptTool,
)

from .e18_utility_toolkit import (
    GenerateProcessOnePagerTool,
)

from .nhs_analytics import (
    GetNHSOrganisationsTool,
    GetNHSMetricsCatalogueTool,
    RunNHSAnalysisCodeTool,
    GetComprehensiveTrustPerformance,
)

# Registry of available custom tools
CUSTOM_TOOLS = [

    # Tavily Tools
    TavilySearchTool(),
    TavilyExtractTool(),
    TavilyCrawlTool(),
    TavilyMapTool(),

    # E2B Code Sandbox Tools
    E2BExecuteCodeTool(),

    # Memory Tools
    AddMemoryTool(),
    SearchMemoryTool(),
    GetMemoryTool(),
    GetAllMemoriesTool(),
    UpdateMemoryTool(),
    DeleteMemoryTool(),

    # Monday Tools
    ListBoardsTool(),
    GetBoardColumnsTool(),
    ListBoardItemsTool(),
    GetItemTool(),
    GetCustomersTool(),
    GetCustomerInfoTool(),
    ListProcessesTool(),
    GetUniqueFilterValuesTool(),

    # Fireflies Tools
    ListMeetingsTool(),
    GetMeetingSummaryTool(),
    GetMeetingTranscriptTool(),

    # E18 Utility Tools
    GenerateProcessOnePagerTool(),

    # NHS Analytics Tools
    GetNHSOrganisationsTool(),
    GetNHSMetricsCatalogueTool(),
    RunNHSAnalysisCodeTool(),
    GetComprehensiveTrustPerformance(),

] 