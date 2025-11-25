"use client";

import React, { useState } from "react";
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbList,
  BreadcrumbPage,
} from "@/components/ui/breadcrumb";
import { PageHeader } from "@/components/ui/page-header";
import { MinimalistBadgeWithText } from "@/components/ui/minimalist-badge";
import { Hash, PackagePlus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { AppHeader } from "@/components/app-header";

import SkillsInterface, {
  useSkills,
  UploadSkillDialog,
} from "@/features/skills";

/**
 * The /skills page.
 * Contains the interface for managing agent skills.
 */
export default function SkillsPage(): React.ReactNode {
  const { skills, isLoading, validateSkillZip, uploadSkill } = useSkills();
  const [showUploadDialog, setShowUploadDialog] = useState(false);

  const skillsCount = skills.length;

  const handleUpload = async (file: File) => {
    await uploadSkill(file);
  };

  return (
    <React.Suspense fallback={<div>Loading...</div>}>
      <AppHeader>
        <Breadcrumb>
          <BreadcrumbList>
            <BreadcrumbItem>
              <BreadcrumbPage>Skills</BreadcrumbPage>
            </BreadcrumbItem>
          </BreadcrumbList>
        </Breadcrumb>
      </AppHeader>

      <div className="container mx-auto px-4 md:px-8 lg:px-12 py-6">
        <PageHeader
          title="Skills"
          description="Manage skills that extend your agents' capabilities"
          badge={
            !isLoading && (
              <MinimalistBadgeWithText
                icon={Hash}
                text={`${skillsCount} skill${skillsCount !== 1 ? "s" : ""}`}
              />
            )
          }
          action={
            <Button onClick={() => setShowUploadDialog(true)}>
              <PackagePlus className="mr-2 h-4 w-4" />
              Upload Skill
            </Button>
          }
        />

        <div className="mt-6">
          <SkillsInterface />
        </div>
      </div>

      <UploadSkillDialog
        open={showUploadDialog}
        onOpenChange={setShowUploadDialog}
        onUpload={handleUpload}
        onValidate={validateSkillZip}
        mode="create"
      />
    </React.Suspense>
  );
}
