"use client";

import { useState, useEffect, useRef } from "react";
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
import { RunbookField } from "@/components/ui/runbook-editor";
import { useConfigStore } from "@/features/chat/hooks/use-config-store";
import { useKnowledgeContext } from "@/features/knowledge/providers/Knowledge";
import { Check, ChevronsUpDown, AlertCircle, ChevronDown, ChevronRight } from "lucide-react";
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
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import _ from "lodash";
import { cn } from "@/lib/utils";
import { getScrollbarClasses } from "@/lib/scrollbar-styles";
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
    | "runbook"
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
  const fieldRef = useRef<HTMLDivElement>(null);

  // Determine whether to use external state or Zustand store
  const isExternallyManaged = externalSetValue !== undefined;

  const currentValue = isExternallyManaged
    ? externalValue
    : store.configsByAgentId?.[agentId]?.[id];

  // Debug logging for field overflow
  useEffect(() => {
    if (!fieldRef.current) return;

    const checkFieldOverflow = () => {
      const element = fieldRef.current;
      if (!element) return;

      const rect = element.getBoundingClientRect();
      const parent = element.parentElement;
      const parentRect = parent?.getBoundingClientRect();

      if (parentRect && rect.width > parentRect.width) {
        console.warn(`🔍 ConfigField OVERFLOW [${label}]:`, {
          fieldType: type,
          fieldLabel: label,
          fieldWidth: rect.width,
          parentWidth: parentRect.width,
          overflow: rect.width - parentRect.width,
          value: currentValue,
          fieldElement: element
        });
      }
    };

    // Check after render and after value changes
    checkFieldOverflow();
    const timeoutId = setTimeout(checkFieldOverflow, 500);

    return () => clearTimeout(timeoutId);
  }, [label, type, currentValue]);

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
    <div className={cn("space-y-2", className)} ref={fieldRef}>
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

      {type === "runbook" && (
        <RunbookField
          value={currentValue || ""}
          onChange={handleChange}
          placeholder={placeholder}
          description={undefined} // Description is shown above, no need to duplicate
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
          onValueChange={(value) => {
            console.log(`📊 Select field [${label}] changed:`, { value, fieldWidth: fieldRef.current?.getBoundingClientRect().width });
            handleChange(value);
          }}
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
      <div className={cn("", className)}>
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
    <div className={cn("space-y-2", className)}>
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
    <div className={cn("flex flex-col items-start gap-2", className)}>
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
  itemSchema, // NEW: Schema for sub-agent fields
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
  itemSchema?: any[]; // Schema for individual sub-agent items
}) {
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
      // Create default sub-agent with fields from schema
      const defaultSubAgent: any = { 
        name: "", 
        description: "", 
        prompt: "", 
        mcp_config: {}, 
        rag_config: {} 
      };
      
      // Add default values from schema
      if (itemSchema) {
        itemSchema.forEach((field) => {
          if (!defaultSubAgent[field.label] && field.default !== undefined) {
            defaultSubAgent[field.label] = field.default;
          }
        });
      }
      
      const next = [...subAgents, defaultSubAgent];
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
      <div className={cn("space-y-3", className)}>
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
                      <RunbookField
                        value={sa.prompt || ""}
                        onChange={(value) => updateAtPath(i, ["prompt"], value)}
                        placeholder="Enter the system prompt for this sub-agent..."
                      />
                    </div>
                  </div>

                  {/* Render sub-agent fields dynamically from schema */}
                  {itemSchema && itemSchema.length > 0 ? (
                    <div className="grid grid-cols-1 gap-3">
                      {itemSchema
                        .filter((field) => !["name", "description", "prompt", "mcp_config", "rag_config"].includes(field.label))
                        .map((field) => (
                          <div key={field.label}>
                            <Label className="text-xs">{_.startCase(field.label)}</Label>
                            {field.type === "select" && field.options ? (
                              <Select
                                value={sa[field.label] || field.default || ""}
                                onValueChange={(v) => updateAtPath(i, [field.label], v)}
                              >
                                <SelectTrigger>
                                  <SelectValue placeholder={field.placeholder || `Select ${field.label}`} />
                                </SelectTrigger>
                                <SelectContent>
                                  {field.options.map((opt: any) => (
                                    <SelectItem key={opt.value} value={opt.value}>
                                      {opt.label}
                                    </SelectItem>
                                  ))}
                                </SelectContent>
                              </Select>
                            ) : field.type === "number" ? (
                              <Input
                                type="number"
                                value={sa[field.label] ?? field.default ?? ""}
                                onChange={(e) => updateAtPath(i, [field.label], Number(e.target.value))}
                                min={field.min}
                                max={field.max}
                                step={field.step || 1}
                              />
                            ) : field.type === "textarea" ? (
                              <Textarea
                                value={sa[field.label] || field.default || ""}
                                onChange={(e) => updateAtPath(i, [field.label], e.target.value)}
                                className="min-h-[80px]"
                              />
                            ) : field.type === "runbook" ? (
                              <RunbookField
                                value={sa[field.label] || field.default || ""}
                                onChange={(value) => updateAtPath(i, [field.label], value)}
                                placeholder={field.placeholder || `Enter ${field.label}...`}
                              />
                            ) : (
                              <Input
                                value={sa[field.label] || field.default || ""}
                                onChange={(e) => updateAtPath(i, [field.label], e.target.value)}
                              />
                            )}
                            {field.description && (
                              <p className="text-xs text-muted-foreground mt-1">{field.description}</p>
                            )}
                          </div>
                        ))}
                    </div>
                  ) : (
                    /* Fallback to legacy hardcoded model fields if no schema */
                    <div className="grid grid-cols-1 gap-3">
                      <div>
                        <Label className="text-xs">Model</Label>
                        <Select
                          value={sa.model?.model || sa.model_name || ""}
                          onValueChange={(v) => updateAtPath(i, ["model_name"], v)}
                        >
                          <SelectTrigger>
                            <SelectValue placeholder="Select a model" />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="anthropic:claude-sonnet-4-5-20250929">Claude 4.5 Sonnet</SelectItem>
                            <SelectItem value="anthropic:claude-3-5-haiku-20250219">Claude 3.5 Haiku</SelectItem>
                            <SelectItem value="openai:gpt-4.1">GPT-4.1</SelectItem>
                            <SelectItem value="openai:gpt-4.1-mini">GPT-4.1 Mini</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>
                    </div>
                  )}

                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <Label className="text-xs">Sub-agent Tools</Label>
                    </div>
                    <Search
                      onSearchChange={debouncedSetSearchTerm}
                      placeholder="Search toolkits and tools..."
                    />
                    <div className={cn("max-h-60 rounded-md border p-2", ...getScrollbarClasses('y'))}>
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

                  <div className="space-y-4">
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
                    {sa.rag_config?.collections && sa.rag_config.collections.length > 0 && (
                      <ConfigFieldRAGTools
                        id={`subagent-${i}-rag-tools`}
                        label="rag"
                        agentId={agentId}
                        value={{
                          collections: sa.rag_config?.collections || [],
                          langconnect_api_url: undefined,
                          enabled_tools: sa.rag_config?.enabled_tools || ["hybrid_search", "fs_list_collections", "fs_list_files", "fs_read_file", "fs_grep_files"],
                        }}
                        setValue={(v) => updateAtPath(i, ["rag_config"], v)}
                      />
                    )}
                  </div>
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
    <div className={cn("space-y-2", className)}>
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

export function ConfigFieldRAGTools({
  id,
  label,
  agentId,
  className,
  value: externalValue,
  setValue: externalSetValue,
}: Pick<
  ConfigFieldProps,
  "id" | "label" | "agentId" | "className" | "value" | "setValue"
>) {
  const { collections } = useKnowledgeContext();
  const store = useConfigStore();
  const actualAgentId = `${agentId}:rag`;

  // State for collapsible groups
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(
    new Set(["Read Operations"]),
  );

  const isExternallyManaged = externalSetValue !== undefined;

  const defaults = (
    isExternallyManaged
      ? externalValue
      : store.configsByAgentId[actualAgentId]?.[label]
  ) as any;

  if (!defaults) {
    console.log('[ConfigFieldRAGTools] No defaults found', {
      actualAgentId,
      label,
      configsByAgentId: store.configsByAgentId,
      ragConfig: store.configsByAgentId[actualAgentId],
    });
    return null;
  }

  // Get the enabled_tools list and tool metadata
  console.log('[ConfigFieldRAGTools] Defaults:', defaults);
  const enabledTools = defaults.enabled_tools || ["hybrid_search", "fs_list_collections", "fs_list_files", "fs_read_file", "fs_grep_files"];
  
  const toggleGroup = (groupName: string) => {
    setExpandedGroups(prev => {
      const newSet = new Set(prev);
      if (newSet.has(groupName)) {
        newSet.delete(groupName);
      } else {
        newSet.add(groupName);
      }
      return newSet;
    });
  };
  
  // Tool groups structure matching the backend configuration
  const toolGroups = [
    {
      name: "Read Operations",
      permission: "viewer",
      tools: [
        {
          name: "hybrid_search",
          label: "Hybrid Search",
          description: "Semantic + keyword search (best for most use cases)",
        },
        {
          name: "fs_list_collections",
          label: "List Collections",
          description: "Browse available document collections",
        },
        {
          name: "fs_list_files",
          label: "List Files",
          description: "Browse documents across collections",
        },
        {
          name: "fs_read_file",
          label: "Read File",
          description: "Read document contents with line numbers",
        },
        {
          name: "fs_grep_files",
          label: "Search in Files (Grep)",
          description: "Search for patterns across documents using regex",
        },
      ],
    },
    {
      name: "Write Operations",
      permission: "editor",
      tools: [
        {
          name: "fs_write_file",
          label: "Write File",
          description: "Create new documents in collections",
        },
        {
          name: "fs_edit_file",
          label: "Edit File",
          description: "Modify existing document contents",
        },
      ],
    },
    {
      name: "Delete Operations",
      permission: "owner",
      tools: [
        {
          name: "fs_delete_file",
          label: "Delete File",
          description: "Permanently remove documents",
        }
      ],
    },
  ];

  // Get user's permissions for selected collections
  const selectedCollections = defaults.collections || [];
  const userPermissionLevels = new Set<string>();
  
  // Check actual permissions for selected collections
  selectedCollections.forEach((collectionId: string) => {
    const collection = collections.find(c => c.uuid === collectionId);
    if (collection?.permission_level) {
      // Add the user's permission level and all lower levels
      if (collection.permission_level === "owner") {
        userPermissionLevels.add("owner");
        userPermissionLevels.add("editor");
        userPermissionLevels.add("viewer");
      } else if (collection.permission_level === "editor") {
        userPermissionLevels.add("editor");
        userPermissionLevels.add("viewer");
      } else {
        userPermissionLevels.add("viewer");
      }
    } else {
      // Fallback to viewer if permission level not found
      userPermissionLevels.add("viewer");
    }
  });

  const handleToggleTool = (toolName: string, checked: boolean) => {
    const currentTools = [...enabledTools];
    
    if (checked) {
      if (!currentTools.includes(toolName)) {
        currentTools.push(toolName);
      }
    } else {
      const index = currentTools.indexOf(toolName);
      if (index > -1) {
        currentTools.splice(index, 1);
      }
    }

    const newValue = {
      ...defaults,
      enabled_tools: currentTools,
    };

    if (isExternallyManaged) {
      externalSetValue(newValue);
      return;
    }

    store.updateConfig(actualAgentId, label, newValue);
  };

  const handleToggleGroup = (groupTools: string[], checked: boolean) => {
    const currentTools = new Set(enabledTools);
    
    if (checked) {
      groupTools.forEach(tool => currentTools.add(tool));
    } else {
      groupTools.forEach(tool => currentTools.delete(tool));
    }

    const newValue = {
      ...defaults,
      enabled_tools: Array.from(currentTools),
    };

    if (isExternallyManaged) {
      externalSetValue(newValue);
      return;
    }

    store.updateConfig(actualAgentId, label, newValue);
  };

  const getGroupState = (groupTools: string[]) => {
    const selectedCount = groupTools.filter(t => enabledTools.includes(t)).length;
    if (selectedCount === 0) return "none";
    if (selectedCount === groupTools.length) return "all";
    return "some";
  };

  if (!selectedCollections.length) {
    return (
      <div className={cn("", className)}>
        <p className="text-sm text-muted-foreground">
          Select at least one collection to configure tools.
        </p>
      </div>
    );
  }

  return (
    <div className={cn("space-y-4", className)}>
      <div>
        <Label className="text-sm font-medium mb-2 block">
          Document Tools
        </Label>
        <p className="text-xs text-muted-foreground mb-3">
          Select which tools the agent can use to interact with your document collections.
          Tools are grouped by permission level.
        </p>
      </div>

      <div className="space-y-2">
        {toolGroups.map((group: any) => {
          const groupToolNames = group.tools.map((t: any) => t.name);
          const groupState = getGroupState(groupToolNames);
          const isExpanded = expandedGroups.has(group.name);
          
          // Check if user has required permission for this group
          const hasPermission = userPermissionLevels.has(group.permission);
          
          return (
            <div
              key={group.name}
              className="border rounded-lg"
            >
              <Collapsible
                open={isExpanded}
                onOpenChange={() => toggleGroup(group.name)}
              >
                <div className={cn(
                  "flex items-center gap-3 p-3 hover:bg-accent/50 transition-colors",
                  !hasPermission && "opacity-50"
                )}>
                  <Checkbox
                    checked={
                      groupState === "all"
                        ? true
                        : groupState === "none"
                          ? false
                          : "indeterminate"
                    }
                    onCheckedChange={(checked) =>
                      handleToggleGroup(groupToolNames, checked === true)
                    }
                    disabled={!hasPermission}
                    onClick={(e) => e.stopPropagation()}
                  />
                  
                  <CollapsibleTrigger asChild>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-6 w-6 p-0"
                    >
                      {isExpanded ? (
                        <ChevronDown className="h-4 w-4" />
                      ) : (
                        <ChevronRight className="h-4 w-4" />
                      )}
                    </Button>
                  </CollapsibleTrigger>
                  
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between">
                      <h4 className="text-sm font-medium truncate">
                        {group.name}
                      </h4>
                      <span className="text-xs text-muted-foreground ml-2">
                        {groupToolNames.filter((t: string) => enabledTools.includes(t)).length}/{groupToolNames.length} enabled
                      </span>
                    </div>
                    {!hasPermission && (
                      <p className="text-xs text-muted-foreground mt-0.5">
                        Requires {group.permission} permission
                      </p>
                    )}
                  </div>
                </div>
                
                <CollapsibleContent>
                  <div className="border-t bg-muted/20">
                    <div className="p-3 space-y-2">
                      {group.tools.map((tool: any) => {
                        const isEnabled = enabledTools.includes(tool.name);
                        
                        return (
                          <div
                            key={tool.name}
                            className="flex items-start gap-3 p-2 rounded hover:bg-background transition-colors"
                          >
                            <Checkbox
                              checked={isEnabled}
                              onCheckedChange={(checked) =>
                                handleToggleTool(tool.name, checked === true)
                              }
                              disabled={!hasPermission}
                              className="mt-0.5"
                            />
                            <div className="flex-1 min-w-0">
                              <div className="text-sm font-medium">
                                {tool.label}
                              </div>
                              <div className="text-xs text-muted-foreground mt-1 line-clamp-2">
                                {tool.description}
                              </div>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                </CollapsibleContent>
              </Collapsible>
            </div>
          );
        })}
      </div>
    </div>
  );
}
