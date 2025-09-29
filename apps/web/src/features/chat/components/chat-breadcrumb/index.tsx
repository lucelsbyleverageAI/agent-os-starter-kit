"use client";

import { useQueryState } from "nuqs";
import { AgentsCombobox } from "@/components/ui/agents-combobox";
import { useAgentsContext } from "@/providers/Agents";
import { useState, useCallback } from "react";
import { NewThreadButton } from "../thread/NewThreadButton";

export function ChatBreadcrumb() {
  const { agents, loading } = useAgentsContext();
  const [open, setOpen] = useState(false);

  const [agentId, setAgentId] = useQueryState("agentId");
  const [deploymentId, setDeploymentId] = useQueryState("deploymentId");
  const [threadId, setThreadId] = useQueryState("threadId");

  // Use threadId to determine if there are messages (threadId indicates active conversation)
  const hasMessages = !!threadId;

  const onAgentChange = useCallback(
    (v: string | string[] | undefined) => {
      const nextValue = Array.isArray(v) ? v[0] : v;
      if (!nextValue) return;

      const [agentId, deploymentId] = nextValue.split(":");
      setAgentId(agentId);
      setDeploymentId(deploymentId);
      setThreadId(null);
    },
    [setAgentId, setDeploymentId, setThreadId],
  );

  const agentValue =
    agentId && deploymentId ? `${agentId}:${deploymentId}` : undefined;

  // Only show the agent selector if there's an active agent
  if (!agentId || !deploymentId) {
    return null;
  }

  return (
    <div className="flex items-center gap-2">
      <AgentsCombobox
        agents={agents}
        agentsLoading={loading}
        value={agentValue}
        setValue={onAgentChange}
        open={open}
        setOpen={setOpen}
        className="min-w-auto"
        header={
          <div className="text-secondary-foreground bg-secondary flex gap-2 p-3 pr-10 pb-3 text-xs">
            <span className="text-secondary-foreground mb-[1px] text-xs">
              Selecting a different agent will create a new thread.
            </span>
          </div>
        }
      />
      {hasMessages && <NewThreadButton hasMessages={hasMessages} />}
    </div>
  );
}
