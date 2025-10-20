"use client";

import React, { useEffect, forwardRef, ForwardedRef, useState } from "react";
import { Save, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  ConfigField,
  ConfigFieldAgents,
  ConfigFieldRAG,
  ConfigFieldTool,
} from "@/features/chat/components/configuration-sidebar/config-field";
import { ConfigSection } from "@/features/chat/components/configuration-sidebar/config-section";
import { useConfigStore } from "@/features/chat/hooks/use-config-store";
import { cn } from "@/lib/utils";
import { useQueryState } from "nuqs";
import { Skeleton } from "@/components/ui/skeleton";
import { useAgents } from "@/hooks/use-agents";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { notify } from "@/utils/toast";
import { agentMessages } from "@/utils/toast-messages";
import _ from "lodash";
import { toast } from "sonner";
import { useMCPContext } from "@/providers/MCP";
import { Search } from "@/components/ui/tool-search";
import { useSearchTools } from "@/hooks/use-search-tools";
import { useFetchPreselectedTools } from "@/hooks/use-fetch-preselected-tools";
import { ConfigToolkitSelector } from "./config-toolkit-selector";
import { useAgentConfig } from "@/hooks/use-agent-config";
import { useAgentsContext } from "@/providers/Agents";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { canUserEditAssistant } from "@/lib/agent-utils";
import { useAuthContext } from "@/providers/Auth";
import { getScrollbarClasses } from "@/lib/scrollbar-styles";
import { AGENT_TAG_GROUPS, getTagLabel } from "@/lib/agent-tags";
import {
  Command,
  CommandEmpty,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { Badge } from "@/components/ui/badge";
import { X, Check } from "lucide-react";


function NameAndDescriptionAlertDialog({
  name,
  setName,
  description,
  setDescription,
  open,
  setOpen,
  handleSave,
}: {
  name: string;
  setName: (name: string) => void;
  description: string;
  setDescription: (description: string) => void;
  open: boolean;
  setOpen: (open: boolean) => void;
  handleSave: () => void;
}) {
  const handleSaveAgent = () => {
    setOpen(false);
    handleSave();
  };
  return (
    <AlertDialog
      open={open}
      onOpenChange={setOpen}
    >
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Agent Name and Description</AlertDialogTitle>
          <AlertDialogDescription>
            Please give your new agent a name and optional description.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <div className="flex flex-col gap-4 p-4">
          <div className="flex flex-col gap-2">
            <Label htmlFor="name">Name</Label>
            <Input
              placeholder="Agent Name"
              id="name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              autoFocus
            />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="description">Description</Label>
            <Input
              placeholder="Agent Description"
              id="description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>
        </div>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction onClick={handleSaveAgent}>
            Submit
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

export interface AIConfigPanelProps {
  className?: string;
  open: boolean;
  setOpen?: (open: boolean) => void;
}

export const ConfigurationSidebar = forwardRef<
  HTMLDivElement,
  AIConfigPanelProps
>(({ className, open, setOpen }, ref: ForwardedRef<HTMLDivElement>) => {
  const { configsByAgentId: _configsByAgentId, resetConfig } = useConfigStore();
  const store = useConfigStore();
  const { tools, setTools, getTools, cursor } = useMCPContext();
  const [agentId] = useQueryState("agentId");
  const [deploymentId] = useQueryState("deploymentId");
  const [threadId] = useQueryState("threadId");
  const { agents, refreshAgentsLoading, refreshAgents, invalidateAssistantListCache } = useAgentsContext();
  const { session, isLoading: authLoading } = useAuthContext();
  const {
    getSchemaAndUpdateConfig,
    configurations,
    toolConfigurations,
    ragConfigurations,
    agentsConfigurations,
    loading,
    supportedConfigs,
  } = useAgentConfig();
  const { updateAgent, createAgent } = useAgents();

  const [newName, setNewName] = useState("");
  const [newDescription, setNewDescription] = useState("");
  const [tags, setTags] = useState<string[]>([]);
  const [
    openNameAndDescriptionAlertDialog,
    setOpenNameAndDescriptionAlertDialog,
  ] = useState(false);

  const { toolSearchTerm, debouncedSetSearchTerm } =
    useSearchTools(tools, {
      preSelectedTools: toolConfigurations[0]?.default?.tools,
    });
  const { loadingMore, setLoadingMore } = useFetchPreselectedTools({
    tools,
    setTools,
    getTools,
    cursor,
    toolConfigurations,
    searchTerm: toolSearchTerm,
  });

  useEffect(() => {
    if (
      !agentId ||
      !deploymentId ||
      loading ||
      !agents?.length ||
      refreshAgentsLoading ||
      authLoading ||
      !session?.accessToken
    )
      return;

    const selectedAgent = agents.find(
      (a) => a.assistant_id === agentId && a.deploymentId === deploymentId,
    );
    if (!selectedAgent) {
      const message = agentMessages.config.fetchError();
      notify.error(message.title, {
        description: message.description,
        key: message.key,
      });
      return;
    }

    // Load tags from selected agent
    setTags(selectedAgent.tags || []);

    // Load schema + defaults
    getSchemaAndUpdateConfig(selectedAgent).catch(() => {});
  }, [open, agentId, deploymentId, agents, refreshAgentsLoading, authLoading, session?.accessToken]);

  const handleSave = async () => {
    
    if (!agentId || !deploymentId || !agents?.length) {
      console.warn(`❌ [ConfigSidebar] Early return - missing data:`, {
        agentId,
        deploymentId,
        agentsLength: agents?.length
      });
      return;
    }
    
    const selectedAgent = agents.find(
      (a) => a.assistant_id === agentId && a.deploymentId === deploymentId,
    );
  
    
    if (!selectedAgent) {
      console.error(`❌ [ConfigSidebar] Agent not found in agents list`);
      toast.error("Failed to save config.", {
        richColors: true,
        description: "Unable to find selected agent.",
      });
      return;
    }
    // If user cannot edit this assistant (default or insufficient permission), branch to create flow
    if (!canUserEditAssistant(selectedAgent) && !newName) {
      setOpenNameAndDescriptionAlertDialog(true);
      return;
    } else if (!canUserEditAssistant(selectedAgent) && newName) {
      const completeConfig = store.getAgentConfig(agentId);
      const result = await createAgent(deploymentId, selectedAgent.graph_id, {
        name: newName,
        description: newDescription,
        config: completeConfig,
        tags: tags || [],
      });
      const newAgent = result.ok ? result.data : null;
      if (!newAgent) {
        toast.error("Failed to create agent", { richColors: true });
        return;
      }

      toast.success("Agent created successfully!");

      // Invalidate caches to ensure fresh data on next access
      try {
        
        // Invalidate assistant list cache (Layer 2) to refresh the agents list
        invalidateAssistantListCache();
        
        // Wait a moment for the initial sync, then refresh
        await new Promise(resolve => setTimeout(resolve, 1000));
        
        // Trigger refresh of agents list to get updated data from mirror
        await refreshAgents(true);
        
      } catch (cacheError) {
        console.warn("Cache invalidation failed:", cacheError);
        // Don't block the user flow if cache invalidation fails
      }

      const newQueryParams = new URLSearchParams({
        agentId: newAgent.assistant_id,
        deploymentId,
        ...(threadId ? { threadId } : {}),
      });
      window.location.href = `/?${newQueryParams.toString()}`;
      return;
    }

    const completeConfig = store.getAgentConfig(agentId);


    const result = await updateAgent(agentId, deploymentId, {
      name: selectedAgent.name,
      description: selectedAgent.description,
      config: completeConfig,
      tags: tags || [],
      metadata: selectedAgent.metadata || undefined,
    });
    

    
    if (!result.ok) {
      console.error(`❌ [ConfigSidebar] Update agent failed:`, result);
      const message = agentMessages.config.saveError();
      notify.error(message.title, {
        description: message.description,
        key: message.key,
      });
      return;
    }

    const message = agentMessages.config.saveSuccess();
    notify.success(message.title, {
      description: message.description,
      key: message.key,
    });

    // Invalidate caches and refresh immediately (no polling)
    try {
      invalidateAssistantListCache();
      await refreshAgents(true);
    } catch (cacheError) {
      console.warn("Cache invalidation failed:", cacheError);
    }
  };

  return (
    <div
      ref={ref}
      data-slot="configuration-sidebar"
      className={cn(
        "fixed top-0 right-0 z-10 h-screen border-l bg-background dark:bg-background shadow-lg transition-all duration-300",
        open ? "w-80 md:w-[36rem]" : "w-0 overflow-hidden border-l-0",
        className,
      )}
    >
      {open && (
        <div className="flex h-full flex-col min-w-0">
          <div className="flex flex-shrink-0 items-center justify-between border-b p-4 min-w-0">
            <h2 className="text-lg font-semibold tracking-tight truncate">Agent Configuration</h2>
            <div className="flex gap-2 items-center flex-shrink-0">
              <TooltipProvider>
                <Tooltip delayDuration={200}>
                  <TooltipTrigger asChild>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => {
                        if (!agentId) return;
                        resetConfig(agentId);
                      }}
                    >
                      <Trash2 className="mr-1 h-4 w-4" />
                      Reset
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent>
                    <p>Reset the configuration to the last saved state</p>
                  </TooltipContent>
                </Tooltip>

                <Tooltip delayDuration={200}>
                  <TooltipTrigger asChild>
                    <Button
                      size="sm"
                      onClick={handleSave}
                    >
                      <Save className="mr-1 h-4 w-4" />
                      Save
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent>
                    <p>Save your changes to the agent</p>
                  </TooltipContent>
                </Tooltip>
              </TooltipProvider>
              {setOpen && (
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => setOpen(false)}
                  className="h-8 w-8"
                >
                  <X className="h-4 w-4" />
                  <span className="sr-only">Close configuration</span>
                </Button>
              )}
            </div>
          </div>
          <Tabs
            defaultValue="general"
            className="flex flex-1 flex-col min-h-0"
          >
            <div className="flex justify-center px-6 pt-4 pb-3 border-b">
              <TabsList variant="branded" className="w-fit flex-shrink-0">
                <TabsTrigger value="general">
                  General
                </TabsTrigger>
                {supportedConfigs.includes("tools") && (
                  <TabsTrigger value="tools">
                    Tools
                  </TabsTrigger>
                )}
                {supportedConfigs.includes("rag") && (
                  <TabsTrigger value="rag">
                    Knowledge
                  </TabsTrigger>
                )}
                {supportedConfigs.includes("supervisor") && (
                  <TabsTrigger value="supervisor">
                    Sub-Agents
                  </TabsTrigger>
                )}
              </TabsList>
            </div>

            <div className={cn("flex-1 min-h-0", ...getScrollbarClasses('y'))}>
              <div className="px-6">

              <TabsContent
                value="general"
                className="m-0 pb-4 pt-2"
              >
                <ConfigSection title="Tags">
                  <div className="flex flex-col items-start justify-start gap-2 min-w-0 w-full">
                    <Label htmlFor="agent_tags">
                      Select categories for your agent
                    </Label>

                    {/* Selected tags display */}
                    {tags.length > 0 && (
                      <div className="flex flex-wrap gap-2">
                        {tags.map((tag) => (
                          <Badge
                            key={tag}
                            variant="secondary"
                            className="gap-1"
                          >
                            {getTagLabel(tag)}
                            <X
                              className="h-3 w-3 cursor-pointer hover:text-destructive"
                              onClick={() => setTags(tags.filter((t) => t !== tag))}
                            />
                          </Badge>
                        ))}
                      </div>
                    )}

                    {/* Multi-select dropdown */}
                    <Popover>
                      <PopoverTrigger asChild>
                        <Button
                          variant="outline"
                          role="combobox"
                          className="w-full justify-between truncate"
                        >
                          <span className="truncate">
                            {tags.length > 0
                              ? `${tags.length} tag${tags.length > 1 ? 's' : ''} selected`
                              : "Select tags..."}
                          </span>
                        </Button>
                      </PopoverTrigger>
                      <PopoverContent className="w-full max-w-[350px] p-0" align="start">
                        <Command className="h-auto max-h-[350px]">
                          <CommandInput placeholder="Search tags..." />
                          <CommandEmpty>No tags found.</CommandEmpty>
                          <CommandList className={cn("max-h-[300px]", ...getScrollbarClasses('y'))}>
                            {Object.entries(AGENT_TAG_GROUPS).map(([category, tagList]) => (
                              <React.Fragment key={category}>
                                {/* Category Header */}
                                <div className="px-3 py-2 text-sm font-medium text-foreground">
                                  {category}
                                </div>

                                {/* Tags in this category */}
                                {tagList.map((tag) => (
                                  <CommandItem
                                    key={tag.value}
                                    value={tag.label}
                                    onSelect={() => {
                                      if (tags.includes(tag.value)) {
                                        setTags(tags.filter((t) => t !== tag.value));
                                      } else {
                                        setTags([...tags, tag.value]);
                                      }
                                    }}
                                  >
                                    <div className="flex items-center gap-2 flex-1 min-w-0">
                                      <div className={`flex h-4 w-4 items-center justify-center rounded-sm border ${
                                        tags.includes(tag.value)
                                          ? "bg-primary border-primary text-primary-foreground"
                                          : "border-muted-foreground"
                                      }`}>
                                        {tags.includes(tag.value) && (
                                          <Check className="h-3 w-3" />
                                        )}
                                      </div>
                                      <div className="flex flex-col flex-1 min-w-0">
                                        <span className="text-sm font-medium">{tag.label}</span>
                                        <span className="text-xs text-muted-foreground line-clamp-2">
                                          {tag.description}
                                        </span>
                                      </div>
                                    </div>
                                  </CommandItem>
                                ))}
                              </React.Fragment>
                            ))}
                          </CommandList>
                        </Command>
                      </PopoverContent>
                    </Popover>
                  </div>
                </ConfigSection>

                <ConfigSection title="Configuration" className="min-w-0">
                  {loading || !agentId ? (
                    <div className="space-y-4">
                      <Skeleton className="h-8 w-full" />
                      <Skeleton className="h-8 w-full" />
                      <Skeleton className="h-8 w-full" />
                    </div>
                  ) : (() => {
                    if (configurations.length > 0) {
                      return configurations.map((c, index) => (
                        <ConfigField
                          key={`${c.label}-${index}`}
                          id={c.label}
                          label={c.label}
                          type={
                            c.type === "boolean" ? "switch" : (c.type ?? "text")
                          }
                          description={c.description}
                          placeholder={c.placeholder}
                          options={c.options}
                          min={c.min}
                          max={c.max}
                          step={c.step}
                          agentId={agentId}
                        />
                      ));
                    }

                    // Fallback: derive fields from store when config schema UI is empty but store has defaults
                    const storeDefaults = (_configsByAgentId?.[agentId] || {}) as Record<string, any>;
                    const keys = Object.keys(storeDefaults).filter((k) => k !== "__defaultValues");
                    if (keys.length === 0) {
                      return (
                        <p className="text-sm text-muted-foreground">No configuration available for this agent.</p>
                      );
                    }
                    return keys.map((key, index) => {
                      const val = storeDefaults[key];
                      let type: "text" | "textarea" | "number" | "switch" | "slider" | "select" | "json" = "text";
                      if (typeof val === "boolean") type = "switch";
                      else if (typeof val === "number") type = "number";
                      else if (val && typeof val === "object") type = "json";
                      return (
                        <ConfigField
                          key={`${key}-fallback-${index}`}
                          id={key}
                          label={key}
                          type={type}
                          agentId={agentId}
                        />
                      );
                    });
                  })()}
                </ConfigSection>
              </TabsContent>

              {supportedConfigs.includes("tools") && (
                <TabsContent
                  value="tools"
                  className="m-0 pb-4 pt-2 space-y-6"
                >
                  <ConfigSection title="Available Tools">
                    <Search
                      onSearchChange={debouncedSetSearchTerm}
                      placeholder="Search toolkits and tools..."
                    />
                    <div className={cn("flex-1 rounded-md", ...getScrollbarClasses('y'))}>
                      {agentId && toolConfigurations[0]?.label ? (
                        <ConfigFieldTool
                          key={`toolkit-selector-${toolConfigurations[0].label}`}
                          id="toolkit-selector"
                          label="toolkit-selector"
                          description=""
                          agentId={agentId}
                          toolId={toolConfigurations[0].label}
                          renderCustom={(value, onChange) => (
                            <ConfigToolkitSelector
                              toolkits={tools.length > 0 ? 
                                // Group tools by toolkit for the selector
                                Object.values(
                                  tools.reduce((acc, tool) => {
                                    const toolkitName = tool.toolkit || 'Other';
                                    const toolkitDisplayName = tool.toolkit_display_name || toolkitName;
                                    
                                    if (!acc[toolkitName]) {
                                      acc[toolkitName] = {
                                        name: toolkitName,
                                        display_name: toolkitDisplayName,
                                        count: 0,
                                        tools: [],
                                      };
                                    }
                                    
                                    acc[toolkitName].tools.push(tool);
                                    acc[toolkitName].count = acc[toolkitName].tools.length;
                                    
                                    return acc;
                                  }, {} as Record<string, any>)
                                ) : []
                              }
                              value={value}
                              onChange={onChange}
                              searchTerm={toolSearchTerm}
                            />
                          )}
                        />
                      ) : !agentId ? (
                        <p className="mt-4 text-center text-sm text-muted-foreground">
                          Select an agent to see tools.
                        </p>
                      ) : (
                        <p className="mt-4 text-center text-sm text-muted-foreground">
                          No tools available for this agent.
                        </p>
                      )}
                      {cursor && !toolSearchTerm && (
                        <div className="flex justify-center py-4">
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={async () => {
                              try {
                                setLoadingMore(true);
                                const moreTool = await getTools(cursor);
                                setTools((prevTools) => [
                                  ...prevTools,
                                  ...moreTool,
                                ]);
                              } catch (error) {
                                console.error(
                                  "Failed to load more tools:",
                                  error,
                                );
                              } finally {
                                setLoadingMore(false);
                              }
                            }}
                            disabled={loadingMore || loading}
                          >
                            {loadingMore ? "Loading..." : "Load More Tools"}
                          </Button>
                        </div>
                      )}
                    </div>
                  </ConfigSection>
                </TabsContent>
              )}

              {supportedConfigs.includes("rag") && (
                <TabsContent
                  value="rag"
                  className="m-0 pb-4 pt-2 space-y-6"
                >
                  <ConfigSection title="Collections">
                    {agentId && ragConfigurations[0]?.label && (
                      <ConfigFieldRAG
                        id={ragConfigurations[0].label}
                        label={ragConfigurations[0].label}
                        agentId={agentId}
                      />
                    )}
                  </ConfigSection>
                  
                  <ConfigSection title="Document Tools">
                    {agentId && ragConfigurations[0]?.label && ragConfigurations[0].toolGroupsMetadata?.tool_groups && (
                      <div className="w-full">
                        {(() => {
                          // Use tool groups from backend schema
                          const toolGroups = ragConfigurations[0].toolGroupsMetadata?.tool_groups || [];
                          
                          // Convert tool groups into toolkit structure for ConfigToolkitSelector
                          const ragToolkits = toolGroups.map(group => ({
                            name: group.name.toLowerCase().replace(/\s+/g, '_'),
                            display_name: group.name,
                            count: group.tools.length,
                            tools: group.tools.map(tool => ({
                              name: tool.name,
                              description: tool.description,
                              toolkit: group.name.toLowerCase().replace(/\s+/g, '_'),
                              toolkit_display_name: group.name,
                              inputSchema: { type: "object" as const },
                            })),
                          }));
                          
                          // Get currently selected tools from RAG config
                          const ragConfig = store.configsByAgentId[`${agentId}:rag`]?.[ragConfigurations[0].label];
                          const selectedTools = ragConfig?.enabled_tools || ragConfigurations[0].toolGroupsMetadata?.default || ["hybrid_search"];
                          
                          return (
                            <ConfigToolkitSelector
                              toolkits={ragToolkits}
                              value={{ url: undefined as any, tools: selectedTools }}
                              onChange={(newValue) => {
                                // Update the enabled_tools in the RAG config
                                const currentRagConfig = store.configsByAgentId[`${agentId}:rag`]?.[ragConfigurations[0].label] || {};
                                store.updateConfig(`${agentId}:rag`, ragConfigurations[0].label, {
                                  ...currentRagConfig,
                                  enabled_tools: newValue?.tools || [],
                                });
                              }}
                              searchTerm=""
                              className="w-full"
                            />
                          );
                        })()}
                      </div>
                    )}
                  </ConfigSection>
                </TabsContent>
              )}

              {supportedConfigs.includes("supervisor") && (
                <TabsContent
                  value="supervisor"
                  className="m-0 pb-4 pt-2 space-y-6"
                >
                  <ConfigSection title="Sub-Agents">
                    {agentId && agentsConfigurations[0]?.label && (
                      <ConfigFieldAgents
                        id="sub_agents"
                        label="sub_agents"
                        agentId={agentId}
                        itemSchema={agentsConfigurations[0].itemSchema}
                      />
                    )}
                  </ConfigSection>
                </TabsContent>
              )}
              </div>
            </div>
          </Tabs>
        </div>
      )}
      <NameAndDescriptionAlertDialog
        name={newName}
        setName={setNewName}
        description={newDescription}
        setDescription={setNewDescription}
        open={openNameAndDescriptionAlertDialog}
        setOpen={setOpenNameAndDescriptionAlertDialog}
        handleSave={handleSave}
      />
    </div>
  );
});

ConfigurationSidebar.displayName = "ConfigurationSidebar";
