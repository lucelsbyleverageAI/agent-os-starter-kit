"use client";

import { useState } from "react";
import { Check, ChevronsUpDown, Package } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
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
import { Badge } from "@/components/ui/badge";
import { useConfigStore } from "@/features/chat/hooks/use-config-store";
import { useSkills } from "@/features/skills/hooks/use-skills";
import { cn } from "@/lib/utils";
import { getScrollbarClasses } from "@/lib/scrollbar-styles";
import type { ConfigurableFieldSkillsMetadata } from "@/types/configurable";
import type { Skill, SkillReference } from "@/types/skill";

interface ConfigFieldSkillsProps {
  id: string;
  label: string;
  agentId: string;
  className?: string;
  value?: ConfigurableFieldSkillsMetadata["default"];
  setValue?: (value: ConfigurableFieldSkillsMetadata["default"]) => void;
}

export function ConfigFieldSkills({
  id,
  label,
  agentId,
  className,
  value: externalValue,
  setValue: externalSetValue,
}: ConfigFieldSkillsProps) {
  const { skills, isLoading } = useSkills();
  const store = useConfigStore();
  const actualAgentId = `${agentId}:skills`;
  const [open, setOpen] = useState(false);

  const isExternallyManaged = externalSetValue !== undefined;

  const defaults = (
    isExternallyManaged
      ? externalValue
      : store.configsByAgentId[actualAgentId]?.[label]
  ) as ConfigurableFieldSkillsMetadata["default"];

  if (!defaults) {
    return null;
  }

  const selectedSkills = defaults.skills || [];
  const selectedSkillIds = selectedSkills.map((s) => s.skill_id);

  const handleToggleSkill = (skill: Skill) => {
    const isSelected = selectedSkillIds.includes(skill.id);

    let newSkills: SkillReference[];
    if (isSelected) {
      newSkills = selectedSkills.filter((s) => s.skill_id !== skill.id);
    } else {
      newSkills = [
        ...selectedSkills,
        {
          skill_id: skill.id,
          name: skill.name,
          description: skill.description,
        },
      ];
    }

    const newValue = { ...defaults, skills: newSkills };

    if (isExternallyManaged) {
      externalSetValue(newValue);
      return;
    }

    store.updateConfig(actualAgentId, label, newValue);
  };

  const getSkillNameFromId = (skillId: string) => {
    const skill = skills.find((s) => s.id === skillId);
    return skill?.name ?? "Unknown Skill";
  };

  return (
    <div className={cn("w-full flex flex-col items-start gap-2", className)}>
      <Label htmlFor={id} className="text-sm font-medium">
        Selected Skills
      </Label>

      {/* Selected skills badges */}
      {selectedSkills.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {selectedSkills.map((skill) => (
            <Badge
              key={skill.skill_id}
              variant="secondary"
              className="gap-1 font-mono text-xs"
            >
              <Package className="h-3 w-3" />
              {skill.name}
            </Badge>
          ))}
        </div>
      )}

      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <Button
            variant="outline"
            role="combobox"
            aria-expanded={open}
            className="w-full justify-between"
            disabled={isLoading}
          >
            {isLoading
              ? "Loading skills..."
              : selectedSkills.length > 0
                ? selectedSkills.length > 1
                  ? `${selectedSkills.length} skills selected`
                  : getSkillNameFromId(selectedSkills[0].skill_id)
                : "Select skills"}
            <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-full p-0" align="start">
          <Command className="w-full">
            <CommandInput placeholder="Search skills..." />
            <CommandList className={cn("max-h-64", ...getScrollbarClasses("y"))}>
              <CommandEmpty>
                {isLoading ? "Loading..." : "No skills found."}
              </CommandEmpty>
              <CommandGroup>
                {skills.map((skill) => {
                  const isSelected = selectedSkillIds.includes(skill.id);
                  return (
                    <CommandItem
                      key={skill.id}
                      value={skill.name}
                      onSelect={() => handleToggleSkill(skill)}
                      className="flex items-start gap-3 py-2"
                    >
                      <Checkbox
                        checked={isSelected}
                        className="mt-0.5"
                        onCheckedChange={() => handleToggleSkill(skill)}
                      />
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="font-mono text-sm font-medium">
                            {skill.name}
                          </span>
                          {skill.is_public && (
                            <Badge variant="outline" className="text-xs">
                              Public
                            </Badge>
                          )}
                        </div>
                        <p className="text-xs text-muted-foreground line-clamp-2 mt-0.5">
                          {skill.description}
                        </p>
                      </div>
                    </CommandItem>
                  );
                })}
              </CommandGroup>
            </CommandList>
          </Command>
        </PopoverContent>
      </Popover>

      <p className="text-xs text-muted-foreground">
        Select skills to enable for this agent. Skills provide specialized
        capabilities and instructions.
      </p>
    </div>
  );
}

/**
 * Compact skills picker for sub-agent configuration.
 * This takes and returns SkillReference[] directly.
 */
interface SubAgentSkillsPickerProps {
  value: SkillReference[];
  onChange: (value: SkillReference[]) => void;
}

export function SubAgentSkillsPicker({ value, onChange }: SubAgentSkillsPickerProps) {
  const { skills, isLoading } = useSkills();
  const [open, setOpen] = useState(false);

  const selectedSkillIds = value?.map((s) => s.skill_id) || [];

  const handleToggleSkill = (skill: Skill) => {
    const isSelected = selectedSkillIds.includes(skill.id);

    if (isSelected) {
      onChange((value || []).filter((s) => s.skill_id !== skill.id));
    } else {
      onChange([
        ...(value || []),
        {
          skill_id: skill.id,
          name: skill.name,
          description: skill.description,
        },
      ]);
    }
  };

  return (
    <div className="w-full space-y-2">
      <Label className="text-xs">Sub-agent Skills</Label>

      {/* Selected skills badges */}
      {value && value.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {value.map((skill) => (
            <Badge
              key={skill.skill_id}
              variant="secondary"
              className="gap-1 font-mono text-xs"
            >
              <Package className="h-3 w-3" />
              {skill.name}
            </Badge>
          ))}
        </div>
      )}

      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <Button
            type="button"
            variant="outline"
            role="combobox"
            aria-expanded={open}
            className="w-full justify-between text-xs h-8"
            disabled={isLoading}
          >
            {isLoading
              ? "Loading..."
              : value && value.length > 0
                ? `${value.length} skill${value.length > 1 ? "s" : ""} selected`
                : "Select skills"}
            <ChevronsUpDown className="ml-2 h-3 w-3 shrink-0 opacity-50" />
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-[300px] p-0" align="start">
          <Command>
            <CommandInput placeholder="Search skills..." className="h-8" />
            <CommandList className={cn("max-h-48", ...getScrollbarClasses("y"))}>
              <CommandEmpty>
                {isLoading ? "Loading..." : "No skills found."}
              </CommandEmpty>
              <CommandGroup>
                {skills.map((skill) => {
                  const isSelected = selectedSkillIds.includes(skill.id);
                  return (
                    <CommandItem
                      key={skill.id}
                      value={skill.name}
                      onSelect={() => handleToggleSkill(skill)}
                      className="flex items-start gap-2 py-1.5"
                    >
                      <Checkbox
                        checked={isSelected}
                        className="mt-0.5 h-3.5 w-3.5"
                        onCheckedChange={() => handleToggleSkill(skill)}
                      />
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-1">
                          <span className="font-mono text-xs font-medium truncate">
                            {skill.name}
                          </span>
                          {skill.is_public && (
                            <Badge variant="outline" className="text-[10px] px-1 py-0">
                              Public
                            </Badge>
                          )}
                        </div>
                        <p className="text-[10px] text-muted-foreground line-clamp-1">
                          {skill.description}
                        </p>
                      </div>
                    </CommandItem>
                  );
                })}
              </CommandGroup>
            </CommandList>
          </Command>
        </PopoverContent>
      </Popover>
    </div>
  );
}
