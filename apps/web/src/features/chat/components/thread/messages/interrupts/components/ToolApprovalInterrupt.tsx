import React, { useState } from "react";
import { InterruptComponentProps } from "../index";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { CheckCircle, XCircle, MessageSquare, Edit, ChevronDown, ChevronRight, ShieldAlert } from "lucide-react";
import { MinimalistBadge } from "@/components/ui/minimalist-badge";
import { prettifyText } from "@/features/chat/utils/interrupt-utils";
import { HumanResponse } from "../../interrupt-types";
import { MarkdownText } from "@/components/ui/markdown-text";
import { cn } from "@/lib/utils";
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
  const [isExpanded, setIsExpanded] = useState(true); // Expanded by default for approval
  const [isEditDialogOpen, setIsEditDialogOpen] = useState(false);
  const [isRespondDialogOpen, setIsRespondDialogOpen] = useState(false);
  const [editedArgs, setEditedArgs] = useState<string>(
    JSON.stringify(interrupt.action_request.args, null, 2)
  );
  const [responseText, setResponseText] = useState("");
  const actionsDisabled = loading || streaming;

  // Extract tool name from action_request
  const toolName = interrupt.action_request.action;
  const readableToolName = prettifyText(toolName);
  const toolArgs = interrupt.action_request.args;

  // Check which actions are allowed based on config
  const allowAccept = interrupt.config.allow_accept;
  const allowEdit = interrupt.config.allow_edit;
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

  const handleOpenEditDialog = () => {
    setEditedArgs(JSON.stringify(toolArgs, null, 2));
    setIsEditDialogOpen(true);
  };

  const handleSaveEdit = async () => {
    try {
      const parsedArgs = JSON.parse(editedArgs);
      const response: HumanResponse = {
        type: "edit",
        args: {
          action: toolName,
          args: parsedArgs
        }
      };
      await onSubmit?.(response);
      setIsEditDialogOpen(false);
    } catch (error) {
      console.error("Invalid JSON in edited arguments", error);
      alert("Invalid JSON. Please check your edits.");
    }
  };

  const handleOpenRespondDialog = () => {
    setResponseText("");
    setIsRespondDialogOpen(true);
  };

  const handleSendResponse = async () => {
    if (!responseText.trim()) {
      alert("Please enter a response message.");
      return;
    }

    const response: HumanResponse = {
      type: "response",
      args: responseText
    };
    await onSubmit?.(response);
    setIsRespondDialogOpen(false);
  };

  const toggleExpanded = () => {
    setIsExpanded(!isExpanded);
  };

  return (
    <>
      <Card className={cn(
        "overflow-hidden relative group transition-all duration-300 ease-out py-0 gap-0",
        "border-2 border-yellow-500/30 bg-yellow-500/5",
        "hover:border-yellow-500 hover:shadow-lg hover:shadow-yellow-500/10 vibrate-on-hover"
      )}>
        {/* Main Content Row */}
        <div
          className="px-4 py-3 cursor-pointer flex items-center justify-between gap-3 w-full min-h-0"
          onClick={toggleExpanded}
        >
          <div className="flex items-center gap-3 min-w-0 flex-1">
            {/* Approval Required Badge */}
            <MinimalistBadge
              icon={ShieldAlert}
              tooltip="Tool Approval Required"
              className="bg-yellow-500/20 text-yellow-600 dark:text-yellow-400 hover:bg-yellow-500/30"
            />

            {/* Title */}
            <div className="text-sm font-medium text-foreground min-w-0 flex-1">
              <span className="truncate">
                Approval required for tool: <span className="font-semibold text-yellow-600 dark:text-yellow-400">{readableToolName}</span>
              </span>
            </div>

            {/* Expand/Collapse Icon */}
            <div className="flex-shrink-0">
              {isExpanded ? (
                <ChevronDown className="h-4 w-4 text-muted-foreground" />
              ) : (
                <ChevronRight className="h-4 w-4 text-muted-foreground" />
              )}
            </div>
          </div>

          {/* Action Buttons - Only show primary actions in collapsed state */}
          {!isExpanded && (
            <div className="flex items-center gap-2 flex-shrink-0" onClick={(e) => e.stopPropagation()}>
              {allowAccept && (
                <Button
                  variant="default"
                  size="sm"
                  onClick={handleAccept}
                  disabled={actionsDisabled}
                >
                  <CheckCircle className="h-4 w-4 mr-1" />
                  Approve
                </Button>
              )}
              {allowIgnore && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleIgnore}
                  disabled={actionsDisabled}
                >
                  <XCircle className="h-4 w-4 mr-1" />
                  Deny
                </Button>
              )}
            </div>
          )}
        </div>

        {/* Expandable Details */}
        {isExpanded && (
          <div className="px-4 pb-4 border-t border-border/50 space-y-4">
            {/* Description */}
            {interrupt.description && (
              <div className="pt-3">
                <MarkdownText className="text-sm text-muted-foreground leading-relaxed">
                  {interrupt.description}
                </MarkdownText>
              </div>
            )}

            {/* Tool Arguments */}
            <div className="space-y-2">
              <h4 className="text-sm font-medium text-foreground">Tool Arguments:</h4>
              <pre className="text-xs bg-muted p-3 rounded-md overflow-x-auto max-h-64 overflow-y-auto">
                {JSON.stringify(toolArgs, null, 2)}
              </pre>
            </div>

            {/* Action Buttons - All options in expanded state */}
            <div className="flex flex-wrap items-center gap-2 pt-2">
              {allowAccept && (
                <Button
                  variant="default"
                  size="sm"
                  onClick={handleAccept}
                  disabled={actionsDisabled}
                  className="flex-shrink-0"
                >
                  <CheckCircle className="h-4 w-4 mr-1" />
                  Approve
                </Button>
              )}

              {allowEdit && (
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={handleOpenEditDialog}
                  disabled={actionsDisabled}
                  className="flex-shrink-0"
                >
                  <Edit className="h-4 w-4 mr-1" />
                  Edit & Approve
                </Button>
              )}

              {allowRespond && (
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={handleOpenRespondDialog}
                  disabled={actionsDisabled}
                  className="flex-shrink-0"
                >
                  <MessageSquare className="h-4 w-4 mr-1" />
                  Respond
                </Button>
              )}

              {allowIgnore && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleIgnore}
                  disabled={actionsDisabled}
                  className="flex-shrink-0"
                >
                  <XCircle className="h-4 w-4 mr-1" />
                  Deny
                </Button>
              )}
            </div>
          </div>
        )}

        {/* Loading state overlay */}
        {streaming && (
          <div className="px-4 pb-2 border-t border-border/50">
            <div className="flex items-center gap-2 text-xs text-muted-foreground pt-2">
              <div className="h-1 w-1 animate-pulse rounded-full bg-primary"></div>
              Processing your response...
            </div>
          </div>
        )}
      </Card>

      {/* Edit Arguments Dialog */}
      <Dialog open={isEditDialogOpen} onOpenChange={setIsEditDialogOpen}>
        <DialogContent className="sm:max-w-[600px]">
          <DialogHeader>
            <DialogTitle>Edit Tool Arguments</DialogTitle>
            <DialogDescription>
              Modify the arguments for <span className="font-semibold">{readableToolName}</span> and approve the modified call.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <label className="text-sm font-medium">Arguments (JSON):</label>
              <Textarea
                value={editedArgs}
                onChange={(e) => setEditedArgs(e.target.value)}
                className="font-mono text-sm min-h-[300px]"
                placeholder='{"key": "value"}'
              />
              <p className="text-xs text-muted-foreground">
                Edit the JSON arguments above. The tool will be called with these modified arguments.
              </p>
            </div>
          </div>

          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setIsEditDialogOpen(false)}
            >
              Cancel
            </Button>
            <Button
              onClick={handleSaveEdit}
              disabled={actionsDisabled}
            >
              <CheckCircle className="h-4 w-4 mr-1" />
              Save & Approve
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Respond Dialog */}
      <Dialog open={isRespondDialogOpen} onOpenChange={setIsRespondDialogOpen}>
        <DialogContent className="sm:max-w-[600px]">
          <DialogHeader>
            <DialogTitle>Send Response to Agent</DialogTitle>
            <DialogDescription>
              Provide feedback to the agent about why you're denying the <span className="font-semibold">{readableToolName}</span> tool call.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <label className="text-sm font-medium">Your Response:</label>
              <Textarea
                value={responseText}
                onChange={(e) => setResponseText(e.target.value)}
                className="min-h-[150px]"
                placeholder="Explain to the agent why this tool call is not appropriate or suggest an alternative approach..."
              />
              <p className="text-xs text-muted-foreground">
                The agent will receive this feedback as a tool message and can adjust its approach.
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
              disabled={actionsDisabled}
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
