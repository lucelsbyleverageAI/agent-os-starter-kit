"use client";

import React, { useEffect, useState, useCallback, useMemo } from "react";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Download, Loader2, FileText, AlertCircle } from "lucide-react";
import { MarkdownText } from "@/components/ui/markdown-text";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark } from "react-syntax-highlighter/dist/esm/styles/prism";

// Types
interface FilePreviewSheetProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  file: {
    display_name: string;
    filename: string;
    file_type: string;
    mime_type: string;
    storage_path: string;
    file_size: number;
    description?: string;
  } | null;
}

interface PreviewState {
  loading: boolean;
  error: string | null;
  content: string | null;
  objectUrl: string | null;
  tableData: string[][] | null;
  htmlContent: string | null;
}

// Language mapping for syntax highlighting
const LANGUAGE_MAP: Record<string, string> = {
  js: "javascript",
  jsx: "javascript",
  ts: "typescript",
  tsx: "typescript",
  py: "python",
  rb: "ruby",
  go: "go",
  rs: "rust",
  java: "java",
  cpp: "cpp",
  c: "c",
  cs: "csharp",
  php: "php",
  swift: "swift",
  kt: "kotlin",
  scala: "scala",
  sh: "bash",
  bash: "bash",
  zsh: "bash",
  json: "json",
  xml: "xml",
  html: "html",
  css: "css",
  scss: "scss",
  sass: "sass",
  less: "less",
  sql: "sql",
  yaml: "yaml",
  yml: "yaml",
  toml: "toml",
  ini: "ini",
  dockerfile: "dockerfile",
  makefile: "makefile",
};

// Helper functions
function formatFileSize(bytes: number): string {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + " " + sizes[i];
}

function getFileExtension(filename: string | undefined): string {
  if (!filename) return "";
  const ext = filename.split(".").pop()?.toLowerCase() || "";
  return ext;
}

function parseCSV(text: string): string[][] {
  const lines = text.split("\n").filter((line) => line.trim());
  return lines.map((row) =>
    row.split(",").map((cell) => cell.trim().replace(/^"|"$/g, ""))
  );
}

// File type detection helpers
function isImage(mimeType: string | undefined): boolean {
  return mimeType?.startsWith("image/") ?? false;
}

function isPDF(mimeType: string | undefined): boolean {
  return mimeType === "application/pdf";
}

function isMarkdown(ext: string): boolean {
  return ["md", "markdown"].includes(ext);
}

function isText(ext: string): boolean {
  return ["txt"].includes(ext);
}

function isCSV(ext: string, mimeType: string | undefined): boolean {
  return ext === "csv" || mimeType === "text/csv";
}

function isExcel(ext: string): boolean {
  return ["xlsx", "xls"].includes(ext);
}

function isWord(ext: string): boolean {
  return ["docx", "doc"].includes(ext);
}

function isPowerPoint(ext: string): boolean {
  return ["pptx", "ppt"].includes(ext);
}

function isCode(ext: string): boolean {
  return ext in LANGUAGE_MAP;
}

// Table component for CSV/Excel preview
function DataTable({ data }: { data: string[][] }) {
  if (!data || data.length === 0) return null;

  const headers = data[0];
  const rows = data.slice(1);

  return (
    <div className="overflow-auto">
      <table className="w-full border-collapse text-sm">
        <thead className="bg-muted sticky top-0">
          <tr>
            {headers.map((header, i) => (
              <th
                key={i}
                className="border border-border p-2 text-left font-medium text-foreground"
              >
                {header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, rowIndex) => (
            <tr key={rowIndex} className="hover:bg-muted/50">
              {row.map((cell, cellIndex) => (
                <td
                  key={cellIndex}
                  className="border border-border p-2 text-muted-foreground"
                >
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function FilePreviewSheet({
  open,
  onOpenChange,
  file,
}: FilePreviewSheetProps) {
  const [previewState, setPreviewState] = useState<PreviewState>({
    loading: false,
    error: null,
    content: null,
    objectUrl: null,
    tableData: null,
    htmlContent: null,
  });

  const fileExtension = useMemo(() => {
    return file ? getFileExtension(file.filename) : "";
  }, [file?.filename]);

  const language = useMemo(() => {
    return LANGUAGE_MAP[fileExtension] || "text";
  }, [fileExtension]);

  // Cleanup object URLs on unmount or file change
  useEffect(() => {
    return () => {
      if (previewState.objectUrl) {
        URL.revokeObjectURL(previewState.objectUrl);
      }
    };
  }, [previewState.objectUrl]);

  // Reset state when file changes
  useEffect(() => {
    if (previewState.objectUrl) {
      URL.revokeObjectURL(previewState.objectUrl);
    }
    setPreviewState({
      loading: false,
      error: null,
      content: null,
      objectUrl: null,
      tableData: null,
      htmlContent: null,
    });
  }, [file?.storage_path]);

  // Fetch file content when sheet opens
  useEffect(() => {
    if (!open || !file || previewState.content || previewState.objectUrl || previewState.tableData || previewState.htmlContent) {
      return;
    }

    const fetchFileContent = async () => {
      setPreviewState((prev) => ({ ...prev, loading: true, error: null }));

      try {
        const params = new URLSearchParams({
          path: file.storage_path,
          bucket: "agent-outputs",
          filename: file.filename,
        });

        const response = await fetch(
          `/api/langconnect/storage/download?${params.toString()}`
        );

        if (!response.ok) {
          throw new Error(`Failed to fetch file: ${response.statusText}`);
        }

        const blob = await response.blob();
        const ext = getFileExtension(file.filename);

        // Handle different file types
        if (isImage(file.mime_type)) {
          const url = URL.createObjectURL(blob);
          setPreviewState((prev) => ({
            ...prev,
            loading: false,
            objectUrl: url,
          }));
        } else if (isPDF(file.mime_type)) {
          const url = URL.createObjectURL(blob);
          setPreviewState((prev) => ({
            ...prev,
            loading: false,
            objectUrl: url,
          }));
        } else if (isCSV(ext, file.mime_type)) {
          const text = await blob.text();
          const tableData = parseCSV(text);
          setPreviewState((prev) => ({
            ...prev,
            loading: false,
            tableData,
          }));
        } else if (isExcel(ext)) {
          // Dynamic import for xlsx to reduce bundle size
          const XLSX = await import("xlsx");
          const arrayBuffer = await blob.arrayBuffer();
          const workbook = XLSX.read(arrayBuffer, { type: "array" });
          const firstSheetName = workbook.SheetNames[0];
          const firstSheet = workbook.Sheets[firstSheetName];
          const jsonData = XLSX.utils.sheet_to_json(firstSheet, {
            header: 1,
          }) as string[][];
          setPreviewState((prev) => ({
            ...prev,
            loading: false,
            tableData: jsonData,
          }));
        } else if (isWord(ext)) {
          // Dynamic import for mammoth to reduce bundle size
          const mammoth = await import("mammoth");
          const arrayBuffer = await blob.arrayBuffer();
          const result = await mammoth.convertToHtml({ arrayBuffer });
          setPreviewState((prev) => ({
            ...prev,
            loading: false,
            htmlContent: result.value,
          }));
        } else if (
          isMarkdown(ext) ||
          isText(ext) ||
          isCode(ext)
        ) {
          const text = await blob.text();
          setPreviewState((prev) => ({
            ...prev,
            loading: false,
            content: text,
          }));
        } else {
          // For unsupported types, just mark as loaded
          setPreviewState((prev) => ({
            ...prev,
            loading: false,
          }));
        }
      } catch (error) {
        console.error("Error fetching file:", error);
        setPreviewState((prev) => ({
          ...prev,
          loading: false,
          error: error instanceof Error ? error.message : "Failed to load file",
        }));
      }
    };

    fetchFileContent();
  }, [open, file, previewState.content, previewState.objectUrl, previewState.tableData, previewState.htmlContent]);

  // Download handler
  const handleDownload = useCallback(async () => {
    if (!file) return;

    try {
      const params = new URLSearchParams({
        path: file.storage_path,
        bucket: "agent-outputs",
        filename: file.filename,
      });

      const response = await fetch(
        `/api/langconnect/storage/download?${params.toString()}`
      );

      if (!response.ok) {
        throw new Error("Download failed");
      }

      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = file.filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (error) {
      console.error("Download error:", error);
    }
  }, [file]);

  // Render preview content based on file type
  const renderPreviewContent = () => {
    if (!file) return null;

    const ext = fileExtension;

    // Loading state
    if (previewState.loading) {
      return (
        <div className="flex flex-col items-center justify-center h-full gap-3 text-muted-foreground">
          <Loader2 className="h-8 w-8 animate-spin" />
          <p className="text-sm">Loading preview...</p>
        </div>
      );
    }

    // Error state
    if (previewState.error) {
      return (
        <div className="flex flex-col items-center justify-center h-full gap-3 text-destructive">
          <AlertCircle className="h-8 w-8" />
          <p className="text-sm">{previewState.error}</p>
          <Button variant="outline" size="sm" onClick={handleDownload}>
            <Download className="h-4 w-4 mr-2" />
            Download Instead
          </Button>
        </div>
      );
    }

    // Image preview
    if (isImage(file.mime_type) && previewState.objectUrl) {
      return (
        <div className="flex items-center justify-center h-full p-4">
          <img
            src={previewState.objectUrl}
            alt={file.display_name}
            className="max-w-full max-h-full object-contain rounded-lg"
          />
        </div>
      );
    }

    // PDF preview
    if (isPDF(file.mime_type) && previewState.objectUrl) {
      return (
        <iframe
          src={previewState.objectUrl}
          className="w-full h-full border-0 rounded-lg"
          title={file.display_name}
        />
      );
    }

    // CSV/Excel table preview
    if ((isCSV(ext, file.mime_type) || isExcel(ext)) && previewState.tableData) {
      return (
        <div className="p-4">
          <DataTable data={previewState.tableData} />
        </div>
      );
    }

    // Word document preview
    if (isWord(ext) && previewState.htmlContent) {
      return (
        <div className="p-6">
          <div
            className="prose prose-sm max-w-none dark:prose-invert"
            dangerouslySetInnerHTML={{ __html: previewState.htmlContent }}
          />
        </div>
      );
    }

    // Markdown preview
    if (isMarkdown(ext) && previewState.content) {
      return (
        <div className="p-6">
          <MarkdownText className="prose prose-sm max-w-none dark:prose-invert">
            {previewState.content}
          </MarkdownText>
        </div>
      );
    }

    // Code preview with syntax highlighting
    if (isCode(ext) && previewState.content) {
      return (
        <SyntaxHighlighter
          language={language}
          style={oneDark}
          customStyle={{
            margin: 0,
            borderRadius: "0.5rem",
            fontSize: "0.875rem",
          }}
          showLineNumbers
        >
          {previewState.content}
        </SyntaxHighlighter>
      );
    }

    // Plain text preview
    if (isText(ext) && previewState.content) {
      return (
        <pre className="p-4 bg-muted rounded-lg overflow-auto text-sm font-mono whitespace-pre-wrap text-foreground">
          {previewState.content}
        </pre>
      );
    }

    // PowerPoint and other unsupported formats
    if (isPowerPoint(ext)) {
      return (
        <div className="flex flex-col items-center justify-center h-full gap-4 text-center p-8">
          <FileText className="h-16 w-16 text-muted-foreground" />
          <div>
            <h3 className="font-medium text-foreground mb-1">
              PowerPoint Preview Not Available
            </h3>
            <p className="text-sm text-muted-foreground">
              PowerPoint files cannot be previewed in the browser.
              <br />
              Please download the file to view it.
            </p>
          </div>
          <Button variant="default" onClick={handleDownload}>
            <Download className="h-4 w-4 mr-2" />
            Download File
          </Button>
        </div>
      );
    }

    // Generic fallback for unsupported types
    return (
      <div className="flex flex-col items-center justify-center h-full gap-4 text-center p-8">
        <FileText className="h-16 w-16 text-muted-foreground" />
        <div>
          <h3 className="font-medium text-foreground mb-1">
            Preview Not Available
          </h3>
          <p className="text-sm text-muted-foreground">
            This file type ({ext.toUpperCase() || "unknown"}) cannot be
            previewed.
            <br />
            Please download the file to view it.
          </p>
        </div>
        <Button variant="default" onClick={handleDownload}>
          <Download className="h-4 w-4 mr-2" />
          Download File
        </Button>
      </div>
    );
  };

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side="right"
        className="w-full sm:max-w-xl md:max-w-2xl lg:max-w-3xl flex flex-col p-0"
      >
        {/* Header */}
        <SheetHeader className="p-4 pb-3 border-b flex-shrink-0">
          <div className="flex items-start justify-between gap-4 pr-8">
            <div className="min-w-0 flex-1">
              <SheetTitle className="truncate">{file?.display_name}</SheetTitle>
              <SheetDescription className="mt-1">
                {file?.filename} &middot; {file ? formatFileSize(file.file_size) : ""}
                {file?.description && (
                  <>
                    <br />
                    <span className="text-muted-foreground">
                      {file.description}
                    </span>
                  </>
                )}
              </SheetDescription>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={handleDownload}
              className="flex-shrink-0"
            >
              <Download className="h-4 w-4 mr-2" />
              Download
            </Button>
          </div>
        </SheetHeader>

        {/* Content */}
        <ScrollArea className="flex-1 min-h-0">
          <div className="h-full min-h-[400px]">{renderPreviewContent()}</div>
        </ScrollArea>
      </SheetContent>
    </Sheet>
  );
}
