"use client";

import React, { useMemo, useCallback } from "react";
import { FileText, Copy, Download } from "lucide-react";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark } from "react-syntax-highlighter/dist/esm/styles/prism";
import { MarkdownText } from "@/components/ui/markdown-text";
import { FileItem } from "@/types/deep-agent";

interface FileViewDialogProps {
  file: FileItem;
  onClose: () => void;
}

export const FileViewDialog = React.memo<FileViewDialogProps>(
  ({ file, onClose }) => {
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

    const handleDownload = useCallback(() => {
      if (file.content) {
        const blob = new Blob([file.content], { type: "text/plain" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = file.path;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
      }
    }, [file.content, file.path]);

    return (
      <Dialog open={true} onOpenChange={onClose}>
        <DialogContent className="max-w-4xl w-full max-h-[80vh] flex flex-col">
          <DialogTitle className="sr-only">{file.path}</DialogTitle>
          <div className="flex justify-between items-center gap-4 pb-4 border-b">
            <div className="flex items-center gap-2 min-w-0">
              <FileText className="w-5 h-5 text-muted-foreground flex-shrink-0" />
              <span className="font-medium truncate">{file.path}</span>
            </div>
            <div className="flex gap-2 flex-shrink-0">
              <Button
                variant="ghost"
                size="sm"
                onClick={handleCopy}
                className="flex items-center gap-2"
              >
                <Copy size={16} />
                Copy
              </Button>
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
