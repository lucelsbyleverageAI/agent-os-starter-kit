import React from "react";
import { InterruptComponentProps } from "../index";
import { useInterruptedActions } from "@/features/chat/hooks/use-interrupted-actions";
import { Button } from "@/components/ui/button";
import { AlertCircle } from "lucide-react";
import { InterruptInput } from "../../interrupt-input";

export function DefaultInterrupt({ interrupt }: InterruptComponentProps) {
  const {
    handleSubmit,
    handleIgnore,
    humanResponse,
    streaming,
    streamFinished,
    loading,
    supportsMultipleMethods,
    hasEdited,
    hasAddedResponse,
    acceptAllowed,
    setSelectedSubmitType,
    setHumanResponse,
    setHasAddedResponse,
    setHasEdited,
    initialHumanInterruptEditValue,
  } = useInterruptedActions({ interrupt });

  const actionsDisabled = loading || streaming;
  const ignoreAllowed = interrupt.config.allow_ignore;
  const actionTitle = interrupt.action_request.action || "Agent Interrupt";

  return (
    <div className="w-full space-y-6 rounded-xl border border-border bg-background p-6">
      {/* Header */}
      <div className="flex items-start gap-3">
        <div className="flex h-8 w-8 items-center justify-center rounded-full bg-amber-100 text-amber-600">
          <AlertCircle className="h-4 w-4" />
        </div>
        <div className="flex-1">
          <h3 className="text-lg font-semibold text-foreground">
            {actionTitle}
          </h3>
          {interrupt.description && (
            <p className="mt-1 text-sm text-muted-foreground">
              {interrupt.description}
            </p>
          )}
        </div>
      </div>

      {/* Action buttons */}
      {ignoreAllowed && (
        <div className="flex flex-wrap gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={handleIgnore}
            disabled={actionsDisabled}
          >
            Ignore
          </Button>
        </div>
      )}

      {/* Interactive input */}
      <InterruptInput
        interruptValue={interrupt}
        humanResponse={humanResponse}
        streaming={streaming}
        streamFinished={streamFinished}
        supportsMultipleMethods={supportsMultipleMethods}
        acceptAllowed={acceptAllowed}
        hasEdited={hasEdited}
        hasAddedResponse={hasAddedResponse}
        initialValues={initialHumanInterruptEditValue.current}
        setHumanResponse={setHumanResponse}
        setSelectedSubmitType={setSelectedSubmitType}
        setHasAddedResponse={setHasAddedResponse}
        setHasEdited={setHasEdited}
        handleSubmit={handleSubmit}
      />
    </div>
  );
} 