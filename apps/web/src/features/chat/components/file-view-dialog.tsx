"use client";

import React, { useMemo, useCallback, useState } from "react";
import { FileText, Copy, Download } from "lucide-react";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark } from "react-syntax-highlighter/dist/esm/styles/prism";
import { MarkdownText } from "@/components/ui/markdown-text";
import { FileItem } from "@/types/deep-agent";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  downloadMarkdownAsDocx,
  downloadAsMarkdown,
} from "@/lib/markdown-to-docx";

interface FileViewDialogProps {
  file: FileItem;
  onClose: () => void;
}

export const FileViewDialog = React.memo<FileViewDialogProps>(
  ({ file, onClose }) => {
    const [downloadFormat, setDownloadFormat] = useState<"md" | "docx">("md");

    const fileExtension = useMemo(() => {
      return file.path.split(".").pop()?.toLowerCase() || "";
    }, [file.path]);

    const isMarkdown = useMemo(() => {
      return fileExtension === "md" || fileExtension === "markdown" || fileExtension === "txt";
    }, [fileExtension]);

    const language = useMemo(() => {
      const languageMap: Record<string, string> = {
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
      return languageMap[fileExtension] || "text";
    }, [fileExtension]);

    const handleCopy = useCallback(() => {
      if (file.content) {
        navigator.clipboard.writeText(file.content);
      }
    }, [file.content]);

    const handleDownload = useCallback(async () => {
      if (file.content) {
        // Get filename without extension
        const filename = file.path.replace(/\.[^/.]+$/, "");

        try {
          if (downloadFormat === "docx") {
            await downloadMarkdownAsDocx(file.content, filename);
          } else {
            downloadAsMarkdown(file.content, filename);
          }
        } catch (error) {
          console.error("Download failed:", error);
        }
      }
    }, [file.content, file.path, downloadFormat]);

    return (
      <Dialog open={true} onOpenChange={onClose}>
        <DialogContent className="max-w-4xl w-full max-h-[80vh] flex flex-col">
          <DialogTitle className="sr-only">{file.path}</DialogTitle>
          <div className="flex justify-between items-center gap-4 pb-4 border-b">
            <div className="flex items-center gap-2 min-w-0">
              <FileText className="w-5 h-5 text-muted-foreground flex-shrink-0" />
              <span className="font-medium truncate">{file.path}</span>
            </div>
            <div className="flex gap-2 flex-shrink-0 items-center">
              <Button
                variant="ghost"
                size="sm"
                onClick={handleCopy}
                className="flex items-center gap-2"
              >
                <Copy size={16} />
                Copy
              </Button>
              <Select value={downloadFormat} onValueChange={(val) => setDownloadFormat(val as "md" | "docx")}>
                <SelectTrigger className="w-[180px]">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="md">Markdown (.md)</SelectItem>
                  <SelectItem value="docx">Word Document (.docx)</SelectItem>
                </SelectContent>
              </Select>
              <Button
                variant="ghost"
                size="sm"
                onClick={handleDownload}
                className="flex items-center gap-2"
              >
                <Download size={16} />
                Download
              </Button>
            </div>
          </div>

          <ScrollArea className="flex-1 max-h-[60vh]">
            {file.content ? (
              isMarkdown ? (
                <div className="p-6 bg-background rounded-lg">
                  <MarkdownText className="prose prose-sm max-w-none dark:prose-invert">
                    {file.content}
                  </MarkdownText>
                </div>
              ) : (
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
                  {file.content}
                </SyntaxHighlighter>
              )
            ) : (
              <div className="flex items-center justify-center p-12 text-muted-foreground">
                <p className="text-sm">File is empty</p>
              </div>
            )}
          </ScrollArea>
        </DialogContent>
      </Dialog>
    );
  },
);

FileViewDialog.displayName = "FileViewDialog";
