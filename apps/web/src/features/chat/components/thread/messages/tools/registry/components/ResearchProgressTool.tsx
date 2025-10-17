import React, { useState } from "react";
import { ToolComponentProps } from "../../types";
import { Card } from "@/components/ui/card";
import { Loader2, ChevronDown, ChevronUp, Globe, CheckCircle } from "lucide-react";
import { MinimalistBadge } from "@/components/ui/minimalist-badge";

interface ParsedToolResult {
  step: number;
  message: string;
  citations: Array<{
    url: string;
    title?: string;
    favicon_url?: string;
  }>;
}

function parseToolResult(toolResult: any): ParsedToolResult {
  try {
    const content = typeof toolResult?.content === 'string' 
      ? JSON.parse(toolResult.content)
      : toolResult?.content || {};
    
    return {
      step: content.step || 1,
      message: content.message || "Processing...",
      citations: content.citations || []
    };
  } catch (error) {
    console.warn("Failed to parse research progress tool result:", error);
    return {
      step: 1,
      message: "Processing...",
      citations: []
    };
  }
}

function truncateText(text: string, maxLength: number = 20): string {
  if (text.length <= maxLength) {
    return text;
  }
  return text.substring(0, maxLength) + "...";
}

function CitationCard({ citation }: { citation: ParsedToolResult['citations'][0] }) {
  const displayText = citation.title || citation.url;
  const truncatedText = truncateText(displayText);
  
  return (
    <a
      href={citation.url}
      target="_blank"
      rel="noopener noreferrer"
      className="group block p-2 border rounded-lg cursor-pointer hover:bg-accent transition-colors"
      title={displayText}
    >
      <div className="flex items-center gap-2">
        <div className="w-4 h-4 flex-shrink-0">
          {citation.favicon_url ? (
            <img
              src={citation.favicon_url}
              alt=""
              className="w-4 h-4 object-contain"
              onError={(e) => {
                // Replace with fallback icon if image fails to load
                const target = e.target as HTMLImageElement;
                target.style.display = 'none';
                target.parentElement!.innerHTML = '<div class="w-4 h-4 text-muted-foreground"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20"/><path d="M2 12h20"/></svg></div>';
              }}
            />
          ) : (
            <Globe className="w-4 h-4 text-muted-foreground" />
          )}
        </div>
        <span className="text-xs text-muted-foreground group-hover:text-foreground transition-colors">
          {truncatedText}
        </span>
      </div>
    </a>
  );
}

export function ResearchProgressTool({ 
  toolCall, 
  toolResult, 
  state, 
  streaming 
}: ToolComponentProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  
  // Parse tool result data
  const data = parseToolResult(toolResult);
  const progressPercentage = (data.step / 5) * 100;
  
  // Determine if still loading - should spin while research is in progress
  // Research is ongoing if we're in loading state OR if step < 5 (final step)
  const isLoading = (state === 'loading' || streaming) || (data.step < 5);
  

  
  return (
    <Card className="w-full p-4 space-y-3">
        {/* Header with spinner, message, and expand button */}
        <div className="flex items-center gap-3 w-full">
        {data.step >= 5 ? (
          <MinimalistBadge
            icon={CheckCircle}
            tooltip="Research completed"
          />
        ) : (
          <MinimalistBadge
            icon={Loader2}
            tooltip="Research in progress"
            className={isLoading ? "animate-spin-slow bg-transparent" : "bg-transparent"}
          />
        )}
                  <div className="flex-1 w-full">
            <div className="flex items-center justify-between w-full">
            <div>
              <h3 className="font-medium text-sm">Research Progress</h3>
              <p className="text-sm text-muted-foreground">
                {data.message}
              </p>
            </div>
            <button
              onClick={() => setIsExpanded(!isExpanded)}
              className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
            >
              {data.citations.length > 0 && (
                <span>{data.citations.length} sources</span>
              )}
              {isExpanded ? (
                <ChevronUp className="w-4 h-4" />
              ) : (
                <ChevronDown className="w-4 h-4" />
              )}
            </button>
          </div>
        </div>
      </div>

      {/* Progress bar */}
      <div className="space-y-2">
        <div className="flex justify-between text-xs text-muted-foreground">
          <span>Step {data.step} of 5</span>
          <span>{Math.round(progressPercentage)}%</span>
        </div>
        <div className="w-full bg-muted rounded-full h-2">
          <div 
            className="bg-primary rounded-full h-2 transition-all duration-300"
            style={{ width: `${progressPercentage}%` }}
          />
        </div>
      </div>

      {/* Expanded content with citations */}
      {isExpanded && (
        <div className="space-y-3">
          <div className="border-t pt-3">
            <h4 className="text-sm font-medium mb-3">
              Sources searched so far:
            </h4>
            {data.citations.length > 0 ? (
              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-2">
                {data.citations.map((citation: ParsedToolResult['citations'][0], index: number) => (
                  <CitationCard key={index} citation={citation} />
                ))}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground italic">
                No sources searched yet
              </p>
            )}
          </div>
        </div>
      )}
    </Card>
  );
} 