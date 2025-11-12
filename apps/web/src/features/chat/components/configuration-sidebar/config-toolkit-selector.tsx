"use client";

import React, { useState, useMemo } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { cn } from "@/lib/utils";
import { Toolkit } from "@/types/tool";
import { ConfigurableFieldMCPMetadata } from "@/types/configurable";
import _ from "lodash";

interface ConfigToolkitSelectorProps {
  toolkits: Toolkit[];
  value: ConfigurableFieldMCPMetadata["default"];
  onChange: (value: ConfigurableFieldMCPMetadata["default"]) => void;
  searchTerm?: string;
  className?: string;
}

export function ConfigToolkitSelector({
  toolkits,
  value,
  onChange,
  searchTerm = "",
  className,
}: ConfigToolkitSelectorProps) {
  const [expandedToolkits, setExpandedToolkits] = useState<Set<string>>(new Set());

  const selectedTools = new Set(value?.tools || []);
  const toolApprovals = value?.tool_approvals || {};

  // Filter toolkits based on search
  const filteredToolkits = useMemo(() => {
    if (!searchTerm.trim()) return toolkits;
    
    return toolkits
      .map(toolkit => {
        const toolkitMatches = toolkit.display_name.toLowerCase().includes(searchTerm.toLowerCase());
        const matchingTools = toolkit.tools.filter(tool =>
          tool.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
          (tool.description && tool.description.toLowerCase().includes(searchTerm.toLowerCase()))
        );
        
        if (toolkitMatches) {
          return toolkit; // Show all tools if toolkit name matches
        } else if (matchingTools.length > 0) {
          return { ...toolkit, tools: matchingTools }; // Show only matching tools
        }
        return null;
      })
      .filter(Boolean) as Toolkit[];
  }, [toolkits, searchTerm]);

  const toggleToolkit = (toolkitName: string) => {
    setExpandedToolkits(prev => {
      const newSet = new Set(prev);
      if (newSet.has(toolkitName)) {
        newSet.delete(toolkitName);
      } else {
        newSet.add(toolkitName);
      }
      return newSet;
    });
  };

  const getToolkitState = (toolkit: Toolkit) => {
    const toolkitTools = toolkit.tools.map(t => t.name);
    const selectedCount = toolkitTools.filter(name => selectedTools.has(name)).length;
    
    if (selectedCount === 0) return "none";
    if (selectedCount === toolkitTools.length) return "all";
    return "some";
  };

  const handleToolkitToggle = (toolkit: Toolkit, checked: boolean) => {
    const toolkitToolNames = toolkit.tools.map(t => t.name);
    const currentTools = new Set(value?.tools || []);
    
    if (checked) {
      // Add all toolkit tools
      toolkitToolNames.forEach(name => currentTools.add(name));
    } else {
      // Remove all toolkit tools
      toolkitToolNames.forEach(name => currentTools.delete(name));
    }
    
    onChange({
      ...value,
      tools: Array.from(currentTools),
    });
  };

  const handleToolToggle = (toolName: string, checked: boolean) => {
    const currentTools = new Set(value?.tools || []);

    if (checked) {
      currentTools.add(toolName);
    } else {
      currentTools.delete(toolName);
      // Also remove from approvals if tool is unchecked
      const newApprovals = { ...toolApprovals };
      delete newApprovals[toolName];
      onChange({
        ...value,
        tools: Array.from(currentTools),
        tool_approvals: newApprovals,
      });
      return;
    }

    onChange({
      ...value,
      tools: Array.from(currentTools),
    });
  };

  const handleApprovalToggle = (toolName: string, requiresApproval: boolean) => {
    const newApprovals = {
      ...toolApprovals,
      [toolName]: requiresApproval,
    };

    onChange({
      ...value,
      tool_approvals: newApprovals,
    });
  };

  if (filteredToolkits.length === 0) {
    return (
      <div className={cn("text-center py-8", className)}>
        <p className="text-sm text-muted-foreground">
          {searchTerm ? `No toolkits found matching "${searchTerm}".` : "No toolkits available."}
        </p>
      </div>
    );
  }

  return (
    <div className={cn("space-y-2", className)}>
      {filteredToolkits.map((toolkit) => {
        const isExpanded = expandedToolkits.has(toolkit.name);
        const toolkitState = getToolkitState(toolkit);
        
        return (
          <div
            key={toolkit.name}
            className="border rounded-lg"
          >
            <Collapsible
              open={isExpanded}
              onOpenChange={() => toggleToolkit(toolkit.name)}
            >
              <div className="flex items-center gap-3 p-3 hover:bg-accent/50 transition-colors">
                <Checkbox
                  checked={
                    toolkitState === "all"
                      ? true
                      : toolkitState === "none"
                        ? false
                        : "indeterminate"
                  }
                  onCheckedChange={(checked) =>
                    handleToolkitToggle(toolkit, checked === true)
                  }
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
                      {toolkit.display_name}
                    </h4>
                    <span className="text-xs text-muted-foreground ml-2">
                      {toolkit.tools.filter(t => selectedTools.has(t.name)).length}/{toolkit.tools.length} tools
                    </span>
                  </div>
                </div>
              </div>
              
              <CollapsibleContent>
                <div className="border-t bg-muted/20">
                  <div className="p-3 space-y-2">
                    {toolkit.tools.map((tool) => {
                      const isToolSelected = selectedTools.has(tool.name);
                      const requiresApproval = toolApprovals[tool.name] || false;

                      return (
                        <div
                          key={tool.name}
                          className="flex items-start gap-3 p-2 rounded hover:bg-background transition-colors"
                        >
                          <Checkbox
                            checked={isToolSelected}
                            onCheckedChange={(checked) =>
                              handleToolToggle(tool.name, checked === true)
                            }
                            className="mt-0.5"
                          />
                          <div className="flex-1 min-w-0">
                            <div className="text-sm font-medium">
                              {_.startCase(tool.name.replace(/^fs_/, ''))}
                            </div>
                            {tool.description && (
                              <div className="text-xs text-muted-foreground mt-1 line-clamp-2">
                                {tool.description}
                              </div>
                            )}
                          </div>
                          {isToolSelected && (
                            <div className="flex items-center gap-2 ml-2">
                              <Label
                                htmlFor={`approval-${tool.name}`}
                                className="text-xs text-muted-foreground whitespace-nowrap cursor-pointer"
                              >
                                Require approval?
                              </Label>
                              <Switch
                                id={`approval-${tool.name}`}
                                checked={requiresApproval}
                                onCheckedChange={(checked) =>
                                  handleApprovalToggle(tool.name, checked)
                                }
                                className="scale-75"
                              />
                            </div>
                          )}
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
  );
}
