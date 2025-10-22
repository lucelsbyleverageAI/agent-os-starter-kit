import { FormEvent, RefObject, useState } from "react";
import { cn } from "@/lib/utils";
import { getScrollbarClasses } from "@/lib/scrollbar-styles";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { LoaderCircle, Plus, Settings } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { ContentBlocksPreview } from "./messages/ContentBlocksPreview";
import { Base64ContentBlock } from "@langchain/core/messages";
import { ProcessingAttachment } from "@/hooks/use-file-upload";
import { LargeMessageWarningDialog } from "@/components/ui/confirmation-dialog";
import {
  calculateMessageCharacterCount,
  LARGE_MESSAGE_WARNING_THRESHOLD
} from "@/features/chat/utils/content-string";
import { ConfigureInputsDialog } from "./ConfigureInputsDialog";
import { GraphSchema } from "@langchain/langgraph-sdk";
import { InputMode } from "@/types/agent";

interface ChatComposerProps {
  dropRef: RefObject<HTMLDivElement | null>;
  chatWidth: string;
  dragOver: boolean;
  handleSubmit: (e: FormEvent) => void;
  contentBlocks: Base64ContentBlock[];
  processingAttachments: ProcessingAttachment[];
  removeBlock: (idx: number) => void;
  removeProcessingAttachment: (id: string) => void;
  setHasInput: (hasInput: boolean) => void;
  handlePaste: (e: React.ClipboardEvent<HTMLTextAreaElement>) => void;
  hasMessages: boolean;
  hideToolCalls: boolean | null;
  setHideToolCalls: (hide: boolean | null) => void;
  handleFileUpload: (e: React.ChangeEvent<HTMLInputElement>) => void;
  isLoading: boolean;
  hasInput: boolean;
  onStop: () => void;
  // When true, disables uploads (images/documents) and related UI controls
  disableUploads?: boolean;
  // New props for chat-with-config mode
  inputMode?: InputMode;
  inputSchema?: GraphSchema["input_schema"] | null;
  agentId?: string;
}

export function ChatComposer({
  dropRef,
  chatWidth,
  dragOver,
  handleSubmit,
  contentBlocks,
  processingAttachments = [],
  removeBlock,
  removeProcessingAttachment,
  setHasInput,
  handlePaste,
  hasMessages,
  hideToolCalls,
  setHideToolCalls,
  handleFileUpload,
  isLoading,
  hasInput,
  onStop,
  disableUploads = false,
  inputMode,
  inputSchema,
  agentId,
}: ChatComposerProps) {
  const [showSizeWarning, setShowSizeWarning] = useState(false);
  const [pendingSubmission, setPendingSubmission] = useState<{
    event: FormEvent;
    characterCount: number;
  } | null>(null);
  const [showConfigDialog, setShowConfigDialog] = useState(false);

  // Determine if we should show the configure inputs button
  const showConfigButton = inputMode === 'chat-with-config' && inputSchema && agentId;

  // Determine if we should disable the send button
  const hasProcessingAttachments = processingAttachments.some(
    (att) => att.status === "processing"
  );
  const hasErrorAttachments = processingAttachments.some(
    (att) => att.status === "error"
  );
  const shouldDisableSend =
    isLoading ||
    (!hasInput && contentBlocks.length === 0) ||
    hasProcessingAttachments ||
    hasErrorAttachments;

  const handleFormSubmit = (e: FormEvent) => {
    e.preventDefault();
    
    // Get text content from the form
    const form = e.currentTarget as HTMLFormElement;
    const formData = new FormData(form);
    const content = (formData.get("input") as string | undefined)?.trim() ?? "";

    // Check message size and show warning if needed
    const characterCount = calculateMessageCharacterCount(content, contentBlocks);
    
    if (characterCount >= LARGE_MESSAGE_WARNING_THRESHOLD) {
      setPendingSubmission({
        event: e,
        characterCount,
      });
      setShowSizeWarning(true);
      return; // Don't submit yet, wait for user confirmation
    }

    // If no warning needed, proceed with original submit
    handleSubmit(e);
  };

  const handleConfirmLargeMessage = () => {
    setShowSizeWarning(false);
    if (pendingSubmission) {
      // Create a fresh form submission without the warning check
      const form = document.querySelector('form') as HTMLFormElement;
      if (form) {
        const syntheticEvent = {
          preventDefault: () => {},
          currentTarget: form,
        } as unknown as FormEvent;
        handleSubmit(syntheticEvent);
      }
      setPendingSubmission(null);
    }
  };

  const _handleCancelLargeMessage = () => {
    setShowSizeWarning(false);
    setPendingSubmission(null);
  };

  return (
    <div
      ref={dropRef}
      className={cn(
        "bg-transparent relative z-10 mb-4 w-full rounded-[2rem] border border-border transition-all",
        chatWidth,
        dragOver
          ? "border-primary border-2 border-dotted"
          : "border border-solid",
      )}
    >
      <form
        onSubmit={handleFormSubmit}
        className="flex flex-col gap-1 p-2"
      >
        {!disableUploads && (
          <ContentBlocksPreview
            blocks={contentBlocks}
            processingAttachments={processingAttachments}
            onRemove={removeBlock}
            onRemoveProcessing={removeProcessingAttachment}
          />
        )}
        <textarea
          name="input"
          onChange={(e) => setHasInput(!!e.target.value.trim())}
          onPaste={(e) => {
            // Allow normal text paste; only suppress attachment handling
            if (!disableUploads) {
              handlePaste(e);
            }
          }}
          onKeyDown={(e) => {
            if (
              e.key === "Enter" &&
              !e.shiftKey &&
              !e.nativeEvent.isComposing
            ) {
              e.preventDefault();
              const el = e.target as HTMLElement | undefined;
              const form = el?.closest("form");
              form?.requestSubmit();
            }
          }}
          placeholder="Type your message..."
          style={{
            minHeight: hasMessages ? '2.5rem' : '5rem',
            maxHeight: '15rem',
            height: 'auto',
            fieldSizing: 'content'
          } as React.CSSProperties & { fieldSizing?: string }}
          className={cn(
            "resize-none border-none bg-transparent px-3 py-2 pb-0 shadow-none ring-0 outline-none focus:ring-0 focus:outline-none",
            ...getScrollbarClasses('y')
          )}
        />

        <div className="flex items-center justify-between px-3 py-1">
          <div className="flex items-center gap-3">
            {!disableUploads && (
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="ghost" size="icon" className="size-8 text-muted-foreground hover:bg-accent">
                    <Plus className="size-5" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="start" className="w-56">
                  <DropdownMenuItem asChild>
                    <Label
                      htmlFor="file-input"
                      className="flex cursor-pointer items-center p-2"
                    >
                      <span>Upload Document or Image</span>
                    </Label>
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            )}

            {showConfigButton && (
              <Button
                variant="ghost"
                size="icon"
                className="size-8 text-muted-foreground hover:bg-accent"
                onClick={() => setShowConfigDialog(true)}
                type="button"
                title="Configure Additional Inputs"
              >
                <Settings className="size-5" />
              </Button>
            )}

            <div className="flex items-center gap-2">
              <Switch
                id="render-tool-calls"
                checked={hideToolCalls ?? false}
                onCheckedChange={setHideToolCalls}
              />
              <Label
                htmlFor="render-tool-calls"
                className="text-sm text-muted-foreground"
              >
                Hide Tool Calls
              </Label>
            </div>
          </div>
          {!disableUploads && (
            <input
              id="file-input"
              type="file"
              onChange={handleFileUpload}
              multiple
              accept={[
                // Images
                "image/jpeg",
                "image/png",
                "image/gif",
                "image/webp",
                // Documents
                "application/pdf",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "text/plain",
                "text/markdown"
              ].join(",")}
              className="hidden"
            />
          )}
          {isLoading ? (
            <Button
              key="stop"
              onClick={onStop}
              className="ml-auto"
            >
              <LoaderCircle className="h-4 w-4 animate-spin" />
              Cancel
            </Button>
          ) : (
            <Button
              type="submit"
              className="ml-auto shadow-md transition-all"
              disabled={shouldDisableSend}
            >
              {hasProcessingAttachments ? "Processing..." : "Send"}
            </Button>
          )}
        </div>
      </form>
      
      {/* Large Message Warning Dialog */}
      <LargeMessageWarningDialog
        open={showSizeWarning}
        onOpenChange={setShowSizeWarning}
        onConfirm={handleConfirmLargeMessage}
        characterCount={pendingSubmission?.characterCount || 0}

        isLoading={isLoading}
      />

      {/* Configure Inputs Dialog */}
      {showConfigButton && (
        <ConfigureInputsDialog
          open={showConfigDialog}
          onOpenChange={setShowConfigDialog}
          agentId={agentId!}
          inputSchema={inputSchema!}
        />
      )}
    </div>
  );
} 