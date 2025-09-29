"use client";

import { useState } from "react";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Label } from "@/components/ui/label";
import { useConfigStore } from "@/features/chat/hooks/use-config-store";
import { useKnowledgeContext } from "@/features/knowledge/providers/Knowledge";
import { Check, ChevronsUpDown, AlertCircle } from "lucide-react";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import _ from "lodash";
import { cn } from "@/lib/utils";
import {
  ConfigurableFieldAgentsMetadata,
  ConfigurableFieldMCPMetadata,
  ConfigurableFieldRAGMetadata,
} from "@/types/configurable";
import { AgentsCombobox } from "@/components/ui/agents-combobox";
import { useAgentsContext } from "@/providers/Agents";
import { getDeployments } from "@/lib/environment/deployments";
import { useOptionalMCPContext } from "@/providers/MCP";
import { ConfigToolkitSelector } from "./config-toolkit-selector";
import { Search } from "@/components/ui/tool-search";
import { useSearchTools } from "@/hooks/use-search-tools";

interface Option {
  label: string;
  value: string;
}

interface ConfigFieldProps {
  id: string;
  label: string;
  type:
    | "text"
    | "textarea"
    | "number"
    | "switch"
    | "slider"
    | "select"
    | "json";
  description?: string;
  placeholder?: string;
  options?: Option[];
  min?: number;
  max?: number;
  step?: number;
  className?: string;
  // Optional props for external state management
  value?: any;
  setValue?: (value: any) => void;
  agentId: string;
}

export function ConfigField({
  id,
  label,
  type,
  description,
  placeholder,
  options = [],
  min,
  max,
  step = 1,
  className,
  value: externalValue, // Rename to avoid conflict
  setValue: externalSetValue, // Rename to avoid conflict
  agentId,
}: ConfigFieldProps) {
  const store = useConfigStore();
  const [jsonError, setJsonError] = useState<string | null>(null);

  // Determine whether to use external state or Zustand store
  const isExternallyManaged = externalSetValue !== undefined;

  const currentValue = isExternallyManaged
    ? externalValue
    : store.configsByAgentId?.[agentId]?.[id];

  const handleChange = (newValue: any) => {
    setJsonError(null); // Clear JSON error on any change
    if (isExternallyManaged && externalSetValue) {
      externalSetValue(newValue); // Use non-null assertion as we checked existence
    } else {
      store.updateConfig(agentId, id, newValue);
    }
  };

  const handleJsonChange = (jsonString: string) => {
    try {
      if (!jsonString.trim()) {
        handleChange(undefined); // Use the unified handleChange
        setJsonError(null);
        return;
      }

      // Attempt to parse for validation first
      const parsedJson = JSON.parse(jsonString);
      // If parsing succeeds, call handleChange with the raw string and clear error
      handleChange(parsedJson); // Use the unified handleChange
      setJsonError(null);
    } catch (_) {
      // If parsing fails, update state with invalid string but set error
      // This allows the user to see their invalid input and the error message
      if (isExternallyManaged && externalSetValue) {
        externalSetValue(jsonString);
      } else {
        store.updateConfig(agentId, id, jsonString);
      }
      setJsonError("Invalid JSON format");
    }
  };

  const handleFormatJson = (jsonString: string) => {
    try {
      const parsed = JSON.parse(jsonString);
      // Directly use handleChange to update with the formatted string
      handleChange(parsed);
      setJsonError(null); // Clear error on successful format
    } catch (_) {
      // If formatting fails (because input is not valid JSON), set the error state
      // Do not change the underlying value that failed to parse/format
      setJsonError("Invalid JSON format");
    }
  };

  return (
    <div className={cn("space-y-2", className)}>
      <div className="flex items-center justify-between">
        <Label
          htmlFor={id}
          className="text-sm font-medium"
        >
          {_.startCase(label)}
        </Label>
        {type === "switch" && (
          <Switch
            id={id}
            checked={!!currentValue} // Use currentValue
            onCheckedChange={handleChange}
          />
        )}
      </div>

      {description && (
        <p className="text-xs whitespace-pre-line text-muted-foreground">
          {description}
        </p>
      )}

      {type === "text" && (
        <Input
          id={id}
          value={currentValue || ""} // Use currentValue
          onChange={(e) => handleChange(e.target.value)}
          placeholder={placeholder}
        />
      )}

      {type === "textarea" && (
        <Textarea
          id={id}
          value={currentValue || ""} // Use currentValue
          onChange={(e) => handleChange(e.target.value)}
          placeholder={placeholder}
          className="min-h-[100px]"
        />
      )}

      {type === "number" && (
        <Input
          id={id}
          type="number"
          value={currentValue !== undefined ? currentValue : ""} // Use currentValue
          onChange={(e) => {
            // Handle potential empty string or invalid number input
            const val = e.target.value;
            if (val === "") {
              handleChange(undefined); // Treat empty string as clearing the value
            } else {
              const num = Number(val);
              // Only call handleChange if it's a valid number
              if (!isNaN(num)) {
                handleChange(num);
              }
              // If not a valid number (e.g., '1.2.3'), do nothing, keep the last valid state
            }
          }}
          min={min}
          max={max}
          step={step}
        />
      )}

      {type === "slider" && (
        <div className="pt-2">
          <div className="mb-2 flex items-center justify-between">
            <span className="text-xs text-muted-foreground">{min ?? ""}</span>
            <span className="text-sm font-medium">
              {/* Use currentValue */}
              {currentValue !== undefined
                ? currentValue
                : min !== undefined && max !== undefined
                  ? (min + max) / 2
                  : ""}
            </span>
            <span className="text-xs text-muted-foreground">{max ?? ""}</span>
          </div>
          <Slider
            id={id}
            // Use currentValue, provide default based on min/max if undefined
            value={[
              currentValue !== undefined
                ? currentValue
                : min !== undefined && max !== undefined
                  ? (min + max) / 2
                  : 0,
            ]}
            min={min}
            max={max}
            step={step}
            onValueChange={(vals) => handleChange(vals[0])}
            disabled={min === undefined || max === undefined} // Disable slider if min/max not provided
          />
        </div>
      )}

      {type === "select" && (
        <Select
          value={currentValue ?? ""} // Use currentValue, provide default empty string if undefined/null
          onValueChange={handleChange}
        >
          <SelectTrigger>
            {/* Display selected value or placeholder */}
            <SelectValue placeholder={placeholder || "Select an option"} />
          </SelectTrigger>
          <SelectContent>
            {/* Add a placeholder/default option if needed */}
            {placeholder && (
              <SelectItem
                value=""
                disabled
              >
                {placeholder}
              </SelectItem>
            )}
            {options.map((option) => (
              <SelectItem
                key={option.value}
                value={option.value}
              >
                {option.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      )}

      {type === "json" && (
        <>
          <Textarea
            id={id}
            value={
              typeof currentValue === "string"
                ? currentValue
                : (JSON.stringify(currentValue, null, 2) ?? "")
            } // Use currentValue
            onChange={(e) => handleJsonChange(e.target.value)}
            placeholder={placeholder || '{\n  "key": "value"\n}'}
            className={cn(
              "min-h-[120px] font-mono text-sm",
              jsonError &&
                "border-red-500 focus:border-red-500 focus-visible:ring-red-500", // Add error styling
            )}
          />
          <div className="flex w-full items-start justify-between gap-2 pt-1">
            {" "}
            {/* Use items-start */}
            <Button
              variant="outline"
              size="sm"
              onClick={() => handleFormatJson(currentValue ?? "")}
              // Disable if value is empty, not a string, or already has a JSON error
              disabled={
                !currentValue || typeof currentValue !== "string" || !!jsonError
              }
              className="mt-1" // Add margin top to align better with textarea
            >
              Format
            </Button>
            {jsonError && (
              <Alert
                variant="destructive"
                className="flex-grow px-3 py-1" // Adjusted styling
              >
                <div className="flex items-center gap-2">
                  {" "}
                  {/* Ensure icon and text are aligned */}
                  <AlertCircle className="h-4 w-4 flex-shrink-0" />{" "}
                  {/* Added flex-shrink-0 */}
                  <AlertDescription className="text-xs">
                    {jsonError}
                  </AlertDescription>
                </div>
              </Alert>
            )}
          </div>
        </>
      )}
    </div>
  );
}

export function ConfigFieldTool({
  id,
  label,
  description,
  agentId,
  className,
  toolId,
  value: externalValue, // Rename to avoid conflict
  setValue: externalSetValue, // Rename to avoid conflict
  renderCustom,
}: Pick<
  ConfigFieldProps,
  | "id"
  | "label"
  | "description"
  | "agentId"
  | "className"
  | "value"
  | "setValue"
> & { 
  toolId: string;
  renderCustom?: (value: any, onChange: (value: any) => void) => React.ReactNode;
}) {
  const store = useConfigStore();
  const actualAgentId = `${agentId}:selected-tools`;

  const isExternallyManaged = externalSetValue !== undefined;

  const defaults = (
    isExternallyManaged
      ? externalValue
      : store.configsByAgentId[actualAgentId]?.[toolId]
  ) as ConfigurableFieldMCPMetadata["default"] | undefined;

  if (!defaults) {
    return null;
  }

  const handleChange = (newValue: any) => {
    if (isExternallyManaged) {
      externalSetValue(newValue);
      return;
    }
    store.updateConfig(actualAgentId, toolId, newValue);
  };

  // If custom render function is provided, use it
  if (renderCustom) {
    return (
      <div className={cn("w-full", className)}>
        {renderCustom(defaults, handleChange)}
      </div>
    );
  }

  // Default single tool toggle behavior
  const checked = defaults.tools?.some((t) => t === label);

  const handleCheckedChange = (checked: boolean) => {
    const newValue = checked
      ? {
          ...defaults,
          // Remove duplicates
          tools: Array.from(
            new Set<string>([...(defaults.tools || []), label]),
          ),
        }
      : {
          ...defaults,
          tools: defaults.tools?.filter((t) => t !== label),
        };

    handleChange(newValue);
  };

  return (
    <div className={cn("w-full space-y-2", className)}>
      <div className="flex items-center justify-between">
        <Label
          htmlFor={id}
          className="text-sm font-medium"
        >
          {_.startCase(label)}
        </Label>
        <Switch
          id={id}
          checked={checked} // Use currentValue
          onCheckedChange={handleCheckedChange}
        />
      </div>

      {description && (
        <p className="text-xs whitespace-pre-line text-muted-foreground">
          {description}
        </p>
      )}
    </div>
  );
}

export function ConfigFieldRAG({
  id,
  label,
  agentId,
  className,
  value: externalValue, // Rename to avoid conflict
  setValue: externalSetValue, // Rename to avoid conflict
}: Pick<
  ConfigFieldProps,
  "id" | "label" | "agentId" | "className" | "value" | "setValue"
>) {
  const { collections } = useKnowledgeContext();
  const store = useConfigStore();
  const actualAgentId = `${agentId}:rag`;
  const [open, setOpen] = useState(false);

  const isExternallyManaged = externalSetValue !== undefined;

  const defaults = (
    isExternallyManaged
      ? externalValue
      : store.configsByAgentId[actualAgentId]?.[label]
  ) as ConfigurableFieldRAGMetadata["default"];

  if (!defaults) {
    return null;
  }

  const selectedCollections = defaults.collections?.length
    ? defaults.collections
    : [];

  const handleSelect = (collectionId: string) => {
    const newValue = selectedCollections.some((s) => s === collectionId)
      ? selectedCollections.filter((s) => s !== collectionId)
      : [...selectedCollections, collectionId];

    if (isExternallyManaged) {
      externalSetValue({
        ...defaults,
        collections: Array.from(new Set(newValue)),
      });
      return;
    }

    store.updateConfig(actualAgentId, label, {
      ...defaults,
      collections: Array.from(new Set(newValue)),
    });
  };

  const getCollectionNameFromId = (collectionId: string) => {
    const collection = collections.find((c) => c.uuid === collectionId);
    return collection?.name ?? "Unknown Collection";
  };

  return (
    <div className={cn("flex w-full flex-col items-start gap-2", className)}>
      <Label
        htmlFor={id}
        className="text-sm font-medium"
      >
        Selected Collections
      </Label>
      <Popover
        open={open}
        onOpenChange={setOpen}
      >
        <PopoverTrigger asChild>
          <Button
            variant="outline"
            role="combobox"
            aria-expanded={open}
            className="w-full justify-between"
          >
            {selectedCollections.length > 0
              ? selectedCollections.length > 1
                ? `${selectedCollections.length} collections selected`
                : getCollectionNameFromId(selectedCollections[0])
              : "Select collections"}
            <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
          </Button>
        </PopoverTrigger>
        <PopoverContent
          className="w-full p-0"
          align="start"
        >
          <Command className="w-full">
            <CommandInput placeholder="Search collections..." />
            <CommandList>
              <CommandEmpty>No collections found.</CommandEmpty>
              <CommandGroup>
                {collections.map((collection) => (
                  <CommandItem
                    key={collection.uuid}
                    value={collection.uuid}
                    onSelect={() => handleSelect(collection.uuid)}
                    className="flex items-center justify-between"
                  >
                    <Check
                      className={cn(
                        "ml-auto h-4 w-4",
                        selectedCollections.includes(collection.uuid)
                          ? "opacity-100"
                          : "opacity-0",
                      )}
                    />
                    <p className="line-clamp-1 flex-1 truncate pr-2">
                      {collection.name}
                    </p>
                  </CommandItem>
                ))}
              </CommandGroup>
            </CommandList>
          </Command>
        </PopoverContent>
      </Popover>
    </div>
  );
}

export function ConfigFieldAgents({
  label,
  agentId,
  className,
  value: externalValue, // Rename to avoid conflict
  setValue: externalSetValue, // Rename to avoid conflict
}: Pick<
  ConfigFieldProps,
  | "id"
  | "label"
  | "description"
  | "agentId"
  | "className"
  | "value"
  | "setValue"
>) {
  const store = useConfigStore();
  const actualAgentId = `${agentId}:agents`;

  // Always call hooks at the top level to maintain hook order
  const optionalMcp = useOptionalMCPContext();
  const mcpTools = optionalMcp?.tools || [];
  const { toolSearchTerm, debouncedSetSearchTerm } = useSearchTools(mcpTools, {
    preSelectedTools: undefined,
  });

  const { agents, loading } = useAgentsContext();
  const deployments = getDeployments();

  // Do not allow adding itself as a sub-agent
  const filteredAgents = agents.filter((a) => a.assistant_id !== agentId);

  const isExternallyManaged = externalSetValue !== undefined;

  const defaults = (
    isExternallyManaged
      ? externalValue
      : store.configsByAgentId[actualAgentId]?.[label]
  ) as ConfigurableFieldAgentsMetadata["default"] | undefined;

  if (!defaults) {
    return null;
  }

  const handleSelectChange = (ids: string[]) => {
    if (!ids.length || ids.every((id) => !id)) {
      if (isExternallyManaged) {
        externalSetValue([]);
        return;
      }

      store.updateConfig(actualAgentId, label, []);
      return;
    }

    const newDefaults = ids.map((id) => {
      const [agent_id, deploymentId] = id.split(":");
      const deployment_url = deployments.find(
        (d) => d.id === deploymentId,
      )?.deploymentUrl;
      if (!deployment_url) {
        console.warn("Deployment not found for ID:", deploymentId);
      }

      return {
        agent_id,
        deployment_url,
        name: agents.find((a) => a.assistant_id === agent_id)?.name,
      };
    });

    if (isExternallyManaged) {
      externalSetValue(newDefaults);
      return;
    }

    store.updateConfig(actualAgentId, label, newDefaults);
  };

  // Builder mode rendering (sub-agent cards)
  if ((store.configsByAgentId[agentId]?.__ui_meta?.[label]?.mode ?? (undefined as any)) === "builder") {
    const subAgents: any[] = (store.configsByAgentId[agentId]?.sub_agents as any[]) || [];

    const setSubAgents = (list: any[]) => {
      // Always update the config store for builder mode
      store.updateConfig(agentId, "sub_agents", list);
      // Also update the form if externally managed
      if (isExternallyManaged && externalSetValue) {
        externalSetValue(list);
      }
    };

    const addSubAgent = () => {
      const next = [
        ...subAgents,
        { name: "", description: "", prompt: "", model: {}, mcp_config: {}, rag_config: {} },
      ];
      setSubAgents(next);
    };

    const removeSubAgent = (index: number) => {
      const next = subAgents.filter((_, i) => i !== index);
      setSubAgents(next);
    };

    const updateAtPath = (index: number, path: string[], value: any) => {
      const next = [...subAgents];
      let cursor: any = next[index] || {};
      for (let i = 0; i < path.length - 1; i++) {
        const key = path[i];
        cursor[key] = cursor[key] ?? {};
        cursor = cursor[key];
      }
      cursor[path[path.length - 1]] = value;
      setSubAgents(next);
    };

    return (
      <div className={cn("w-full space-y-3", className)}>
        <div className="flex items-center justify-between">
          <Label className="text-sm font-medium">Sub-Agents</Label>
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={addSubAgent}
          >
            Add sub-agent
          </Button>
        </div>

        {subAgents.length === 0 && (
          <p className="text-sm text-muted-foreground">No sub-agents yet. Click "Add sub-agent" to start.</p>
        )}

        <div className="space-y-2">
          {subAgents.map((sa, i) => (
            <div
              key={i}
              className="rounded-md border p-3"
            >
              <div className="flex items-center justify-between">
                <div>
                  <div className="text-sm font-medium">{sa.name || `Sub-agent ${i + 1}`}</div>
                  {sa.description && (
                    <div className="text-xs text-muted-foreground line-clamp-1">{sa.description}</div>
                  )}
                </div>
                <div className="flex gap-2">
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    onClick={() => updateAtPath(i, ["__open"], !sa.__open)}
                  >
                    {sa.__open ? "Close" : "Edit"}
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="destructive"
                    onClick={() => removeSubAgent(i)}
                  >
                    Remove
                  </Button>
                </div>
              </div>

              {sa.__open && (
                <div className="mt-3 space-y-3">
                  <div className="grid grid-cols-1 gap-3">
                    <div>
                      <Label className="text-xs">Name</Label>
                      <Input
                        value={sa.name || ""}
                        onChange={(e) => updateAtPath(i, ["name"], e.target.value)}
                      />
                    </div>
                    <div>
                      <Label className="text-xs">Description</Label>
                      <Textarea
                        value={sa.description || ""}
                        onChange={(e) => updateAtPath(i, ["description"], e.target.value)}
                        className="min-h-[80px]"
                      />
                    </div>
                    <div>
                      <Label className="text-xs">System Prompt</Label>
                      <Textarea
                        value={sa.prompt || ""}
                        onChange={(e) => updateAtPath(i, ["prompt"], e.target.value)}
                        className="min-h-[100px]"
                      />
                    </div>
                  </div>

                  <div className="grid grid-cols-1 gap-3">
                    <div>
                      <Label className="text-xs">Model</Label>
                      <Select
                        value={sa.model?.model || ""}
                        onValueChange={(v) => updateAtPath(i, ["model", "model"], v)}
                      >
                        <SelectTrigger>
                          <SelectValue placeholder="Select a model" />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="anthropic:claude-3-7-sonnet-latest">Claude 3.7 Sonnet</SelectItem>
                          <SelectItem value="anthropic:claude-3-5-sonnet-latest">Claude 3.5 Sonnet</SelectItem>
                          <SelectItem value="openai:gpt-4o">GPT-4o</SelectItem>
                          <SelectItem value="openai:gpt-4o-mini">GPT-4o mini</SelectItem>
                          <SelectItem value="openai:gpt-4.1">GPT-4.1</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <Label className="text-xs">Max Tokens</Label>
                        <Input
                          type="number"
                          value={sa.model?.max_tokens ?? 4000}
                          onChange={(e) => updateAtPath(i, ["model", "max_tokens"], Number(e.target.value))}
                        />
                      </div>
                      <div>
                        <Label className="text-xs">Temperature</Label>
                        <Input
                          type="number"
                          step={0.1}
                          value={sa.model?.temperature ?? 0.7}
                          onChange={(e) => updateAtPath(i, ["model", "temperature"], Number(e.target.value))}
                        />
                      </div>
                    </div>
                  </div>

                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <Label className="text-xs">Sub-agent Tools</Label>
                    </div>
                    <Search
                      onSearchChange={debouncedSetSearchTerm}
                      placeholder="Search toolkits and tools..."
                    />
                    <div className="max-h-60 overflow-y-auto rounded-md border p-2">
                      <ConfigToolkitSelector
                        toolkits={(() => {
                          const grouped = (mcpTools || []).reduce((acc: Record<string, any>, tool: any) => {
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
                          }, {});
                          return Object.values(grouped) as any[];
                        })()}
                        value={{ url: undefined as any, tools: sa.mcp_config?.tools || [] }}
                        onChange={(v) => updateAtPath(i, ["mcp_config", "tools"], (v && v.tools) ? v.tools : [])}
                        searchTerm={toolSearchTerm}
                      />
                    </div>
                  </div>

                  <ConfigFieldRAG
                    id={`subagent-${i}-rag`}
                    label="rag"
                    agentId={agentId}
                    value={{
                      collections: sa.rag_config?.collections || [],
                      langconnect_api_url: undefined,
                    }}
                    setValue={(v) => updateAtPath(i, ["rag_config"], v)}
                  />
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    );
  }

  // Default selector (supervisor) rendering
  return (
    <div className={cn("w-full space-y-2", className)}>
      <AgentsCombobox
        agents={filteredAgents}
        agentsLoading={loading}
        value={defaults.map(
          (defaultValue) =>
            `${defaultValue.agent_id}:${deployments.find((d) => d.deploymentUrl === defaultValue.deployment_url)?.id}`,
        )}
        setValue={(v) =>
          Array.isArray(v) ? handleSelectChange(v) : handleSelectChange([v])
        }
        multiple
        className="w-full"
      />

      <p className="text-xs text-muted-foreground">
        The agents to make available to this supervisor.
      </p>
    </div>
  );
}
