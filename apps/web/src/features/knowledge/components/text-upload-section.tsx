"use client";

import React from "react";
import { Textarea } from "@/components/ui/textarea";

interface TextUploadSectionProps {
  textContent: string;
  onTextChange: (text: string) => void;
}

export function TextUploadSection({ textContent, onTextChange }: TextUploadSectionProps) {
  return (
    <div className="space-y-4">
      <div className="space-y-2">
        <Textarea
          placeholder="Paste or type text here..."
          value={textContent}
          onChange={(e) => onTextChange(e.target.value)}
          className="min-h-[200px] resize-y"
        />
      </div>
    </div>
  );
} 