"use client";

import { Icon } from "@fluentui/react/lib/Icon";
import { getFileTypeIconProps, FileTypeIconSize } from "@fluentui/react-file-type-icons";
import {
  FileText,
  FileImage,
  FileCode,
  File,
  type LucideIcon,
} from "lucide-react";
import { cn } from "@/lib/utils";

// Office file extensions that use Fluent UI branded icons
const FLUENT_EXTENSIONS = new Set([
  "docx", "doc",
  "xlsx", "xls", "csv",
  "pptx", "ppt",
  "pdf",
]);

// Map extensions to Lucide icons and colors for non-Office files
const LUCIDE_ICON_MAP: Record<string, { icon: LucideIcon; colorClass: string }> = {
  // Images
  png: { icon: FileImage, colorClass: "text-purple-500" },
  jpg: { icon: FileImage, colorClass: "text-purple-500" },
  jpeg: { icon: FileImage, colorClass: "text-purple-500" },
  gif: { icon: FileImage, colorClass: "text-purple-500" },
  webp: { icon: FileImage, colorClass: "text-purple-500" },
  svg: { icon: FileImage, colorClass: "text-purple-500" },
  bmp: { icon: FileImage, colorClass: "text-purple-500" },
  // HTML
  html: { icon: FileCode, colorClass: "text-orange-600" },
  htm: { icon: FileCode, colorClass: "text-orange-600" },
  // Markdown
  md: { icon: FileText, colorClass: "text-slate-600" },
  markdown: { icon: FileText, colorClass: "text-slate-600" },
  // Text
  txt: { icon: FileText, colorClass: "text-gray-500" },
};

// Valid Fluent UI icon sizes
const FLUENT_ICON_SIZES: FileTypeIconSize[] = [16, 20, 24, 32, 40, 48, 64, 96];

// Get the closest valid Fluent UI icon size
function getClosestFluentSize(size: number): FileTypeIconSize {
  return FLUENT_ICON_SIZES.reduce((prev, curr) =>
    Math.abs(curr - size) < Math.abs(prev - size) ? curr : prev
  );
}

interface BrandedFileIconProps {
  /** File extension (e.g., "docx", "pdf", "png") */
  extension: string | undefined;
  /** Icon size in pixels */
  size?: number;
  /** Additional CSS classes */
  className?: string;
}

/**
 * Renders branded file type icons:
 * - Microsoft Fluent UI icons for Office files (Word, Excel, PowerPoint, PDF)
 * - Colored Lucide icons for other file types (images, text, html, etc.)
 */
export function BrandedFileIcon({ extension, size = 20, className }: BrandedFileIconProps) {
  const ext = extension?.toLowerCase().replace(".", "") || "";

  // Use Fluent UI for Office files
  if (FLUENT_EXTENSIONS.has(ext)) {
    const fluentSize = getClosestFluentSize(size);
    return (
      <Icon
        {...getFileTypeIconProps({ extension: ext, size: fluentSize })}
        className={className}
      />
    );
  }

  // Use Lucide icons for other file types
  const lucideConfig = LUCIDE_ICON_MAP[ext];
  if (lucideConfig) {
    const LucideIconComponent = lucideConfig.icon;
    return (
      <LucideIconComponent
        size={size}
        className={cn(lucideConfig.colorClass, className)}
      />
    );
  }

  // Default fallback
  return (
    <File
      size={size}
      className={cn("text-muted-foreground", className)}
    />
  );
}
