import React, { useState } from "react";
import { InterruptComponentProps } from "../index";
import { Button } from "@/components/ui/button";
import { CheckCircle, XCircle, MessageSquare } from "lucide-react";
import { prettifyText } from "@/features/chat/utils/interrupt-utils";
import { HumanResponse } from "../../interrupt-types";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle
} from "@/components/ui/dialog";

export function ToolApprovalInterrupt({
  interrupt,
  onSubmit,
  streaming = false,
  loading = false
}: InterruptComponentProps) {
  const [isRespondDialogOpen, setIsRespondDialogOpen] = useState(false);
  const [responseText, setResponseText] = useState("");
  const actionsDisabled = loading || streaming;

  // Extract tool name from action_request and strip the tool_approval_ prefix
  const toolName = interrupt.action_request?.action || '';
  const actualToolName = toolName.replace(/^tool_approval_/, '');
  const readableToolName = prettifyText(actualToolName);

  // Check which actions are allowed based on config
  const allowAccept = interrupt.config.allow_accept;
  const allowRespond = interrupt.config.allow_respond;
  const allowIgnore = interrupt.config.allow_ignore;

  const handleAccept = async () => {
    const response: HumanResponse = {
      type: "accept",
      args: null
    };
    await onSubmit?.(response);
  };

  const handleIgnore = async () => {
    const response: HumanResponse = {
      type: "ignore",
      args: null
    };
    await onSubmit?.(response);
  };

  const handleOpenRespondDialog = () => {
    setResponseText("");
    setIsRespondDialogOpen(true);
  };

  const handleSendResponse = async () => {
    if (!responseText.trim()) {
      return;
    }

    const response: HumanResponse = {
      type: "response",
      args: responseText
    };
    await onSubmit?.(response);
    setIsRespondDialogOpen(false);
    setResponseText("");
  };

  return (
    <>
      {/* Match the styling and height of DefaultToolCall component */}
      <div className="overflow-hidden rounded-lg border border-yellow-500/30 bg-yellow-500/5">
        <div className="px-4 py-2 flex items-center justify-between gap-3 w-full">
          {/* Left: Approval Text */}
          <div className="flex items-center gap-2 min-w-0 flex-1">
            <span className="text-sm text-muted-foreground">
              Approval request:
            </span>
            <span className="text-sm font-medium text-foreground">
              {readableToolName}
            </span>
          </div>

          {/* Right: Action Buttons in a Row */}
          <div className="flex items-center gap-2 flex-shrink-0">
            {allowAccept && (
              <Button
                variant="default"
                size="sm"
                onClick={handleAccept}
                disabled={actionsDisabled}
              >
                <CheckCircle className="h-3.5 w-3.5 mr-1" />
                Accept
              </Button>
            )}

            {allowIgnore && (
              <Button
                variant="outline"
                size="sm"
                onClick={handleIgnore}
                disabled={actionsDisabled}
              >
                <XCircle className="h-3.5 w-3.5 mr-1" />
                Reject
              </Button>
            )}

            {allowRespond && (
              <Button
                variant="secondary"
                size="sm"
                onClick={handleOpenRespondDialog}
                disabled={actionsDisabled}
              >
                <MessageSquare className="h-3.5 w-3.5 mr-1" />
                Respond
              </Button>
            )}
          </div>
        </div>
      </div>

      {/* Respond Dialog */}
      <Dialog open={isRespondDialogOpen} onOpenChange={setIsRespondDialogOpen}>
        <DialogContent className="sm:max-w-[600px]">
          <DialogHeader>
            <DialogTitle>Respond to Agent</DialogTitle>
            <DialogDescription>
              Provide feedback or alternative instructions to the agent.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <label className="text-sm font-medium">Your Response:</label>
              <Textarea
                value={responseText}
                onChange={(e) => setResponseText(e.target.value)}
                className="min-h-[200px]"
                placeholder="Example: Please use a different search query, or: This tool is not needed, proceed without it..."
                autoFocus
              />
              <p className="text-xs text-muted-foreground">
                The agent will receive your feedback and adjust accordingly.
              </p>
            </div>
          </div>

          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setIsRespondDialogOpen(false)}
            >
              Cancel
            </Button>
            <Button
              onClick={handleSendResponse}
              disabled={actionsDisabled || !responseText.trim()}
            >
              <MessageSquare className="h-4 w-4 mr-1" />
              Send Response
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
