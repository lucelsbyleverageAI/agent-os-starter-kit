"""
Markdown formatting utilities for NHS analytics tools.

This module provides pure data formatting functions for converting database
query results into readable markdown tables and text. No analysis or insights
are generated - only data presentation.
"""

from typing import Any, List, Optional, Dict
from decimal import Decimal


def format_markdown_table(
    headers: List[str],
    rows: List[List[Any]],
    alignments: Optional[List[str]] = None
) -> str:
    """
    Generate a markdown table from headers and rows.

    Args:
        headers: Column headers
        rows: List of row data (each row is a list of values)
        alignments: Optional list of alignments ('left', 'right', 'center')
                   Defaults to 'left' for all columns

    Returns:
        Formatted markdown table string
    """
    if not rows:
        return "_No data available_\n"

    if alignments is None:
        alignments = ['left'] * len(headers)

    # Convert all values to strings
    header_strs = [str(h) for h in headers]
    row_strs = [[_format_cell_value(cell) for cell in row] for row in rows]

    # Calculate column widths
    col_widths = [len(h) for h in header_strs]
    for row in row_strs:
        for i, cell in enumerate(row):
            col_widths[i] = max(col_widths[i], len(cell))

    # Build table
    lines = []

    # Header row
    header_row = '| ' + ' | '.join(
        header_strs[i].ljust(col_widths[i]) for i in range(len(headers))
    ) + ' |'
    lines.append(header_row)

    # Separator row
    separator_cells = []
    for i, align in enumerate(alignments):
        width = col_widths[i]
        if align == 'center':
            sep = ':' + '-' * (width - 2) + ':'
        elif align == 'right':
            sep = '-' * (width - 1) + ':'
        else:  # left
            sep = '-' * width
        separator_cells.append(sep)

    separator_row = '| ' + ' | '.join(separator_cells) + ' |'
    lines.append(separator_row)

    # Data rows
    for row in row_strs:
        data_row = '| ' + ' | '.join(
            row[i].ljust(col_widths[i]) for i in range(len(row))
        ) + ' |'
        lines.append(data_row)

    return '\n'.join(lines) + '\n'


def _format_cell_value(value: Any) -> str:
    """Format a single cell value for markdown table display."""
    if value is None:
        return '-'
    if isinstance(value, bool):
        return 'Yes' if value else 'No'
    if isinstance(value, (int, Decimal)):
        return str(value)
    if isinstance(value, float):
        # Round to reasonable precision
        return f"{value:.1f}" if abs(value) >= 1 else f"{value:.3f}"
    return str(value)


def format_percentage(value: Optional[float], decimal_places: int = 1) -> str:
    """
    Format a decimal value (0-1 or 0-100) as a percentage string.

    Args:
        value: Decimal value (e.g., 0.887 or 88.7)
        decimal_places: Number of decimal places to show

    Returns:
        Formatted percentage string (e.g., "88.7%")
    """
    if value is None:
        return '-'

    # Detect if value is already in 0-100 range or 0-1 range
    # Use absolute value to handle negative percentages (e.g., -6.32% deficit)
    if abs(value) > 1:
        pct = value
    else:
        pct = value * 100

    return f"{pct:.{decimal_places}f}%"


def format_percentile_rank(percentile: Optional[float], as_integer: bool = True) -> str:
    """
    Format a percentile rank (0-1 scale) as a readable percentage.

    Args:
        percentile: Percentile value (0-1, where 0.75 = 75th percentile)
        as_integer: If True, round to integer percentage

    Returns:
        Formatted percentile string (e.g., "75%")
    """
    if percentile is None:
        return '-'

    pct = percentile * 100

    if as_integer:
        return f"{int(round(pct))}%"
    else:
        return f"{pct:.1f}%"


def format_target_status(met: Optional[bool]) -> str:
    """
    Format target achievement boolean as Yes/No.

    Args:
        met: Whether target was met

    Returns:
        "Yes", "No", or "-" for None
    """
    if met is None:
        return '-'
    return 'Yes' if met else 'No'


def format_value_with_unit(value: Optional[float], unit: str, decimal_places: int = 1) -> str:
    """
    Format a metric value with its unit.

    Args:
        value: Numeric value
        unit: Unit of measurement ('percentage', 'weeks', 'score', 'count', etc.)
        decimal_places: Number of decimal places for non-percentage values

    Returns:
        Formatted string with unit
    """
    if value is None:
        return '-'

    if unit.lower() in ['percentage', 'percent', 'pct']:
        return format_percentage(value, decimal_places)
    elif unit.lower() in ['weeks', 'week', 'wks']:
        return f"{value:.{decimal_places}f} wks"
    elif unit.lower() in ['score', 'scores']:
        return f"{value:.{decimal_places}f}"
    elif unit.lower() in ['count', 'number', 'n']:
        return str(int(value))
    else:
        return f"{value:.{decimal_places}f} {unit}"


def format_rank(rank: Optional[int], total: Optional[int] = None) -> str:
    """
    Format a ranking position.

    Args:
        rank: Ranking position (1-based)
        total: Optional total number of entities for "X/Y" format

    Returns:
        Formatted rank string
    """
    if rank is None:
        return '-'

    if total is not None:
        return f"{rank}/{total}"
    else:
        return str(rank)


def format_change(current: Optional[float], previous: Optional[float], unit: str = 'pp') -> str:
    """
    Format the change between two values.

    Args:
        current: Current period value
        previous: Previous period value
        unit: Unit for change ('pp' for percentage points, 'wks' for weeks, etc.)

    Returns:
        Formatted change string with +/- sign
    """
    if current is None or previous is None:
        return '-'

    change = current - previous
    sign = '+' if change >= 0 else ''

    if unit == 'pp':
        return f"{sign}{change:.1f}pp"
    elif unit == 'wks':
        return f"{sign}{change:.1f} wks"
    else:
        return f"{sign}{change:.1f}"


def format_section_header(title: str, level: int = 2) -> str:
    """
    Format a markdown section header.

    Args:
        title: Section title
        level: Header level (1-6)

    Returns:
        Formatted markdown header
    """
    hashes = '#' * level
    return f"{hashes} {title}\n"


def format_metadata_line(label: str, value: str) -> str:
    """
    Format a metadata line (bold label with value).

    Args:
        label: Label text
        value: Value text

    Returns:
        Formatted line like "**Label**: value"
    """
    return f"**{label}**: {value}"


def format_cohort_statistics(
    min_val: Optional[float],
    q1: Optional[float],
    median: Optional[float],
    q3: Optional[float],
    max_val: Optional[float],
    unit: str = 'percentage'
) -> str:
    """
    Format cohort distribution statistics as a markdown table.

    Args:
        min_val: Minimum value
        q1: First quartile (25th percentile)
        median: Median (50th percentile)
        q3: Third quartile (75th percentile)
        max_val: Maximum value
        unit: Unit of measurement

    Returns:
        Formatted markdown table
    """
    headers = ['Statistic', 'Value']
    rows = [
        ['Minimum', format_value_with_unit(min_val, unit)],
        ['Q1 (25th percentile)', format_value_with_unit(q1, unit)],
        ['Median (50th percentile)', format_value_with_unit(median, unit)],
        ['Q3 (75th percentile)', format_value_with_unit(q3, unit)],
        ['Maximum', format_value_with_unit(max_val, unit)],
    ]

    return format_markdown_table(headers, rows, alignments=['left', 'right'])


def build_markdown_document(sections: List[Dict[str, Any]]) -> str:
    """
    Build a complete markdown document from sections.

    Args:
        sections: List of section dictionaries with keys:
                 - 'type': 'header', 'metadata', 'table', 'text'
                 - 'content': Content appropriate for the type
                 - 'level': Header level (for headers)

    Returns:
        Complete markdown document string
    """
    lines = []

    for section in sections:
        section_type = section.get('type')
        content = section.get('content')

        if section_type == 'header':
            level = section.get('level', 2)
            lines.append(format_section_header(content, level))

        elif section_type == 'metadata':
            # Content should be dict of label: value pairs
            metadata_lines = []
            for label, value in content.items():
                metadata_lines.append(format_metadata_line(label, value))
            lines.append(' | '.join(metadata_lines))
            lines.append('')

        elif section_type == 'table':
            # Content should have 'headers', 'rows', optional 'alignments'
            table = format_markdown_table(
                content['headers'],
                content['rows'],
                content.get('alignments')
            )
            lines.append(table)

        elif section_type == 'text':
            lines.append(str(content))
            lines.append('')

        elif section_type == 'separator':
            lines.append('---\n')

    return '\n'.join(lines)
