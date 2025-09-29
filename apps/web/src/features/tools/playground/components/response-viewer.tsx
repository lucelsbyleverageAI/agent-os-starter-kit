"use client";

import type React from "react";

import { useState, useMemo, useEffect } from "react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Loader2, AlertTriangle, ChevronDown, ChevronUp, ChevronRight, Image as ImageIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { getScrollbarClasses } from "@/lib/scrollbar-styles";
import { extractImagesFromResponse, type ExtractedImage } from "@/lib/image-utils";

interface ResponseViewerProps {
  response: any;
  isLoading: boolean;
  errorMessage?: string;
  authRequiredMessage?: React.ReactNode;
}

export function ResponseViewer({
  response,
  isLoading,
  errorMessage,
  authRequiredMessage,
}: ResponseViewerProps) {
  const [viewMode, setViewMode] = useState<"pretty" | "raw" | "images">("pretty");

  // Extract images from response
  const extractedImages = useMemo(() => {
    if (!response) return [];
    return extractImagesFromResponse(response);
  }, [response]);

  // Show images tab only if images are detected
  const hasImages = extractedImages.length > 0;

  if (authRequiredMessage) {
    return <div className="w-full max-w-full">{authRequiredMessage}</div>;
  }

  if (errorMessage) {
    return (
      <div className="flex flex-col items-center justify-center rounded-md border border-red-200 bg-red-50 p-6 text-red-700 w-full max-w-full">
        <AlertTriangle className="mb-3 h-8 w-8 text-red-500" />
        <p className="mb-1 text-lg font-semibold">Error</p>
        <p className="text-center text-sm break-words">{errorMessage}</p>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center py-12 w-full">
        <Loader2 className="mb-4 h-8 w-8 animate-spin text-primary" />
        <p className="text-gray-500">Executing tool...</p>
        <p className="text-xs text-gray-400 mt-2">This may take several minutes for complex operations</p>
      </div>
    );
  }

  if (!response) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-gray-500 w-full">
        <p>No response yet. Run the tool to see results.</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full w-full max-w-full space-y-4">
      <Tabs
        value={viewMode}
        onValueChange={(v) => setViewMode(v as "pretty" | "raw" | "images")}
        className="flex flex-col h-full w-full"
      >
        <TabsList className={cn("grid w-fit grid-cols-2 flex-shrink-0", hasImages && "grid-cols-3")}>
          <TabsTrigger value="pretty">Pretty</TabsTrigger>
          <TabsTrigger value="raw">Raw</TabsTrigger>
          {hasImages && (
            <TabsTrigger value="images" className="flex items-center gap-1">
              <ImageIcon className="h-3 w-3" />
              Images ({extractedImages.length})
            </TabsTrigger>
          )}
        </TabsList>

        <TabsContent
          value="pretty"
          className="pt-4 w-full max-w-full flex-1 min-h-0"
        >
          <PrettyView response={response} />
        </TabsContent>

        <TabsContent
          value="raw"
          className="pt-4 w-full max-w-full flex-1 min-h-0"
        >
          <RawView response={response} />
        </TabsContent>

        {hasImages && (
          <TabsContent
            value="images"
            className="pt-4 w-full max-w-full flex-1 min-h-0"
          >
            <ImagesView images={extractedImages} />
          </TabsContent>
        )}
      </Tabs>
    </div>
  );
}

function PrettyView({ response }: { response: any }) {
  return (
    <div className={cn("rounded-md border bg-gray-50 p-4 w-full max-w-full h-full", ...getScrollbarClasses('both'))}>
      <div className="min-w-0 max-w-full">
        {renderValue(response, true)}
      </div>
    </div>
  );
}

// Enhanced RawView with intelligent JSON viewer
function RawView({ response }: { response: any }) {
  return (
    <div className={cn("w-full max-w-full h-full rounded-md bg-gray-900", ...getScrollbarClasses('both'))}>
      <div className={cn("p-4 text-sm font-mono min-w-0 max-w-full h-full", ...getScrollbarClasses('both'))}>
        <div className="min-w-0 max-w-full">
          <JsonViewer data={response} />
        </div>
      </div>
    </div>
  );
}

// Intelligent JSON Viewer Component
interface JsonViewerProps {
  data: any;
  level?: number;
  isLast?: boolean;
  parentKey?: string;
}

function JsonViewer({ data, level = 0, isLast = true, parentKey }: JsonViewerProps) {
  const [isCollapsed, setIsCollapsed] = useState(false);
  const indent = "  ".repeat(level);
  
  // Determine if this value can be collapsed
  const isCollapsible = (typeof data === 'object' && data !== null && 
    (Array.isArray(data) ? data.length > 0 : Object.keys(data).length > 0));

  // Render primitive values
  if (data === null) {
    return <span className="text-gray-400">null</span>;
  }
  
  if (data === undefined) {
    return <span className="text-gray-400">undefined</span>;
  }
  
  if (typeof data === 'boolean') {
    return <span className="text-yellow-400">{data.toString()}</span>;
  }
  
  if (typeof data === 'number') {
    return <span className="text-blue-400">{data}</span>;
  }
  
  if (typeof data === 'string') {
    return <span className="text-green-400 break-all">"{data}"</span>;
  }

  // Handle arrays
  if (Array.isArray(data)) {
    if (data.length === 0) {
      return <span className="text-gray-300">[]</span>;
    }

    return (
      <div className="text-gray-100 min-w-0 max-w-full">
        <span className="flex items-center flex-wrap">
          {isCollapsible && (
            <button
              onClick={() => setIsCollapsed(!isCollapsed)}
              className="mr-1 text-gray-400 hover:text-gray-200 transition-colors flex-shrink-0"
            >
              {isCollapsed ? (
                <ChevronRight className="h-3 w-3" />
              ) : (
                <ChevronDown className="h-3 w-3" />
              )}
            </button>
          )}
          <span className="text-gray-300 flex-shrink-0">[</span>
          {isCollapsed && (
            <span className="ml-1 text-gray-500 text-xs flex-shrink-0">
              {data.length} item{data.length !== 1 ? 's' : ''}
            </span>
          )}
        </span>
        
        {!isCollapsed && (
          <div className="ml-2 min-w-0 max-w-full">
            {data.map((item, index) => (
              <div key={index} className="flex min-w-0 max-w-full">
                <span className="text-gray-500 mr-2 flex-shrink-0">{indent}  </span>
                <div className="flex-1 min-w-0">
                  <JsonViewer 
                    data={item} 
                    level={level + 1} 
                    isLast={index === data.length - 1}
                  />
                  {index < data.length - 1 && <span className="text-gray-300">,</span>}
                </div>
              </div>
            ))}
          </div>
        )}
        
        <div className="flex">
          <span className="text-gray-500 mr-2 flex-shrink-0">{indent}</span>
          <span className="text-gray-300">]</span>
        </div>
      </div>
    );
  }

  // Handle objects
  if (typeof data === 'object') {
    const entries = Object.entries(data);
    
    if (entries.length === 0) {
      return <span className="text-gray-300">{"{}"}</span>;
    }

    return (
      <div className="text-gray-100 min-w-0 max-w-full">
        <span className="flex items-center flex-wrap">
          {isCollapsible && (
            <button
              onClick={() => setIsCollapsed(!isCollapsed)}
              className="mr-1 text-gray-400 hover:text-gray-200 transition-colors flex-shrink-0"
            >
              {isCollapsed ? (
                <ChevronRight className="h-3 w-3" />
              ) : (
                <ChevronDown className="h-3 w-3" />
              )}
            </button>
          )}
          <span className="text-gray-300 flex-shrink-0">{"{"}</span>
          {isCollapsed && (
            <span className="ml-1 text-gray-500 text-xs flex-shrink-0">
              {entries.length} key{entries.length !== 1 ? 's' : ''}
            </span>
          )}
        </span>
        
        {!isCollapsed && (
          <div className="ml-2 min-w-0 max-w-full">
            {entries.map(([key, value], index) => (
              <div key={key} className="flex min-w-0 max-w-full">
                <span className="text-gray-500 mr-2 flex-shrink-0">{indent}  </span>
                <div className="flex-1 min-w-0">
                  <span className="text-cyan-400 break-all">"{key}"</span>
                  <span className="text-gray-300">: </span>
                  <JsonViewer 
                    data={value} 
                    level={level + 1} 
                    isLast={index === entries.length - 1}
                    parentKey={key}
                  />
                  {index < entries.length - 1 && <span className="text-gray-300">,</span>}
                </div>
              </div>
            ))}
          </div>
        )}
        
        <div className="flex">
          <span className="text-gray-500 mr-2 flex-shrink-0">{indent}</span>
          <span className="text-gray-300">{"}"}</span>
        </div>
      </div>
    );
  }

  // Fallback for any other types
  return <span className="text-purple-400">{String(data)}</span>;
}

// Component for collapsible long text content
function CollapsibleText({ text, maxLength = 500 }: { text: string; maxLength?: number }) {
  const [isExpanded, setIsExpanded] = useState(false);
  const shouldTruncate = text.length > maxLength;
  
  if (!shouldTruncate) {
    return <span className="font-mono break-all whitespace-pre-wrap min-w-0 max-w-full">{text}</span>;
  }

  return (
    <div className="space-y-2 min-w-0 max-w-full">
      <span className="font-mono break-all whitespace-pre-wrap min-w-0 max-w-full">
        {isExpanded ? text : `${text.slice(0, maxLength)}...`}
      </span>
      <Button
        variant="ghost"
        size="sm"
        onClick={() => setIsExpanded(!isExpanded)}
        className="h-6 px-2 text-xs text-gray-600 hover:text-gray-800"
      >
        {isExpanded ? (
          <>
            <ChevronUp className="h-3 w-3 mr-1" />
            Show less
          </>
        ) : (
          <>
            <ChevronDown className="h-3 w-3 mr-1" />
            Show more ({text.length - maxLength} more characters)
          </>
        )}
      </Button>
    </div>
  );
}

// Enhanced string rendering with JSON detection
function renderStringValue(value: string): React.ReactNode {
  // Try to detect and parse JSON within strings
  const trimmedValue = value.trim();
  
  // Check if it looks like JSON (starts with { or [)
  if ((trimmedValue.startsWith('{') && trimmedValue.endsWith('}')) || 
      (trimmedValue.startsWith('[') && trimmedValue.endsWith(']'))) {
    try {
      const parsed = JSON.parse(trimmedValue);
      return (
        <div className="space-y-2 min-w-0 max-w-full">
          <div className="text-xs text-gray-500 font-medium">Parsed JSON content:</div>
          <div className="border-l-2 border-blue-200 pl-3 min-w-0 max-w-full">
            {renderValue(parsed, false)}
          </div>
        </div>
      );
    } catch {
      // Not valid JSON, fall through to regular string rendering
    }
  }

  // Regular string rendering with collapsible long content
  return <CollapsibleText text={value} />;
}

// Enhanced renderValue function with proper width constraints
function renderValue(value: any, isRoot = false): React.ReactNode {
  if (value === null || value === undefined) {
    return <span className="text-gray-400">null</span>;
  }

  if (typeof value === "object" && Array.isArray(value)) {
    return (
      <div className={cn(
        "space-y-1 min-w-0 max-w-full",
        !isRoot && "border-l-2 border-gray-200 pl-3"
      )}>
        {value.length === 0 ? (
          <span className="text-gray-400">[] (Empty array)</span>
        ) : (
          value.map((item, index) => (
            <div key={index} className="min-w-0 max-w-full">
              <div className="flex items-start gap-2 min-w-0 max-w-full">
                <span className="text-xs text-gray-500 font-mono flex-shrink-0">[{index}]</span>
                <div className="min-w-0 flex-1 max-w-full">
                  {renderValue(item)}
                </div>
              </div>
            </div>
          ))
        )}
      </div>
    );
  }

  if (typeof value === "object") {
    const entries = Object.entries(value);
    return (
      <div className={cn(
        "space-y-1 min-w-0 max-w-full",
        !isRoot && "border-l-2 border-gray-200 pl-3"
      )}>
        {entries.length === 0 ? (
          <span className="text-gray-400">{"{{}} (Empty object)"}</span>
        ) : (
          entries.map(([k, v]) => {
            const valueRendersContainer = typeof v === "object" && v !== null;
            return (
              <div key={k} className="min-w-0 max-w-full">
                <div className="flex flex-col gap-1 min-w-0 max-w-full">
                  <div className="flex items-start gap-2 min-w-0 max-w-full">
                    <span className="font-medium text-gray-700 flex-shrink-0">{k}:</span>
                    {!valueRendersContainer && (
                      <div className="min-w-0 flex-1 max-w-full">
                        {renderValue(v, false)}
                      </div>
                    )}
                  </div>
                  {valueRendersContainer && (
                    <div className="ml-2 min-w-0 max-w-full">
                      {renderValue(v, false)}
                    </div>
                  )}
                </div>
              </div>
            );
          })
        )}
      </div>
    );
  }

  if (typeof value === "boolean") {
    return (
      <span className={cn("font-mono", value ? "text-green-600" : "text-red-600")}>
        {String(value)}
      </span>
    );
  }

  if (typeof value === "number") {
    return <span className="font-mono text-blue-600">{value}</span>;
  }

  // Enhanced string rendering with JSON detection and wrapping
  return renderStringValue(String(value));
}

// Images View Component
function ImagesView({ images }: { images: ExtractedImage[] }) {
  return (
    <div className={cn("w-full max-w-full h-full", ...getScrollbarClasses('both'))}>
      <div className="p-4">
        <div className="mb-4">
          <h3 className="font-medium text-gray-900 mb-1">
            Generated Images ({images.length})
          </h3>
          <p className="text-sm text-gray-500">
            Click on any image to view it in full size
          </p>
        </div>
        
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {images.map((image, index) => (
            <ImageCard key={index} image={image} index={index} />
          ))}
        </div>
      </div>
    </div>
  );
}

// Individual Image Card Component
function ImageCard({ image, index }: { image: ExtractedImage; index: number }) {
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [displayName, setDisplayName] = useState(`Image ${index + 1}`);
  const [imageSize, setImageSize] = useState<string | null>(null);

  // Load image URL based on type
  useEffect(() => {
    const loadImage = async () => {
      setIsLoading(true);
      setError(null);
      
      try {
        const { getImageRenderUrl } = await import('@/lib/image-utils');
        const url = await getImageRenderUrl(image);
        setImageUrl(url);
      } catch (err) {
        console.error('Failed to load image:', err);
        setError(err instanceof Error ? err.message : 'Failed to load image');
      } finally {
        setIsLoading(false);
      }
    };

    loadImage();
  }, [image]);

  // Load display name and size
  useEffect(() => {
    const loadMetadata = async () => {
      try {
        const { getImageDisplayName, getImageSize } = await import('@/lib/image-utils');
        setDisplayName(getImageDisplayName(image));
        const size = getImageSize(image);
        setImageSize(size);
      } catch (err) {
        console.error('Failed to load image metadata:', err);
        // Keep default values
      }
    };

    loadMetadata();
  }, [image, index]);

  if (isLoading) {
    return (
      <div className="aspect-square bg-gray-100 rounded-lg flex items-center justify-center">
        <div className="text-center">
          <Loader2 className="h-6 w-6 animate-spin text-gray-400 mx-auto mb-2" />
          <p className="text-xs text-gray-500">Loading image...</p>
        </div>
      </div>
    );
  }

  if (error || !imageUrl) {
    return (
      <div className="aspect-square bg-red-50 border border-red-200 rounded-lg flex items-center justify-center">
        <div className="text-center p-4">
          <AlertTriangle className="h-6 w-6 text-red-400 mx-auto mb-2" />
          <p className="text-xs text-red-600 break-words">
            {error || 'Failed to load image'}
          </p>
          <p className="text-xs text-gray-400 mt-1 font-mono">
            Type: {image.type}
          </p>
        </div>
      </div>
    );
  }

  return (
    <>
      <div className="bg-white border border-gray-200 rounded-lg overflow-hidden hover:shadow-md transition-shadow">
        <div 
          className="aspect-square bg-gray-100 cursor-pointer relative group overflow-hidden"
          onClick={() => setIsModalOpen(true)}
        >
          <img
            src={imageUrl}
            alt={displayName}
            className="w-full h-full object-contain bg-white"
            style={{ display: 'block' }}
            onError={(e) => {
              console.error('Image failed to load:', imageUrl);
              setError('Failed to display image');
            }}
            onLoad={() => {
              // Image loaded successfully
            }}
          />
        </div>
        
        <div className="p-3">
          <div className="flex items-center justify-between mb-1">
            <h4 className="font-medium text-sm text-gray-900 truncate">
              {displayName}
            </h4>
            <span className="text-xs text-gray-500 bg-gray-100 px-2 py-0.5 rounded">
              {image.type.toUpperCase()}
            </span>
          </div>
          
          {imageSize && (
            <p className="text-xs text-gray-500">{imageSize}</p>
          )}
          
          {image.metadata?.path && (
            <p className="text-xs text-gray-400 mt-1 font-mono">
              Path: {image.metadata.path.join('.')}
            </p>
          )}
        </div>
      </div>

      {/* Image Modal */}
      {isModalOpen && (
        <ImageModal
          imageUrl={imageUrl}
          displayName={displayName}
          image={image}
          onClose={() => setIsModalOpen(false)}
        />
      )}
    </>
  );
}

// Full-size Image Modal
function ImageModal({ 
  imageUrl, 
  displayName, 
  image, 
  onClose 
}: { 
  imageUrl: string; 
  displayName: string; 
  image: ExtractedImage; 
  onClose: () => void; 
}) {
  return (
    <div 
      className="fixed inset-0 flex items-center justify-center z-50 p-4"
      onClick={onClose}
    >
      <div className="max-w-4xl max-h-full bg-white rounded-lg overflow-hidden shadow-2xl border">
        <div className="flex items-center justify-between p-4 border-b bg-gray-50">
          <div>
            <h3 className="font-medium text-gray-900">{displayName}</h3>
            <p className="text-sm text-gray-500">Type: {image.type}</p>
          </div>
          <Button
            variant="ghost"
            size="sm"
            onClick={onClose}
            className="h-8 w-8 p-0 hover:bg-gray-200"
          >
            ×
          </Button>
        </div>
        
        <div className="p-4 bg-gray-50">
          <img
            src={imageUrl}
            alt={displayName}
            className="max-w-full max-h-[70vh] object-contain mx-auto bg-white rounded shadow-sm"
            onClick={(e) => e.stopPropagation()}
          />
        </div>
      </div>
    </div>
  );
}
