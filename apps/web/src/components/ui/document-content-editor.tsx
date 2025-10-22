"use client";

import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import {
  Bold,
  Italic,
  Underline,
  Heading1,
  Heading2,
  Heading3,
  List,
  ListOrdered,
  Code,
  Quote,
  Link,
  FileEdit,
} from "lucide-react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { MarkdownText } from "@/components/ui/markdown-text";
import { cn } from "@/lib/utils";
import { getScrollbarClasses } from "@/lib/scrollbar-styles";

interface DocumentContentEditorProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  value: string;
  onChange: (value: string) => void;
  onSave: (content: string) => Promise<void>;
  title?: string;
  placeholder?: string;
  saving?: boolean;
}

export function DocumentContentEditor({
  open,
  onOpenChange,
  value,
  onChange,
  onSave,
  title = "Edit Document Content",
  placeholder = "Enter document content here...",
  saving = false,
}: DocumentContentEditorProps) {
  const [localValue, setLocalValue] = useState(value);
  const [activeTab, setActiveTab] = useState<string>("edit");

  // Update local value when external value changes or dialog opens
  useEffect(() => {
    if (open) {
      setLocalValue(value);
      setActiveTab("edit");
    }
  }, [open, value]);

  const handleSave = async () => {
    // Pass the localValue directly to onSave to avoid React state update timing issues
    await onSave(localValue);
  };

  const handleCancel = () => {
    setLocalValue(value); // Reset to original value
    onOpenChange(false);
  };

  const insertMarkdown = (before: string, after: string = "", placeholder: string = "") => {
    const textarea = document.querySelector('textarea[data-document-content-editor]') as HTMLTextAreaElement;
    if (!textarea) return;

    const start = textarea.selectionStart;
    const end = textarea.selectionEnd;
    const selectedText = localValue.substring(start, end);
    const textToInsert = selectedText || placeholder;

    const newText =
      localValue.substring(0, start) +
      before +
      textToInsert +
      after +
      localValue.substring(end);

    setLocalValue(newText);

    // Set cursor position after insertion
    setTimeout(() => {
      textarea.focus();
      const newCursorPos = start + before.length + textToInsert.length;
      textarea.setSelectionRange(newCursorPos, newCursorPos);
    }, 0);
  };

  const toolbarButtons = [
    {
      icon: Heading1,
      label: "Heading 1",
      action: () => insertMarkdown("# ", "", "Heading"),
    },
    {
      icon: Heading2,
      label: "Heading 2",
      action: () => insertMarkdown("## ", "", "Heading"),
    },
    {
      icon: Heading3,
      label: "Heading 3",
      action: () => insertMarkdown("### ", "", "Heading"),
    },
    {
      icon: Bold,
      label: "Bold",
      action: () => insertMarkdown("**", "**", "bold text"),
    },
    {
      icon: Italic,
      label: "Italic",
      action: () => insertMarkdown("_", "_", "italic text"),
    },
    {
      icon: Underline,
      label: "Underline",
      action: () => insertMarkdown("<u>", "</u>", "underlined text"),
    },
    {
      icon: Code,
      label: "Code",
      action: () => insertMarkdown("`", "`", "code"),
    },
    {
      icon: Quote,
      label: "Quote",
      action: () => insertMarkdown("> ", "", "quote"),
    },
    {
      icon: List,
      label: "Bulleted List",
      action: () => insertMarkdown("- ", "", "list item"),
    },
    {
      icon: ListOrdered,
      label: "Numbered List",
      action: () => insertMarkdown("1. ", "", "list item"),
    },
    {
      icon: Link,
      label: "Link",
      action: () => insertMarkdown("[", "](url)", "link text"),
    },
  ];

  return (
    <Dialog open={open} onOpenChange={saving ? undefined : onOpenChange}>
      <DialogContent className="max-w-5xl h-[90vh] flex flex-col p-0 gap-0">
        <DialogHeader className="px-6 pt-6 pb-4 border-b flex-shrink-0">
          <div className="flex items-center justify-between">
            <DialogTitle className="flex items-center gap-2.5 text-xl">
              <FileEdit className="h-5 w-5" />
              {title}
            </DialogTitle>
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                onClick={handleCancel}
                size="sm"
                disabled={saving}
              >
                Cancel
              </Button>
              <Button
                onClick={handleSave}
                size="sm"
                disabled={saving}
              >
                {saving ? (
                  <div className="flex items-center space-x-2">
                    <div className="h-4 w-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                    <span>Saving...</span>
                  </div>
                ) : (
                  "Save Changes"
                )}
              </Button>
            </div>
          </div>
        </DialogHeader>

        <div className="flex-1 min-h-0 px-6 pb-6 pt-4">
          <Tabs value={activeTab} onValueChange={setActiveTab} className="flex flex-col h-full">
            <TabsList className="w-fit mb-4">
              <TabsTrigger value="edit">Edit</TabsTrigger>
              <TabsTrigger value="preview">Preview</TabsTrigger>
            </TabsList>

            <TabsContent value="edit" className="flex-1 flex flex-col min-h-0 mt-0">
              {/* Single card container */}
              <div className="flex-1 flex flex-col border rounded-lg overflow-hidden bg-card min-h-0">
                {/* Toolbar */}
                <div className="flex flex-wrap gap-1 p-3 border-b bg-muted/30 flex-shrink-0">
                  {toolbarButtons.map((button, index) => (
                    <Button
                      key={index}
                      type="button"
                      variant="ghost"
                      size="sm"
                      onClick={button.action}
                      className="h-8 w-8 p-0 hover:bg-background"
                      title={button.label}
                      disabled={saving}
                    >
                      <button.icon className="h-4 w-4" />
                    </Button>
                  ))}
                </div>

                {/* Editor - scrollable */}
                <div className={cn("flex-1 min-h-0 overflow-y-auto", ...getScrollbarClasses('y'))}>
                  <Textarea
                    data-document-content-editor
                    value={localValue}
                    onChange={(e) => setLocalValue(e.target.value)}
                    placeholder={placeholder}
                    disabled={saving}
                    className="w-full h-full min-h-full resize-none font-mono text-sm border-0 focus-visible:ring-0 focus-visible:ring-offset-0 rounded-none p-4"
                  />
                </div>
              </div>
            </TabsContent>

            <TabsContent value="preview" className="flex-1 min-h-0 mt-0">
              {/* Single card container for preview */}
              <div className={cn("h-full border rounded-lg overflow-hidden bg-card")}>
                <div className={cn("h-full overflow-y-auto p-6", ...getScrollbarClasses('y'))}>
                  {localValue ? (
                    <div className="document-preview max-w-none">
                      <MarkdownText>{localValue}</MarkdownText>
                    </div>
                  ) : (
                    <p className="text-muted-foreground text-center py-8">
                      No content to preview. Start writing in the Edit tab.
                    </p>
                  )}
                </div>
              </div>
            </TabsContent>
          </Tabs>
        </div>
      </DialogContent>
    </Dialog>
  );
}
