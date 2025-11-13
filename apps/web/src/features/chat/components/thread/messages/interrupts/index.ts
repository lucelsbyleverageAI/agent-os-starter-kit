import { DefaultInterrupt, LightToolReviewInterrupt, ToolApprovalInterrupt } from "./components";

// Import the types directly from the existing interrupt types file
export type { 
  HumanInterrupt, 
  HumanResponse, 
  HumanInterruptConfig, 
  ActionRequest, 
  HumanResponseWithEdits,
  SubmitType,
  InterruptValue 
} from "../interrupt-types";

export interface InterruptComponentProps {
  interrupt: import("../interrupt-types").HumanInterrupt;
  onSubmit: (response: any) => Promise<void>;
  onResolve?: () => Promise<void>;
  onIgnore?: () => Promise<void>;
  streaming?: boolean;
  streamFinished?: boolean;
  loading?: boolean;
}

export type InterruptComponent = React.ComponentType<InterruptComponentProps>;

export const INTERRUPT_REGISTRY: Record<string, InterruptComponent> = {
  // Light component for all tool call reviews
  // This will match any action starting with 'tool_call_review_'
};

export const DEFAULT_INTERRUPT_COMPONENT = DefaultInterrupt;

export function getInterruptComponent(actionName: string): InterruptComponent {
  // Check for tool approval pattern (tool_approval_*)
  if (actionName.startsWith('tool_approval_')) {
    return ToolApprovalInterrupt;
  }

  // Check for tool call review pattern
  if (actionName.startsWith('tool_call_review_')) {
    return LightToolReviewInterrupt;
  }

  // Check for exact matches in registry
  if (INTERRUPT_REGISTRY[actionName]) {
    return INTERRUPT_REGISTRY[actionName];
  }

  // Fallback to default
  return DEFAULT_INTERRUPT_COMPONENT;
}

// Export the InterruptResolver for use in other components
export { InterruptResolver } from "./InterruptResolver"; 