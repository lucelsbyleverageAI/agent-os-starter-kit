"use client";

import { useState, useCallback } from "react";
import { Upload, FileArchive, Check, X, AlertCircle, Loader2 } from "lucide-react";
import { useDropzone } from "react-dropzone";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { cn } from "@/lib/utils";
import type { SkillValidationResult } from "@/types/skill";

interface UploadSkillDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onUpload: (file: File) => Promise<void>;
  onValidate: (file: File) => Promise<SkillValidationResult>;
  mode?: "create" | "update";
  skillName?: string;
}

export function UploadSkillDialog({
  open,
  onOpenChange,
  onUpload,
  onValidate,
  mode = "create",
  skillName,
}: UploadSkillDialogProps) {
  const [file, setFile] = useState<File | null>(null);
  const [isValidating, setIsValidating] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [validation, setValidation] = useState<SkillValidationResult | null>(null);

  const reset = useCallback(() => {
    setFile(null);
    setValidation(null);
    setIsValidating(false);
    setIsUploading(false);
  }, []);

  const onDrop = useCallback(
    async (acceptedFiles: File[]) => {
      if (acceptedFiles.length === 0) return;

      const selectedFile = acceptedFiles[0];
      setFile(selectedFile);
      setValidation(null);
      setIsValidating(true);

      try {
        const result = await onValidate(selectedFile);
        setValidation(result);
      } catch (err) {
        setValidation({
          valid: false,
          name: null,
          description: null,
          pip_requirements: null,
          files: [],
          errors: [err instanceof Error ? err.message : "Validation failed"],
        });
      } finally {
        setIsValidating(false);
      }
    },
    [onValidate]
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      "application/zip": [".zip"],
      "application/x-zip-compressed": [".zip"],
    },
    maxFiles: 1,
    multiple: false,
  });

  const handleUpload = async () => {
    if (!file || !validation?.valid) return;

    setIsUploading(true);
    try {
      await onUpload(file);
      reset();
      onOpenChange(false);
    } catch (err) {
      console.error("Upload failed:", err);
    } finally {
      setIsUploading(false);
    }
  };

  const handleClose = () => {
    if (!isUploading) {
      reset();
      onOpenChange(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>
            {mode === "create" ? "Upload Skill" : `Update "${skillName}"`}
          </DialogTitle>
          <DialogDescription>
            {mode === "create"
              ? "Upload a zip file containing SKILL.md and supporting files."
              : "Upload a new version of this skill."}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {/* Dropzone */}
          <div
            {...getRootProps()}
            className={cn(
              "relative cursor-pointer rounded-lg border-2 border-dashed p-8 text-center transition-colors",
              isDragActive
                ? "border-primary bg-primary/5"
                : "border-muted-foreground/25 hover:border-muted-foreground/50",
              file && "border-solid"
            )}
          >
            <input {...getInputProps()} />
            {file ? (
              <div className="flex items-center justify-center gap-3">
                <FileArchive className="h-8 w-8 text-muted-foreground" />
                <div className="text-left">
                  <p className="font-medium">{file.name}</p>
                  <p className="text-sm text-muted-foreground">
                    {(file.size / 1024).toFixed(1)} KB
                  </p>
                </div>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-8 w-8"
                  onClick={(e) => {
                    e.stopPropagation();
                    reset();
                  }}
                >
                  <X className="h-4 w-4" />
                </Button>
              </div>
            ) : (
              <div className="space-y-2">
                <Upload className="mx-auto h-8 w-8 text-muted-foreground" />
                <div>
                  <p className="font-medium">
                    {isDragActive ? "Drop the file here" : "Drop a zip file or click to browse"}
                  </p>
                  <p className="text-sm text-muted-foreground">
                    ZIP file containing SKILL.md at the root
                  </p>
                </div>
              </div>
            )}
          </div>

          {/* Validation Status */}
          {isValidating && (
            <div className="flex items-center justify-center gap-2 text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              <span>Validating skill package...</span>
            </div>
          )}

          {/* Validation Result */}
          {validation && !isValidating && (
            <div className="space-y-3">
              {validation.valid ? (
                <Alert className="border-green-200 bg-green-50">
                  <Check className="h-4 w-4 text-green-600" />
                  <AlertDescription className="text-green-800">
                    Valid skill package
                  </AlertDescription>
                </Alert>
              ) : (
                <Alert variant="destructive">
                  <AlertCircle className="h-4 w-4" />
                  <AlertDescription>
                    <ul className="list-disc pl-4 space-y-1">
                      {validation.errors.map((error, i) => (
                        <li key={i}>{error}</li>
                      ))}
                    </ul>
                  </AlertDescription>
                </Alert>
              )}

              {validation.valid && (
                <div className="rounded-lg border bg-muted/50 p-4 space-y-3">
                  <div>
                    <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                      Skill Name
                    </p>
                    <p className="font-mono">{validation.name}</p>
                  </div>
                  <div>
                    <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                      Description
                    </p>
                    <p className="text-sm">{validation.description}</p>
                  </div>
                  {validation.pip_requirements && validation.pip_requirements.length > 0 && (
                    <div>
                      <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-1">
                        Dependencies
                      </p>
                      <div className="flex flex-wrap gap-1">
                        {validation.pip_requirements.map((pkg) => (
                          <Badge key={pkg} variant="secondary" className="text-xs">
                            {pkg}
                          </Badge>
                        ))}
                      </div>
                    </div>
                  )}
                  <div>
                    <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                      Files
                    </p>
                    <p className="text-sm text-muted-foreground">
                      {validation.files.length} file{validation.files.length !== 1 ? "s" : ""}
                    </p>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={handleClose} disabled={isUploading}>
            Cancel
          </Button>
          <Button
            onClick={handleUpload}
            disabled={!validation?.valid || isUploading}
          >
            {isUploading ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Uploading...
              </>
            ) : (
              <>
                <Upload className="mr-2 h-4 w-4" />
                {mode === "create" ? "Upload Skill" : "Update Skill"}
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
