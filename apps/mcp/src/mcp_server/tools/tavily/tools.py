"""Tavily tools mirroring the official Tavily MCP server definitions and behaviour."""

from typing import Any, Dict, List, Optional

from ..base import CustomTool, ToolParameter
from ...utils.logging import get_logger
from ...utils.exceptions import ToolExecutionError
from ...utils.excel_processor import is_excel_url, process_excel_url
from .client import TavilyClient
from ..youtube_service import youtube_service
try:
    from docling.document_converter import DocumentConverter
    from docling.datamodel.base_models import InputFormat
    from docling.document_converter import PdfFormatOption
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    _DOCLING_AVAILABLE = True
except Exception:
    DocumentConverter = None  # type: ignore
    InputFormat = None  # type: ignore
    PdfFormatOption = None  # type: ignore
    PdfPipelineOptions = None  # type: ignore
    _DOCLING_AVAILABLE = False


logger = get_logger(__name__)


def _ensure_array(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _validate_search_params(args: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and clean search parameters for Tavily API.

    Auto-fixes conflicting parameters:
    - topic='news' or 'finance': drops 'country' (not supported)
    - topic='general': drops 'days' (not supported)
    - Date conflicts: prioritizes start_date/end_date > time_range > days

    Returns cleaned dict with None/empty values filtered out.
    """
    topic = args.get("topic", "general")

    # Build cleaned payload - filter None, empty strings, empty lists, and False booleans
    cleaned = {}
    for key, value in args.items():
        # Skip None, empty strings, empty lists
        if value is None or value == "" or value == []:
            continue
        # Skip False booleans (Tavily API prefers omission over explicit False)
        if value is False:
            continue
        cleaned[key] = value

    # Auto-fix conflicting parameters based on topic
    # 'days' only works with topic='news'
    if topic != "news" and "days" in cleaned:
        del cleaned["days"]

    # 'country' only works with topic='general'
    if topic != "general" and "country" in cleaned:
        del cleaned["country"]

    # Handle conflicting date/time parameters
    # Priority: start_date/end_date > time_range > days
    has_start_date = "start_date" in cleaned
    has_end_date = "end_date" in cleaned
    has_date_range = has_start_date or has_end_date
    has_time_range = "time_range" in cleaned
    has_days = "days" in cleaned

    if has_date_range:
        # If explicit date range provided, drop time_range and days
        if has_time_range:
            del cleaned["time_range"]
        if has_days:
            del cleaned["days"]

        # Tavily doesn't allow start_date == end_date
        # If they're the same, remove end_date (search from start_date onwards)
        if has_start_date and has_end_date:
            if cleaned["start_date"] == cleaned["end_date"]:
                del cleaned["end_date"]

    elif has_time_range and has_days:
        # If both time_range and days, prefer time_range (more explicit)
        del cleaned["days"]

    return cleaned


def _format_results(response: Dict[str, Any]) -> str:
    output: List[str] = []

    answer = response.get("answer")
    if answer:
        output.append(f"Answer: {answer}")

    output.append("Detailed Results:")
    for result in response.get("results", []) or []:
        output.append(f"\nTitle: {result.get('title')}")
        output.append(f"URL: {result.get('url')}")

        # Add metadata information if available
        metadata = result.get("metadata", {})
        if metadata:
            if metadata.get("source_type") == "youtube":
                output.append(f"Type: YouTube Video")
                output.append(f"Video ID: {metadata.get('video_id', 'N/A')}")
                if metadata.get("duration_seconds"):
                    duration = metadata.get("duration_seconds")
                    minutes = duration // 60
                    seconds = duration % 60
                    output.append(f"Duration: {minutes}m {seconds}s")
                if metadata.get("total_word_count"):
                    output.append(f"Total Words: {metadata.get('total_word_count')}")
                if metadata.get("returned_word_count"):
                    output.append(f"Returned Words: {metadata.get('returned_word_count')}")
                if metadata.get("has_more_content"):
                    output.append(f"Has More Content: Yes (use offset_words={metadata.get('offset_words', 0) + metadata.get('returned_word_count', 0)} to continue)")
            elif result.get("content_truncated"):
                output.append(f"Content Truncated: Yes")
                if result.get("total_words"):
                    output.append(f"Total Words: {result.get('total_words')}")
                if result.get("returned_words"):
                    output.append(f"Returned Words: {result.get('returned_words')}")

        output.append(f"Content: {result.get('content')}")
        raw_content = result.get("raw_content")
        if raw_content:
            output.append(f"Raw Content: {raw_content}")
        favicon = result.get("favicon")
        if favicon:
            output.append(f"Favicon: {favicon}")

    images = response.get("images") or []
    if images:
        output.append("\nImages:")
        for idx, image in enumerate(images, start=1):
            if isinstance(image, str):
                output.append(f"\n[{idx}] URL: {image}")
            else:
                url = image.get("url")
                desc = image.get("description")
                output.append(f"\n[{idx}] URL: {url}")
                if desc:
                    output.append(f"   Description: {desc}")

    return "\n".join(output)


def _format_crawl_results(response: Dict[str, Any]) -> str:
    output: List[str] = []
    output.append("Crawl Results:")
    output.append(f"Base URL: {response.get('base_url')}")

    output.append("\nCrawled Pages:")
    for idx, page in enumerate(response.get("results", []) or [], start=1):
        output.append(f"\n[{idx}] URL: {page.get('url')}")
        raw_content = page.get("raw_content")
        if raw_content:
            preview = raw_content[:200] + ("..." if len(raw_content) > 200 else "")
            output.append(f"Content: {preview}")
        favicon = page.get("favicon")
        if favicon:
            output.append(f"Favicon: {favicon}")

    return "\n".join(output)


def _format_map_results(response: Dict[str, Any]) -> str:
    output: List[str] = []
    output.append("Site Map Results:")
    output.append(f"Base URL: {response.get('base_url')}")

    output.append("\nMapped Pages:")
    for idx, page in enumerate(response.get("results", []) or [], start=1):
        output.append(f"\n[{idx}] URL: {page}")

    return "\n".join(output)


class _TavilyBase(CustomTool):
    toolkit_name = "tavily"
    toolkit_display_name = "Tavily"

    def __init__(self) -> None:
        super().__init__()
        self.client = TavilyClient()


class TavilySearchTool(_TavilyBase):
    @property
    def name(self) -> str:
        return "tavily-search"

    @property
    def description(self) -> str:
        return (
            "A powerful web search tool using Tavily's AI search engine. "
            "Supports three topics: 'general' (default), 'news', and 'finance'. "
            "IMPORTANT parameter constraints by topic: "
            "topic='general' can use 'country' for geo-targeting but cannot use 'days'. "
            "topic='news' can use 'days' for recency filtering but cannot use 'country'. "
            "topic='finance' is for financial data and cannot use 'country' or 'days'. "
            "All topics support 'time_range' and 'start_date'/'end_date' for date filtering."
        )

    def get_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(name="query", type="string", description="Search query", required=True),
            ToolParameter(name="search_depth", type="string", description="The depth of the search. It can be 'basic' or 'advanced'", required=False, default="basic", enum=["basic","advanced"]),
            ToolParameter(name="topic", type="string", description="Search category: 'general' (default, supports country), 'news' (supports days), or 'finance'. Each has different parameter constraints.", required=False, default="general", enum=["general","news","finance"]),
            ToolParameter(name="days", type="number", description="Days back to search. ONLY valid when topic='news'. Will error if used with other topics. Use time_range for general/finance topics.", required=False),
            ToolParameter(name="time_range", type="string", description="The time range back from the current date to include in the search results. This feature is available for both 'general' and 'news' search topics", required=False, enum=["day","week","month","year","d","w","m","y"]),
            ToolParameter(name="start_date", type="string", description="Filter results after this date (YYYY-MM-DD format). Works with all topics.", required=False),
            ToolParameter(name="end_date", type="string", description="Filter results before this date (YYYY-MM-DD format). Works with all topics.", required=False),
            ToolParameter(name="max_results", type="number", description="The maximum number of search results to return", required=False, default=10),
            ToolParameter(name="include_images", type="boolean", description="Include a list of query-related images in the response", required=False, default=False),
            ToolParameter(name="include_image_descriptions", type="boolean", description="Include a list of query-related images and their descriptions in the response", required=False, default=False),
            ToolParameter(name="include_raw_content", type="boolean", description="Include the cleaned and parsed HTML content of each search result", required=False, default=False),
            ToolParameter(name="include_domains", type="array", description="A list of domains to specifically include in the search results, if the user asks to search on specific sites set this to the domain of the site", required=False, default=[], items={"type":"string"}),
            ToolParameter(name="exclude_domains", type="array", description="List of domains to specifically exclude, if the user asks to exclude a domain set this to the domain of the site", required=False, default=[], items={"type":"string"}),
            ToolParameter(name="country", type="string", description="Boost results from a specific country. ONLY valid when topic='general'. Will error if used with news/finance topics. Country names must be lowercase with spaces.", required=False, enum=[
                'afghanistan','albania','algeria','andorra','angola','argentina','armenia','australia','austria','azerbaijan','bahamas','bahrain','bangladesh','barbados','belarus','belgium','belize','benin','bhutan','bolivia','bosnia and herzegovina','botswana','brazil','brunei','bulgaria','burkina faso','burundi','cambodia','cameroon','canada','cape verde','central african republic','chad','chile','china','colombia','comoros','congo','costa rica','croatia','cuba','cyprus','czech republic','denmark','djibouti','dominican republic','ecuador','egypt','el salvador','equatorial guinea','eritrea','estonia','ethiopia','fiji','finland','france','gabon','gambia','georgia','germany','ghana','greece','guatemala','guinea','haiti','honduras','hungary','iceland','india','indonesia','iran','iraq','ireland','israel','italy','jamaica','japan','jordan','kazakhstan','kenya','kuwait','kyrgyzstan','latvia','lebanon','lesotho','liberia','libya','liechtenstein','lithuania','luxembourg','madagascar','malawi','malaysia','maldives','mali','malta','mauritania','mauritius','mexico','moldova','monaco','mongolia','montenegro','morocco','mozambique','myanmar','namibia','nepal','netherlands','new zealand','nicaragua','niger','nigeria','north korea','north macedonia','norway','oman','pakistan','panama','papua new guinea','paraguay','peru','philippines','poland','portugal','qatar','romania','russia','rwanda','saudi arabia','senegal','serbia','singapore','slovakia','slovenia','somalia','south africa','south korea','south sudan','spain','sri lanka','sudan','sweden','switzerland','syria','taiwan','tajikistan','tanzania','thailand','togo','trinidad and tobago','tunisia','turkey','turkmenistan','uganda','ukraine','united arab emirates','united kingdom','united states','uruguay','uzbekistan','venezuela','vietnam','yemen','zambia','zimbabwe'
            ]),
            ToolParameter(name="include_favicon", type="boolean", description="Whether to include the favicon URL for each result", required=False, default=False),
        ]

    async def _execute_impl(self, user_id: str, **kwargs: Any) -> str:
        try:
            args = dict(kwargs)
            args["include_domains"] = _ensure_array(args.get("include_domains"))
            args["exclude_domains"] = _ensure_array(args.get("exclude_domains"))

            # Validate parameter combinations and clean payload
            validated_args = _validate_search_params(args)

            response = await self.client.search({
                "query": validated_args.get("query"),
                "search_depth": validated_args.get("search_depth"),
                "topic": validated_args.get("topic"),
                "days": validated_args.get("days"),
                "time_range": validated_args.get("time_range"),
                "max_results": validated_args.get("max_results"),
                "include_images": validated_args.get("include_images"),
                "include_image_descriptions": validated_args.get("include_image_descriptions"),
                "include_raw_content": validated_args.get("include_raw_content"),
                "include_domains": validated_args.get("include_domains"),
                "exclude_domains": validated_args.get("exclude_domains"),
                "country": validated_args.get("country"),
                "include_favicon": validated_args.get("include_favicon"),
                "start_date": validated_args.get("start_date"),
                "end_date": validated_args.get("end_date"),
            })
            return _format_results(response)
        except Exception as e:
            if isinstance(e, ToolExecutionError):
                raise
            raise ToolExecutionError("tavily-search", str(e))


class TavilyExtractTool(_TavilyBase):
    @property
    def name(self) -> str:
        return "tavily-extract"

    @property
    def description(self) -> str:
        return (
            "A powerful content extraction tool that retrieves and processes raw content from "
            "specified URLs including YouTube videos (extracts transcripts), web pages, and documents. "
            "Ideal for data collection, content analysis, and research tasks. Supports content length "
            "controls for managing large documents."
        )

    def get_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(name="urls", type="array", description="List of URLs to extract content from (including YouTube videos)", required=True, items={"type":"string"}),
            ToolParameter(name="extract_depth", type="string", description="Depth of extraction - 'basic' or 'advanced', if usrls are linkedin use 'advanced' or if explicitly told to use advanced", required=False, default="basic", enum=["basic","advanced"]),
            ToolParameter(name="include_images", type="boolean", description="Include a list of images extracted from the urls in the response", required=False, default=False),
            ToolParameter(name="format", type="string", description="The format of the extracted web page content. markdown returns content in markdown format. text returns plain text and may increase latency.", required=False, default="markdown", enum=["markdown","text"]),
            ToolParameter(name="include_favicon", type="boolean", description="Whether to include the favicon URL for each result", required=False, default=False),
            ToolParameter(name="max_words", type="number", description="Maximum number of words to return per URL (default: 5000). Use 0 for unlimited. For long content, use offset_words to get subsequent sections.", required=False, default=5000),
            ToolParameter(name="offset_words", type="number", description="Number of words to skip from beginning (for pagination of long content). Default: 0", required=False, default=0),
        ]

    async def _execute_impl(self, user_id: str, **kwargs: Any) -> str:
        try:
            args = dict(kwargs)
            args["urls"] = _ensure_array(args.get("urls"))
            max_words = args.get("max_words", 5000)
            offset_words = args.get("offset_words", 0)

            # Convert max_words 0 to None for unlimited
            if max_words == 0:
                max_words = None

            # Separate YouTube URLs from other URLs
            youtube_urls = []
            regular_urls = []
            for url in args.get("urls", []):
                if youtube_service.is_youtube_url(url):
                    youtube_urls.append(url)
                else:
                    regular_urls.append(url)

            # Process regular URLs with Tavily
            response = None
            if regular_urls:
                response = await self.client.extract({
                    "urls": regular_urls,
                    "extract_depth": args.get("extract_depth"),
                    "include_images": args.get("include_images"),
                    "format": args.get("format"),
                    "include_favicon": args.get("include_favicon"),
                })

            # Process YouTube URLs separately
            youtube_results = []
            for youtube_url in youtube_urls:
                try:
                    transcript = await youtube_service.extract_transcript(
                        youtube_url,
                        max_words=max_words,
                        offset_words=offset_words
                    )
                    youtube_result = {
                        "url": youtube_url,
                        "title": f"YouTube Video {transcript.metadata.get('video_id', '')}",
                        "content": transcript.content,
                        "raw_content": transcript.content,
                        "metadata": transcript.metadata
                    }
                    youtube_results.append(youtube_result)
                except Exception as e:
                    logger.warning(f"Failed to extract YouTube transcript for {youtube_url}: {e}")
                    # Add failed YouTube URL to the results with error message
                    youtube_results.append({
                        "url": youtube_url,
                        "title": "YouTube Video (Failed)",
                        "content": f"Failed to extract transcript: {str(e)}",
                        "raw_content": "",
                        "metadata": {"error": str(e)}
                    })

            # Merge results
            if response is None:
                response = {"results": youtube_results}
            else:
                if "results" not in response:
                    response["results"] = []
                response["results"].extend(youtube_results)

            # Check each requested URL; if Tavily has no meaningful content for it, fallback to Docling when available
            results = response.get("results") if isinstance(response, dict) else None
            urls: List[str] = list(args.get("urls") or [])
            def _is_meaningful(rec: Dict[str, Any]) -> bool:
                if not isinstance(rec, dict):
                    return False
                a = (rec.get("raw_content") or "").strip()
                b = (rec.get("content") or "").strip()
                return bool(a or b)

            fallback_sections: List[str] = []
            for url in urls:
                has_for_url = False
                if results:
                    for r in results:
                        if isinstance(r, dict) and r.get("url") == url and _is_meaningful(r):
                            has_for_url = True
                            break
                if not has_for_url:
                    # Try Excel processing first for Excel files
                    if is_excel_url(url):
                        try:
                            content = await process_excel_url(url)
                            if content.strip():
                                fallback_sections.append(f"Excel Extracted Content for {url}:\n\n" + content)
                                continue
                        except Exception as excel_err:
                            logger.warning(f"Excel processing failed for {url}: {excel_err}")

                    # Fall back to Docling for non-Excel files or if Excel processing failed
                    if _DOCLING_AVAILABLE:
                        try:
                            pipeline_options = PdfPipelineOptions(
                                do_ocr=True,
                                do_table_structure=True,
                                do_picture_analysis=False,
                            )
                            converter = DocumentConverter(
                                format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)}
                            )
                            conversion_result = converter.convert(url)
                            if hasattr(conversion_result, "document") and conversion_result.document:
                                content = conversion_result.document.export_to_markdown()
                                if content.strip():
                                    fallback_sections.append(f"Fallback (Docling) Extracted Content for {url}:\n\n" + content)
                        except Exception as _docling_err:
                            logger.warning(f"Docling fallback failed for {url}: {_docling_err}")

            # Apply content length controls to all results
            if max_words and results:
                for result in results:
                    if isinstance(result, dict) and "content" in result:
                        content = result.get("content", "")
                        words = content.split()
                        if offset_words > 0 or (max_words and len(words) > max_words):
                            trimmed_words = words[offset_words:offset_words + max_words] if max_words else words[offset_words:]
                            result["content"] = " ".join(trimmed_words)
                            result["content_truncated"] = True
                            result["total_words"] = len(words)
                            result["returned_words"] = len(trimmed_words)
                    if isinstance(result, dict) and "raw_content" in result:
                        raw_content = result.get("raw_content", "")
                        words = raw_content.split()
                        if offset_words > 0 or (max_words and len(words) > max_words):
                            trimmed_words = words[offset_words:offset_words + max_words] if max_words else words[offset_words:]
                            result["raw_content"] = " ".join(trimmed_words)

            base_text = _format_results(response)
            if fallback_sections:
                # Apply word limits to fallback sections
                if max_words:
                    limited_sections = []
                    for section in fallback_sections:
                        words = section.split()
                        if offset_words > 0 or len(words) > max_words:
                            trimmed_words = words[offset_words:offset_words + max_words] if max_words else words[offset_words:]
                            section_text = " ".join(trimmed_words)
                            section_text += f"\n\n[Content truncated. Total words: {len(words)}, Returned: {len(trimmed_words)}]"
                            limited_sections.append(section_text)
                        else:
                            limited_sections.append(section)
                    return base_text + "\n\n" + "\n\n".join(limited_sections)
                else:
                    return base_text + "\n\n" + "\n\n".join(fallback_sections)
            return base_text
        except Exception as e:
            if isinstance(e, ToolExecutionError):
                raise
            raise ToolExecutionError("tavily-extract", str(e))


class TavilyCrawlTool(_TavilyBase):
    @property
    def name(self) -> str:
        return "tavily-crawl"

    @property
    def description(self) -> str:
        return (
            "A powerful web crawler that initiates a structured web crawl starting from a specified "
            "base URL. The crawler expands from that point like a tree, following internal links "
            "across pages. You can control how deep and wide it goes, and guide it to focus on "
            "specific sections of the site."
        )

    def get_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(name="url", type="string", description="The root URL to begin the crawl", required=True),
            ToolParameter(name="max_depth", type="integer", description="Max depth of the crawl. Defines how far from the base URL the crawler can explore.", required=False, default=1),
            ToolParameter(name="max_breadth", type="integer", description="Max number of links to follow per level of the tree (i.e., per page)", required=False, default=20),
            ToolParameter(name="limit", type="integer", description="Total number of links the crawler will process before stopping", required=False, default=50),
            ToolParameter(name="instructions", type="string", description="Natural language instructions for the crawler", required=False),
            ToolParameter(name="select_paths", type="array", description="Regex patterns to select only URLs with specific path patterns (e.g., /docs/.*, /api/v1.*)", required=False, default=[], items={"type":"string"}),
            ToolParameter(name="select_domains", type="array", description="Regex patterns to select crawling to specific domains or subdomains (e.g., ^docs\\.example\\.com$)", required=False, default=[], items={"type":"string"}),
            ToolParameter(name="allow_external", type="boolean", description="Whether to allow following links that go to external domains", required=False, default=False),
            ToolParameter(name="categories", type="array", description="Filter URLs using predefined categories like documentation, blog, api, etc", required=False, default=[], items={"type":"string", "enum": ["Careers","Blog","Documentation","About","Pricing","Community","Developers","Contact","Media"]}),
            ToolParameter(name="extract_depth", type="string", description="Advanced extraction retrieves more data, including tables and embedded content, with higher success but may increase latency", required=False, default="basic", enum=["basic","advanced"]),
            ToolParameter(name="format", type="string", description="The format of the extracted web page content. markdown returns content in markdown format. text returns plain text and may increase latency.", required=False, default="markdown", enum=["markdown","text"]),
            ToolParameter(name="include_favicon", type="boolean", description="Whether to include the favicon URL for each result", required=False, default=False),
        ]

    async def _execute_impl(self, user_id: str, **kwargs: Any) -> str:
        try:
            args = dict(kwargs)
            args["select_paths"] = _ensure_array(args.get("select_paths"))
            args["select_domains"] = _ensure_array(args.get("select_domains"))
            args["categories"] = _ensure_array(args.get("categories"))
            response = await self.client.crawl({
                "url": args.get("url"),
                "max_depth": args.get("max_depth"),
                "max_breadth": args.get("max_breadth"),
                "limit": args.get("limit"),
                "instructions": args.get("instructions"),
                "select_paths": args.get("select_paths"),
                "select_domains": args.get("select_domains"),
                "allow_external": args.get("allow_external"),
                "categories": args.get("categories"),
                "extract_depth": args.get("extract_depth"),
                "format": args.get("format"),
                "include_favicon": args.get("include_favicon"),
            })
            return _format_crawl_results(response)
        except Exception as e:
            if isinstance(e, ToolExecutionError):
                raise
            raise ToolExecutionError("tavily-crawl", str(e))


class TavilyMapTool(_TavilyBase):
    @property
    def name(self) -> str:
        return "tavily-map"

    @property
    def description(self) -> str:
        return (
            "A powerful web mapping tool that creates a structured map of website URLs, allowing you "
            "to discover and analyze site structure, content organization, and navigation paths. "
            "Perfect for site audits, content discovery, and understanding website architecture."
        )

    def get_parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(name="url", type="string", description="The root URL to begin the mapping", required=True),
            ToolParameter(name="max_depth", type="integer", description="Max depth of the mapping. Defines how far from the base URL the crawler can explore", required=False, default=1),
            ToolParameter(name="max_breadth", type="integer", description="Max number of links to follow per level of the tree (i.e., per page)", required=False, default=20),
            ToolParameter(name="limit", type="integer", description="Total number of links the crawler will process before stopping", required=False, default=50),
            ToolParameter(name="instructions", type="string", description="Natural language instructions for the crawler", required=False),
            ToolParameter(name="select_paths", type="array", description="Regex patterns to select only URLs with specific path patterns (e.g., /docs/.*, /api/v1.*)", required=False, default=[], items={"type":"string"}),
            ToolParameter(name="select_domains", type="array", description="Regex patterns to select crawling to specific domains or subdomains (e.g., ^docs\\.example\\.com$)", required=False, default=[], items={"type":"string"}),
            ToolParameter(name="allow_external", type="boolean", description="Whether to allow following links that go to external domains", required=False, default=False),
            ToolParameter(name="categories", type="array", description="Filter URLs using predefined categories like documentation, blog, api, etc", required=False, default=[], items={"type":"string", "enum": ["Careers","Blog","Documentation","About","Pricing","Community","Developers","Contact","Media"]}),
        ]

    async def _execute_impl(self, user_id: str, **kwargs: Any) -> str:
        try:
            args = dict(kwargs)
            args["select_paths"] = _ensure_array(args.get("select_paths"))
            args["select_domains"] = _ensure_array(args.get("select_domains"))
            args["categories"] = _ensure_array(args.get("categories"))
            response = await self.client.map({
                "url": args.get("url"),
                "max_depth": args.get("max_depth"),
                "max_breadth": args.get("max_breadth"),
                "limit": args.get("limit"),
                "instructions": args.get("instructions"),
                "select_paths": args.get("select_paths"),
                "select_domains": args.get("select_domains"),
                "allow_external": args.get("allow_external"),
                "categories": args.get("categories"),
            })
            return _format_map_results(response)
        except Exception as e:
            if isinstance(e, ToolExecutionError):
                raise
            raise ToolExecutionError("tavily-map", str(e))


