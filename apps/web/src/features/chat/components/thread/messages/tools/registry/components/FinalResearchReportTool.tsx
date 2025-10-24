import React, { useState, useCallback, useRef, useEffect } from "react";
import { ToolComponentProps } from "../../types";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { 
  Download as DownloadIcon, 
  Maximize2Icon, 
  X as XIcon, 
  FileText, 
  Link as LinkIcon,
  ChevronDown,
  ChevronRight
} from "lucide-react";
import { MinimalistBadge } from "@/components/ui/minimalist-badge";
import { CheckCircle, Loader2, AlertCircle } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import "katex/dist/katex.min.css";

interface ReportSection {
  name: string;
  content: string;
}

interface Citation {
  url: string;
  title: string;
  favicon_url?: string;
}

interface ReportMetadata {
  word_count: number;
  section_count: number;
  citation_count: number;
}

interface ReportData {
  sections: ReportSection[];
  total_citations: Citation[];
  metadata: ReportMetadata;
}

// Helper function to convert image to base64 with proper sizing
const getLogoAsBase64 = async (targetHeight: number = 40): Promise<string> => {
  try {
    const response = await fetch('/logo_icon_round.png');
    const blob = await response.blob();
    
    return new Promise((resolve, reject) => {
      const img = new Image();
      img.onload = () => {
        // Create canvas to resize image
        const canvas = document.createElement('canvas');
        const ctx = canvas.getContext('2d');
        if (!ctx) {
          reject(new Error('Failed to get canvas context'));
          return;
        }
        
        // Calculate new dimensions maintaining aspect ratio
        const aspectRatio = img.width / img.height;
        const newHeight = targetHeight;
        const newWidth = newHeight * aspectRatio;
        
        canvas.width = newWidth;
        canvas.height = newHeight;
        
        // Draw resized image
        ctx.drawImage(img, 0, 0, newWidth, newHeight);
        
        // Convert to base64
        resolve(canvas.toDataURL('image/png'));
      };
      
      img.onerror = reject;
      img.src = URL.createObjectURL(blob);
    });
  } catch (error) {
    console.error('Error loading logo:', error);
    return '';
  }
};

export function FinalResearchReportTool({ 
  toolCall, 
  toolResult, 
  state, 
  streaming,
  onRetry 
}: ToolComponentProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const [showCitations, setShowCitations] = useState(false);
  const modalRef = useRef<HTMLDivElement>(null);
  const sectionRefs = useRef<(HTMLDivElement | null)[]>([]);
  const [activeSection, setActiveSection] = useState<number>(0);

  // Parse tool result
  let reportData: ReportData | null = null;
  if (state === "completed" && toolResult?.content) {
    try {
      const parsed = typeof toolResult.content === "string" 
        ? JSON.parse(toolResult.content) 
        : toolResult.content;
      reportData = {
        sections: parsed.sections || [],
        total_citations: parsed.total_citations || [],
        metadata: parsed.metadata || { word_count: 0, section_count: 0, citation_count: 0 }
      };
    } catch (e) {
      console.error('Error parsing report data:', e);
      reportData = null;
    }
  }

  // Enhanced markdown to HTML converter for Word documents
  const markdownToHtml = (markdown: string): string => {
    // Handle tables first - improved markdown table parsing
    const handleTables = (text: string): string => {
      // Match markdown tables with proper formatting
      const lines = text.split('\n');
      let result = '';
      let i = 0;
      
      while (i < lines.length) {
        const line = lines[i].trim();
        
        // Check if this line starts a table (contains | characters)
        if (line.includes('|') && line.startsWith('|') && line.endsWith('|')) {
          const headerLine = line;
          
          // Check if next line is separator (contains -, :, |)
          if (i + 1 < lines.length) {
            const separatorLine = lines[i + 1].trim();
            if (separatorLine.includes('|') && (separatorLine.includes('-') || separatorLine.includes(':'))) {
              // This is a table! Parse it
              const headerCells = headerLine.split('|')
                .map(cell => cell.trim())
                .filter(cell => cell.length > 0);
              
              const headerHtml = headerCells.map(cell => `<th>${cell}</th>`).join('');
              
              // Skip separator line and collect data rows
              i += 2;
              const rows = [];
              while (i < lines.length && lines[i].trim().includes('|') && 
                     lines[i].trim().startsWith('|') && lines[i].trim().endsWith('|')) {
                const cells = lines[i].trim().split('|')
                  .map(cell => cell.trim())
                  .filter(cell => cell.length > 0);
                if (cells.length > 0) {
                  const cellsHtml = cells.map(cell => `<td>${cell}</td>`).join('');
                  rows.push(`<tr>${cellsHtml}</tr>`);
                }
                i++;
              }
              
              result += `<table><thead><tr>${headerHtml}</tr></thead><tbody>${rows.join('')}</tbody></table>\n\n`;
              continue;
            }
          }
        }
        
        result += line + '\n';
        i++;
      }
      
      return result;
    };
    
    // First handle tables
    const html = handleTables(markdown);
    
    // Split into paragraphs and process each one
    const paragraphs = html.split('\n\n');
    
    return paragraphs.map(paragraph => {
      // Skip if it's already a table
      if (paragraph.includes('<table>')) {
        return paragraph;
      }
      
      let processedHtml = paragraph
        // Headers
        .replace(/^### (.*$)/gm, '<h3>$1</h3>')
        .replace(/^## (.*$)/gm, '<h2>$1</h2>')
        .replace(/^# (.*$)/gm, '<h1>$1</h1>')
        // Bold and italic
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/\*(.*?)\*/g, '<em>$1</em>')
        // Links
        .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2">$1</a>');
      
      // Handle lists
      if (paragraph.includes('* ')) {
        processedHtml = processedHtml.replace(/^\* (.*$)/gm, '<li>$1</li>');
        processedHtml = '<ul>' + processedHtml + '</ul>';
      } else if (!processedHtml.startsWith('<h') && !processedHtml.startsWith('<table') && processedHtml.trim().length > 0) {
        // Wrap non-header, non-table content in paragraphs
        processedHtml = '<p>' + processedHtml.replace(/\n/g, '<br>') + '</p>';
      }
      
      return processedHtml;
    }).join('');
  };

  // Download as Word document
  const handleDownload = useCallback(async () => {
    if (!reportData) return;

    try {
      // Get logo as base64 with proper sizing (40px height)
      const logoBase64 = await getLogoAsBase64(40);
      
      // Generate HTML for Word document
      const sectionsHtml = reportData.sections
        .map(section => `
          <div style="margin-bottom: 40px;">
            <h2 style="color: #003250; font-size: 18px; font-weight: bold; margin-bottom: 15px; border-bottom: 1px solid #e5e7eb; padding-bottom: 10px;">
              ${section.name}
            </h2>
            <div style="margin-bottom: 20px;">
              ${markdownToHtml(section.content)}
            </div>
          </div>
        `).join('');

      const citationsHtml = reportData.total_citations.length > 0 
        ? `
          <div style="margin-top: 50px; border-top: 2px solid #003250; padding-top: 30px;">
            <h2 style="color: #003250; font-size: 18px; font-weight: bold; margin-bottom: 20px;">
              References & Citations
            </h2>
            <ol style="margin-left: 20px;">
              ${reportData.total_citations.map(citation => `
                <li style="margin-bottom: 10px; font-size: 14px;">
                  <strong>${citation.title}</strong><br/>
                  <a href="${citation.url}" style="color: #003250; text-decoration: none;">
                    ${citation.url}
                  </a>
                </li>
              `).join('')}
            </ol>
          </div>
        ` : '';

      const html = `
        <html>
          <head>
            <meta charset='utf-8'>
            <style>
              .document-header {
                display: flex;
                align-items: center;
                gap: 16px;
                padding-bottom: 20px;
                border-bottom: 2px solid #003250;
                margin-bottom: 30px;
              }
              .header-logo {
                width: auto;
              }
              .header-title {
                color: #003250;
                font-size: 24px;
                font-weight: bold;
                margin: 0;
              }
              body {
                font-family: Arial, sans-serif;
                max-width: 800px;
                margin: 0 auto;
                padding: 40px 20px;
              }
              .metadata-section {
                background-color: #f9fafb;
                padding: 20px;
                border-radius: 8px;
                margin-bottom: 30px;
                border-left: 4px solid #003250;
              }
              table {
                border-collapse: collapse;
                width: 100%;
                margin: 20px 0;
                border: 1px solid #003250;
              }
              th, td {
                border: 1px solid #003250;
                padding: 8px 12px;
                text-align: left;
                vertical-align: top;
              }
              th {
                background-color: #f8f9fa;
                font-weight: bold;
                color: #003250;
              }
              tbody tr:nth-child(even) {
                background-color: #f8f9fa;
              }
              thead tr {
                background-color: #f8f9fa;
              }
              h1, h2, h3, h4, h5, h6 {
                color: #003250;
                margin-top: 24px;
                margin-bottom: 16px;
              }
              p {
                margin-bottom: 16px;
              }
              ul, ol {
                margin-bottom: 16px;
                padding-left: 24px;
              }
              li {
                margin-bottom: 8px;
              }
            </style>
          </head>
          <body>
            <div class="document-header">
              ${logoBase64 ? `<img src="${logoBase64}" alt="Logo" class="header-logo" />` : ''}
              <h1 class="header-title">AI Research Report</h1>
            </div>
            
            <div class="metadata-section">
              <h3 style="margin-top: 0; margin-bottom: 12px; color: #003250;">Report Summary</h3>
              <p style="margin-bottom: 0;">
                <strong>Sections:</strong> ${reportData.metadata.section_count} | 
                <strong>Total Words:</strong> ${reportData.metadata.word_count.toLocaleString()} | 
                <strong>Citations:</strong> ${reportData.metadata.citation_count}
              </p>
            </div>
            
            ${sectionsHtml}
            ${citationsHtml}
          </body>
        </html>
      `;

      // Send HTML to conversion API
      const response = await fetch('/api/convert/html-to-docx', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          html,
          filename: 'AI_Research_Report'
        }),
      });

      if (!response.ok) {
        throw new Error(`Conversion failed: ${response.statusText}`);
      }

      // Get the blob from response
      const blob = await response.blob();

      // Create download link
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "AI_Research_Report.docx";
      document.body.appendChild(a);
      a.click();

      // Cleanup
      setTimeout(() => {
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
      }, 100);
    } catch (error) {
      console.error('Error generating download:', error);
    }
  }, [reportData]);

  // Handle click outside modal to close
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (modalRef.current && !modalRef.current.contains(event.target as Node)) {
        setIsExpanded(false);
      }
    }
    if (isExpanded) {
      document.addEventListener("mousedown", handleClickOutside);
    }
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, [isExpanded]);

  // Scroll to section on navigation click
  const scrollToSection = (idx: number) => {
    const ref = sectionRefs.current[idx];
    if (ref) {
      ref.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  };

  // Track active section for navigation highlight
  useEffect(() => {
    if (!isExpanded || !reportData?.sections.length) return;
    
    const handleScroll = () => {
      const offsets = sectionRefs.current.map(ref => 
        ref ? ref.getBoundingClientRect().top : Infinity
      );
      const modalTop = modalRef.current?.getBoundingClientRect().top ?? 0;
      
      let active = 0;
      for (let i = 0; i < offsets.length; i++) {
        if (offsets[i] - modalTop < 120) {
          active = i;
        }
      }
      setActiveSection(active);
    };
    
    const container = modalRef.current;
    if (container) {
      container.addEventListener("scroll", handleScroll);
    }
    
    return () => {
      if (container) container.removeEventListener("scroll", handleScroll);
    };
  }, [isExpanded, reportData?.sections.length]);

  // Loading state
  if (state === "loading" || streaming) {
    return (
      <Card className="w-full p-4">
        <div className="flex items-center gap-3">
          <MinimalistBadge
            icon={Loader2}
            tooltip="Compiling research report"
            className="animate-spin-slow"
          />
          <div>
            <h3 className="font-medium text-foreground">
              Compiling AI Research Report...
            </h3>
            <p className="text-sm text-muted-foreground">
              Finalizing sections and citations
            </p>
          </div>
        </div>
      </Card>
    );
  }

  // Error state
  if (state === "error") {
    return (
      <Card className="w-full p-4">
        <div className="flex items-center gap-3 mb-3">
          <MinimalistBadge
            icon={AlertCircle}
            tooltip="Error generating report"
          />
          <div>
            <h3 className="font-medium text-foreground">
              Error Generating Report
            </h3>
            <p className="text-sm text-muted-foreground">
              Failed to compile research report
            </p>
          </div>
        </div>
        {onRetry && (
          <Button onClick={onRetry} variant="outline" size="sm">
            Retry
          </Button>
        )}
      </Card>
    );
  }

  // Collapsed preview
  if (!isExpanded) {
    return (
      <Card className="w-full p-4 cursor-pointer transition-all hover:border-primary hover:shadow-lg"
            onClick={() => setIsExpanded(true)}>
        <div className="flex items-center gap-3">
          <MinimalistBadge
            icon={CheckCircle}
            tooltip="Report completed"
          />
          <div className="flex-1">
            <h3 className="font-medium text-foreground">
              AI Research Report
            </h3>
            {/* <p className="text-sm text-muted-foreground">
              {reportData?.metadata.section_count} sections • {reportData?.metadata.word_count.toLocaleString()} words • {reportData?.metadata.citation_count} citations
            </p> */}
          </div>
          <div className="flex items-center gap-2 text-muted-foreground">
            <Maximize2Icon className="w-4 h-4" />
            <span className="text-sm">Expand</span>
          </div>
        </div>
      </Card>
    );
  }

  // Expanded modal view
  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
      <div
        ref={modalRef}
        className="w-full max-w-7xl h-full max-h-[90vh] bg-card rounded-lg shadow-xl overflow-hidden flex"
        onClick={e => e.stopPropagation()}
      >
        {/* Sidebar Navigation */}
        <div className="w-80 bg-sidebar border-r border-border flex flex-col">
          <div className="p-6 border-b border-border">
            <h2 className="font-semibold text-sidebar-foreground mb-2">Navigation</h2>
            <div className="flex gap-2 text-xs text-sidebar-foreground/70">
              <span>{reportData?.metadata.section_count} sections</span>
              <span>•</span>
              <span>{reportData?.metadata.word_count.toLocaleString()} words</span>
            </div>
          </div>
          
          <div className="flex-1 overflow-y-auto p-4">
            <div className="space-y-2">
              {reportData?.sections.map((section, idx) => (
                <button
                  key={idx}
                  onClick={() => scrollToSection(idx)}
                  className={`w-full text-left p-3 rounded-lg transition-colors text-sm font-medium ${
                    activeSection === idx
                      ? "bg-sidebar-accent text-sidebar-accent-foreground"
                      : "text-sidebar-foreground hover:bg-sidebar-accent/50"
                  }`}
                >
                  <div className="flex items-center gap-2">
                    <FileText className="w-4 h-4 flex-shrink-0" />
                    <span className="truncate">{section.name}</span>
                  </div>
                </button>
              ))}
            </div>
            
            {reportData?.total_citations && reportData.total_citations.length > 0 && (
              <div className="mt-6 pt-4 border-t border-sidebar-border">
                <button
                  onClick={() => setShowCitations(!showCitations)}
                  className="w-full text-left p-3 rounded-lg transition-colors text-sm font-medium text-sidebar-foreground hover:bg-sidebar-accent/50"
                >
                  <div className="flex items-center gap-2">
                    <LinkIcon className="w-4 h-4 flex-shrink-0" />
                    <span>Citations ({reportData.total_citations.length})</span>
                    {showCitations ? (
                      <ChevronDown className="w-4 h-4 ml-auto" />
                    ) : (
                      <ChevronRight className="w-4 h-4 ml-auto" />
                    )}
                  </div>
                </button>
                
                {showCitations && (
                  <div className="mt-2 space-y-1 pl-6">
                    {reportData.total_citations.map((citation, idx) => (
                      <a
                        key={idx}
                        href={citation.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="block p-2 text-xs text-sidebar-foreground/70 hover:text-sidebar-foreground hover:bg-sidebar-accent/30 rounded"
                      >
                        <div className="truncate font-medium">{citation.title}</div>
                        <div className="truncate text-sidebar-foreground/50">{citation.url}</div>
                      </a>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        {/* Main Content */}
        <div className="flex-1 flex flex-col">
          {/* Header */}
          <div className="p-6 border-b border-border flex items-center justify-between">
            <div className="flex items-center gap-4">
              <img src="/logo_icon_round.png" alt="Logo" className="h-8 w-8" />
              <div>
                <h1 className="text-xl font-semibold text-foreground">AI Research Report</h1>
                <p className="text-sm text-muted-foreground">
                  Generated research report with {reportData?.metadata.section_count} sections
                </p>
              </div>
            </div>
            
            <div className="flex items-center gap-2">
                             <Button
                 onClick={handleDownload}
                 variant="default"
                 size="sm"
                 className="flex items-center gap-2"
               >
                 <DownloadIcon className="w-4 h-4" />
                 Download Word
               </Button>
              <Button
                onClick={() => setIsExpanded(false)}
                variant="ghost"
                size="sm"
                className="flex items-center gap-2"
              >
                <XIcon className="w-4 h-4" />
                Close
              </Button>
            </div>
          </div>

          {/* Content */}
          <div className="flex-1 overflow-y-auto p-8">
            <div className="max-w-4xl mx-auto space-y-12">
              {reportData?.sections.map((section, idx) => (
                <div
                  key={idx}
                  ref={el => { sectionRefs.current[idx] = el; }}
                  className="section-content"
                >
                  <h2 className="text-2xl font-bold text-foreground mb-6 pb-3 border-b border-border">
                    {section.name}
                  </h2>
                  <div className="prose prose-sm max-w-none">
                    <ReactMarkdown
                      remarkPlugins={[remarkGfm, remarkMath]}
                      rehypePlugins={[rehypeKatex]}
                      components={{
                        h1: ({ ...props }) => <h1 className="text-xl font-bold text-foreground mb-4 mt-8" {...props} />,
                        h2: ({ ...props }) => <h2 className="text-lg font-bold text-foreground mt-6 mb-3" {...props} />,
                        h3: ({ ...props }) => <h3 className="text-base font-bold text-foreground mt-4 mb-2" {...props} />,
                        p: ({ ...props }) => <p className="text-sm text-muted-foreground leading-relaxed mb-4" {...props} />,
                        ul: ({ ...props }) => <ul className="mb-4 space-y-2 ml-6 list-disc text-sm" {...props} />,
                        ol: ({ ...props }) => <ol className="mb-4 space-y-2 ml-6 list-decimal text-sm" {...props} />,
                        li: ({ ...props }) => <li className="text-sm text-muted-foreground" {...props} />,
                        strong: ({ ...props }) => <strong className="font-semibold text-foreground" {...props} />,
                        a: ({ ...props }) => (
                          <a 
                            className="text-primary underline hover:no-underline" 
                            target="_blank" 
                            rel="noopener noreferrer" 
                            {...props} 
                          />
                        ),
                        table: ({ ...props }) => (
                          <div className="overflow-x-auto my-6">
                            <table className="min-w-full border border-border rounded-lg">
                              {props.children}
                            </table>
                          </div>
                        ),
                        thead: ({ ...props }) => (
                          <thead className="bg-muted">
                            {props.children}
                          </thead>
                        ),
                        tr: ({ ...props }) => (
                          <tr className="border-b border-border hover:bg-muted/50">
                            {props.children}
                          </tr>
                        ),
                        th: ({ ...props }) => (
                          <th className="px-4 py-3 text-left text-xs font-semibold text-foreground uppercase tracking-wider">
                            {props.children}
                          </th>
                        ),
                        td: ({ ...props }) => (
                          <td className="px-4 py-3 text-sm text-muted-foreground">
                            {props.children}
                          </td>
                        ),
                      }}
                    >
                      {section.content}
                    </ReactMarkdown>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
} 