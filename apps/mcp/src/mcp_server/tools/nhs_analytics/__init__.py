"""
NHS Performance Data Analysis Toolkit

Provides tools for analyzing NHS performance data using E2B code sandboxes
with direct database connectivity, plus predefined analytical tools.

Discovery Tools:
- GetNHSOrganisationsTool: Retrieve NHS organizations with filtering and search
- ListAvailableMetricsTool: List all available metrics with breakdown dimensions and values

Flexible Analysis:
- RunNHSAnalysisCodeTool: Execute Python/SQL code with database access

Predefined Analytics:
- GetComprehensiveTrustPerformance: Complete performance overview for a single trust
- GetRankingByMetricTool: Get ranked performance leaderboard for any metric
"""

from .tools import (
    GetNHSOrganisationsTool,
    RunNHSAnalysisCodeTool,
    ListAvailableMetricsTool,
    GetRankingByMetricTool,
    GetComprehensiveTrustPerformance,
)

__all__ = [
    "GetNHSOrganisationsTool",
    "RunNHSAnalysisCodeTool",
    "ListAvailableMetricsTool",
    "GetRankingByMetricTool",
    "GetComprehensiveTrustPerformance",
]
