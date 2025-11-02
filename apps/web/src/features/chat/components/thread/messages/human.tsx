import { Message } from "@langchain/langgraph-sdk";
import { useStreamContext } from "@/features/chat/providers/Stream";
import { useState } from "react";
import { getContentString } from "@/features/chat/utils/content-string";
import { cn } from "@/lib/utils";
import { Textarea } from "@/components/ui/textarea";
import { BranchSwitcher, CommandBar } from "./shared";
import { useQueryState } from "nuqs";
import { useConfigStore } from "@/features/chat/hooks/use-config-store";
import { useAuthContext } from "@/providers/Auth";
import { MultimodalPreview } from "./MultimodalPreview";
import { isBase64ContentBlock } from "@/lib/multimodal-utils";
import { MinimalistBadgeWithText } from "@/components/ui/minimalist-badge";
import { FileText } from "lucide-react";
import { MarkdownText } from "@/components/ui/markdown-text";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { getScrollbarClasses } from "@/lib/scrollbar-styles";
import { ImagePreviewDialog } from "@/components/ui/image-preview-dialog";

function extractTextFromXML(text: string): string {
  const contentMatch = text.match(/<Content>([\s\S]*?)<\/Content>/);
  return contentMatch ? contentMatch[1].trim() : text;
}

interface MinimalistFilePreviewProps {
  block: any;
}

function MinimalistFilePreview({ block }: MinimalistFilePreviewProps) {
  const [isOpen, setIsOpen] = useState(false);
  
  // Extract filename and content
  let filename = "";
  let extractedContent = "";
  
  if (block.metadata?.filename) {
    filename = block.metadata.filename;
  }
  
  if (typeof block.data === "string") {
    // Old format: base64 encoded data
    extractedContent = extractTextFromXML(block.data);
  } else if (block.text && typeof block.text === "string") {
    // New format: text block with XML content
    extractedContent = extractTextFromXML(block.text);
  }
  
  return (
    <Dialog open={isOpen} onOpenChange={setIsOpen}>
      <DialogTrigger asChild>
        <button className="transition-opacity hover:opacity-80">
          <MinimalistBadgeWithText
            icon={FileText}
            text={filename}
            tooltip="Click to view document content"
            className="cursor-pointer"
          />
        </button>
      </DialogTrigger>
      <DialogContent className={cn("!max-w-5xl !w-[80vw] max-h-[90vh] flex flex-col", ...getScrollbarClasses('y'))}>
        <DialogHeader className="flex-shrink-0">
          <DialogTitle className="flex items-center gap-2">
            <FileText className="h-5 w-5" />
            {filename}
          </DialogTitle>
        </DialogHeader>
        <div className={cn("flex-1 min-h-0 overflow-y-auto pr-4", ...getScrollbarClasses('y'))}>
          <MarkdownText>{extractedContent}</MarkdownText>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function EditableContent({
  value,
  setValue,
  onSubmit,
}: {
  value: string;
  setValue: React.Dispatch<React.SetStateAction<string>>;
  onSubmit: () => void;
}) {
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
      e.preventDefault();
      onSubmit();
    }
  };

  return (
    <Textarea
      value={value}
      onChange={(e) => setValue(e.target.value)}
      onKeyDown={handleKeyDown}
      className="focus-visible:ring-0"
    />
  );
}

export function HumanMessage({
  message,
  isLoading,
}: {
  message: Message;
  isLoading: boolean;
}) {
  const { session } = useAuthContext();
  const [agentId] = useQueryState("agentId");

  const thread = useStreamContext();
  const meta = thread.getMessagesMetadata(message);
  const parentCheckpoint = meta?.firstSeenState?.parent_checkpoint;

  const [isEditing, setIsEditing] = useState(false);
  const [value, setValue] = useState("");
  const [previewImage, setPreviewImage] = useState<{url: string, title: string} | null>(null);
  const contentString = getContentString(message.content);

  const handleSubmitEdit = () => {
    if (!agentId) return;

    setIsEditing(false);

    const newMessage: Message = { type: "human", content: value };
    const { getAgentConfig } = useConfigStore.getState();

    thread.submit(
      { messages: [newMessage] },
      {
        checkpoint: parentCheckpoint,
        streamMode: ["values"],
        optimisticValues: (prev: { messages?: Message[] }) => {
          const values = meta?.firstSeenState?.values;
          if (!values) return prev;

          return {
            ...values,
            messages: [...(values.messages.slice(0, -1) ?? []), newMessage],
          };
        },
        config: {
          configurable: getAgentConfig(agentId),
        },
        metadata: {
          supabaseAccessToken: session?.accessToken,
        },
        streamSubgraphs: true,
      },
    );
  };

  return (
    <div
      className={cn(
        "group ml-auto flex items-center gap-2 max-w-[70%]",
        isEditing && "w-full",
      )}
    >
      <div className={cn("flex flex-col gap-2", isEditing && "w-full")}>
        {isEditing ? (
          <EditableContent
            value={value}
            setValue={setValue}
            onSubmit={handleSubmitEdit}
          />
        ) : (
          <div className="flex flex-col gap-2">
            {/* Render images and files if no text */}
            {Array.isArray(message.content) && message.content.length > 0 && (
              <div className="flex flex-wrap items-end justify-end gap-2">
                {message.content.reduce<React.ReactNode[]>(
                  (acc, block, idx) => {
                    if (isBase64ContentBlock(block)) {
                      // Handle extracted text content with minimalist preview
                      if ((block as any).metadata?.extracted_text) {
                        acc.push(
                          <MinimalistFilePreview
                            key={idx}
                            block={block}
                          />
                        );
                      } else {
                        // Regular file or image preview using MultimodalPreview
                        acc.push(
                          <MultimodalPreview
                            key={idx}
                            block={block}
                            size="md"
                            expandable={true}
                            onExpand={(url, title) => setPreviewImage({ url, title })}
                          />
                        );
                      }
                    }
                    return acc;
                  },
                  [],
                )}
              </div>
            )}
            {/* Render text if present */}
            {contentString ? (
              <p className="bg-muted ml-auto w-fit rounded-3xl px-4 py-2 text-left whitespace-pre-wrap">
                {contentString}
              </p>
            ) : null}
          </div>
        )}

        <div
          className={cn(
            "ml-auto flex items-center gap-2 transition-opacity",
            "opacity-0 group-focus-within:opacity-100 group-hover:opacity-100",
            isEditing && "opacity-100",
          )}
        >
          <BranchSwitcher
            branch={meta?.branch}
            branchOptions={meta?.branchOptions}
            onSelect={(branch) => thread.setBranch(branch)}
            isLoading={isLoading}
          />
          <CommandBar
            isLoading={isLoading}
            content={contentString}
            isEditing={isEditing}
            setIsEditing={(c) => {
              if (c) {
                setValue(contentString);
              }
              setIsEditing(c);
            }}
            handleSubmitEdit={handleSubmitEdit}
            isHumanMessage={true}
          />
        </div>
      </div>

      {previewImage && (
        <ImagePreviewDialog
          open={!!previewImage}
          onOpenChange={(open) => !open && setPreviewImage(null)}
          imageUrl={previewImage.url}
          title={previewImage.title}
        />
      )}
    </div>
  );
}
