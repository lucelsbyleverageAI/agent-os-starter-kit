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
    GetProcessesTool,
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
    GetProcessesTool(),
    
] 