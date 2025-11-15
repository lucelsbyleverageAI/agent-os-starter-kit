"use client";

import React, {
  createContext,
  useContext,
  ReactNode,
  useState,
  useRef,
  useMemo
} from "react";
import { useStream } from "@langchain/langgraph-sdk/react";
import { type Message } from "@langchain/langgraph-sdk";
import {
  uiMessageReducer,
  type UIMessage,
  type RemoveUIMessage,
} from "@langchain/langgraph-sdk/react-ui";
import { useQueryState } from "nuqs";
import Image from "next/image";
import { AgentsCombobox } from "@/components/ui/agents-combobox";
import { useAgentsContext } from "@/providers/Agents";
import { useAuthContext } from "@/providers/Auth";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { getDeployments } from "@/lib/environment/deployments";

export type StateType = { 
  messages: Message[]; 
  ui?: UIMessage[];
  todos?: any[];
  files?: Record<string, any>;
  [key: string]: any; // Allow additional properties for deep agents
};

const useTypedStream = useStream<
  StateType,
  {
    UpdateType: {
      messages?: Message[] | Message | string;
      ui?: (UIMessage | RemoveUIMessage)[] | UIMessage | RemoveUIMessage;
    };
    CustomEventType: UIMessage | RemoveUIMessage;
  }
>;

type StreamContextType = ReturnType<typeof useTypedStream>;
const StreamContext = createContext<StreamContextType | undefined>(undefined);

const StreamSession = ({
  children,
  agentId,
  deploymentId,
  accessToken,
  useProxyRoute,
}: {
  children: ReactNode;
  agentId: string;
  deploymentId: string;
  accessToken?: string;
  useProxyRoute?: boolean;
}) => {
  const deployment = getDeployments().find((d) => d.id === deploymentId);
  if (!deployment) {
    throw new Error(`Deployment ${deploymentId} not found`);
  }

  let deploymentUrl = deployment.deploymentUrl;
  if (useProxyRoute) {
    const baseApiUrl = process.env.NEXT_PUBLIC_BASE_API_URL;
    if (!baseApiUrl) {
      throw new Error(
        "Failed to create client: Base API URL not configured. Please set NEXT_PUBLIC_BASE_API_URL",
      );
    }
    deploymentUrl = `${baseApiUrl}/langgraph/proxy/${deploymentId}`;
  }

  const [threadId, setThreadId] = useQueryState("threadId");

  const streamValue = useTypedStream({
    apiUrl: deploymentUrl,
    assistantId: agentId,
    threadId: threadId ?? null,
    // Note: current SDK options do not expose streamMode; rely on defaults
    onCustomEvent: (event, options) => {
      // Handle n8n streaming chunks emitted from the backend
      if (event && typeof event === "object" && (event as any).n8n_chunk) {
        const chunk = String((event as any).n8n_chunk ?? "");
        if (!chunk) return;
        options.mutate((prev) => {
          const messages = [...(prev.messages ?? [])];
          const last = messages[messages.length - 1];
          if (last && (last as any).role === "assistant") {
            // Append to the existing assistant message with simple de-dupe
            const current = typeof (last as any).content === "string"
              ? String((last as any).content)
              : String((last as any).content ?? "");
            // Skip if the chunk is already a suffix (guards against re-emitted chunks)
            if (!current.endsWith(chunk)) {
              (last as any).content = `${current}${chunk}`;
            }
          } else {
            // Start a new assistant message with the first chunk
            messages.push({ role: "assistant", content: chunk } as any);
          }
          return { ...prev, messages } as any;
        });
        return;
      }

      // Default behaviour: treat custom event as UI message update
      options.mutate((prev) => {
        const ui = uiMessageReducer(prev.ui ?? [], event as any);
        return { ...prev, ui };
      });
    },
    onThreadId: (id) => {
      // Use history.replaceState via nuqs setter to avoid adding a history entry
      setThreadId(id, { history: "replace" as any });
    },
    defaultHeaders: {
      ...(!useProxyRoute
        ? {
            Authorization: `Bearer ${accessToken}`,
            "x-supabase-access-token": accessToken,
          }
        : {
            "x-auth-scheme": "langsmith",
          }),
    },
  });



  return (
    <StreamContext.Provider value={streamValue}>
      {children}
    </StreamContext.Provider>
  );
};

export const StreamProvider: React.FC<{ children: ReactNode }> = ({
  children,
}) => {
  const { agents, loading } = useAgentsContext();
  const [agentId, setAgentId] = useQueryState("agentId");
  const [deploymentId, setDeploymentId] = useQueryState("deploymentId");
  const [threadId] = useQueryState("threadId"); // Get threadId for keying StreamSession
  const [value, setValue] = useState("");
  const [open, setOpen] = useState(false);
  const { session, isLoading: authLoading } = useAuthContext();

  // Track previous threadId to distinguish thread creation from thread switching
  const lastKnownThreadIdRef = useRef<string | null>(threadId);

  // Generate stable key that doesn't change during thread creation (null → id)
  // but DOES change during thread switching (id-A → id-B)
  const streamKey = useMemo(() => {
    const prev = lastKnownThreadIdRef.current;
    const current = threadId;

    // Scenario 1: Thread creation (null → "new-id")
    // Don't change key - let the stream naturally receive the new threadId
    if (prev === null && current !== null) {
      lastKnownThreadIdRef.current = current;
      return 'new-chat';
    }

    // Scenario 2: Thread switch ("old-id" → "new-id")
    // Change key to force remount and prevent race conditions
    if (prev !== null && current !== null && prev !== current) {
      lastKnownThreadIdRef.current = current;
      return current;
    }

    // Scenario 3: New chat (both null or returning to null)
    if (current === null) {
      lastKnownThreadIdRef.current = null;
      return 'new-chat';
    }

    // Scenario 4: Same thread or first render with threadId
    lastKnownThreadIdRef.current = current;
    return current ?? 'new-chat';
  }, [threadId]);

  const handleValueChange = (v: string) => {
    setValue(v);
    setOpen(false);
  };

  const handleStartChat = () => {
    if (!value) {
      toast.info("Please select an agent");
      return;
    }
    const [agentId_, deploymentId_] = value.split(":");
    setAgentId(agentId_);
    setDeploymentId(deploymentId_);
  };

  // Show the form if we: don't have an API URL, or don't have an assistant ID
  if (!agentId || !deploymentId) {
    return (
      <div className="flex h-full w-full items-center justify-center p-4 -mt-8">
        <div className="animate-in fade-in-0 zoom-in-95 bg-background flex min-h-64 max-w-3xl flex-col rounded-lg border shadow-lg">
          <div className="mt-14 flex flex-col gap-2 p-6">
            <div className="flex flex-col items-start gap-2">
              <Image 
                src="/logo_icon_round.png" 
                alt="AgentOS Logo" 
                width={28} 
                height={28} 
              />
              <h1 className="text-xl font-semibold tracking-tight">
                AgentOS
              </h1>
            </div>
            <p className="text-muted-foreground">
              Welcome to AgentOS's chat service! To continue, please select
              an agent to chat with.
            </p>
          </div>
          <div className="mb-24 grid grid-cols-[1fr_auto] gap-4 px-6 pt-4">
            <AgentsCombobox
              disableDeselect
              agents={agents}
              agentsLoading={loading}
              value={value}
              setValue={(v) =>
                Array.isArray(v)
                  ? handleValueChange(v[0])
                  : handleValueChange(v)
              }
              open={open}
              setOpen={setOpen}
              showBorder={true}
            />
            <Button onClick={handleStartChat}>Start Chat</Button>
          </div>
        </div>
      </div>
    );
  }

  const useProxyRoute = process.env.NEXT_PUBLIC_USE_LANGSMITH_AUTH === "true";

  // Respect auth loading state - don't validate while auth is still loading
  if (authLoading) {
    return (
      <div className="flex h-full w-full items-center justify-center">
        <div className="animate-in fade-in-0 zoom-in-95 bg-background flex min-h-32 max-w-md flex-col items-center justify-center rounded-lg border p-6 shadow-lg">
          <div className="flex items-center gap-3">
            <div className="h-4 w-4 animate-spin rounded-full border-2 border-muted-foreground border-t-transparent" />
            <span className="text-sm text-muted-foreground">
              Initialising authentication...
            </span>
          </div>
        </div>
      </div>
    );
  }

  // Only validate after auth has finished loading
  if (!useProxyRoute && !session?.accessToken) {
    return (
      <div className="flex h-full w-full items-center justify-center">
        <div className="animate-in fade-in-0 zoom-in-95 bg-background flex min-h-32 max-w-md flex-col items-center justify-center rounded-lg border p-6 shadow-lg">
          <div className="flex flex-col items-center gap-3">
            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-destructive/10">
              <span className="text-destructive text-sm font-medium">!</span>
            </div>
            <div className="text-center">
              <p className="text-sm font-medium">Authentication Required</p>
              <p className="text-xs text-muted-foreground mt-1">
                Please sign in to continue using the chat service.
              </p>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <StreamSession
      key={streamKey} // Smart key: stable during creation, changes on switch
      agentId={agentId}
      deploymentId={deploymentId}
      accessToken={session?.accessToken ?? undefined}
      useProxyRoute={useProxyRoute}
    >
      {children}
    </StreamSession>
  );
};

// Create a custom hook to use the context
export const useStreamContext = (): StreamContextType => {
  const context = useContext(StreamContext);
  if (context === undefined) {
    throw new Error("useStreamContext must be used within a StreamProvider");
  }
  return context;
};

export default StreamContext;
