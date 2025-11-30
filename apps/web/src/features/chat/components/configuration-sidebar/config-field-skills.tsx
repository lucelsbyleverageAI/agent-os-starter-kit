"use client";

import { useState, useMemo } from "react";
import { Search } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
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

/**
 * Skills picker component - fully controlled via props.
 * Follows the same simple pattern as ConfigToolkitSelector.
 */
export function ConfigFieldSkills({
  id,
  label,
  agentId,
  className,
  value,
  setValue,
}: ConfigFieldSkillsProps) {
  const { skills, isLoading } = useSkills();
  const [searchTerm, setSearchTerm] = useState("");

  // Read directly from props - no memoization needed for selection state
  const selectedSkills = value?.skills || [];
  const selectedSkillIds = selectedSkills.map((s) => s.skill_id);

  // Filter skills based on search term (memoized since filtering is expensive)
  const filteredSkills = useMemo(() => {
    if (!searchTerm.trim()) return skills;
    const term = searchTerm.toLowerCase();
    return skills.filter(
      (skill) =>
        skill.name.toLowerCase().includes(term) ||
        (skill.description && skill.description.toLowerCase().includes(term))
    );
  }, [skills, searchTerm]);

  // Get select all state: "all", "some", or "none"
  const getSelectAllState = () => {
    if (skills.length === 0) return "none";
    const selectedCount = selectedSkillIds.length;
    if (selectedCount === 0) return "none";
    if (selectedCount === skills.length) return "all";
    return "some";
  };

  // Handle select all / deselect all
  const handleSelectAll = (checked: boolean) => {
    if (checked) {
      // Select all skills
      const allSkillRefs: SkillReference[] = skills.map((skill) => ({
        skill_id: skill.id,
        name: skill.name,
        description: skill.description,
      }));
      setValue?.({ skills: allSkillRefs });
    } else {
      // Deselect all
      setValue?.({ skills: [] });
    }
  };

  // Simple toggle handler - no guards needed
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

    setValue?.({ skills: newSkills });
  };

  if (!value) {
    return null;
  }

  return (
    <div className={cn("w-full space-y-3", className)}>
      {/* Header with count */}
      <Label htmlFor={id} className="text-sm font-medium">
        Skills ({selectedSkills.length}/{skills.length})
      </Label>

      {/* Search Input */}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          placeholder="Search skills..."
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          className="pl-9"
        />
      </div>

      {/* Select All */}
      {skills.length > 0 && (
        <div className="flex items-center gap-2">
          <Checkbox
            id={`${id}-select-all`}
            checked={
              getSelectAllState() === "all"
                ? true
                : getSelectAllState() === "none"
                  ? false
                  : "indeterminate"
            }
            onCheckedChange={(checked) => handleSelectAll(checked === true)}
          />
          <Label
            htmlFor={`${id}-select-all`}
            className="text-sm text-muted-foreground cursor-pointer"
          >
            {getSelectAllState() === "all" ? "Deselect all" : "Select all"}
          </Label>
        </div>
      )}

      {/* Scrollable Skills List */}
      <div className={cn("border rounded-lg max-h-64 overflow-y-auto", ...getScrollbarClasses("y"))}>
        {isLoading ? (
          <div className="p-4 text-center text-sm text-muted-foreground">
            Loading skills...
          </div>
        ) : filteredSkills.length === 0 ? (
          <div className="p-4 text-center text-sm text-muted-foreground">
            {searchTerm ? `No skills found matching "${searchTerm}".` : "No skills available."}
          </div>
        ) : (
          filteredSkills.map((skill) => {
            const isSelected = selectedSkillIds.includes(skill.id);
            return (
              <div
                key={skill.id}
                className="flex items-start gap-3 p-3 hover:bg-accent/50 transition-colors border-b last:border-b-0"
              >
                <Checkbox
                  checked={isSelected}
                  onCheckedChange={() => handleToggleSkill(skill)}
                  className="mt-0.5"
                />
                <div className="flex-1 min-w-0">
                  <span className="text-sm font-medium">{skill.name}</span>
                  {skill.description && (
                    <p className="text-xs text-muted-foreground line-clamp-2 mt-0.5">
                      {skill.description}
                    </p>
                  )}
                </div>
              </div>
            );
          })
        )}
      </div>

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
 * Follows the same simple pattern as ConfigToolkitSelector.
 */
interface SubAgentSkillsPickerProps {
  value: SkillReference[];
  onChange: (value: SkillReference[]) => void;
}

export function SubAgentSkillsPicker({ value, onChange }: SubAgentSkillsPickerProps) {
  const { skills, isLoading } = useSkills();
  const [searchTerm, setSearchTerm] = useState("");

  // Read directly from props - no memoization needed
  const selectedSkillIds = (value || []).map((s) => s.skill_id);

  // Filter skills based on search term (memoized since filtering is expensive)
  const filteredSkills = useMemo(() => {
    if (!searchTerm.trim()) return skills;
    const term = searchTerm.toLowerCase();
    return skills.filter(
      (skill) =>
        skill.name.toLowerCase().includes(term) ||
        (skill.description && skill.description.toLowerCase().includes(term))
    );
  }, [skills, searchTerm]);

  // Simple toggle handler
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
      {/* Header with count */}
      <Label className="text-xs">
        Sub-agent Skills ({(value || []).length}/{skills.length})
      </Label>

      {/* Search Input */}
      <div className="relative">
        <Search className="absolute left-2 top-1/2 h-3 w-3 -translate-y-1/2 text-muted-foreground" />
        <Input
          placeholder="Search skills..."
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          className="pl-7 h-7 text-xs"
        />
      </div>

      {/* Scrollable Skills List */}
      <div className={cn("border rounded-lg max-h-40 overflow-y-auto", ...getScrollbarClasses("y"))}>
        {isLoading ? (
          <div className="p-2 text-center text-xs text-muted-foreground">
            Loading...
          </div>
        ) : filteredSkills.length === 0 ? (
          <div className="p-2 text-center text-xs text-muted-foreground">
            {searchTerm ? "No skills found." : "No skills available."}
          </div>
        ) : (
          filteredSkills.map((skill) => {
            const isSelected = selectedSkillIds.includes(skill.id);
            return (
              <div
                key={skill.id}
                className="flex items-start gap-2 p-2 hover:bg-accent/50 transition-colors border-b last:border-b-0"
              >
                <Checkbox
                  checked={isSelected}
                  onCheckedChange={() => handleToggleSkill(skill)}
                  className="mt-0.5 h-3.5 w-3.5"
                />
                <div className="flex-1 min-w-0">
                  <span className="text-xs font-medium truncate">{skill.name}</span>
                  {skill.description && (
                    <p className="text-[10px] text-muted-foreground line-clamp-1">
                      {skill.description}
                    </p>
                  )}
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
