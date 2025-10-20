"use client";

import * as React from "react";
import { Check, ChevronDown, Star, Loader2 } from "lucide-react";

import { cn } from "@/lib/utils";
import { getScrollbarClasses } from "@/lib/scrollbar-styles";
import { Button } from "@/components/ui/button";
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
import { Agent } from "@/types/agent";
import {
  isUserDefaultAssistant,
  sortAgentGroup,
  isPrimaryAssistant,
} from "@/lib/agent-utils";

import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";

/**
 * Truncates agent name to 50 characters with ellipsis
 */
function truncateAgentName(name: string, maxLength: number = 50): string {
  if (name.length <= maxLength) return name;
  return name.slice(0, maxLength) + "...";
}

export interface AgentsComboboxProps {
  agents: Agent[];
  agentsLoading: boolean;
  /**
   * The placeholder text to display when no value is selected.
   * @default "Select an agent..."
   */
  placeholder?: string;
  open?: boolean;
  setOpen?: (open: boolean) => void;
  /**
   * Single agent value (string) or multiple agent values (string[])
   */
  value?: string | string[];
  /**
   * Callback for setting the value. Accepts a string for single selection or string[] for multiple selection.
   */
  setValue?: (value: string | string[]) => void;
  /**
   * Enable multiple selection mode
   * @default false
   */
  multiple?: boolean;
  /**
   * Prevent deselection of selected values
   * @default false
   */
  disableDeselect?: boolean;
  className?: string;
  style?: React.CSSProperties;
  trigger?: React.ReactNode;
  triggerAsChild?: boolean;
  header?: React.ReactNode;
  footer?: React.ReactNode;
  /**
   * Show border around the trigger button
   * @default false
   */
  showBorder?: boolean;
}

/**
 * Returns the selected agent's name
 * @param value The value of the selected agent.
 * @param agents The array of agents.
 * @returns The name of the selected agent.
 */
const getSelectedAgentValue = (
  value: string,
  agents: Agent[],
): React.ReactNode => {
  const [selectedAssistantId, selectedDeploymentId] = value.split(":");
  const selectedAgent = agents.find(
    (item) =>
      item.assistant_id === selectedAssistantId &&
      item.deploymentId === selectedDeploymentId,
  );

  if (selectedAgent) {
    return (
      <span className="flex w-full items-center gap-2 text-foreground font-normal truncate" title={selectedAgent.name}>
        {truncateAgentName(selectedAgent.name)}
      </span>
    );
  }
  return "";
};

/**
 * Returns a formatted display string for multiple selected agents
 * @param values Array of selected agent values
 * @param agents The array of agents
 * @returns Formatted string for display
 */
const getMultipleSelectedAgentValues = (
  values: string[],
  agents: Agent[],
): React.ReactNode => {
  if (values.length === 0) return "";
  if (values.length === 1) return getSelectedAgentValue(values[0], agents);
  return `${values.length} agents selected`;
};

const getNameFromValue = (value: string, agents: Agent[]) => {
  const [selectedAssistantId, selectedDeploymentId] = value.split(":");
  const selectedAgent = agents.find(
    (item) =>
      item.assistant_id === selectedAssistantId &&
      item.deploymentId === selectedDeploymentId,
  );

  if (selectedAgent) {
    return selectedAgent.name;
  }
  return "";
};

export function AgentsCombobox({
  agents,
  placeholder = "Select an agent...",
  open,
  setOpen,
  value,
  setValue,
  multiple = false,
  disableDeselect = false,
  className,
  trigger,
  triggerAsChild,
  header,
  footer,
  style,
  agentsLoading,
  showBorder = false,
}: AgentsComboboxProps) {
  // Convert value to array for internal handling
  const selectedValues = React.useMemo(() => {
    if (!value) return [];
    return Array.isArray(value) ? value : [value];
  }, [value]);

  // Handle selection of an item
  const handleSelect = (currentValue: string) => {
    if (!setValue) return;

    if (multiple) {
      // For multiple selection mode
      const newValues = [...selectedValues];
      const index = newValues.indexOf(currentValue);

      if (index === -1) {
        // Add the value if not already selected
        newValues.push(currentValue);
      } else if (!disableDeselect) {
        // Remove the value if already selected (only if deselection is allowed)
        newValues.splice(index, 1);
      }

      setValue(newValues);
    } else {
      // For single selection mode (backward compatibility)
      const shouldDeselect =
        currentValue === selectedValues[0] && !disableDeselect;
      setValue(shouldDeselect ? "" : currentValue);
      setOpen?.(false);
    }
  };

  return (
    <Popover
      open={open}
      onOpenChange={setOpen}
    >
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            <PopoverTrigger asChild={triggerAsChild || !trigger}>
              {trigger || (
                <Button
                  variant={showBorder ? "outline" : "ghost"}
                  role="combobox"
                  aria-expanded={open}
                  className={cn(
                    "min-w-[200px] justify-between font-normal transition-colors cursor-pointer",
                    showBorder 
                      ? "border-border bg-background text-foreground hover:bg-accent hover:text-foreground" 
                      : "border-0 bg-transparent text-muted-foreground hover:bg-accent hover:text-foreground",
                    className
                  )}
                  style={style}
                >
                  {selectedValues.length > 0
                    ? multiple
                      ? getMultipleSelectedAgentValues(selectedValues, agents)
                      : getSelectedAgentValue(selectedValues[0], agents)
                    : placeholder}
                  <ChevronDown className="h-4 w-4 opacity-50" />
                </Button>
              )}
            </PopoverTrigger>
          </TooltipTrigger>
          <TooltipContent>
            <p>Select Agent</p>
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
      <PopoverContent
        align="start"
        className="w-full min-w-[200px] p-0 rounded-xl"
      >
        <Command
          className="rounded-xl overflow-hidden [&_[data-slot=command-input-wrapper]]:rounded-t-xl [&_[data-slot=command-input-wrapper]]:border-b-0"
          filter={(value: string, search: string) => {
            const name = getNameFromValue(value, agents);
            if (!name) return 0;
            if (name.toLowerCase().includes(search.toLowerCase())) {
              return 1;
            }
            return 0;
          }}
        >
          <CommandInput placeholder="Search agents..." className="border-none" />
          <CommandList className={cn("max-h-[300px]", ...getScrollbarClasses('y'))}>
            <CommandEmpty>
              {agentsLoading ? (
                <span className="flex items-center justify-center gap-2 py-6">
                  <Loader2 className="size-4 animate-spin" />
                  Loading agents...
                </span>
              ) : (
                "No agents found."
              )}
            </CommandEmpty>
            
            {header}

            {/* Flat list of all agents sorted by default status and updated date */}
            {(() => {
              const sortedAgents = sortAgentGroup(agents);

              return sortedAgents.map((item) => {
                const itemValue = `${item.assistant_id}:${item.deploymentId}`;
                const isSelected = selectedValues.includes(itemValue);
                const isDefault = isUserDefaultAssistant(item);
                const isPrimary = isPrimaryAssistant(item);

                return (
                  <CommandItem
                    key={itemValue}
                    value={itemValue}
                    onSelect={handleSelect}
                    className="flex w-full items-center justify-between px-6 py-2 text-muted-foreground hover:text-foreground hover:bg-accent cursor-pointer"
                  >
                    <div className="flex items-center gap-3 flex-1 min-w-0">
                      <Check
                        className={cn(
                          "h-4 w-4 flex-shrink-0",
                          isSelected ? "opacity-100" : "opacity-0",
                        )}
                      />

                      <span className="flex-1 truncate text-sm" title={item.name}>
                        {truncateAgentName(item.name)}
                      </span>
                    </div>

                    <div className="flex items-center gap-2 flex-shrink-0">
                      {isPrimary && (
                        <Star className="h-4 w-4 text-yellow-500" />
                      )}
                      {isDefault && (
                        <span className="text-xs text-muted-foreground">
                          Default
                        </span>
                      )}
                    </div>
                  </CommandItem>
                );
              });
            })()}

            {footer}
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}
