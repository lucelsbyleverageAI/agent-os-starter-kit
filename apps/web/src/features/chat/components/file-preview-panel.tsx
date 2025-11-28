"use client";

import React, { useEffect, useState, useCallback, useMemo, useRef } from "react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Download, Loader2, FileText, AlertCircle, X } from "lucide-react";
import { MarkdownText } from "@/components/ui/markdown-text";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark } from "react-syntax-highlighter/dist/esm/styles/prism";
import { cn } from "@/lib/utils";
import { useFilePreview, type FilePreviewFile } from "../context/file-preview-context";

// Types
interface WorkbookSheet {
  name: string;
  data: string[][];
}

interface PreviewState {
  loading: boolean;
  error: string | null;
  content: string | null;
  objectUrl: string | null;
  tableData: string[][] | null;
  htmlContent: string | null;
  workbookSheets: WorkbookSheet[] | null;
  activeSheet: number;
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

// Sheet tabs component for Excel workbooks
function SheetTabs({
  sheets,
  activeIndex,
  onSelect,
}: {
  sheets: WorkbookSheet[];
  activeIndex: number;
  onSelect: (index: number) => void;
}) {
  if (sheets.length <= 1) return null;

  return (
    <div className="flex gap-0.5 border-t bg-muted/30 px-2 py-1 overflow-x-auto">
      {sheets.map((sheet, i) => (
        <button
          key={i}
          onClick={() => onSelect(i)}
          className={cn(
            "px-3 py-1.5 text-xs font-medium rounded-md transition-all whitespace-nowrap",
            i === activeIndex
              ? "bg-background text-foreground shadow-sm border border-border"
              : "text-muted-foreground hover:text-foreground hover:bg-background/50"
          )}
        >
          {sheet.name}
        </button>
      ))}
    </div>
  );
}

// Enhanced table component for CSV/Excel preview
function DataTable({ data }: { data: string[][] }) {
  if (!data || data.length === 0) return null;

  const headers = data[0];
  const rows = data.slice(1);

  return (
    <div className="overflow-auto max-h-[calc(100vh-280px)]">
      <table className="w-full border-collapse text-sm">
        <thead className="bg-muted/80 sticky top-0 z-10">
          <tr>
            {/* Row number header */}
            <th className="border border-border p-2 text-center font-medium text-muted-foreground bg-muted w-12 sticky left-0">
              #
            </th>
            {headers.map((header, i) => (
              <th
                key={i}
                className="border border-border p-2 text-left font-medium text-foreground min-w-[100px]"
              >
                {header || `Column ${i + 1}`}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, rowIndex) => (
            <tr
              key={rowIndex}
              className={cn(
                "hover:bg-primary/5 transition-colors",
                rowIndex % 2 === 0 ? "bg-background" : "bg-muted/20"
              )}
            >
              {/* Row number */}
              <td className="border border-border p-2 text-center text-xs text-muted-foreground bg-muted/50 sticky left-0 font-mono">
                {rowIndex + 1}
              </td>
              {row.map((cell, cellIndex) => (
                <td
                  key={cellIndex}
                  className="border border-border p-2 text-foreground"
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

export function FilePreviewPanel() {
  const { file, closePreview } = useFilePreview();

  const [previewState, setPreviewState] = useState<PreviewState>({
    loading: false,
    error: null,
    content: null,
    objectUrl: null,
    tableData: null,
    htmlContent: null,
    workbookSheets: null,
    activeSheet: 0,
  });

  const docxContainerRef = useRef<HTMLDivElement>(null);

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
      workbookSheets: null,
      activeSheet: 0,
    });
  }, [file?.storage_path]);

  // Fetch file content when panel mounts or file changes
  useEffect(() => {
    if (!file || previewState.content || previewState.objectUrl || previewState.tableData || previewState.htmlContent || previewState.workbookSheets) {
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

          // Parse all sheets
          const sheets: WorkbookSheet[] = workbook.SheetNames.map((name) => ({
            name,
            data: XLSX.utils.sheet_to_json(workbook.Sheets[name], {
              header: 1,
            }) as string[][],
          }));

          setPreviewState((prev) => ({
            ...prev,
            loading: false,
            workbookSheets: sheets,
            activeSheet: 0,
            tableData: sheets[0]?.data || null,
          }));
        } else if (isWord(ext)) {
          // Dynamic import for docx-preview for better Word rendering
          const docxPreview = await import("docx-preview");
          const arrayBuffer = await blob.arrayBuffer();

          // Create a temporary container to render the document
          const tempContainer = document.createElement("div");
          await docxPreview.renderAsync(arrayBuffer, tempContainer, undefined, {
            className: "docx-preview",
            inWrapper: false,
            ignoreWidth: true,
            ignoreHeight: false,
            ignoreFonts: false,
            breakPages: true,
            useBase64URL: true,
          });

          // Style each section via JavaScript (inline styles override library styles)
          const sections = tempContainer.querySelectorAll("section.docx-preview");
          const totalPages = sections.length;
          sections.forEach((section, index) => {
            const el = section as HTMLElement;
            el.style.backgroundColor = "white";
            el.style.border = "1px solid #e5e7eb";
            el.style.boxShadow = "0 1px 3px 0 rgb(0 0 0 / 0.1)";
            el.style.marginBottom = "12px";
            el.style.position = "relative";

            // Add page number
            const pageNumber = document.createElement("div");
            pageNumber.textContent = `Page ${index + 1} of ${totalPages}`;
            pageNumber.style.cssText = `
              position: absolute;
              bottom: 12px;
              left: 50%;
              transform: translateX(-50%);
              font-size: 12px;
              color: #6b7280;
              background: rgba(255,255,255,0.9);
              padding: 4px 12px;
              border-radius: 9999px;
            `;
            el.appendChild(pageNumber);
          });

          // Wrap all content in our own styled container
          const wrapper = document.createElement("div");
          wrapper.style.cssText = `
            background: #f3f4f6;
            padding: 12px;
            min-height: 100%;
          `;
          while (tempContainer.firstChild) {
            wrapper.appendChild(tempContainer.firstChild);
          }
          tempContainer.appendChild(wrapper);

          setPreviewState((prev) => ({
            ...prev,
            loading: false,
            htmlContent: tempContainer.innerHTML,
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
  }, [file, previewState.content, previewState.objectUrl, previewState.tableData, previewState.htmlContent, previewState.workbookSheets]);

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

  // Sheet switching handler for Excel workbooks
  const handleSheetChange = useCallback((index: number) => {
    if (!previewState.workbookSheets || index < 0 || index >= previewState.workbookSheets.length) {
      return;
    }
    setPreviewState((prev) => ({
      ...prev,
      activeSheet: index,
      tableData: prev.workbookSheets?.[index]?.data || null,
    }));
  }, [previewState.workbookSheets]);

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

    // Excel table preview with sheet tabs
    if (isExcel(ext) && previewState.workbookSheets && previewState.tableData) {
      return (
        <div className="flex flex-col h-full">
          <div className="flex-1 p-4 overflow-auto">
            <DataTable data={previewState.tableData} />
          </div>
          <SheetTabs
            sheets={previewState.workbookSheets}
            activeIndex={previewState.activeSheet}
            onSelect={handleSheetChange}
          />
        </div>
      );
    }

    // CSV table preview
    if (isCSV(ext, file.mime_type) && previewState.tableData) {
      return (
        <div className="p-4">
          <DataTable data={previewState.tableData} />
        </div>
      );
    }

    // Word document preview (using docx-preview)
    if (isWord(ext) && previewState.htmlContent) {
      return (
        <div
          ref={docxContainerRef}
          className="docx-preview-container overflow-auto h-full bg-[#f3f4f6]"
          dangerouslySetInnerHTML={{ __html: previewState.htmlContent }}
        />
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

  if (!file) return null;

  return (
    <div className="flex flex-col h-full border-l bg-muted/30">
      {/* Header */}
      <div className="p-4 pb-3 border-b flex-shrink-0 bg-muted/50">
        <div className="flex items-center justify-between gap-4">
          <div className="min-w-0 flex-1">
            <h2 className="font-semibold text-foreground truncate">
              {file.display_name} {`(${formatFileSize(file.file_size)})`}
            </h2>
            {file.description && (
              <p className="mt-1 text-sm text-muted-foreground">
                {file.description}
              </p>
            )}
          </div>
          <div className="flex items-center gap-2 flex-shrink-0">
            <Button
              variant="outline"
              size="sm"
              onClick={handleDownload}
            >
              <Download className="h-4 w-4 mr-2" />
              Download
            </Button>
            <Button
              variant="ghost"
              size="icon"
              onClick={closePreview}
              className="h-8 w-8"
            >
              <X className="h-4 w-4" />
              <span className="sr-only">Close preview</span>
            </Button>
          </div>
        </div>
      </div>

      {/* Content */}
      <ScrollArea className="flex-1 min-h-0">
        <div className="h-full min-h-[400px]">{renderPreviewContent()}</div>
      </ScrollArea>
    </div>
  );
}
