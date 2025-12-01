"use client";

import { useState } from "react";
import { useSkills } from "./hooks/use-skills";
import { SkillsGallery } from "./components/skills-gallery";
import { UploadSkillDialog } from "./components/upload-skill-dialog";
import { DeleteSkillDialog } from "./components/delete-skill-dialog";
import { ManageSkillAccessDialog } from "./components/manage-skill-access-dialog";
import type { Skill } from "@/types/skill";

export { useSkills } from "./hooks/use-skills";
export { SkillCard, SkillCardLoading } from "./components/skill-card";
export { SkillsGallery } from "./components/skills-gallery";
export { UploadSkillDialog } from "./components/upload-skill-dialog";
export { DeleteSkillDialog } from "./components/delete-skill-dialog";
export { ManageSkillAccessDialog } from "./components/manage-skill-access-dialog";

export default function SkillsInterface() {
  const {
    skills,
    isLoading,
    validateSkillZip,
    uploadSkill,
    updateSkill,
    deleteSkill,
    downloadSkill,
  } = useSkills();

  // Dialog state
  const [showUploadDialog, setShowUploadDialog] = useState(false);
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);
  const [showManageAccessDialog, setShowManageAccessDialog] = useState(false);
  const [selectedSkill, setSelectedSkill] = useState<Skill | null>(null);
  const [uploadMode, setUploadMode] = useState<"create" | "update">("create");

  // Handlers (reserved for future create button in header)
  const _handleCreateClick = () => {
    setUploadMode("create");
    setSelectedSkill(null);
    setShowUploadDialog(true);
  };

  const handleUpdateClick = (skill: Skill) => {
    setUploadMode("update");
    setSelectedSkill(skill);
    setShowUploadDialog(true);
  };

  const handleDeleteClick = (skill: Skill) => {
    setSelectedSkill(skill);
    setShowDeleteDialog(true);
  };

  const handleManageAccessClick = (skill: Skill) => {
    setSelectedSkill(skill);
    setShowManageAccessDialog(true);
  };

  const handleUpload = async (file: File) => {
    if (uploadMode === "create") {
      await uploadSkill(file);
    } else if (selectedSkill) {
      await updateSkill(selectedSkill.id, file);
    }
  };

  const handleDelete = async (skill: Skill) => {
    return await deleteSkill(skill.id);
  };

  const handleDownload = async (skill: Skill) => {
    await downloadSkill(skill);
  };

  return (
    <>
      <SkillsGallery
        skills={skills}
        isLoading={isLoading}
        onUpdate={handleUpdateClick}
        onDelete={handleDeleteClick}
        onShare={handleManageAccessClick}
        onDownload={handleDownload}
      />

      <UploadSkillDialog
        open={showUploadDialog}
        onOpenChange={setShowUploadDialog}
        onUpload={handleUpload}
        onValidate={validateSkillZip}
        mode={uploadMode}
        skillName={selectedSkill?.name}
      />

      <DeleteSkillDialog
        open={showDeleteDialog}
        onOpenChange={setShowDeleteDialog}
        skill={selectedSkill}
        onConfirm={handleDelete}
      />

      {selectedSkill && (
        <ManageSkillAccessDialog
          open={showManageAccessDialog}
          onOpenChange={setShowManageAccessDialog}
          skill={selectedSkill}
        />
      )}
    </>
  );
}

// Export a function to trigger creating a new skill (used by page header)
export function useSkillsActions() {
  const [showUploadDialog, setShowUploadDialog] = useState(false);

  return {
    showUploadDialog,
    setShowUploadDialog,
    openUploadDialog: () => setShowUploadDialog(true),
  };
}
