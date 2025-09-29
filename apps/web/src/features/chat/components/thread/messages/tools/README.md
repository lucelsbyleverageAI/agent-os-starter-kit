# Tool Call Registry System

This directory contains the tool call registry system that allows you to create custom UI components for different types of tool calls based on the tool name and graph context.

## 📋 Table of Contents

- [How It Works](#how-it-works)
- [File Structure](#file-structure)
- [Adding a New Tool Component](#adding-a-new-tool-component)
- [Component Interface](#component-interface)
- [Registry Configuration](#registry-configuration)
- [Tool Lifecycle](#tool-lifecycle)
- [Examples](#examples)
- [Integration](#integration)
- [Best Practices](#best-practices)

## 🎯 How It Works

The tool registry system routes different types of tool calls to appropriate UI components based on the tool name and graph context:

1. **Registry (`registry/index.ts`)**: Maps tool names to React components using `"graphId:toolName"` or `"*:toolName"` keys
2. **ToolCallResolver**: Routes tool calls to the appropriate component based on registry lookup
3. **Default Fallback**: Unknown tool names fall back to `SimpleToolCall` (modern card UI)
4. **Silent Tools**: Certain tools can be marked as "silent" and never render
5. **Graph-Specific Tools**: Same tool name can have different UIs for different graphs
6. **Early Detection**: Tool calls show loading states immediately when initiated
7. **Lifecycle Awareness**: Handles streaming → executing → completed states

### Flow Diagram

```
Tool Call → ToolCallResolver → Registry Lookup → Component Selection
                                      ↓
                            Pattern Match or Default
                                      ↓
                            Render Selected Component
```

## 📁 File Structure

```
tools/
├── README.md                         # This documentation
├── index.ts                          # Main exports
├── types.ts                          # TypeScript interfaces
├── utils.ts                          # Utility functions
├── ToolCallResolver.tsx              # Router component
└── registry/
    ├── index.ts                      # Registry + routing logic
    ├── shared/                       # Reusable components
    │   ├── ToolArgumentsTable.tsx    # Arguments display
    │   ├── ToolResultDisplay.tsx     # Results display
    │   └── index.ts                  # Exports
    └── components/                   # Tool-specific UI components
        ├── DefaultToolCall.tsx       # Legacy UI (uses existing ToolCalls)
        ├── SilentToolCall.tsx        # Never renders
        ├── SimpleToolCall.tsx        # Modern card UI (default)
        └── index.ts                  # Component exports
```

## ✨ Adding a New Tool Component

### Step 1: Create the Component

Create a new component in the `registry/components/` directory:

```typescript
// registry/components/MyCustomTool.tsx
import React, { useState } from "react";
import { ToolComponentProps } from "../../types";
import { Card } from "@/components/ui/card";
import { CheckCircle, Loader2, AlertCircle } from "lucide-react";
import { MinimalistBadge } from "@/components/ui/minimalist-badge";
import { getToolDisplayName } from "../../utils";
import { ToolArgumentsTable, ToolResultDisplay } from "../shared";

export function MyCustomTool({ 
  toolCall, 
  toolResult, 
  state, 
  streaming 
}: ToolComponentProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const toolDisplayName = getToolDisplayName(toolCall);

  const getStateBadge = () => {
    switch (state) {
      case 'completed':
        return <MinimalistBadge icon={CheckCircle} tooltip="Completed" />;
      case 'error':
        return <MinimalistBadge icon={AlertCircle} tooltip="Error" />;
      default:
        return <MinimalistBadge icon={Loader2} tooltip="Processing" className="animate-spin" />;
    }
  };

  return (
    <Card className="p-4 space-y-3">
      <div className="flex items-center gap-3">
        {getStateBadge()}
        <div className="flex-1">
          <h3 className="font-medium">
            Custom Tool: {toolDisplayName}
          </h3>
          <p className="text-sm text-muted-foreground">
            {state === 'completed' ? 'Processing complete' : 'Working on your request...'}
          </p>
        </div>
      </div>

      {/* Show arguments */}
      {toolCall.args && Object.keys(toolCall.args).length > 0 && (
        <ToolArgumentsTable args={toolCall.args} />
      )}

      {/* Show results when completed */}
      {state === 'completed' && toolResult && (
        <ToolResultDisplay toolResult={toolResult} />
      )}
    </Card>
  );
}
```

### Step 2: Export the Component

Add your component to `registry/components/index.ts`:

```typescript
export { DefaultToolCall } from "./DefaultToolCall";
export { SilentToolCall } from "./SilentToolCall";
export { SimpleToolCall } from "./SimpleToolCall";
export { MyCustomTool } from "./MyCustomTool"; // ← Add this
```

### Step 3: Register the Component

Add your component to the registry in `registry/index.ts`:

```typescript
import { MyCustomTool } from "./components";

export const TOOL_REGISTRY: ToolRegistry = {
  // Global registration (all graphs)
  "*:my_tool_name": {
    component: MyCustomTool,
  },
  
  // Graph-specific registration
  "my_graph_id:my_tool_name": {
    component: MyCustomTool,
  },
  
  // Silent tool (never renders)
  "*:internal_tool": {
    component: SilentToolCall,
    silent: true,
  },
  
  // ... other registrations
};
```

### Step 4: Test Your Component

Your component will now automatically be used when a tool call has:
- `toolCall.name === "my_tool_name"` (global)
- `toolCall.name === "my_tool_name"` AND `graphId === "my_graph_id"` (graph-specific)

## 🔧 Component Interface

All tool components must implement the `ToolComponentProps` interface:

```typescript
interface ToolComponentProps {
  toolCall: NonNullable<AIMessage["tool_calls"]>[0];  // The tool call object
  toolResult?: ToolMessage;                           // Matching result (if available)
  state: 'loading' | 'completed' | 'error';          // Current state
  streaming?: boolean;                                // If args are still streaming
  graphId: string;                                    // Current graph ID
  onRetry?: () => void;                              // Retry failed tool call
}
```

### Tool Call Structure

```typescript
// toolCall object structure
{
  name: string;                    // Tool name (used for registry routing)
  id: string;                      // Unique tool call ID
  args: Record<string, any>;       // Tool arguments
  type: "tool_call";               // Always "tool_call"
}
```

### Tool Result Structure

```typescript
// toolResult object structure (when available)
{
  type: "tool";
  tool_call_id: string;           // Matches toolCall.id
  name: string;                   // Tool name
  content: string | object;       // Tool execution result
}
```

## ⚙️ Registry Configuration

### Registry Keys

The registry uses a key format: `"graphId:toolName"` or `"*:toolName"` for global tools.

```typescript
export const TOOL_REGISTRY: ToolRegistry = {
  // Global tools (available for all graphs)
  "*:web_search": {
    component: WebSearchTool,
  },
  
  // Graph-specific tools
  "research_agent:web_search": {
    component: ResearchWebSearchTool,  // Custom UI for research agent
  },
  
  // Silent tools (never render)
  "*:debug_logging": {
    component: SilentToolCall,
    silent: true,
  },
};
```

### Resolution Priority

When resolving which component to use:

1. **Silent tools**: Check if tool is marked as silent (never render)
2. **Hide toggle**: Respect the "Hide Tool Calls" toggle (except for silent tools)
3. **Graph-specific**: Look for `"graphId:toolName"` first
4. **Global fallback**: Fall back to `"*:toolName"`
5. **Default**: Use `SimpleToolCall` if no match found

### Registry Entry Options

```typescript
interface ToolRegistryEntry {
  component: ToolComponent;       // React component to render
  graphIds?: string[];           // Optional: restrict to specific graphs
  silent?: boolean;              // If true, never render
}
```

## 🔄 Tool Lifecycle

Tools go through different states during execution:

### 1. **Loading State (`state: 'loading'`)**
- **When**: Tool call is detected and being prepared
- **Streaming**: Arguments may still be coming in (`streaming: true`)
- **Early Detection**: Shows immediately when tool call is initiated
- **UI**: Show loading spinner, optionally show partial arguments

### 2. **Executing State (`state: 'loading'`, `streaming: false`)**
- **When**: Tool arguments are complete, backend is executing
- **UI**: Show loading spinner, show complete arguments

### 3. **Completed State (`state: 'completed'`)**
- **When**: Tool execution finished successfully and result is available
- **UI**: Show completion badge, final arguments, and results

### 4. **Error State (`state: 'error'`)**
- **When**: Tool execution failed or timed out
- **UI**: Show error badge, error message, and retry button

## 📚 Examples

### Example 1: Simple Card Tool (Default)

```typescript
// Uses the SimpleToolCall component (default for all tools)
// Provides clean card UI with expand/collapse for args and results
export function SimpleToolCall({ toolCall, toolResult, state, streaming }: ToolComponentProps) {
  // Modern card UI with:
  // - Loading/completion badges
  // - Expandable arguments
  // - Expandable results
  // - Clean typography
}
```

### Example 2: Silent Tool

```typescript
// For tools that should never render (debugging, logging, etc.)
export function SilentToolCall(_props: ToolComponentProps) {
  return null; // Never renders anything
}

// Register as:
"*:internal_logging": {
  component: SilentToolCall,
  silent: true,
},
```

### Example 3: Graph-Specific Tool

```typescript
// Different UI for same tool on different graphs
export function ResearchWebSearchTool({ toolCall, state }: ToolComponentProps) {
  return (
    <div className="border-l-4 border-blue-500 p-4">
      <h3>Research Web Search</h3>
      <p>Searching academic sources for: {toolCall.args?.query}</p>
      {/* Research-specific UI */}
    </div>
  );
}

// Register as:
"research_agent:web_search": {
  component: ResearchWebSearchTool,
},
```

### Example 4: Complex Tool with States

```typescript
export function DatabaseQueryTool({ toolCall, toolResult, state, onRetry }: ToolComponentProps) {
  return (
    <Card className="p-4">
      <div className="flex items-center gap-3 mb-3">
        {state === 'loading' && <Loader2 className="animate-spin" />}
        {state === 'completed' && <CheckCircle className="text-green-500" />}
        {state === 'error' && <AlertCircle className="text-red-500" />}
        
        <div>
          <h3>Database Query</h3>
          <p className="text-sm text-muted-foreground">
            {state === 'loading' && 'Executing query...'}
            {state === 'completed' && 'Query completed'}
            {state === 'error' && 'Query failed'}
          </p>
        </div>
      </div>

      {/* Show SQL query */}
      {toolCall.args?.sql && (
        <pre className="bg-gray-100 p-2 rounded text-sm">
          {toolCall.args.sql}
        </pre>
      )}

      {/* Show results */}
      {state === 'completed' && toolResult && (
        <ToolResultDisplay toolResult={toolResult} />
      )}

      {/* Retry button for errors */}
      {state === 'error' && onRetry && (
        <button onClick={onRetry} className="mt-2 px-3 py-1 bg-red-500 text-white rounded">
          Retry Query
        </button>
      )}
    </Card>
  );
}
```

## 🔗 Integration

The system integrates with the existing AI message component:

```typescript
// In ai.tsx
import { ToolCallResolver, matchToolCallsWithResults } from "./tools";

// Replace old ToolCalls with ToolCallResolver
{hasEarlyToolCalls && (
  <div className="space-y-2">
    {hasToolCalls && message.tool_calls && 
      matchToolCallsWithResults(
        message.tool_calls,
        thread.messages,
        isLoading
      ).map((item, idx) => (
        <ToolCallResolver
          key={item.toolCall.id || idx}
          toolCall={item.toolCall}
          toolResult={item.toolResult}
          state={item.state}
          streaming={item.streaming}
        />
      ))
    }
  </div>
)}
```

## 🎨 Shared Components

Use these building blocks for consistent UI:

### ToolArgumentsTable
Display tool arguments in a formatted table:
```typescript
<ToolArgumentsTable args={toolCall.args} />
```

### ToolResultDisplay
Display tool results with expand/collapse:
```typescript
<ToolResultDisplay toolResult={toolResult} />
```

### MinimalistBadge
Consistent badge styling:
```typescript
<MinimalistBadge
  icon={CheckCircle}
  tooltip="Tool Completed"
/>
```

## 🚀 Best Practices

1. **Component Naming**: Use descriptive names like `DatabaseQueryTool`, `ImageGenerationTool`
2. **State Handling**: Always handle all three states (loading, completed, error)
3. **Error Recovery**: Provide retry functionality where appropriate
4. **Performance**: Use React.memo for expensive components
5. **Accessibility**: Include proper ARIA labels and keyboard navigation
6. **Responsive Design**: Ensure components work on mobile devices
7. **Consistent Styling**: Use existing UI components and follow design system
8. **Early Feedback**: Show loading states immediately when tools are detected
9. **Graceful Degradation**: Handle missing data gracefully
10. **Graph Context**: Use `graphId` prop for graph-specific behavior

## 🔧 Utility Functions

### getToolDisplayName
Convert snake_case tool names to readable format:
```typescript
getToolDisplayName({ name: "web_search_api" }) // "Web Search Api"
```

### matchToolCallsWithResults
Match tool calls with their results and determine states:
```typescript
const toolCallsWithResults = matchToolCallsWithResults(
  message.tool_calls,
  thread.messages,
  isLoading
);
```

### hasToolCallArgs
Check if a tool call has arguments:
```typescript
if (hasToolCallArgs(toolCall)) {
  // Show arguments UI
}
```

## 🎯 Configuration Examples

### Global Tool for All Graphs
```typescript
"*:code_interpreter": {
  component: CodeInterpreterTool,
},
```

### Graph-Specific Override
```typescript
"research_agent:web_search": {
  component: AcademicWebSearchTool,  // Different UI for research
},
"*:web_search": {
  component: StandardWebSearchTool,  // Default for other graphs
},
```

### Silent Internal Tool
```typescript
"*:debug_logger": {
  component: SilentToolCall,
  silent: true,  // Never renders, even with toggle off
},
```

### Multiple Tools Same Component
```typescript
"*:image_generation": { component: MediaTool },
"*:video_generation": { component: MediaTool },
"*:audio_generation": { component: MediaTool },
```

This registry system provides maximum flexibility while maintaining consistency and backward compatibility with existing tool call functionality. The default `SimpleToolCall` component ensures all tools have a modern, clean UI out of the box!
