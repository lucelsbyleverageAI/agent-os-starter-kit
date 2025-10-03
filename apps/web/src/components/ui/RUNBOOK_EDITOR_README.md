# Runbook Editor Component

A rich markdown editor component for creating and editing detailed AI agent prompts and instructions.

## Overview

The Runbook Editor provides a professional markdown editing experience with a toolbar for common formatting operations and a preview mode. It's designed to encourage users to write comprehensive, well-structured prompts instead of short, inadequate instructions.

## Features

- **Rich Markdown Toolbar**: Quick access to formatting options including:
  - Headings (H1, H2, H3)
  - Bold, Italic, Underline
  - Code blocks and inline code
  - Blockquotes
  - Bulleted and numbered lists
  - Links
  
- **Live Preview**: Toggle between edit and preview modes to see how the markdown renders
- **Full-screen Modal**: Large, distraction-free editing environment
- **Auto-save on Close**: Changes are saved when the modal is closed

## Usage

### In Configuration Files

To use the runbook editor in your agent configuration, set the field type to `"runbook"` in the metadata:

```python
from pydantic import BaseModel, Field

class AgentConfig(BaseModel):
    system_prompt: str = Field(
        default="Default prompt...",
        metadata={
            "x_oap_ui_config": {
                "type": "runbook",  # Use runbook instead of textarea
                "placeholder": "Enter detailed instructions...",
                "description": "Comprehensive system prompt for the agent",
            }
        },
    )
```

### Direct Component Usage

```tsx
import { RunbookField } from "@/components/ui/runbook-editor";

function MyComponent() {
  const [prompt, setPrompt] = useState("");

  return (
    <RunbookField
      value={prompt}
      onChange={setPrompt}
      placeholder="Enter your instructions..."
      description="Optional description text"
      buttonLabel="Create or Edit Runbook"
    />
  );
}
```

## Configuration Files Updated

The following configuration files have been updated to use the runbook type:

1. **Tools Agent** (`langgraph/src/agent_platform/agents/tools_agent/config.py`)
   - `system_prompt` field

2. **Deep Agent** (`langgraph/src/agent_platform/agents/deepagents/basic_deepagent/configuration.py`)
   - `system_prompt` field
   - Sub-agent `prompt` field

3. **Supervisor Agent** (`langgraph/src/agent_platform/agents/supervisor_agent/config.py`)
   - `system_prompt` field

4. **Deep Research Agent** (`langgraph/src/agent_platform/agents/deep_research_agent/configuration.py`)
   - `mcp_prompt` field

## Styling

The runbook preview uses custom CSS classes defined in `apps/web/src/app/globals.css`. The `.runbook-preview` class provides styling for:

- Headings (H1-H4)
- Paragraphs
- Lists (ordered and unordered)
- Code blocks and inline code
- Blockquotes
- Links
- Tables
- Horizontal rules

## Benefits

1. **Encourages Quality**: The dedicated editor interface signals to users that prompts should be detailed and well-thought-out
2. **Better UX**: Larger editing space with formatting tools makes it easier to write comprehensive instructions
3. **Preview Mode**: Users can see exactly how their markdown will render
4. **Consistent Formatting**: Toolbar ensures consistent markdown syntax across all prompts

## Design Inspiration

This component was inspired by Semaphore's runbook editor, which uses a similar modal-based approach to encourage users to create detailed, professional agent configurations.

