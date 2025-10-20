import React from "react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { X, Check } from "lucide-react";
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
import { cn } from "@/lib/utils";
import { getScrollbarClasses } from "@/lib/scrollbar-styles";

// Separate component for tags selector to comply with React Hooks rules
function TagsSelector({ value = [], onChange }: { value: string[]; onChange: (value: string[]) => void }) {
  const [open, setOpen] = React.useState(false);
  const commandListRef = React.useRef<HTMLDivElement>(null);

  const toggleTag = (tagValue: string) => {
    if (value.includes(tagValue)) {
      onChange(value.filter((t: string) => t !== tagValue));
    } else {
      onChange([...value, tagValue]);
    }
  };

  const removeTag = (tagToRemove: string) => {
    onChange(value.filter((tag: string) => tag !== tagToRemove));
  };

  // Enable mouse wheel scrolling - cmdk blocks it by default
  React.useEffect(() => {
    if (!open) return;

    // Wait for portal to render
    const timeoutId = setTimeout(() => {
      const el = commandListRef.current || document.querySelector('[cmdk-list]') as HTMLElement;
      if (!el) return;

      const handleWheel = (e: WheelEvent) => {
        e.preventDefault();
        e.stopPropagation();
        el.scrollTop += e.deltaY;
      };

      el.addEventListener('wheel', handleWheel, { passive: false });

      return () => {
        el.removeEventListener('wheel', handleWheel);
      };
    }, 100);

    return () => {
      clearTimeout(timeoutId);
    };
  }, [open]);

  return (
    <div className="flex w-full flex-col items-start justify-start gap-2">
      <Label htmlFor="oap_tags">
        Tags <span className="text-xs text-muted-foreground">(Select categories for your agent)</span>
      </Label>

      {/* Selected tags display */}
      {value.length > 0 && (
        <div className="flex flex-wrap gap-2 w-full">
          {value.map((tag: string) => (
            <Badge
              key={tag}
              variant="secondary"
              className="gap-1"
            >
              {getTagLabel(tag)}
              <X
                className="h-3 w-3 cursor-pointer hover:text-destructive"
                onClick={() => removeTag(tag)}
              />
            </Badge>
          ))}
        </div>
      )}

      {/* Multi-select dropdown */}
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <Button
            variant="outline"
            role="combobox"
            aria-expanded={open}
            className="w-full justify-between"
          >
            {value.length > 0
              ? `${value.length} tag${value.length > 1 ? 's' : ''} selected`
              : "Select tags..."}
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-[400px] p-0" align="start">
          <Command className="h-auto max-h-[350px]">
            <CommandInput placeholder="Search tags..." />
            <CommandEmpty>No tags found.</CommandEmpty>
            <CommandList
              ref={commandListRef as any}
              className={cn("max-h-[300px]", ...getScrollbarClasses('y'))}
            >
              {Object.entries(AGENT_TAG_GROUPS).map(([category, tags]) => (
                <React.Fragment key={category}>
                  {/* Category Header */}
                  <div className="px-3 py-2 text-sm font-medium text-foreground">
                    {category}
                  </div>

                  {/* Tags in this category */}
                  {tags.map((tag) => (
                    <CommandItem
                      key={tag.value}
                      value={tag.label}
                      onSelect={() => toggleTag(tag.value)}
                    >
                      <div className="flex items-center gap-2 flex-1">
                        <div className={`flex h-4 w-4 items-center justify-center rounded-sm border ${
                          value.includes(tag.value)
                            ? "bg-primary border-primary text-primary-foreground"
                            : "border-muted-foreground"
                        }`}>
                          {value.includes(tag.value) && (
                            <Check className="h-3 w-3" />
                          )}
                        </div>
                        <div className="flex flex-col flex-1">
                          <span className="text-sm font-medium">{tag.label}</span>
                          <span className="text-xs text-muted-foreground">
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
  );
}

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
    tags: string[];
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
      <Tabs defaultValue="general" className="flex flex-1 flex-col min-h-0">
        <div className="flex justify-center pt-2 pb-3">
          <TabsList variant="branded" className="w-fit flex-shrink-0">
            <TabsTrigger value="general">General</TabsTrigger>
            {hasTools && <TabsTrigger value="tools">Tools</TabsTrigger>}
            {hasRag && <TabsTrigger value="rag">Knowledge</TabsTrigger>}
            {hasAgents && <TabsTrigger value="supervisor">Sub-Agents</TabsTrigger>}
          </TabsList>
        </div>

        <TabsContent value="general" className="m-0 pt-2">
          <div className="flex w-full flex-col items-start justify-start gap-2 space-y-2">
            <p className="text-lg font-semibold tracking-tight">Agent Details</p>
            <div className="flex w-full flex-col items-start justify-start gap-2">
              <Label htmlFor="oap_name">
                Name <span className="text-red-500">*</span>
                <span className="ml-2 text-xs text-muted-foreground">
                  ({form.watch("name")?.length || 0}/50)
                </span>
              </Label>
              <Input
                id="oap_name"
                {...form.register("name", {
                  maxLength: {
                    value: 50,
                    message: "Name must be 50 characters or less"
                  }
                })}
                placeholder="Emails Agent"
                maxLength={50}
              />
              {form.formState.errors.name && (
                <span className="text-xs text-red-500">
                  {form.formState.errors.name.message}
                </span>
              )}
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

            {/* Tags Multi-Select */}
            <Controller
              control={form.control}
              name="tags"
              render={({ field: { value = [], onChange } }) => (
                <TagsSelector value={value} onChange={onChange} />
              )}
            />
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
            <div className="flex w-full flex-col items-start justify-start gap-6">
              {/* Collections Selection */}
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

              {/* Document Tools */}
              {ragConfigurations[0]?.toolGroupsMetadata?.tool_groups && (
                  <div className="flex w-full flex-col items-start justify-start gap-2">
                    <p className="text-lg font-semibold tracking-tight">Document Tools</p>
                    <div className="w-full">
                      <Controller
                        control={form.control}
                        name={`config.${ragConfigurations[0].label}`}
                        render={({ field: { value, onChange } }) => {
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
                          
                          const selectedTools = value?.enabled_tools || ragConfigurations[0].toolGroupsMetadata?.default || ["hybrid_search"];
                          
                          return (
                            <ConfigToolkitSelector
                              toolkits={ragToolkits}
                              value={{ url: undefined as any, tools: selectedTools }}
                              onChange={(newValue) => {
                                onChange({
                                  ...value,
                                  enabled_tools: newValue?.tools || [],
                                });
                              }}
                              searchTerm=""
                              className="w-full"
                            />
                          );
                        }}
                      />
                    </div>
                  </div>
                )}
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
                        itemSchema={agentsConfigurations[0]?.itemSchema}
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
