"use client";

import { useState, useMemo } from "react";
import { ChevronRightIcon, PackageOpen } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Search } from "@/components/ui/tool-search";
import { SkillCard, SkillCardLoading } from "./skill-card";
import type { Skill } from "@/types/skill";

interface SkillsGalleryProps {
  skills: Skill[];
  isLoading: boolean;
  onUpdate?: (skill: Skill) => void;
  onDelete?: (skill: Skill) => void;
  onShare?: (skill: Skill) => void;
}

export function SkillsGallery({
  skills,
  isLoading,
  onUpdate,
  onDelete,
  onShare,
}: SkillsGalleryProps) {
  const [searchTerm, setSearchTerm] = useState("");
  const [currentPage, setCurrentPage] = useState(1);
  const itemsPerPage = 12;

  // Filter skills based on search
  const filteredSkills = useMemo(() => {
    if (!searchTerm) return skills;
    const searchLower = searchTerm.toLowerCase();
    return skills.filter((skill) => {
      return (
        skill.name.toLowerCase().includes(searchLower) ||
        skill.description.toLowerCase().includes(searchLower)
      );
    });
  }, [skills, searchTerm]);

  // Pagination
  const totalPages = Math.ceil(filteredSkills.length / itemsPerPage);
  const startIndex = (currentPage - 1) * itemsPerPage;
  const paginatedSkills = filteredSkills.slice(startIndex, startIndex + itemsPerPage);
  const hasMore = currentPage < totalPages;

  const handleLoadMore = () => {
    setCurrentPage((prev) => prev + 1);
  };

  // Show empty state
  if (!isLoading && skills.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-center">
        <PackageOpen className="h-16 w-16 text-muted-foreground/50 mb-4" />
        <h3 className="text-lg font-semibold mb-2">No skills yet</h3>
        <p className="text-muted-foreground max-w-md">
          Skills are modular capability packages that give your agents specialized
          abilities. Upload your first skill to get started.
        </p>
      </div>
    );
  }

  return (
    <div className="flex w-full flex-col gap-6">
      {/* Search Section */}
      <div className="flex w-full items-center justify-start">
        <Search
          onSearchChange={(value) => {
            setSearchTerm(value);
            setCurrentPage(1); // Reset to first page on search
          }}
          placeholder="Search skills..."
          className="w-full md:w-[calc(50%-0.5rem)] lg:w-[calc(33.333%-0.667rem)]"
        />
      </div>

      {/* Skills Grid */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
        {isLoading &&
          Array.from({ length: 6 }).map((_, index) => (
            <SkillCardLoading key={`skill-card-loading-${index}`} />
          ))}

        {!isLoading &&
          paginatedSkills.map((skill) => (
            <SkillCard
              key={skill.id}
              skill={skill}
              onUpdate={onUpdate}
              onDelete={onDelete}
              onShare={onShare}
            />
          ))}

        {!isLoading && filteredSkills.length === 0 && searchTerm && (
          <p className="col-span-full my-4 w-full text-center text-sm text-muted-foreground">
            No skills found matching &quot;{searchTerm}&quot;.
          </p>
        )}
      </div>

      {/* Load More Button */}
      {!searchTerm && hasMore && !isLoading && (
        <div className="mt-4 flex justify-center">
          <Button
            onClick={handleLoadMore}
            variant="outline"
            className="gap-1 px-2.5"
          >
            Load More Skills
            <ChevronRightIcon className="h-4 w-4" />
          </Button>
        </div>
      )}
    </div>
  );
}
