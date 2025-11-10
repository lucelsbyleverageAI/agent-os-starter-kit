"""NHS Analytics tools implementation for the MCP server."""

import json
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Union

from ..base import CustomTool, ToolParameter
from ...config import settings
from ...utils.logging import get_logger
from ...utils.exceptions import ToolExecutionError

from .base import (
    get_nhs_database_url,
    get_sandbox_helper_code,
    get_sandbox_config,
    get_sandbox_class,
    NHSStorageClient
)
from . import formatters
from . import queries

logger = get_logger(__name__)


class GetNHSOrganisationsTool(CustomTool):
    """Retrieve NHS organisations with filtering and search capabilities."""

    toolkit_name = "nhs_analytics"
    toolkit_display_name = "NHS Analytics"

    @property
    def name(self) -> str:
        return "get_nhs_organisations"

    @property
    def description(self) -> str:
        return (
            "Retrieve NHS organisations (trusts) with optional filtering by region, "
            "trust type, subtype, and keyword search. Returns organisation codes, names, "
            "and metadata needed for performance data analysis. "
            "Use this tool first to discover available organisations before querying performance metrics."
        )

    def get_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="region",
                type="string",
                description=(
                    "Filter by NHS England region. "
                ),
                required=False,
            ),
            ToolParameter(
                name="trust_type",
                type="string",
                description=(
                    "Filter by trust type. "
                ),
                required=False,
            ),
            ToolParameter(
                name="trust_subtype",
                type="string",
                description=(
                    "Filter by trust subtype. "
                ),
                required=False,
            ),
            ToolParameter(
                name="search",
                type="string",
                description="Keyword search on organisation name (case-insensitive partial match)",
                required=False,
            ),
            ToolParameter(
                name="org_codes",
                type="array",
                description="Specific organisation codes to retrieve (e.g., ['RJ1', 'RRK'])",
                required=False,
                items={"type": "string"},
            ),
        ]

    async def _execute_impl(self, user_id: str, **kwargs: Any) -> Any:
        """Execute the get NHS organisations tool."""
        region = kwargs.get("region")
        trust_type = kwargs.get("trust_type")
        trust_subtype = kwargs.get("trust_subtype")
        search = kwargs.get("search")
        org_codes = kwargs.get("org_codes", [])

        logger.info(
            "Fetching NHS organisations",
            region=region,
            trust_type=trust_type,
            search=search,
            org_codes_count=len(org_codes) if org_codes else 0,
        )

        try:
            # Build SQL query with filters
            from sqlalchemy import create_engine, text
            import pandas as pd

            db_url = get_nhs_database_url(for_external_sandbox=False)  # MCP server runs in Docker
            engine = create_engine(db_url)

            # Start with base query
            sql = "SELECT org_code, trust_name, region, trust_type, trust_subtype FROM performance_data.dim_organisations WHERE 1=1"
            params = {}

            # Add filters
            if org_codes:
                placeholders = ", ".join([f":org_code_{i}" for i in range(len(org_codes))])
                sql += f" AND org_code IN ({placeholders})"
                for i, code in enumerate(org_codes):
                    params[f"org_code_{i}"] = code

            if region:
                sql += " AND region = :region"
                params["region"] = region

            if trust_type:
                sql += " AND trust_type = :trust_type"
                params["trust_type"] = trust_type

            if trust_subtype:
                sql += " AND trust_subtype = :trust_subtype"
                params["trust_subtype"] = trust_subtype

            if search:
                sql += " AND LOWER(trust_name) LIKE LOWER(:search)"
                params["search"] = f"%{search}%"

            sql += " ORDER BY trust_name"

            # Execute query
            df = pd.read_sql(text(sql), engine, params=params)

            logger.info(f"Retrieved {len(df)} NHS organisations")

            # Convert to JSON-serializable format
            result = {
                "count": len(df),
                "organisations": df.to_dict(orient="records"),
            }

            return json.dumps(result, indent=2)

        except Exception as e:
            logger.error(f"Failed to fetch NHS organisations: {e}", exc_info=True)
            raise ToolExecutionError(
                "get_nhs_organisations",
                f"Failed to retrieve organisations: {str(e)}"
            )


class RunNHSAnalysisCodeTool(CustomTool):
    """Execute Python code in E2B sandbox with NHS database access."""

    toolkit_name = "nhs_analytics"
    toolkit_display_name = "NHS Analytics"

    # Configuration
    DEFAULT_TIMEOUT = 600  # 10 minutes for complex analysis
    REQUEST_TIMEOUT = 60
    NHS_PACKAGES = [
        "pandas",
        "numpy",
        "matplotlib",
        "seaborn",
        "plotly",
        "sqlalchemy",
        "psycopg2-binary",
    ]

    def __init__(self) -> None:
        super().__init__()
        self._sandbox_cache: Dict[Tuple[str, str], Dict[str, Any]] = {}
        self._storage_client = NHSStorageClient()

    @property
    def name(self) -> str:
        return "run_nhs_analysis_code"

    @property
    def description(self) -> str:
        return (
            "Execute Python code in a persistent E2B sandbox with direct access to the NHS performance database. "
            "A database connection (db_engine) is pre-configured and available for use with pandas. "
            "Environment variables NHS_DB_URL and NHS_SCHEMA are set. "
            "Use pandas.read_sql() to execute SQL queries against the performance_data schema. "
            "Matplotlib/plotly charts are automatically uploaded to storage and URLs returned. "
            "Sandbox state persists across calls within the same thread_id."
        )

    def get_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="code",
                type="string",
                description="Python code to execute. Use pd.read_sql(query, db_engine) to query the database.",
                required=True,
            ),
            ToolParameter(
                name="thread_id",
                type="string",
                description="Thread identifier for sandbox persistence (default: 'default'). Same thread_id reuses the same sandbox.",
                required=False,
            ),
            ToolParameter(
                name="reset",
                type="boolean",
                description="Kill existing sandbox and start fresh (default: false)",
                required=False,
                default=False,
            ),
            ToolParameter(
                name="timeout_seconds",
                type="integer",
                description="Execution timeout in seconds (default: 600, max: 600)",
                required=False,
            ),
        ]

    async def _execute_impl(self, user_id: str, **kwargs: Any) -> Any:
        """Execute NHS analysis code in sandbox (Docker local or E2B cloud)."""
        # Extract parameters
        code = kwargs.get("code", "").strip()
        thread_id = kwargs.get("thread_id") or "default"
        reset = kwargs.get("reset", False)
        timeout_seconds = min(kwargs.get("timeout_seconds", self.DEFAULT_TIMEOUT), 600)

        if not code:
            raise ToolExecutionError("run_nhs_analysis_code", "No code provided to execute")

        # Get sandbox configuration
        sandbox_mode, db_url, network_name = get_sandbox_config()

        logger.info(
            "NHS analysis code execution started",
            user_id=user_id,
            thread_id=thread_id,
            reset=reset,
            code_length=len(code),
            sandbox_mode=sandbox_mode,
        )

        sandbox = None
        execution_sandbox_id = None

        try:
            # Get or create sandbox
            sandbox, execution_sandbox_id, is_new = await self._get_or_create_sandbox(
                user_id, thread_id, reset, network_name
            )

            # Ensure packages are installed before running any code that needs them
            cache_key = (user_id, thread_id)
            cache_entry = self._sandbox_cache.get(cache_key, {})
            packages_installed = cache_entry.get("packages_installed", False)

            if not packages_installed or reset:
                logger.info("Installing NHS analytics packages in sandbox")
                await self._install_packages(sandbox, self.NHS_PACKAGES)
                # Mark packages as installed in cache
                cache_entry["packages_installed"] = True
                self._sandbox_cache[cache_key] = cache_entry

            # Prepend helper code to user code to ensure db_engine is defined
            helper_code = get_sandbox_helper_code()
            full_code = f"{helper_code}\n\n# User Code:\n{code}"

            # Execute combined code (helper + user)
            logger.info("Executing NHS analysis code with database setup")
            execution = await sandbox.run_code(
                full_code,
                envs={
                    "NHS_DB_URL": db_url,
                    "NHS_SCHEMA": "performance_data",
                },
                timeout=timeout_seconds,
            )

            # Process results
            result = {
                "success": not bool(execution.error),
                "sandbox_id": execution_sandbox_id,
                "thread_id": thread_id,
                "stdout": execution.logs.stdout if execution.logs else [],
                "stderr": execution.logs.stderr if execution.logs else [],
                "error": str(execution.error) if execution.error else None,
                "results": [],
                "visualizations": [],
            }

            # Process execution results (including images/charts)
            if execution.results:
                for res in execution.results:
                    if hasattr(res, '__dict__'):
                        result_dict = {}

                        # Handle different result types
                        if hasattr(res, 'text'):
                            result_dict['text'] = res.text
                        if hasattr(res, 'html'):
                            result_dict['html'] = res.html
                        if hasattr(res, 'json'):
                            result_dict['json'] = res.json
                        if hasattr(res, 'png'):
                            # Upload PNG to storage
                            if res.png:
                                try:
                                    import base64
                                    png_bytes = base64.b64decode(res.png)
                                    filename = f"{int(time.time())}_chart.png"
                                    url = await self._storage_client.upload_visualization(
                                        user_id, filename, png_bytes, "image/png"
                                    )
                                    result["visualizations"].append({
                                        "type": "png",
                                        "url": url,
                                        "filename": filename,
                                    })
                                    logger.info("Uploaded PNG visualization", url=url)
                                except Exception as e:
                                    logger.warning(f"Failed to upload PNG: {e}")

                        result["results"].append(result_dict)

            logger.info(
                "NHS analysis code execution completed",
                success=result["success"],
                stdout_lines=len(result["stdout"]),
                stderr_lines=len(result["stderr"]),
                visualizations=len(result["visualizations"]),
            )

            return json.dumps(result, indent=2)

        except Exception as e:
            logger.error(f"NHS analysis code execution failed: {e}", exc_info=True)
            return json.dumps({
                "success": False,
                "error": str(e),
                "sandbox_id": execution_sandbox_id,
                "thread_id": thread_id,
                "stdout": [],
                "stderr": [],
                "results": [],
            }, indent=2)

    async def _get_or_create_sandbox(
        self,
        user_id: str,
        thread_id: str,
        reset: bool,
        network_name: str
    ) -> Tuple[Union[Any, Any], str, bool]:
        """Get or create a sandbox for NHS analysis.

        Args:
            user_id: User ID
            thread_id: Thread ID for sandbox isolation
            reset: Whether to reset the sandbox
            network_name: Docker network name (for local sandboxes)

        Returns:
            Tuple of (sandbox, sandbox_id, is_new_sandbox)
        """
        cache_key = (user_id, thread_id)

        # Handle reset
        if reset and cache_key in self._sandbox_cache:
            try:
                cache_entry = self._sandbox_cache[cache_key]
                old_sandbox = cache_entry.get("sandbox")
                if old_sandbox:
                    await old_sandbox.kill()
                del self._sandbox_cache[cache_key]
                logger.info("Reset sandbox for NHS analysis")
            except Exception as e:
                logger.warning(f"Failed to kill old sandbox: {e}")

        # Check cache
        if cache_key in self._sandbox_cache and not reset:
            try:
                cache_entry = self._sandbox_cache[cache_key]
                sandbox = cache_entry.get("sandbox")
                if sandbox:
                    is_running = await sandbox.is_running()
                    if is_running:
                        await sandbox.set_timeout(self.DEFAULT_TIMEOUT)
                        logger.info("Using cached NHS analysis sandbox", sandbox_id=sandbox.sandbox_id)
                        return sandbox, sandbox.sandbox_id, False
                    else:
                        del self._sandbox_cache[cache_key]
            except Exception:
                if cache_key in self._sandbox_cache:
                    del self._sandbox_cache[cache_key]

        # Create new sandbox using factory
        SandboxClass = get_sandbox_class()

        metadata = {
            "user_id": user_id,
            "thread_id": thread_id,
            "purpose": "nhs_analytics",
            "created_at": str(int(time.time())),
        }

        # Create sandbox with appropriate parameters
        if network_name:
            # Local Docker sandbox
            sandbox = await SandboxClass.create(
                timeout=self.DEFAULT_TIMEOUT,
                metadata=metadata,
                network_name=network_name,
            )
        else:
            # E2B sandbox
            sandbox = await SandboxClass.create(
                timeout=self.DEFAULT_TIMEOUT,
                metadata=metadata,
                api_key=settings.e2b_api_key,
                request_timeout=self.REQUEST_TIMEOUT,
            )

        self._sandbox_cache[cache_key] = {
            "sandbox": sandbox,
            "packages_installed": False,
        }

        logger.info("Created new NHS analysis sandbox", sandbox_id=sandbox.sandbox_id)

        return sandbox, sandbox.sandbox_id, True

    async def _install_packages(self, sandbox: Any, packages: List[str]) -> None:
        """Install Python packages in sandbox and verify installation.

        Works with both E2B AsyncSandbox and DockerLocalSandbox.
        """
        if not packages:
            return

        packages_str = " ".join(packages)
        logger.info(f"Installing packages: {packages_str}")

        install_code = f"""
import subprocess
import sys

print("Installing NHS analytics packages: {packages_str}")
try:
    result = subprocess.run([
        sys.executable, "-m", "pip", "install", "--quiet"
    ] + {packages!r}, capture_output=True, text=True, timeout=180)

    if result.returncode == 0:
        print("✅ Packages installed successfully")

        # Verify critical packages can be imported
        try:
            import sqlalchemy
            import psycopg2
            print("✅ Critical packages verified (sqlalchemy, psycopg2)")
        except ImportError as ie:
            print(f"❌ Package verification failed: {{ie}}")
            raise
    else:
        print(f"❌ Package installation failed: {{result.stderr}}")
        raise RuntimeError(f"pip install failed: {{result.stderr}}")

except Exception as e:
    print(f"❌ Package installation error: {{e}}")
    raise
"""

        try:
            execution = await sandbox.run_code(install_code, timeout=240)

            # Check if installation was successful
            if execution.error:
                error_msg = str(execution.error)
                logger.error("Package installation failed", error=error_msg)
                raise ToolExecutionError(
                    "run_nhs_analysis_code",
                    f"Failed to install required packages: {error_msg}"
                )

            # Check stdout for success message
            stdout_text = "\n".join(execution.logs.stdout) if execution.logs else ""
            if "Packages installed successfully" not in stdout_text:
                logger.error("Package installation did not complete successfully", stdout=stdout_text)
                raise ToolExecutionError(
                    "run_nhs_analysis_code",
                    f"Package installation did not complete successfully. Check logs."
                )

            logger.info("NHS analytics packages installed and verified successfully")

        except ToolExecutionError:
            raise
        except Exception as e:
            logger.error(f"Unexpected error installing packages: {e}", exc_info=True)
            raise ToolExecutionError(
                "run_nhs_analysis_code",
                f"Unexpected error installing packages: {str(e)}"
            )


class ListAvailableMetricsTool(CustomTool):
    """List all available NHS performance metrics with their metadata and breakdown dimensions."""

    toolkit_name = "nhs_analytics"
    toolkit_display_name = "NHS Analytics"

    @property
    def name(self) -> str:
        return "list_available_metrics"

    @property
    def description(self) -> str:
        return (
            "List all available NHS performance metrics with codes, names, categories, and breakdown dimensions. "
            "Returns metric IDs, labels, domains (RTT/Cancer/Oversight), units, performance direction "
            "(higher/lower is better), NHS target thresholds, and available disaggregation breakdowns with their values. "
            "Use this tool to discover available metrics before using get_ranking_by_metric. "
            "Example: Returns 'cancer_62d_pct_within_target' with breakdowns by cancer_type (Lung, Breast, etc.) and referral_route."
        )

    def get_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="domain",
                type="string",
                description="Filter by domain: 'rtt', 'cancer', or 'oversight' (optional - returns all if not specified)",
                required=False,
            ),
        ]

    async def _execute_impl(self, user_id: str, **kwargs: Any) -> Any:
        """Execute the list available metrics tool."""
        domain = kwargs.get("domain")

        logger.info("Fetching available NHS metrics", domain=domain)

        try:
            from sqlalchemy import create_engine, text

            db_url = get_nhs_database_url(for_external_sandbox=False)
            engine = create_engine(db_url)

            # Query metrics catalogue
            query = """
                SELECT
                    metric_id,
                    metric_label,
                    domain,
                    unit,
                    higher_is_better,
                    target_threshold,
                    min_denominator,
                    disaggregation_dims,
                    notes
                FROM performance_data.metric_catalogue
                WHERE 1=1
            """

            params = {}
            if domain:
                query += " AND domain = :domain"
                params["domain"] = domain

            query += " ORDER BY domain, metric_id"

            with engine.connect() as conn:
                result = conn.execute(text(query), params)
                metrics = []

                for row in result:
                    metric_dict = dict(row._mapping)

                    # Get disaggregation values for this metric
                    disagg_dims = metric_dict.get("disaggregation_dims")
                    if disagg_dims:
                        # Get actual values for each dimension
                        disagg_values = queries.get_metric_disaggregation_values(
                            engine,
                            metric_dict["metric_id"],
                            disagg_dims
                        )
                        metric_dict["disaggregation_values"] = disagg_values
                    else:
                        metric_dict["disaggregation_values"] = {}

                    metrics.append(metric_dict)

            logger.info(f"Retrieved {len(metrics)} metrics")

            # Format as JSON
            result = {
                "count": len(metrics),
                "metrics": metrics,
                "domains": {
                    "rtt": "Referral to Treatment waiting times",
                    "cancer": "Cancer waiting times (28-day, 31-day, 62-day standards)",
                    "oversight": "NHS Oversight Framework metrics"
                }
            }

            return json.dumps(result, indent=2, default=str)

        except Exception as e:
            logger.error(f"Failed to fetch available metrics: {e}", exc_info=True)
            raise ToolExecutionError(
                "list_available_metrics",
                f"Failed to retrieve metrics: {str(e)}"
            )


class GetRankingByMetricTool(CustomTool):
    """Get ranked performance leaderboard for a specific NHS metric with optional filters."""

    toolkit_name = "nhs_analytics"
    toolkit_display_name = "NHS Analytics"

    @property
    def name(self) -> str:
        return "get_ranking_by_metric"

    @property
    def description(self) -> str:
        return (
            "Get a ranked performance leaderboard for any NHS metric showing how all trusts perform. "
            "Returns markdown-formatted rankings with trust names, values, national percentiles, regions, and "
            "cohort statistics (min, Q1, median, Q3, max). Supports filtering by region, trust type, and "
            "disaggregated metrics (e.g., rank trusts specifically on lung cancer performance or specific RTT pathways). "
            "Use list_available_metrics first to discover valid metric IDs and breakdown options. "
            "Example: metric_id='cancer_62d_pct_within_target' with cancer_type='Lung' ranks all trusts on lung cancer 62-day performance."
        )

    def get_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="metric_id",
                type="string",
                description="Metric ID from metrics catalogue (e.g., 'rtt_pct_within_18', 'cancer_62d_pct_within_target', 'OF0014'). Use list_available_metrics to discover IDs.",
                required=True,
            ),
            ToolParameter(
                name="period",
                type="string",
                description="Reporting period (e.g., '2025-08', 'Q1 2025/26'). Defaults to latest available period if not specified.",
                required=False,
            ),
            ToolParameter(
                name="region",
                type="string",
                description="Filter to specific NHS England region (e.g., 'London', 'South East')",
                required=False,
            ),
            ToolParameter(
                name="trust_type",
                type="string",
                description="Filter to specific trust type (e.g., 'Acute trust', 'Mental Health trust')",
                required=False,
            ),
            ToolParameter(
                name="trust_subtype",
                type="string",
                description="Filter to specific trust subtype",
                required=False,
            ),
            ToolParameter(
                name="cancer_type",
                type="string",
                description="For cancer metrics: specific cancer type (e.g., 'Lung', 'Breast', 'Colorectal'). Use null for trust-level aggregates.",
                required=False,
            ),
            ToolParameter(
                name="referral_route",
                type="string",
                description="For cancer metrics: referral route (e.g., 'URGENT SUSPECTED CANCER', 'ALL ROUTES'). Defaults to 'ALL ROUTES' for trust aggregates.",
                required=False,
            ),
            ToolParameter(
                name="rtt_part_type",
                type="string",
                description="For RTT metrics: pathway type (e.g., 'Overall', 'Part_1A', 'Part_1B', 'Part_2'). Defaults to 'Overall'.",
                required=False,
            ),
            ToolParameter(
                name="top_n",
                type="integer",
                description="Number of top performers to return (default: 10)",
                required=False,
                default=10,
            ),
            ToolParameter(
                name="bottom_n",
                type="integer",
                description="Number of bottom performers to return (default: 10)",
                required=False,
                default=10,
            ),
            ToolParameter(
                name="highlight_org_code",
                type="string",
                description="Always include this organization in results even if mid-table (e.g., 'RJ1')",
                required=False,
            ),
        ]

    async def _execute_impl(self, user_id: str, **kwargs: Any) -> Any:
        """Execute the get ranking by metric tool."""
        metric_id = kwargs.get("metric_id")
        period = kwargs.get("period")
        region = kwargs.get("region")
        trust_type = kwargs.get("trust_type")
        trust_subtype = kwargs.get("trust_subtype")
        cancer_type = kwargs.get("cancer_type")
        referral_route = kwargs.get("referral_route")
        rtt_part_type = kwargs.get("rtt_part_type")
        top_n = kwargs.get("top_n", 10)
        bottom_n = kwargs.get("bottom_n", 10)
        highlight_org_code = kwargs.get("highlight_org_code")

        if not metric_id:
            raise ToolExecutionError(
                "get_ranking_by_metric",
                "metric_id parameter is required"
            )

        logger.info(
            "Fetching metric rankings",
            metric_id=metric_id,
            period=period,
            region=region,
            cancer_type=cancer_type,
            rtt_part_type=rtt_part_type,
        )

        try:
            from sqlalchemy import create_engine

            db_url = get_nhs_database_url(for_external_sandbox=False)
            engine = create_engine(db_url)

            # Infer domain from metric_id prefix
            if metric_id.startswith("rtt_"):
                domain = "rtt"
            elif metric_id.startswith("cancer_"):
                domain = "cancer"
            elif metric_id.startswith("OF") or metric_id == "oversight_average_score" or "segment" in metric_id.lower():
                domain = "oversight"
            else:
                raise ToolExecutionError(
                    "get_ranking_by_metric",
                    f"Cannot infer domain from metric_id: {metric_id}. Expected prefix: 'rtt_', 'cancer_', or 'OF'"
                )

            # Build cohort filter
            cohort_filter = {}
            if region:
                cohort_filter["region"] = region
            if trust_type:
                cohort_filter["trust_type"] = trust_type
            if trust_subtype:
                cohort_filter["trust_subtype"] = trust_subtype

            # Build disaggregation filter
            disagg_filter = {}
            if cancer_type is not None:
                disagg_filter["cancer_type"] = cancer_type
            if referral_route:
                disagg_filter["referral_route"] = referral_route
            if rtt_part_type:
                disagg_filter["rtt_part_type"] = rtt_part_type

            # For oversight, auto-detect latest period per metric if not provided
            if period is None and domain == "oversight":
                metric_periods = queries.get_latest_periods_per_metric(engine, "oversight")
                period = metric_periods.get(metric_id)
                if not period:
                    raise ToolExecutionError(
                        "get_ranking_by_metric",
                        f"No data found for oversight metric: {metric_id}"
                    )
                logger.info(f"Auto-detected period for {metric_id}: {period}")

            # Call rankings query
            rankings_data = queries.get_domain_rankings(
                engine=engine,
                domain=domain,
                metric_id=metric_id,
                period=period,
                cohort_filter=cohort_filter or None,
                disaggregation_filter=disagg_filter or None,
                top_n=top_n,
                bottom_n=bottom_n,
                highlight_org_code=highlight_org_code
            )

            # Format as markdown
            markdown_output = formatters.format_metric_rankings(rankings_data)

            logger.info(
                "Metric rankings retrieved successfully",
                metric_id=metric_id,
                rankings_count=len(rankings_data.get("rankings", []))
            )

            return markdown_output

        except ToolExecutionError:
            raise
        except Exception as e:
            logger.error(f"Failed to fetch metric rankings: {e}", exc_info=True)
            raise ToolExecutionError(
                "get_ranking_by_metric",
                f"Failed to retrieve rankings: {str(e)}"
            )


class GetComprehensiveTrustPerformance(CustomTool):
    """Get comprehensive performance overview for a single NHS trust across all domains."""

    toolkit_name = "nhs_analytics"
    toolkit_display_name = "NHS Analytics"

    @property
    def name(self) -> str:
        return "get_comprehensive_trust_performance"

    @property
    def description(self) -> str:
        return (
            "Retrieve comprehensive performance metrics for a single NHS trust across all domains "
            "(RTT, Cancer, Oversight). Automatically uses the latest reporting period for each domain "
            "and metric. Returns markdown-formatted data including: trust metrics with national/regional/"
            "cohort percentiles, quartile comparisons, regional rankings, and detailed breakdowns by "
            "cancer type, referral route, and RTT pathway type. "
            "Pure factual data presentation with no analysis or insights.\n\n"
            "Note: Cancer route and type breakdowns exclude cancer types with <20 patients for "
            "statistical validity. Trust-level aggregates (shown in 'Overall Performance by Standard') "
            "include all patients for official reporting."
        )

    def get_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="org_code",
                type="string",
                description="NHS organisation code (e.g., 'RJ1')",
                required=True,
            ),
            ToolParameter(
                name="include_domains",
                type="array",
                description="Domains to include. Default: all domains ['rtt', 'cancer', 'oversight']",
                required=False,
                items={"type": "string", "enum": ["rtt", "cancer", "oversight"]},
                default=["rtt", "cancer", "oversight"],
            ),
            ToolParameter(
                name="include_cancer_breakdown",
                type="boolean",
                description="Include cancer type and referral route breakdown (default: true)",
                required=False,
                default=True,
            ),
            ToolParameter(
                name="include_rtt_breakdown",
                type="boolean",
                description="Include RTT pathway type breakdown (default: true)",
                required=False,
                default=True,
            ),
        ]

    async def _execute_impl(self, user_id: str, **kwargs: Any) -> Any:
        """Execute comprehensive trust performance retrieval."""
        org_code = kwargs.get("org_code")
        include_domains = kwargs.get("include_domains", ["rtt", "cancer", "oversight"])
        include_cancer_breakdown = kwargs.get("include_cancer_breakdown", True)
        include_rtt_breakdown = kwargs.get("include_rtt_breakdown", True)

        if not org_code:
            raise ToolExecutionError(
                "get_comprehensive_trust_performance",
                "org_code parameter is required"
            )

        logger.info(
            "Fetching comprehensive trust performance",
            org_code=org_code,
            domains=include_domains,
            cancer_breakdown=include_cancer_breakdown,
            rtt_breakdown=include_rtt_breakdown,
        )

        try:
            from sqlalchemy import create_engine

            db_url = get_nhs_database_url(for_external_sandbox=False)
            engine = create_engine(db_url)

            # Get performance data (always uses latest periods)
            data = queries.get_comprehensive_performance(
                engine=engine,
                org_code=org_code,
                period=None,  # Always use latest periods
                domains=include_domains,
                include_rtt_breakdown=include_rtt_breakdown,
                include_cancer_breakdown=include_cancer_breakdown
            )

            # Check for errors
            if "error" in data:
                raise ToolExecutionError(
                    "get_comprehensive_trust_performance",
                    data["error"]
                )

            trust_info = data["trust_info"]
            periods_by_domain = data["periods"]  # Dict mapping domain to period
            metrics = data["metrics"]

            # Build markdown document
            sections = []

            # Header
            sections.append({
                "type": "header",
                "content": f"Performance Overview: {trust_info['trust_name']}",
                "level": 1
            })

            # Metadata
            sections.append({
                "type": "metadata",
                "content": {
                    "Code": trust_info['org_code'],
                    "Region": trust_info['region'],
                    "Type": trust_info['trust_type'],
                    "Subtype": trust_info['trust_subtype']
                }
            })

            # Show periods by domain (different domains may have different periods)
            period_info = {}
            for domain, period_val in periods_by_domain.items():
                if period_val:
                    domain_label = {
                        'rtt': 'RTT Period',
                        'cancer': 'Cancer Period',
                        'oversight': 'Oversight Period'
                    }.get(domain, f"{domain.upper()} Period")
                    period_info[domain_label] = period_val

            if period_info:
                sections.append({
                    "type": "metadata",
                    "content": period_info
                })

            sections.append({"type": "separator"})

            # Group metrics by domain
            metrics_by_domain = {}
            for metric in metrics:
                domain = metric['domain']
                if domain not in metrics_by_domain:
                    metrics_by_domain[domain] = []
                metrics_by_domain[domain].append(metric)

            # Log metrics by domain
            domain_counts = {domain: len(metrics_list) for domain, metrics_list in metrics_by_domain.items()}
            logger.info(f"Metrics grouped by domain: {domain_counts}")

            # RTT Domain
            if 'rtt' in metrics_by_domain:
                logger.info(f"Processing RTT domain: {len(metrics_by_domain['rtt'])} metrics before filtering")
                sections.append({
                    "type": "header",
                    "content": "RTT (Referral to Treatment) Performance",
                    "level": 2
                })

                # Add RTT explanation
                sections.append({
                    "type": "text",
                    "content": "_RTT (Referral to Treatment) measures how long patients wait from GP referral to receiving treatment. The 18-week standard requires that 92% of patients on incomplete pathways wait no longer than 18 weeks._"
                })

                sections.append({
                    "type": "text",
                    "content": "**Understanding the percentile rankings**: Percentiles show where this trust ranks compared to peers. A higher percentile means better performance. For example, '64%' means this trust performs better than 64% of trusts in that cohort."
                })

                sections.append({
                    "type": "header",
                    "content": "Key Metrics",
                    "level": 3
                })

                # Build RTT table
                headers = [
                    "Metric", "Value", "Target", "Met", "National %", "Trust Type %",
                    "Trust Subtype %", "Regional Rank"
                ]
                alignments = ["left", "right", "right", "center", "right", "right", "right", "right"]

                rows = []
                seen_metrics = set()  # Track metric_ids to prevent duplicates in output
                for m in metrics_by_domain['rtt']:
                    # Filter to 'Overall' metrics only (not breakdown parts like Part_1A)
                    if m.get('rtt_part_type') == 'Overall' or not m.get('rtt_part_type'):
                        # Skip if we've already added this metric (defensive deduplication)
                        metric_id = m.get('metric_id')
                        if metric_id in seen_metrics:
                            continue
                        seen_metrics.add(metric_id)

                        rows.append([
                            m['metric_label'],
                            formatters.format_value_with_unit(m['value'], m['unit']),
                            formatters.format_value_with_unit(m['target_threshold'], m['unit']) if m['target_threshold'] else '-',
                            formatters.format_target_status(m['target_met']),
                            formatters.format_percentile_rank(m['percentile_overall']),
                            formatters.format_percentile_rank(m['percentile_trust_type']),
                            formatters.format_percentile_rank(m['percentile_trust_subtype']),
                            formatters.format_rank(m.get('regional_rank'), m.get('regional_total'))
                        ])

                sections.append({
                    "type": "table",
                    "content": {
                        "headers": headers,
                        "rows": rows,
                        "alignments": alignments
                    }
                })

                # Cohort comparison table
                sections.append({
                    "type": "header",
                    "content": "Cohort Comparison",
                    "level": 3
                })

                sections.append({
                    "type": "text",
                    "content": "_This shows how the trust's performance compares to different peer groups using quartiles (Q1 = 25th percentile, Median = 50th percentile, Q3 = 75th percentile). Values are shown for the '% within 18 weeks (flow)' metric._"
                })

                cohort_headers = ["Cohort", "Q1", "Median", "Q3", "Your Trust"]
                cohort_rows = []

                # Get first RTT 'Overall' metric for cohort stats
                # With DISTINCT ON in queries.py, each metric appears only once
                if metrics_by_domain['rtt']:
                    sample_metric = next((m for m in metrics_by_domain['rtt']
                                        if m.get('rtt_part_type') == 'Overall' or not m.get('rtt_part_type')), None)
                    if sample_metric:
                        unit = sample_metric['unit']
                        cohort_rows.append([
                            "National",
                            formatters.format_value_with_unit(sample_metric.get('national_q1'), unit),
                            formatters.format_value_with_unit(sample_metric.get('national_median'), unit),
                            formatters.format_value_with_unit(sample_metric.get('national_q3'), unit),
                            formatters.format_value_with_unit(sample_metric['value'], unit)
                        ])
                        cohort_rows.append([
                            f"{trust_info['trust_type']}",
                            formatters.format_value_with_unit(sample_metric.get('trust_type_q1'), unit),
                            formatters.format_value_with_unit(sample_metric.get('trust_type_median'), unit),
                            formatters.format_value_with_unit(sample_metric.get('trust_type_q3'), unit),
                            formatters.format_value_with_unit(sample_metric['value'], unit)
                        ])
                        cohort_rows.append([
                            f"{trust_info['trust_subtype']}",
                            formatters.format_value_with_unit(sample_metric.get('trust_subtype_q1'), unit),
                            formatters.format_value_with_unit(sample_metric.get('trust_subtype_median'), unit),
                            formatters.format_value_with_unit(sample_metric.get('trust_subtype_q3'), unit),
                            formatters.format_value_with_unit(sample_metric['value'], unit)
                        ])
                        cohort_rows.append([
                            f"{trust_info['region']} Region",
                            formatters.format_value_with_unit(sample_metric.get('region_q1'), unit),
                            formatters.format_value_with_unit(sample_metric.get('region_median'), unit),
                            formatters.format_value_with_unit(sample_metric.get('region_q3'), unit),
                            formatters.format_value_with_unit(sample_metric['value'], unit)
                        ])

                sections.append({
                    "type": "table",
                    "content": {
                        "headers": cohort_headers,
                        "rows": cohort_rows,
                        "alignments": ["left", "right", "right", "right", "right"]
                    }
                })

                # RTT breakdown if requested
                if include_rtt_breakdown:
                    sections.append({
                        "type": "header",
                        "content": "Pathway Type Breakdown",
                        "level": 3
                    })

                    sections.append({
                        "type": "text",
                        "content": "_RTT pathways are split into different types: Part 1A (admitted patients treated), Part 1B (non-admitted patients treated), Part 2 (incomplete pathways - patients still waiting), and Part 2A (active monitoring pathways). This breakdown shows performance across these different pathway types._"
                    })

                    breakdown_rows = []
                    pathway_types_found = set()
                    seen_pathway_combos = set()  # Deduplicate by (pathway, metric_id)

                    for m in metrics_by_domain['rtt']:
                        rtt_part = m.get('rtt_part_type')
                        pathway_types_found.add(rtt_part)

                        if rtt_part and rtt_part != 'Overall':
                            # Deduplicate by (pathway, metric_id) combination
                            combo_key = (rtt_part, m.get('metric_id'))
                            if combo_key in seen_pathway_combos:
                                continue
                            seen_pathway_combos.add(combo_key)

                            breakdown_rows.append([
                                rtt_part,
                                m['metric_label'],
                                formatters.format_value_with_unit(m['value'], m['unit']),
                                formatters.format_percentile_rank(m['percentile_overall'])
                            ])

                    logger.info(f"RTT breakdown: Found pathway types: {pathway_types_found}, unique breakdown rows: {len(breakdown_rows)}")

                    if breakdown_rows:
                        sections.append({
                            "type": "table",
                            "content": {
                                "headers": ["Pathway", "Metric", "Value", "National %"],
                                "rows": breakdown_rows,
                                "alignments": ["left", "left", "right", "right"]
                            }
                        })
                    else:
                        # Show explanatory message if no pathway breakdown data available
                        sections.append({
                            "type": "text",
                            "content": "_No pathway breakdown data available. Only 'Overall' pathway metrics are present in the dataset._"
                        })

                sections.append({"type": "separator"})

            # Cancer Domain
            if 'cancer' in metrics_by_domain:
                logger.info(f"Processing cancer domain: {len(metrics_by_domain['cancer'])} metrics before filtering")

                sections.append({
                    "type": "header",
                    "content": "Cancer Waiting Times Performance",
                    "level": 2
                })

                # Add Cancer explanation
                sections.append({
                    "type": "text",
                    "content": "_NHS cancer waiting times standards track how quickly patients receive diagnosis and treatment. Key standards include: **28-day Faster Diagnosis Standard** (75% target - patients receive a definitive diagnosis or ruling out of cancer within 28 days), **31-day First Treatment** (96% target - from decision to treat to first treatment), and **62-day Urgent Referral** (85% target - from urgent GP referral to first treatment)._"
                })

                sections.append({
                    "type": "text",
                    "content": "**Numerator/Denominator**: Numerator shows patients meeting the standard, denominator shows total patients measured. The percentage is calculated as numerator ÷ denominator."
                })

                sections.append({
                    "type": "text",
                    "content": "_Note: National % and Trust Type % show percentile rankings for aggregated performance (all cancer types combined). These are calculated by aggregating each trust's numerators and denominators, then ranking trusts nationally. Individual trusts may have different case mixes, which can affect comparisons._"
                })

                sections.append({
                    "type": "text",
                    "content": "**Data quality filtering:** Route and cancer type breakdowns exclude cancer types with fewer than 20 patients to ensure statistical validity. The 'Overall Performance by Standard' section above includes all patients for official reporting."
                })

                sections.append({
                    "type": "header",
                    "content": "Overall Performance by Standard",
                    "level": 3
                })

                headers = [
                    "Standard", "Value", "Target", "Met", "National %", "Trust Type %",
                    "Numerator", "Denominator"
                ]
                rows = []

                # Use pre-computed trust-level aggregates (cancer_type IS NULL)
                # These aggregate rows are created in the database view and sum across all cancer types
                logger.info(f"Cancer: Total metrics before filtering: {len(metrics_by_domain['cancer'])}")

                overall_cancer_metrics = [
                    m for m in metrics_by_domain['cancer']
                    if m.get('cancer_type') is None and m.get('referral_route') == 'ALL ROUTES'
                ]

                logger.info(f"Cancer: Found {len(overall_cancer_metrics)} trust-level aggregate metrics (cancer_type IS NULL)")

                # Defensive deduplication by metric_id (should not be needed, but safeguards against bugs)
                seen_metric_ids = set()
                deduplicated_metrics = []
                duplicate_count = 0

                for m in overall_cancer_metrics:
                    metric_id = m.get('metric_id')
                    if metric_id not in seen_metric_ids:
                        seen_metric_ids.add(metric_id)
                        deduplicated_metrics.append(m)
                    else:
                        duplicate_count += 1
                        logger.warning(f"Cancer: Duplicate detected for metric_id={metric_id}, cancer_type={m.get('cancer_type')}, referral_route={m.get('referral_route')}")

                if duplicate_count > 0:
                    logger.warning(f"Cancer: Removed {duplicate_count} duplicate rows via deduplication")

                overall_cancer_metrics = deduplicated_metrics

                for m in overall_cancer_metrics:
                    rows.append([
                        m['metric_label'].replace('_', ' ').title(),
                        formatters.format_value_with_unit(m['value'], m['unit']),
                        formatters.format_value_with_unit(m['target_threshold'], m['unit']) if m.get('target_threshold') else '-',
                        formatters.format_target_status(m.get('target_met')),
                        formatters.format_percentile_rank(m.get('percentile_overall')),
                        formatters.format_percentile_rank(m.get('percentile_trust_type')),
                        int(m['numerator']) if m.get('numerator') else '-',
                        int(m['denominator']) if m.get('denominator') else '-'
                    ])

                logger.info(f"Cancer: Displaying {len(rows)} trust-level aggregate standards in main table")

                if len(rows) == 0:
                    logger.warning(f"Cancer: Zero trust-level aggregates found. Total cancer metrics: {len(metrics_by_domain['cancer'])}")

                sections.append({
                    "type": "table",
                    "content": {
                        "headers": headers,
                        "rows": rows,
                        "alignments": ["left", "right", "right", "center", "right", "right", "right", "right"]
                    }
                })

                # Cancer breakdown if requested
                if include_cancer_breakdown:
                    # By cancer type - show ALL ROUTES only to avoid duplicates
                    cancer_type_rows = []
                    seen_cancer_combos = set()  # Track (cancer_type, metric_id) to avoid duplicates

                    for m in metrics_by_domain['cancer']:
                        # Only show ALL ROUTES for cancer type breakdown
                        if m.get('cancer_type') and (m.get('referral_route') == 'ALL ROUTES' or not m.get('referral_route')):
                            combo_key = (m.get('cancer_type'), m.get('metric_id'))
                            if combo_key in seen_cancer_combos:
                                continue
                            seen_cancer_combos.add(combo_key)

                            cancer_type_rows.append([
                                m.get('cancer_type', '-'),
                                m['metric_label'].replace('_', ' ').title(),
                                formatters.format_value_with_unit(m['value'], m['unit']),
                                formatters.format_percentile_rank(m['percentile_overall']),
                                int(m['numerator']) if m.get('numerator') else '-',
                                int(m['denominator']) if m.get('denominator') else '-'
                            ])

                    if cancer_type_rows:
                        sections.append({
                            "type": "header",
                            "content": "Performance by Cancer Type (ALL ROUTES)",
                            "level": 3
                        })

                        sections.append({
                            "type": "text",
                            "content": "_This breakdown shows performance for each specific cancer type. 'ALL ROUTES' means all referral pathways combined (urgent suspected cancer, screening, consultant upgrades, etc.)._"
                        })

                        sections.append({
                            "type": "table",
                            "content": {
                                "headers": ["Cancer Type", "Standard", "Value", "National %", "Numerator", "Denominator"],
                                "rows": cancer_type_rows,
                                "alignments": ["left", "left", "right", "right", "right", "right"]
                            }
                        })

                    # By referral route - aggregate across cancer types for each specific route
                    # IMPORTANT: Filter by org_code to ensure we only aggregate THIS trust's data
                    route_aggregated = {}
                    for m in metrics_by_domain['cancer']:
                        # DEFENSIVE CHECK: Only process rows for the requested org_code
                        if m.get('org_code') != org_code:
                            logger.warning(f"Cancer: Skipping row with wrong org_code: {m.get('org_code')} (expected {org_code})")
                            continue

                        referral_route = m.get('referral_route')
                        # Skip ALL ROUTES (already shown in main table)
                        # Only show specific routes like USC, Screening
                        if referral_route and referral_route != 'ALL ROUTES':
                            metric_id = m.get('metric_id')
                            route_key = (referral_route, metric_id)

                            if route_key not in route_aggregated:
                                route_aggregated[route_key] = {
                                    'referral_route': referral_route,
                                    'metric_label': m['metric_label'],
                                    'unit': m['unit'],
                                    'numerator': 0,
                                    'denominator': 0,
                                    'percentile_overall': m.get('percentile_overall')
                                }

                            # Aggregate across cancer types
                            if m.get('numerator'):
                                route_aggregated[route_key]['numerator'] += m['numerator']
                            if m.get('denominator'):
                                route_aggregated[route_key]['denominator'] += m['denominator']

                    # Calculate aggregate values for each route
                    route_rows = []
                    for route_key, agg in route_aggregated.items():
                        if agg['denominator'] > 0:
                            agg['value'] = agg['numerator'] / agg['denominator']
                        else:
                            agg['value'] = None

                        route_rows.append([
                            agg['referral_route'],
                            agg['metric_label'].replace('_', ' ').title(),
                            formatters.format_value_with_unit(agg['value'], agg['unit']),
                            formatters.format_percentile_rank(agg['percentile_overall']),
                            int(agg['numerator']) if agg.get('numerator') else '-',
                            int(agg['denominator']) if agg.get('denominator') else '-'
                        ])

                    if route_rows:
                        sections.append({
                            "type": "header",
                            "content": "Performance by Referral Route (aggregated across cancer types)",
                            "level": 3
                        })

                        sections.append({
                            "type": "text",
                            "content": "_This shows performance for each referral pathway, aggregated across all cancer types. Routes include: 'URGENT SUSPECTED CANCER' (USC - 2-week wait referrals), 'BREAST SYMPTOMATIC, CANCER NOT SUSPECTED', 'Consultant Upgrade' (consultant-initiated pathways), and screening routes._"
                        })

                        sections.append({
                            "type": "table",
                            "content": {
                                "headers": ["Referral Route", "Standard", "Value", "National %", "Numerator", "Denominator"],
                                "rows": route_rows,
                                "alignments": ["left", "left", "right", "right", "right", "right"]
                            }
                        })

                sections.append({"type": "separator"})

            # Oversight Domain
            if 'oversight' in metrics_by_domain:
                logger.info(f"Processing oversight domain: {len(metrics_by_domain['oversight'])} metrics")

                sections.append({
                    "type": "header",
                    "content": "NHS Oversight Framework",
                    "level": 2
                })

                # Add Oversight explanation
                sections.append({
                    "type": "text",
                    "content": "_The NHS Oversight Framework assesses trusts across multiple domains including urgent & emergency care, elective care, primary care, mental health, finance, and workforce. Metrics report at different frequencies (quarterly, monthly, annually, rolling 12-month) shown in the 'Period' column._"
                })

                sections.append({
                    "type": "text",
                    "content": "**Regional Rank** shows the trust's position compared to other trusts in the same region (e.g., '8/20' means ranked 8th out of 20 regional trusts, where lower rank numbers indicate better performance)."
                })

                # Include Period column to show each metric's reporting period
                headers = ["Metric", "Value", "Period", "National %", "Trust Type %", "Regional Rank"]
                rows = []

                # Filter out duplicate score metrics
                # Oversight data has both raw metrics (OF0xxx) and normalized scores (OF1xxx, OF4xxx)
                # We want to show only the raw metrics to avoid duplicates
                seen_metric_names = set()
                filtered_metrics = []

                # Check if granular metrics exist (non-summary metrics)
                has_granular_metrics = any(
                    not m.get('metric_id', '').startswith(('OF1', 'OF4')) and
                    'domain score' not in m.get('metric_label', '').lower() and
                    'domain segment' not in m.get('metric_label', '').lower() and
                    m.get('metric_label') not in ['Adjusted segment', 'Unadjusted segment', 'Financial override',
                                                  'Oversight: average metric score', 'Average metric score']
                    for m in metrics_by_domain['oversight']
                )

                for m in metrics_by_domain['oversight']:
                    metric_id = m.get('metric_id', '')
                    metric_label = m.get('metric_label', '')

                    # Skip normalized score versions (OF1xxx, OF4xxx series)
                    # These are transformed versions of the raw metrics
                    if metric_id.startswith('OF1') or metric_id.startswith('OF4'):
                        continue

                    # Skip domain-level summary scores (already have detailed metrics)
                    if 'domain score' in metric_label.lower() or 'domain segment' in metric_label.lower():
                        continue

                    # Skip overall summary metrics ONLY if granular data is available
                    # If only summary metrics exist, we should show them rather than nothing
                    if has_granular_metrics and metric_label in ['Adjusted segment', 'Unadjusted segment', 'Financial override',
                                                                  'Oversight: average metric score', 'Average metric score']:
                        continue

                    # Deduplicate by metric label (in case same metric appears with different IDs)
                    if metric_label in seen_metric_names:
                        continue

                    seen_metric_names.add(metric_label)
                    filtered_metrics.append(m)

                logger.info(f"Oversight: Filtered from {len(metrics_by_domain['oversight'])} to {len(filtered_metrics)} unique metrics")

                for m in filtered_metrics:
                    # Format regional ranking as "X/Y"
                    regional_rank = f"{int(m['regional_rank'])}/{int(m['regional_total'])}" if m.get('regional_rank') and m.get('regional_total') else '-'

                    rows.append([
                        m['metric_label'],
                        formatters.format_value_with_unit(m['value'], m['unit']),
                        m.get('period', '-'),  # Show the reporting period for this metric
                        formatters.format_percentile_rank(m['percentile_overall']),
                        formatters.format_percentile_rank(m['percentile_trust_type']),
                        regional_rank
                    ])

                logger.info(f"Oversight: Displaying {len(rows)} metrics")

                if len(rows) == 0:
                    logger.warning(f"Oversight: Zero rows to display despite {len(metrics_by_domain['oversight'])} metrics in data")

                sections.append({
                    "type": "table",
                    "content": {
                        "headers": headers,
                        "rows": rows,
                        "alignments": ["left", "right", "center", "right", "right", "right"]
                    }
                })

                sections.append({"type": "separator"})

            # Build final markdown
            markdown_output = formatters.build_markdown_document(sections)

            logger.info(
                "Comprehensive trust performance retrieved successfully",
                org_code=org_code,
                metrics_count=len(metrics)
            )

            return markdown_output

        except ToolExecutionError:
            raise
        except Exception as e:
            logger.error(f"Failed to fetch comprehensive trust performance: {e}", exc_info=True)
            raise ToolExecutionError(
                "get_comprehensive_trust_performance",
                f"Failed to retrieve performance data: {str(e)}"
            )
