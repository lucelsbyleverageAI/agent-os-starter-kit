import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { Search } from "@/components/ui/tool-search";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  ConfigField,
  ConfigFieldAgents,
  ConfigFieldRAG,
} from "@/features/chat/components/configuration-sidebar/config-field";
import { ConfigToolkitSelector } from "@/features/chat/components/configuration-sidebar/config-toolkit-selector";
import { useSearchTools } from "@/hooks/use-search-tools";
import { useMCPContext } from "@/providers/MCP";
import {
  ConfigurableFieldAgentsMetadata,
  ConfigurableFieldMCPMetadata,
  ConfigurableFieldRAGMetadata,
  ConfigurableFieldUIMetadata,
} from "@/types/configurable";
import _ from "lodash";
import { useFetchPreselectedTools } from "@/hooks/use-fetch-preselected-tools";
import { Controller, useFormContext } from "react-hook-form";
 

export function AgentFieldsFormLoading() {
  return (
    <div className="flex w-full flex-col items-start justify-start gap-2 space-y-2">
      {Array.from({ length: 2 }).map((_, index) => (
        <div
          key={`loading-${index}`}
          className="flex w-full flex-col items-start justify-start gap-2"
        >
          <Skeleton className="h-10 w-[85%]" />
          <Skeleton className="h-16 w-full" />
        </div>
      ))}
    </div>
  );
}

interface AgentFieldsFormProps {
  configurations: ConfigurableFieldUIMetadata[];
  toolConfigurations: ConfigurableFieldMCPMetadata[];
  agentId: string;
  ragConfigurations: ConfigurableFieldRAGMetadata[];
  agentsConfigurations: ConfigurableFieldAgentsMetadata[];
}

export function AgentFieldsForm({
  configurations,
  toolConfigurations,
  agentId,
  ragConfigurations,
  agentsConfigurations,
}: AgentFieldsFormProps) {
  const form = useFormContext<{
    name: string;
    description: string;
    config: Record<string, any>;
  }>();

  const { tools, setTools, getTools, cursor, loading } = useMCPContext();
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

  const hasTools = toolConfigurations.length > 0;
  const hasRag = ragConfigurations.length > 0;
  const hasAgents = agentsConfigurations.length > 0;

  return (
    <div className="flex flex-col gap-6 py-2">
      <Tabs defaultValue="general" className="flex flex-1 flex-col">
        <TabsList className="flex-shrink-0 justify-start bg-transparent px-0">
          <TabsTrigger value="general">General</TabsTrigger>
          {hasTools && <TabsTrigger value="tools">Tools</TabsTrigger>}
          {hasRag && <TabsTrigger value="rag">Knowledge</TabsTrigger>}
          {hasAgents && <TabsTrigger value="supervisor">Sub-Agents</TabsTrigger>}
        </TabsList>

        <TabsContent value="general" className="m-0 pt-2">
          <div className="flex w-full flex-col items-start justify-start gap-2 space-y-2">
            <p className="text-lg font-semibold tracking-tight">Agent Details</p>
            <div className="flex w-full flex-col items-start justify-start gap-2">
              <Label htmlFor="oap_name">
                Name <span className="text-red-500">*</span>
              </Label>
              <Input
                id="oap_name"
                {...form.register("name")}
                placeholder="Emails Agent"
              />
            </div>
            <div className="flex w-full flex-col items-start justify-start gap-2">
              <Label htmlFor="oap_description">
                Description <span className="text-red-500">*</span>
              </Label>
              <Textarea
                id="oap_description"
                {...form.register("description")}
                placeholder="Agent that handles emails"
              />
            </div>
          </div>

          {configurations.length > 0 && (
            <div className="mt-6 flex w-full flex-col items-start justify-start gap-2 space-y-2">
              <p className="text-lg font-semibold tracking-tight">Configuration</p>
              {configurations.map((c, index) => (
                <Controller
                  key={`${c.label}-${index}`}
                  control={form.control}
                  name={`config.${c.label}`}
                  render={({ field: { value, onChange } }) => (
                    <ConfigField
                      className="w-full"
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
                      value={value}
                      setValue={onChange}
                      agentId={agentId}
                    />
                  )}
                />
              ))}
            </div>
          )}
        </TabsContent>

        {hasTools && (
          <TabsContent value="tools" className="m-0 pt-2">
            <div className="flex w-full flex-col items-start justify-start gap-4">
              <p className="text-lg font-semibold tracking-tight">Agent Tools</p>
              <Search
                onSearchChange={debouncedSetSearchTerm}
                placeholder="Search toolkits and tools..."
                className="w-full"
              />
              <div className="w-full">
                {toolConfigurations[0]?.label ? (
                  <Controller
                    control={form.control}
                    name={`config.${toolConfigurations[0].label}`}
                    render={({ field: { value, onChange } }) => (
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
                ) : (
                  <p className="my-4 w-full text-center text-sm text-slate-500">
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
                          console.error("Failed to load more tools:", error);
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
            </div>
          </TabsContent>
        )}

        {hasRag && (
          <TabsContent value="rag" className="m-0 pt-2">
            <div className="flex w-full flex-col items-start justify-start gap-2">
              <p className="text-lg font-semibold tracking-tight">Agent Knowledge</p>
              <Controller
                control={form.control}
                name={`config.${ragConfigurations[0].label}`}
                render={({ field: { value, onChange } }) => (
                  <ConfigFieldRAG
                    id={ragConfigurations[0].label}
                    label={ragConfigurations[0].label}
                    agentId={agentId}
                    value={value}
                    setValue={onChange}
                  />
                )}
              />
            </div>
          </TabsContent>
        )}

        {hasAgents && (
          <TabsContent value="supervisor" className="m-0 pt-2">
            {(() => {
              const agentsField = agentsConfigurations[0];
              const title = agentsField?.mode === "builder" ? "Sub-Agents" : "Agents to Supervise";
              const fieldLabel = agentsField?.label || "agents";
              return (
                <div className="flex w-full flex-col items-start justify-start gap-2">
                  <p className="text-lg font-semibold tracking-tight">{title}</p>
                  <Controller
                    control={form.control}
                    name={`config.${fieldLabel}`}
                    render={({ field: { value, onChange } }) => (
                      <ConfigFieldAgents
                        id={fieldLabel}
                        label={fieldLabel}
                        agentId={agentId}
                        value={value}
                        setValue={onChange}
                      />
                    )}
                  />
                </div>
              );
            })()}
          </TabsContent>
        )}
      </Tabs>
    </div>
  );
}
