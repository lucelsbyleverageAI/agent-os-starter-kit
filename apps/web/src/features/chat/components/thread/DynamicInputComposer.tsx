import { FormEvent, RefObject, useEffect } from "react";
import { Base64ContentBlock } from "@langchain/core/messages";
import { ProcessingAttachment } from "@/hooks/use-file-upload";
import { useAgentConfig } from "@/hooks/use-agent-config";
import { ChatComposer } from "./ChatComposer";
import { FormInputComposer } from "./FormInputComposer";
import { useAgentsContext } from "@/providers/Agents";
import { useQueryState } from "nuqs";

interface DynamicInputComposerProps {
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
}

export function DynamicInputComposer(props: DynamicInputComposerProps) {
  const { agents } = useAgentsContext();
  const [agentId] = useQueryState("agentId");
  const { inputMode, inputSchema, loading: schemaLoading, getSchemaAndUpdateConfig } = useAgentConfig();

  // Find current agent
  const currentAgent = agents.find(agent => agent.assistant_id === agentId);
  const isN8NAgent = currentAgent?.graph_id === "n8n_agent";

  // Fetch and process schema when agent changes
  useEffect(() => {
    if (currentAgent) {
      getSchemaAndUpdateConfig(currentAgent);
    }
  }, [currentAgent, getSchemaAndUpdateConfig]);

  // Prefer a smooth default: render chat by default while schema loads
  if (schemaLoading || inputMode === 'loading') {
    return <ChatComposer {...props} />;
  }

  // Handle error cases gracefully
  if (!currentAgent) {
    console.warn(`DynamicInputComposer: Agent ${agentId} not found in agents list. Available agents:`, agents.map(a => ({ id: a.assistant_id, name: a.name })));
    return (
      <div className="bg-transparent relative z-10 mb-4 w-full rounded-[2rem] border border-destructive/50">
        <div className="flex items-center justify-center p-6">
          <div className="text-center">
            <p className="text-sm font-medium text-destructive">Agent not found</p>
            <p className="text-xs text-muted-foreground mt-1">
              Please select a valid agent to continue
            </p>
          </div>
        </div>
      </div>
    );
  }

  // If no schema found, default to chat mode with warning
  if (!inputSchema) {
    console.warn(`No input schema found for agent ${agentId} (${currentAgent?.name || 'unknown'}), defaulting to chat mode. Mode: ${inputMode}, Schema loading: ${schemaLoading}`);
    return <ChatComposer {...props} />;
  }

  // Route based on input mode
  switch (inputMode) {
    case 'chat':
      return <ChatComposer {...props} disableUploads={!!isN8NAgent} />;

    case 'chat-with-config':
      // Extract non-message fields from schema
      return (
        <ChatComposer
          {...props}
          disableUploads={!!isN8NAgent}
          inputMode={inputMode}
          inputSchema={inputSchema}
          agentId={agentId || undefined}
        />
      );

    case 'form':
      return (
        <FormInputComposer
          inputSchema={inputSchema}
          chatWidth={props.chatWidth}
          isLoading={props.isLoading}
          onStop={props.onStop}
          hasMessages={props.hasMessages}
        />
      );

    default:
      // Fallback to chat mode for unknown input modes
      return <ChatComposer {...props} disableUploads={!!isN8NAgent} />;
  }
} 