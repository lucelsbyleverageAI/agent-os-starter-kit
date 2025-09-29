# Human Interrupt Registry

This directory contains the interrupt registry system that allows you to create custom UI components for different types of human interrupts based on the action name.

## 📋 Table of Contents

- [How It Works](#how-it-works)
- [File Structure](#file-structure)
- [Adding a New Interrupt Component](#adding-a-new-interrupt-component)
- [Component Interface](#component-interface)
- [Registry Configuration](#registry-configuration)
- [Examples](#examples)
- [Troubleshooting](#troubleshooting)

## 🎯 How It Works

The interrupt registry system routes different types of human interrupts to appropriate UI components based on the `action_request.action` field:

1. **Registry (`index.ts`)**: Maps action names to React components
2. **InterruptResolver**: Routes interrupts to the appropriate component based on action name
3. **Default Fallback**: Unknown action names fall back to the existing generic UI
4. **Custom Components**: Specialized UIs for specific interrupt types

### Flow Diagram

```
Interrupt → InterruptResolver → Registry Lookup → Component Selection
                                      ↓
                            Pattern Match or Default
                                      ↓
                            Render Selected Component
```

## 📁 File Structure

```
interrupts/
├── index.ts                          # Registry + exports  
├── interrupt-types.ts                # Type definitions
├── InterruptResolver.tsx             # Router component
└── components/
    ├── index.ts                     # Component exports
    ├── DefaultInterrupt.tsx         # Generic UI (fallback)
    └── LightToolReviewInterrupt.tsx # Light tool review UI
```

## ✨ Adding a New Interrupt Component

### Step 1: Create the Component

Create a new component in the `components/` directory:

```typescript
// components/MyCustomInterrupt.tsx
import React from "react";
import { InterruptComponentProps } from "../index";
import { Button } from "@/components/ui/button";
import { CheckCircle, XCircle } from "lucide-react";
import { HumanResponse } from "../interrupt-types";

export function MyCustomInterrupt({ 
  interrupt, 
  onSubmit, 
  streaming = false, 
  loading = false 
}: InterruptComponentProps) {
  const actionsDisabled = loading || streaming;

  const handleApprove = async () => {
    const response: HumanResponse = {
      type: "accept",
      args: interrupt.action_request
    };
    await onSubmit(response);
  };

  const handleDeny = async () => {
    const response: HumanResponse = {
      type: "ignore", 
      args: null
    };
    await onSubmit(response);
  };

  return (
    <div className="w-full max-w-4xl space-y-4 rounded-xl border border-border bg-card p-6">
      <div className="flex items-start gap-3">
        <div className="flex h-8 w-8 items-center justify-center rounded-full bg-blue-100 text-blue-600">
          🤖
        </div>
        <div className="flex-1">
          <h3 className="text-lg font-semibold text-foreground">
            Custom Action Required
          </h3>
          <p className="mt-1 text-sm text-muted-foreground">
            {interrupt.description || "Please review this action."}
          </p>
        </div>
      </div>
      
      <div className="flex justify-end gap-3">
        <Button
          variant="outline"
          onClick={handleDeny}
          disabled={actionsDisabled}
          className="flex items-center gap-2"
        >
          <XCircle className="h-4 w-4" />
          Deny
        </Button>
        <Button
          onClick={handleApprove}
          disabled={actionsDisabled}
          className="flex items-center gap-2"
        >
          <CheckCircle className="h-4 w-4" />
          Approve
        </Button>
      </div>
    </div>
  );
}
```

### Step 2: Export the Component

Add your component to `components/index.ts`:

```typescript
export { DefaultInterrupt } from "./DefaultInterrupt";
export { LightToolReviewInterrupt } from "./LightToolReviewInterrupt";
export { MyCustomInterrupt } from "./MyCustomInterrupt"; // ← Add this
```

### Step 3: Register the Component

Add your component to the registry in `index.ts`:

```typescript
import { MyCustomInterrupt } from "./components";

export const INTERRUPT_REGISTRY: Record<string, InterruptComponent> = {
  "my_custom_action": MyCustomInterrupt,           // ← Add this
  "another_action": MyCustomInterrupt,             // ← Multiple actions can use same component
  // ... other registrations
};
```

### Step 4: Test Your Component

Your component will now automatically be used when an interrupt has:
- `action_request.action === "my_custom_action"`
- `action_request.action === "another_action"`

## 🔧 Component Interface

All interrupt components must implement the `InterruptComponentProps` interface:

```typescript
interface InterruptComponentProps {
  interrupt: HumanInterrupt;           // The interrupt data
  onSubmit: (response: any) => Promise<void>;  // Submit handler
  onResolve?: () => Promise<void>;     // Optional resolve handler
  onIgnore?: () => Promise<void>;      // Optional ignore handler
  streaming?: boolean;                 // Whether currently streaming
  streamFinished?: boolean;            // Whether stream has finished
  loading?: boolean;                   // Whether in loading state
}
```

### Interrupt Data Structure

```typescript
interface HumanInterrupt {
  action_request: {
    action: string;                    // Action name (used for routing)
    args: Record<string, any>;         // Action arguments
  };
  config: {
    allow_ignore: boolean;             // Can user ignore?
    allow_respond: boolean;            // Can user respond with text?
    allow_edit: boolean;               // Can user edit arguments?
    allow_accept: boolean;             // Can user accept as-is?
  };
  description?: string;                // Optional markdown description
}
```

### Response Types

Your component should submit one of these response types:

```typescript
// Accept the action as-is
const acceptResponse: HumanResponse = {
  type: "accept",
  args: interrupt.action_request  // Original action
};

// Ignore/skip the action
const ignoreResponse: HumanResponse = {
  type: "ignore", 
  args: null
};

// Provide textual feedback
const responseWithFeedback: HumanResponse = {
  type: "response",
  args: "Please try a different approach"
};

// Edit the action arguments
const editResponse: HumanResponse = {
  type: "edit",
  args: {
    action: interrupt.action_request.action,
    args: { ...interrupt.action_request.args, modified: true }
  }
};
```

## ⚙️ Registry Configuration

### Pattern Matching

The registry supports pattern matching for dynamic routing:

```typescript
export function getInterruptComponent(actionName: string): InterruptComponent {
  // Pattern matching - actions starting with 'tool_call_review_'
  if (actionName.startsWith('tool_call_review_')) {
    return LightToolReviewInterrupt;
  }
  
  // Exact matches in registry
  if (INTERRUPT_REGISTRY[actionName]) {
    return INTERRUPT_REGISTRY[actionName];
  }
  
  // Fallback to default
  return DEFAULT_INTERRUPT_COMPONENT;
}
```

### Priority Order

1. **Pattern matches** (e.g., `tool_call_review_*`)
2. **Exact registry matches** (e.g., `my_custom_action`)
3. **Default component** (fallback)

## 📚 Examples

### Example 1: Light Tool Review Component

```typescript
// For actions like "tool_call_review_search_documents"
export function LightToolReviewInterrupt({ interrupt, onSubmit }: InterruptComponentProps) {
  const toolName = interrupt.action_request.action.replace('tool_call_review_', '');
  const readableToolName = prettifyText(toolName);

  return (
    <div className="border rounded-lg p-4">
      <p>Agent wants to use: <strong>{readableToolName}</strong></p>
      <div className="flex gap-2 mt-4">
        <Button onClick={() => onSubmit({ type: "accept", args: interrupt.action_request })}>
          Accept
        </Button>
        <Button variant="outline" onClick={() => onSubmit({ type: "ignore", args: null })}>
          Deny
        </Button>
      </div>
    </div>
  );
}
```

### Example 2: Complex Approval Component

```typescript
// For actions requiring detailed review
export function DetailedApprovalInterrupt({ interrupt, onSubmit }: InterruptComponentProps) {
  const [feedback, setFeedback] = useState("");

  return (
    <div className="space-y-4">
      <h3>Detailed Review Required</h3>
      <pre className="bg-gray-100 p-4 rounded">
        {JSON.stringify(interrupt.action_request.args, null, 2)}
      </pre>
      <textarea 
        value={feedback}
        onChange={(e) => setFeedback(e.target.value)}
        placeholder="Optional feedback..."
      />
      <div className="flex gap-2">
        <Button onClick={() => onSubmit({ type: "accept", args: interrupt.action_request })}>
          Approve
        </Button>
        <Button onClick={() => onSubmit({ type: "response", args: feedback })}>
          Provide Feedback
        </Button>
        <Button variant="destructive" onClick={() => onSubmit({ type: "ignore", args: null })}>
          Reject
        </Button>
      </div>
    </div>
  );
}
```

## 🔧 Troubleshooting

### Interrupts Not Displaying

If your interrupts are not showing in the UI, check:

1. **Registry Registration**: Ensure your component is properly registered in `index.ts`
2. **Schema Validation**: Verify the interrupt matches the expected schema
3. **Component Props**: Ensure your component accepts `InterruptComponentProps`
4. **Action Names**: Check that the action name matches your registry entry

### Debugging Steps

1. **Add Console Logging**:
```typescript
// In your component
```

2. **Check InterruptResolver**:
```typescript
// In InterruptResolver.tsx
console.log("Action resolved to component:", { 
  actionName, 
  componentName: InterruptComponent.name 
});
```

3. **Verify Registry Lookup**:
```typescript
// In index.ts getInterruptComponent function
```

### Common Issues

- **Missing Exports**: Ensure your component is exported from `components/index.ts`
- **Type Mismatches**: Verify your component implements `InterruptComponentProps`
- **Wrong Action Names**: Check that backend sends the expected action names
- **Hook Dependencies**: Ensure InterruptResolver properly wraps the hook functions

### Testing Your Component

To test your component:

1. **Backend Setup**: Configure your agent to send interrupts with your action name
2. **UI Testing**: Trigger the interrupt flow in the chat interface
3. **Response Handling**: Verify that your component's responses are properly handled
4. **Edge Cases**: Test with missing data, long text, network errors

## 🚀 Best Practices

1. **Component Naming**: Use descriptive names like `ToolApprovalInterrupt`
2. **Error Handling**: Always handle loading and error states
3. **Accessibility**: Include proper ARIA labels and keyboard navigation
4. **Responsive Design**: Ensure components work on mobile devices
5. **Performance**: Use React.memo for expensive components
6. **Type Safety**: Always type your props and response objects

## 🎨 Styling Guidelines

- Use existing UI components from `@/components/ui/`
- Follow the established design system colors and spacing
- Ensure consistent visual hierarchy across interrupt types
- Support both light and dark themes
- Maintain responsive layouts for all screen sizes

---

This registry system provides a flexible and maintainable way to handle different types of human interrupts while keeping the codebase organized and extensible.
