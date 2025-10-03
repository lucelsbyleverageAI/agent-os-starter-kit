import React from "react";
import { InterruptValue, HumanInterrupt } from "./interrupt-types";
import { InterruptResolver } from "./interrupts/InterruptResolver";
import { IMPROPER_SCHEMA } from "@/constants";

interface InterruptProps {
  interruptValue?: InterruptValue;
  isLastMessage?: boolean;
  hasNoAIOrToolMessages?: boolean;
}

function isAgentInboxInterruptSchema(value: any): boolean {
  if (!value || typeof value !== 'object') {
        return false;
  }
  
  if (!Array.isArray(value.interrupts)) {
        return false;
  }
  
  if (value.interrupts.length === 0) {
        return false;
  }
  
  if (value.interrupts[0]?.action_request?.action === IMPROPER_SCHEMA) {
        return false;
  }
  
    return true;
}

function isDirectHumanInterrupt(value: any): boolean {
  if (!value || typeof value !== 'object') {
        return false;
  }
  
  // Check for direct HumanInterrupt schema
  if (value.action_request && value.config && 
      value.action_request.action && 
      typeof value.action_request.action === 'string') {
        return true;
  }
  
    return false;
}

function isStandardLangGraphInterrupt(value: any): boolean {
  if (!value || typeof value !== 'object') {
        return false;
  }
  
  // Check for standard LangGraph interrupt schema
  if (value.tool_name && value.message && typeof value.tool_name === 'string') {
        return true;
  }
  
    return false;
}

// InteractiveInterruptView is now replaced by the InterruptResolver registry system

export function Interrupt({ 
  interruptValue, 
  isLastMessage = false, 
  hasNoAIOrToolMessages = false 
}: InterruptProps) {
  // Don't render if no interrupt value
  if (!interruptValue) {
        return null;
  }

  const isAgentInboxSchema = isAgentInboxInterruptSchema(interruptValue);
  const isDirectSchema = isDirectHumanInterrupt(interruptValue);
  const isStandardSchema = isStandardLangGraphInterrupt(interruptValue);
  const shouldRender = isLastMessage || hasNoAIOrToolMessages;

  // Render agent inbox style interrupts with registry system
  if (isAgentInboxSchema && shouldRender) {
    const interrupt = interruptValue.interrupts![0];
        return <InterruptResolver interrupt={interrupt} />;
  }

  // Render direct HumanInterrupt format
  if (isDirectSchema && shouldRender) {
    const interrupt = interruptValue as HumanInterrupt;
        return <InterruptResolver interrupt={interrupt} />;
  }

  // Handle standard LangGraph interrupts (temporary fallback during migration)
  if (isStandardSchema && shouldRender) {
        
    // Create a simple approval UI for legacy format
    return (
      <div className="w-full space-y-4 rounded-xl border border-amber-200 bg-amber-50 p-6">
        <div className="flex items-start gap-3">
          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-amber-100 text-amber-600">
            ⚠️
          </div>
          <div className="flex-1">
            <h3 className="text-lg font-semibold text-foreground">
              Tool Approval Required (Legacy Format)
            </h3>
            <p className="mt-1 text-sm text-muted-foreground">
              The backend is using an old interrupt format. Please update to Agent Inbox schema.
            </p>
          </div>
        </div>
        
        <div className="bg-white rounded-lg p-4 border">
          <pre className="text-sm text-gray-700 whitespace-pre-wrap">
            {JSON.stringify(interruptValue, null, 2)}
          </pre>
        </div>
        
        <p className="text-sm text-amber-700">
          To enable full interrupt functionality, update the backend to use the Agent Inbox interrupt schema.
        </p>
      </div>
    );
  }

  // No supported interrupt format found
    return null;
} 