# Linked Items Configuration System

This document explains how the linked items configuration system works for Monday.com tools.

## Overview

The linked items configuration system allows you to specify which additional columns should be displayed when showing linked items from specific boards. This provides more context-rich output for board relations whilst keeping the display concise and relevant.

## Configuration File

The configuration is stored in `linked_item_columns_config.yaml` in this directory. The file maps board IDs to the specific columns that should be displayed for linked items from those boards.

### Format

```yaml
"<board_id>":
  name: "Board Display Name"
  columns:
    - id: "<column_id>"
      label: "Display Label"
      type: "<column_type>"
```

### Current Configuration

The system is configured for the following boards:

- **Process Master (1653909648)**: Department, Sub-Department, Hours Saved per annum, Metrics comment, Process Description
- **Customer Master (1644881752)**: Comments
- **Deal Master (1694049876)**: Partner, Vendor (dropdowns)
- **Contacts (1653883216)**: Job Title
- **Workshops (1723128552)**: Workshop Notes, Customer/Prospect

## How It Works

1. **Loading**: The configuration is loaded once and cached for performance
2. **Column Selection**: For each linked item, the system:
   - Checks if the item's board ID has specific configuration
   - If configured: Shows the specified columns PLUS all short column types
   - If not configured: Shows only status and due date (legacy behaviour)
3. **Short Column Types**: Always included regardless of configuration:
   - status, dropdown, date, numbers, text, email, phone, link, checkbox, people, rating, formula, etc.

## Column Display Logic

For linked items from configured boards, columns are displayed if they are:

1. **Explicitly configured** in the YAML file, OR
2. **Short column types** that should always be shown

Long text fields and other verbose column types are only shown if explicitly configured.

## Example Output

Before (only status and due):
```
• [Process A](board:Process Master) (ID: 12345) (Status: In Progress | Due: 12/06/2024)
```

After (with configuration):
```
• [Process A](board:Process Master) (ID: 12345) (Status: In Progress | Due: 12/06/2024 | Department: 📋 Finance | Hours Saved per annum: 240)
```

## Adding New Board Configurations

To add configuration for a new board:

1. Get the board ID (use the `list_boards` tool)
2. Get the column IDs (use the `get_board_columns` tool)
3. Add an entry to `linked_item_columns_config.yaml`:

```yaml
"<new_board_id>":
  name: "New Board Name"
  columns:
    - id: "column_id_1"
      label: "Display Name 1"
      type: "text"
    - id: "column_id_2"
      label: "Display Name 2"
      type: "dropdown"
```

4. The configuration will be automatically reloaded

## Testing

Run the test script to verify configuration:

```bash
cd apps/mcp/src/mcp_server/tools/monday/
python test_config.py
```

## Files

- `linked_item_columns_config.yaml`: Configuration file
- `linked_item_config.py`: Configuration loader and utilities
- `utils.py`: Updated formatting logic
- `test_config.py`: Test script
- This README file

## Troubleshooting

- **Configuration not loading**: Check the YAML syntax and file permissions
- **Columns not showing**: Verify the column IDs match exactly (case-sensitive)
- **Performance issues**: The configuration is cached, but very large configs may impact performance
- **Missing PyYAML**: Run `poetry install` in the apps/mcp directory to install dependencies

## Future Enhancements

Possible improvements:
- Per-tool configuration overrides
- Maximum display length per board
- Dynamic column selection based on column names
- UI for managing configurations