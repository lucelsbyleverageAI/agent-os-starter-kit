import React from "react";
import { HumanInterrupt, HumanResponse } from "../interrupt-types";
import { getInterruptComponent, InterruptComponentProps } from "./index";
import { useInterruptedActions } from "@/features/chat/hooks/use-interrupted-actions";
import { useStreamContext } from "@/features/chat/providers/Stream";
import { Message } from "@langchain/langgraph-sdk";
import { useConfigStore } from "@/features/chat/hooks/use-config-store";
import { useAuthContext } from "@/providers/Auth";
import { logger } from "@/lib/logger";

interface InterruptResolverProps {
  interrupt: HumanInterrupt;
}

export function InterruptResolver({ interrupt }: InterruptResolverProps) {
  // Extract action name from the interrupt
  const actionName = interrupt.action_request.action;
  
  // Get the appropriate component from the registry
  const InterruptComponent = getInterruptComponent(actionName);
  
  // Use the interrupt actions hook to get the real functionality
  const {
    streaming,
    streamFinished,
    loading,
    handleSubmit,
    handleIgnore,
    handleResolve,
  } = useInterruptedActions({ interrupt });

  const thread = useStreamContext();
  const { getAgentConfig } = useConfigStore();
  const { session } = useAuthContext();

  // Create wrapper functions that match the expected interface
  const onSubmit = async (response: HumanResponse) => {
    try {
      // Get agent configuration and log for debugging
      const agentId = thread.assistantId;
      const agentConfig = getAgentConfig(agentId);

      logger.debug("[InterruptResolver] Resuming with config", {
        agentId,
        hasToolApprovals: !!agentConfig?.mcp_config?.tool_approvals,
        toolApprovalCount: Object.keys(agentConfig?.mcp_config?.tool_approvals || {}).length
      });

      // For registry components, we need to bypass the form submission logic
      // and directly call the thread submit with the response
      thread.submit(
        { messages: thread.messages }, // Pass existing messages to backend
        {
          command: {
            resume: [response],
          },
          streamMode: ["values"],
          config: {
            configurable: agentConfig,
          },
          metadata: {
            supabaseAccessToken: session?.accessToken,
          },
          optimisticValues: (prev: { messages?: Message[] }) => {
            const result = {
              ...prev,
              messages: thread.messages, // Preserve locally
            };
            return result;
          },
        },
      );
    } catch (e: any) {
      console.error("Error sending human response from registry component", e);
      // Fallback to the original handler if direct submission fails
      const mockEvent = { preventDefault: () => {} } as React.MouseEvent<HTMLButtonElement, MouseEvent>;
      await handleSubmit(mockEvent);
    }
  };
  
  const onResolve = async () => {
    const mockEvent = { preventDefault: () => {} } as React.MouseEvent<HTMLButtonElement, MouseEvent>;
    await handleResolve(mockEvent);
  };
  
  const onIgnore = async () => {
    const mockEvent = { preventDefault: () => {} } as React.MouseEvent<HTMLButtonElement, MouseEvent>;
    await handleIgnore(mockEvent);
  };
  
  // Create props for the interrupt component
  const componentProps: InterruptComponentProps = {
    interrupt,
    onSubmit,
    onResolve,
    onIgnore,
    streaming,
    streamFinished,
    loading,
  };
  
  return <InterruptComponent {...componentProps} />;
} 