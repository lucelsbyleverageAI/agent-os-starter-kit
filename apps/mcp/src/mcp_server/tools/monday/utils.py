"""Utility functions for formatting Monday.com data."""

import json
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from ...utils.logging import get_logger
from .linked_item_config import should_include_column_for_board, get_board_config

logger = get_logger(__name__)


def truncate_text(text: str, max_chars: int) -> str:
    """Truncate text to a character limit."""
    if not text or len(text) <= max_chars:
        return text
    return text[:max_chars - 3] + "..."


def clean_html_content(html_content: str) -> str:
    """Clean HTML and convert to markdown-friendly text."""
    if not html_content:
        return ""
    
    cleaned = html_content
    
    # Convert user mentions to @username format
    cleaned = re.sub(r'<a[^>]*data-mention-type="User"[^>]*>@([^<]+)</a>', r'@\1', cleaned)
    
    # Convert basic HTML formatting
    cleaned = re.sub(r'<strong><u>(.*?)</u></strong>', r'**\1**', cleaned)  # Bold underline
    cleaned = re.sub(r'<strong>(.*?)</strong>', r'**\1**', cleaned)  # Bold
    cleaned = re.sub(r'<u>(.*?)</u>', r'\1', cleaned)  # Remove underline tags
    cleaned = re.sub(r'<em>(.*?)</em>', r'*\1*', cleaned)  # Italic
    
    # Convert lists
    cleaned = re.sub(r'<ul>', '', cleaned)
    cleaned = re.sub(r'</ul>', '', cleaned)
    cleaned = re.sub(r'<ol>', '', cleaned)
    cleaned = re.sub(r'</ol>', '', cleaned)
    cleaned = re.sub(r'<li>(.*?)</li>', r'• \1', cleaned)
    
    # Convert paragraphs to line breaks
    cleaned = re.sub(r'<p>', '', cleaned)
    cleaned = re.sub(r'</p>', '\n', cleaned)
    
    # Convert line breaks
    cleaned = re.sub(r'<br\s*/?>', '\n', cleaned)
    
    # Remove any remaining HTML tags
    cleaned = re.sub(r'<[^>]*>', '', cleaned)
    
    # Clean up extra whitespace and line breaks
    cleaned = re.sub(r'\n\s*\n\s*\n', '\n\n', cleaned)  # Multiple line breaks to double
    cleaned = cleaned.strip()
    cleaned = re.sub(r'\uFEFF', '', cleaned)  # Remove zero-width no-break space
    
    return cleaned


def extract_public_file_urls(assets: List[Dict[str, Any]]) -> List[str]:
    """Extract public URLs from assets.

    DEPRECATED: This function is no longer used. File URLs are now displayed
    inline with file columns in format_column_value().
    """
    if not assets:
        return []
    
    urls = []
    for asset in assets:
        # Prefer public_url if available, otherwise use url
        url = asset.get("public_url") or asset.get("url")
        if url:
            urls.append(url)
    
    return urls


def format_date(date_string: str) -> str:
    """Format date string to a readable format."""
    if not date_string:
        return ""
    
    try:
        # Parse the date (assuming ISO format)
        date_obj = datetime.fromisoformat(date_string.replace('Z', '+00:00'))
        return date_obj.strftime('%d/%m/%Y %H:%M')
    except Exception:
        # Return as-is if parsing fails
        return date_string


def get_all_status_values(column_values: List[Dict[str, Any]]) -> List[str]:
    """Get all status column values from a list of column values."""
    if not column_values:
        return []
    
    status_values = []
    for col in column_values:
        if col.get("type") == "status" and col.get("text"):
            title = col.get("column", {}).get("title", "Status")
            text = col.get("text")
            status_values.append(f"{title}: {text}")
    
    return status_values


def get_item_due_date(column_values: List[Dict[str, Any]]) -> Optional[str]:
    """Get due date from column values."""
    if not column_values:
        return None
    
    for col in column_values:
        if col.get("type") == "date":
            title = col.get("column", {}).get("title", "").lower()
            if "due" in title or "deadline" in title:
                return col.get("text")
    
    return None


def format_linked_item_details(item: Dict[str, Any], board_id: str, max_chars: int = 200) -> List[str]:
    """
    Format additional column details for a linked item based on board configuration.
    Returns a list of formatted strings for the configured columns.
    """
    details = []
    item_column_values = item.get("column_values", [])
    
    if not item_column_values:
        return details
    
    # Get board configuration
    board_config = get_board_config(board_id)
    
    for col in item_column_values:
        col_id = col.get("id", "")
        col_type = col.get("type", "")
        text = col.get("text", "")
        value = col.get("value", "")
        column_info = col.get("column", {})
        title = column_info.get("title", "Unknown Column")
        
        # Skip empty values
        if not text and not value:
            continue
        
        # Check if this column should be included for this board
        if should_include_column_for_board(board_id, col_id, col_type):
            # Format the column value
            if col_type == "long_text":
                if text and text.strip():
                    # Truncate long text for linked items
                    truncated = truncate_text(text, max_chars)
                    details.append(f"{title}: {truncated}")
            elif col_type == "status":
                details.append(f"{title}: 🏷️ {text}")
            elif col_type == "dropdown":
                details.append(f"{title}: 📋 {text}")
            elif col_type == "date":
                details.append(f"{title}: 📅 {text}")
            elif col_type == "people":
                details.append(f"{title}: 👤 {text}")
            elif col_type == "numbers":
                details.append(f"{title}: {text}")
            elif col_type in ["text", "email", "phone", "link"]:
                details.append(f"{title}: {text}")
            elif col_type == "checkbox":
                if value:
                    try:
                        parsed = json.loads(value)
                        is_checked = parsed.get("checked", False)
                        details.append(f"{title}: {'✅' if is_checked else '⬜'}")
                    except (json.JSONDecodeError, TypeError):
                        details.append(f"{title}: ⬜")
                else:
                    details.append(f"{title}: ⬜")
            elif col_type == "rating":
                details.append(f"{title}: ⭐ {text}")
            elif col_type == "formula":
                details.append(f"{title}: 🧮 {text}")
            elif text:  # Default for other types
                details.append(f"{title}: {text}")
    
    return details


def format_column_value(column: Dict[str, Any], max_linked_items: int = 20, assets: Optional[List[Dict[str, Any]]] = None, item_id: Optional[str] = None) -> Optional[str]:
    """Format a single column value based on its type."""
    col_type = column.get("type")
    text = column.get("text")
    value = column.get("value")
    column_info = column.get("column", {})
    title = column_info.get("title", "Unknown Column")
    
    # Skip empty or null values for most types
    if not text and not value and col_type != "board_relation":
        return None
    
    try:
        if col_type == "text" or col_type == "email" or col_type == "phone" or col_type == "link":
            return f"**{title}:** {text}" if text else None
        
        elif col_type == "long_text":
            if text and text.strip():
                max_length = 5000
                truncated = text[:max_length] + "..." if len(text) > max_length else text
                indented = "\n".join(f"> {line}" for line in truncated.split("\n"))
                return f"**{title}:**\n{indented}"
            return None
        
        elif col_type == "numbers":
            return f"**{title}:** {text}" if text else None
        
        elif col_type == "date":
            return f"**{title}:** 📅 {text}" if text else None
        
        elif col_type == "status":
            return f"**{title}:** 🏷️ {text}" if text else None
        
        elif col_type == "dropdown":
            return f"**{title}:** 📋 {text}" if text else None
        
        elif col_type == "people":
            return f"**{title}:** 👤 {text}" if text else None
        
        elif col_type == "checkbox":
            if value:
                try:
                    parsed = json.loads(value)
                    is_checked = parsed.get("checked", False)
                    return f"**{title}:** {'✅' if is_checked else '⬜'}"
                except (json.JSONDecodeError, TypeError):
                    return f"**{title}:** ⬜"
            return f"**{title}:** ⬜"
        
        elif col_type == "board_relation":
            linked_items = column.get("linked_items", [])
            if linked_items:
                links = []
                # Limit the number of linked items displayed
                items_to_process = linked_items[:max_linked_items]
                
                for item in items_to_process:
                    item_name = item.get("name", "Unknown Item")
                    item_id = item.get("id", "")
                    board_info = item.get("board", {})
                    board_name = board_info.get("name", "Unknown Board")
                    board_id = board_info.get("id", "")
                    
                    # Get status indicators for linked item (legacy behaviour)
                    item_column_values = item.get("column_values", [])
                    all_statuses = get_all_status_values(item_column_values)
                    due_date = get_item_due_date(item_column_values)
                    
                    status_indicators = all_statuses.copy()
                    if due_date:
                        status_indicators.append(f"Due: {due_date}")
                    
                    # Get additional column details based on board configuration
                    additional_details = format_linked_item_details(item, board_id)
                    
                    # Combine status indicators with additional details
                    all_indicators = status_indicators + additional_details
                    
                    status_text = f" ({' | '.join(all_indicators)})" if all_indicators else ""
                    links.append(f"• [{item_name}](board:{board_name}) (ID: {item_id}){status_text}")
                
                # Add a note if there are more items than displayed
                if len(linked_items) > max_linked_items:
                    links.append(f"• ... and {len(linked_items) - max_linked_items} more linked items")
                
                return f"**{title}:**\n" + "\n".join(links)
            return None
        
        elif col_type == "formula":
            return f"**{title}:** 🧮 {text}" if text else None
        
        elif col_type == "rating":
            return f"**{title}:** ⭐ {text}" if text else None
        
        elif col_type == "timeline":
            if value:
                try:
                    timeline_data = json.loads(value)
                    from_date = timeline_data.get("from")
                    to_date = timeline_data.get("to")
                    
                    if from_date and to_date:
                        from_formatted = datetime.fromisoformat(from_date.replace('Z', '+00:00')).strftime('%d/%m/%Y')
                        to_formatted = datetime.fromisoformat(to_date.replace('Z', '+00:00')).strftime('%d/%m/%Y')
                        return f"**{title}:** 📊 {from_formatted} → {to_formatted}"
                except (json.JSONDecodeError, ValueError):
                    pass
            return f"**{title}:** 📊 {text}" if text else None
        
        elif col_type in ["file", "assets"]:
            # Format file columns with filename and download URLs
            if not text:
                return None

            # The text field contains comma-separated private URLs, not filenames
            private_urls = [url.strip() for url in text.split(",")]

            # Match URLs with assets to get filenames and public URLs
            formatted_files = []
            if assets:
                for private_url in private_urls:
                    # Find matching asset by private URL
                    matching_asset = None
                    for asset in assets:
                        if asset.get("url") == private_url:
                            matching_asset = asset
                            break

                    if matching_asset:
                        filename = matching_asset.get("name", "Unknown File")
                        public_url = matching_asset.get("public_url") or matching_asset.get("url", "")
                        file_entry = f"  • Filename: {filename}\n    Download URL: {public_url}"
                        # Add download tool instruction if item_id is available
                        if item_id:
                            file_entry += f"\n    💡 To download: Use 'download_monday_file' tool with item_id='{item_id}' and filename='{filename}'"
                        formatted_files.append(file_entry)
                    else:
                        # Asset not found, show URL as fallback
                        formatted_files.append(f"  • Filename: (filename not available)\n    Download URL: {private_url}")
            else:
                # No assets provided, show URLs only
                for private_url in private_urls:
                    formatted_files.append(f"  • Filename: (filename not available)\n    Download URL: {private_url}")

            if formatted_files:
                return f"**{title}:**\n" + "\n".join(formatted_files)

            return f"**{title}:** 📎 {text}" if text else None
        
        elif col_type == "mirror":
            return f"**{title}:** 🔗 {text}" if text else None
        
        elif col_type in ["subtasks", "subitems"]:
            return f"**{title}:** 📝 {text}" if text else None
        
        elif col_type in ["doc", "direct_doc", "monday_doc"]:
            return f"**{title}:** 📄 {text}" if text else None
        
        elif col_type in ["auto_number", "item_id"]:
            return f"**{title}:** #{text}" if text else None
        
        elif col_type in ["creation_log", "last_updated"]:
            return f"**{title}:** 🕐 {text}" if text else None
        
        elif col_type == "location":
            return f"**{title}:** 📍 {text}" if text else None
        
        elif col_type == "country":
            return f"**{title}:** 🌍 {text}" if text else None
        
        elif col_type == "color_picker":
            return f"**{title}:** 🎨 {text}" if text else None
        
        elif col_type in ["hour", "time_tracking"]:
            return f"**{title}:** ⏰ {text}" if text else None
        
        elif col_type == "week":
            return f"**{title}:** 📅 Week {text}" if text else None
        
        elif col_type == "world_clock":
            return f"**{title}:** 🌐 {text}" if text else None
        
        elif col_type == "button":
            return f"**{title}:** 🔘 Button"
        
        elif col_type == "vote":
            return f"**{title}:** 🗳️ {text}" if text else None
        
        elif col_type == "tags":
            return f"**{title}:** 🏷️ {text}" if text else None
        
        elif col_type == "dependency":
            return f"**{title}:** 🔗 {text}" if text else None
        
        elif col_type == "progress":
            return f"**{title}:** 📊 {text}%" if text else None
        
        else:
            # Default case for unknown column types
            return f"**{title}:** {text}" if text else None
    
    except Exception as e:
        logger.warning(f"Error formatting column {title} of type {col_type}: {str(e)}")
        return f"**{title}:** {text}" if text else None


def format_assets(assets: List[Dict[str, Any]]) -> str:
    """Format assets as markdown.

    DEPRECATED: This function is no longer used. File attachments are now displayed
    inline with file columns in format_column_value().
    """
    if not assets:
        return ""
    
    asset_list = []
    for asset in assets:
        name = asset.get("name", "Unknown File")
        url = asset.get("public_url") or asset.get("url", "")
        extension = asset.get("file_extension", "File").upper()
        
        if url:
            asset_list.append(f"• [{name}]({url}) ({extension})")
        else:
            asset_list.append(f"• {name} ({extension})")
    
    if asset_list:
        return f"\n## 📎 Attachments\n" + "\n".join(asset_list)
    
    return ""


def format_updates(updates: List[Dict[str, Any]], max_updates: int, max_chars: int) -> str:
    """Format updates and replies as markdown."""
    if not updates:
        return ""
    
    formatted_updates = []
    
    # Sort updates by date (newest first)
    sorted_updates = sorted(updates, key=lambda x: x.get("created_at", ""), reverse=True)
    
    for i, update in enumerate(sorted_updates[:max_updates]):
        if i > 0:
            formatted_updates.append("---\n")
        
        # Format main update
        creator_name = update.get("creator", {}).get("name", "Unknown User")
        created_at = format_date(update.get("created_at", ""))
        body = update.get("body", "")
        clean_body = clean_html_content(body)
        
        if len(clean_body) > max_chars:
            clean_body = truncate_text(clean_body, max_chars)
        
        formatted_updates.append(f"💬 **Update** by **{creator_name}** on {created_at}")
        formatted_updates.append(f"ID: {update.get('id', '')}\n")
        
        if clean_body:
            formatted_updates.append(f"{clean_body}\n")
        
        # Format replies if they exist
        replies = update.get("replies", [])
        if replies:
            # Sort replies by date (oldest first for threaded conversation)
            sorted_replies = sorted(replies, key=lambda x: x.get("created_at", ""))
            
            formatted_updates.append(f"  **{len(sorted_replies)} Repl{'ies' if len(sorted_replies) != 1 else 'y'}:**\n")
            
            for reply in sorted_replies:
                reply_creator = reply.get("creator", {}).get("name", "Unknown User")
                reply_created = format_date(reply.get("created_at", ""))
                reply_body = reply.get("body", "")
                clean_reply = clean_html_content(reply_body)
                
                if len(clean_reply) > max_chars // 2:  # Use half limit for replies
                    clean_reply = truncate_text(clean_reply, max_chars // 2)
                
                formatted_updates.append(f"  ↳ **Reply** by **{reply_creator}** on {reply_created}")
                formatted_updates.append(f"  ID: {reply.get('id', '')}\n")
                
                if clean_reply:
                    # Add indentation to each line of content
                    indented_content = "\n".join(f"  {line}" for line in clean_reply.split("\n"))
                    formatted_updates.append(f"{indented_content}\n")
        
        formatted_updates.append("")
    
    if formatted_updates:
        return f"\n## 💬 Recent Updates\n\n" + "\n".join(formatted_updates)
    
    return ""


def format_monday_item(
    item: Dict[str, Any], 
    include_updates: bool = False,
    max_updates: int = 5,
    include_linked_items: bool = False,
    max_linked_items: int = 20,
    max_characters: int = 5000
) -> str:
    """Format a Monday item as markdown."""
    try:
        markdown_parts = []
        
        # Item header
        item_name = item.get("name", "Unnamed Item")
        item_id = item.get("id", "")
        markdown_parts.append(f"# {item_name}\n")
        markdown_parts.append(f"**Item ID:** {item_id}\n")
        
        # Add board info if available
        board = item.get("board")
        if board:
            board_name = board.get("name", "")
            board_id = board.get("id", "")
            markdown_parts.append(f"**Board:** {board_name} (ID: {board_id})\n")
        
        # Add creation/update info
        created_at = item.get("created_at")
        updated_at = item.get("updated_at")
        creator = item.get("creator", {})
        
        if created_at:
            markdown_parts.append(f"**Created:** {format_date(created_at)}")
        if updated_at:
            markdown_parts.append(f"**Updated:** {format_date(updated_at)}")
        if creator.get("name"):
            markdown_parts.append(f"**Creator:** {creator.get('name')}")
        
        markdown_parts.append("")

        # Get assets for file column formatting
        assets = item.get("assets", [])

        # Format column values
        column_values = item.get("column_values", [])
        if column_values:
            formatted_columns = []

            for column in column_values:
                formatted = format_column_value(column, max_linked_items, assets, item_id)
                if formatted:
                    formatted_columns.append(formatted)

            if formatted_columns:
                markdown_parts.append("## 📋 Details\n")
                markdown_parts.append("\n\n".join(formatted_columns))
                markdown_parts.append("")
        
        # Format updates if requested
        if include_updates:
            updates = item.get("updates", [])
            if updates:
                updates_markdown = format_updates(updates, max_updates, max_characters // 3)
                if updates_markdown:
                    markdown_parts.append(updates_markdown)
        
        result = "\n".join(markdown_parts)
        
        # Truncate if too long
        if len(result) > max_characters:
            result = truncate_text(result, max_characters)
        
        return result
        
    except Exception as e:
        logger.error(f"Error formatting Monday item: {str(e)}")
        return f"# Error Processing Item\n\nUnable to format Monday.com data: {str(e)}"


def format_multiple_items(
    items: List[Dict[str, Any]], 
    max_characters: int = 5000,
    include_updates: bool = False,
    max_updates: int = 5,
    max_linked_items: int = 20
) -> str:
    """Format multiple Monday items as markdown."""
    if not items:
        return "*No items found.*"
    
    formatted_items = []
    chars_used = 0
    
    for i, item in enumerate(items):
        if i > 0:
            formatted_items.append("\n---\n")
            chars_used += 6  # Length of separator
        
        item_markdown = format_monday_item(
            item, 
            include_updates=include_updates,
            max_updates=max_updates,
            include_linked_items=True,  # Enable linked items for multiple items view
            max_linked_items=max_linked_items,
            max_characters=max_characters // len(items)  # Distribute character limit
        )
        
        # Check if adding this item would exceed the limit
        if chars_used + len(item_markdown) > max_characters:
            remaining_items = len(items) - i
            if remaining_items > 0:
                formatted_items.append(f"\n*... and {remaining_items} more items (truncated due to character limit)*")
            break
        
        formatted_items.append(item_markdown)
        chars_used += len(item_markdown)
    
    return "".join(formatted_items)