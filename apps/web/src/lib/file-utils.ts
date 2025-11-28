import {
  FileText,
  FileSpreadsheet,
  FileImage,
  FileCode,
  File,
  type LucideIcon,
} from "lucide-react";

/**
 * Returns the appropriate Lucide icon component for a given MIME type
 */
export function getFileIcon(mimeType: string | undefined): LucideIcon {
  if (!mimeType) {
    return File;
  }
  if (mimeType.startsWith("image/")) {
    return FileImage;
  }
  if (
    mimeType.includes("spreadsheet") ||
    mimeType.includes("excel") ||
    mimeType === "text/csv"
  ) {
    return FileSpreadsheet;
  }
  if (mimeType === "text/html") {
    return FileCode;
  }
  if (
    mimeType.includes("document") ||
    mimeType.includes("word") ||
    mimeType === "application/pdf" ||
    mimeType === "text/markdown" ||
    mimeType === "text/plain"
  ) {
    return FileText;
  }
  return File;
}

/**
 * Returns the appropriate Lucide icon component for a given file extension
 */
export function getFileIconByExtension(extension: string | undefined): LucideIcon {
  if (!extension) {
    return File;
  }
  const ext = extension.toLowerCase().replace(".", "");
  switch (ext) {
    case "png":
    case "jpg":
    case "jpeg":
    case "gif":
    case "webp":
    case "svg":
    case "bmp":
      return FileImage;
    case "xlsx":
    case "xls":
    case "csv":
      return FileSpreadsheet;
    case "html":
    case "htm":
      return FileCode;
    case "pdf":
    case "docx":
    case "doc":
    case "txt":
    case "md":
    case "markdown":
    case "pptx":
    case "ppt":
      return FileText;
    default:
      return File;
  }
}

/**
 * Returns the Tailwind text color class for a file icon based on file type/extension
 */
export function getFileIconColorClass(fileType: string | undefined): string {
  if (!fileType) {
    return "text-muted-foreground";
  }
  const ext = fileType.toLowerCase().replace(".", "");
  switch (ext) {
    case "pdf":
      return "text-red-500";
    case "docx":
    case "doc":
      return "text-blue-500";
    case "xlsx":
    case "xls":
    case "csv":
      return "text-green-500";
    case "pptx":
    case "ppt":
      return "text-orange-500";
    case "png":
    case "jpg":
    case "jpeg":
    case "gif":
    case "webp":
      return "text-purple-500";
    case "html":
    case "htm":
      return "text-orange-600";
    case "md":
    case "markdown":
      return "text-slate-600";
    case "txt":
      return "text-gray-500";
    default:
      return "text-muted-foreground";
  }
}

/**
 * Returns the Tailwind classes for a file type badge (background + text color)
 */
export function getFileTypeBadgeClass(fileType: string): string {
  const ext = fileType.toLowerCase().replace(".", "");
  switch (ext) {
    case "pdf":
      return "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300";
    case "docx":
    case "doc":
      return "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300";
    case "xlsx":
    case "xls":
    case "csv":
      return "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300";
    case "pptx":
    case "ppt":
      return "bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-300";
    case "png":
    case "jpg":
    case "jpeg":
    case "gif":
    case "webp":
      return "bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300";
    case "html":
    case "htm":
      return "bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-300";
    case "md":
    case "markdown":
      return "bg-slate-100 text-slate-700 dark:bg-slate-900/30 dark:text-slate-300";
    case "txt":
      return "bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300";
    default:
      return "bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300";
  }
}

/**
 * Formats a file size in bytes to a human-readable string
 */
export function formatFileSize(bytes: number): string {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + " " + sizes[i];
}
