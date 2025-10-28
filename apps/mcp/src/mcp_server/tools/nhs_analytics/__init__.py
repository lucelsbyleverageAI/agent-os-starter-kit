"""
NHS Performance Data Analysis Toolkit

Provides tools for analyzing NHS performance data using E2B code sandboxes
with direct database connectivity, plus predefined analytical tools.

Discovery Tools:
- GetNHSOrganisationsTool: Retrieve NHS organizations with filtering and search
- GetNHSMetricsCatalogueTool: List all available performance metrics

Flexible Analysis:
- RunNHSAnalysisCodeTool: Execute Python/SQL code with database access

Predefined Analytics:
- GetComprehensiveTrustPerformance: Complete performance overview for a single trust
"""

from .tools import (
    GetNHSOrganisationsTool,
    GetNHSMetricsCatalogueTool,
    RunNHSAnalysisCodeTool,
    GetComprehensiveTrustPerformance,
)

__all__ = [
    "GetNHSOrganisationsTool",
    "GetNHSMetricsCatalogueTool",
    "RunNHSAnalysisCodeTool",
    "GetComprehensiveTrustPerformance",
]
