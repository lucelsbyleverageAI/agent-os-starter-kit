"use client";

import React, { useState } from "react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { getScrollbarClasses } from "@/lib/scrollbar-styles";
import { MinimalistBadge, MinimalistBadgeWithText } from "@/components/ui/minimalist-badge";
import { Plus, X, Globe, Youtube, AlertCircle, CheckCircle } from "lucide-react";
import { v4 as uuidv4 } from "uuid";
import type { URLItem } from "./enhanced-upload-dialog";

interface URLUploadSectionProps {
  urls: URLItem[];
  onURLsChange: (urls: URLItem[]) => void;
}

// URL validation
const validateURL = (url: string): boolean => {
  try {
    new URL(url);
    return true;
  } catch {
    return false;
  }
};

// YouTube detection
const detectYouTube = (url: string): boolean => {
  return /(?:youtube\.com|youtu\.be)/.test(url);
};

// Extract domain for display
const extractDomain = (url: string): string => {
  try {
    return new URL(url).hostname;
  } catch {
    return url;
  }
};

export function URLUploadSection({ urls, onURLsChange }: URLUploadSectionProps) {
  const [urlInput, setUrlInput] = useState('');
  const [inputError, setInputError] = useState('');

  const addURL = () => {
    const trimmedUrl = urlInput.trim();
    
    if (!trimmedUrl) {
      setInputError('Please enter a URL');
      return;
    }

    // Add protocol if missing
    let processedUrl = trimmedUrl;
    if (!trimmedUrl.startsWith('http://') && !trimmedUrl.startsWith('https://')) {
      processedUrl = 'https://' + trimmedUrl;
    }

    if (!validateURL(processedUrl)) {
      setInputError('Please enter a valid URL');
      return;
    }

    // Check for duplicates
    const exists = urls.some(item => item.url === processedUrl);
    if (exists) {
      setInputError('This URL has already been added');
      return;
    }

    const newURL: URLItem = {
      id: uuidv4(),
      url: processedUrl,
      isValid: true,
      isYouTube: detectYouTube(processedUrl)
    };

    onURLsChange([...urls, newURL]);
    setUrlInput('');
    setInputError('');
    
    toast.success(`Added ${newURL.isYouTube ? 'YouTube video' : 'URL'}`, {
      description: extractDomain(processedUrl)
    });
  };

  const removeURL = (id: string) => {
    onURLsChange(urls.filter(url => url.id !== id));
  };

  const handleInputChange = (value: string) => {
    setUrlInput(value);
    if (inputError) setInputError('');
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      addURL();
    }
  };

  return (
    <div className="space-y-4">
      {/* URL Input */}
      <div className="space-y-2">
        <div className="flex gap-2">
          <div className="flex-1">
            <Input
              placeholder="Enter URL"
              value={urlInput}
              onChange={(e) => handleInputChange(e.target.value)}
              onKeyPress={handleKeyPress}
              className={inputError ? 'border-red-300 focus:border-red-500' : ''}
            />
            {inputError && (
              <p className="text-sm text-red-600 mt-1 flex items-center gap-1">
                <AlertCircle className="h-3 w-3" />
                {inputError}
              </p>
            )}
          </div>
          <Button 
            onClick={addURL} 
            disabled={!urlInput.trim()}
            className="px-6"
          >
            <Plus className="h-4 w-4" />
          </Button>
        </div>
        
        <p className="text-xs text-muted-foreground italic">
          *Extracts text from web pages and will transcribe YouTube URLs
        </p>
      </div>

      {/* URL List */}
      {urls.length > 0 && (
        <div className="space-y-2">
          <h4 className="font-medium text-sm text-gray-700">
            URLs to Process ({urls.length})
          </h4>
          <div className={cn("space-y-2 max-h-60", ...getScrollbarClasses('y'))}>
            {urls.map((urlItem) => (
              <URLCard 
                key={urlItem.id}
                urlItem={urlItem}
                onRemove={() => removeURL(urlItem.id)}
              />
            ))}
          </div>
        </div>
      )}

      {/* Empty State */}
      {urls.length === 0 && (
        <div className="text-center py-8 border-2 border-dashed border-gray-200 rounded-lg">
          <Globe className="h-12 w-12 text-gray-400 mx-auto mb-3" />
          <h3 className="font-medium text-gray-700 mb-1">No URLs added yet</h3>
          <p className="text-sm text-gray-500">
            Add web pages or YouTube videos to import their content
          </p>
        </div>
      )}
    </div>
  );
}

// URL Card Component
interface URLCardProps {
  urlItem: URLItem;
  onRemove: () => void;
}

function URLCard({ urlItem, onRemove }: URLCardProps) {
  const domain = extractDomain(urlItem.url);
  
  return (
    <Card className="transition-all hover:shadow-sm !py-1">
      <CardContent className="!px-3 !py-1.5">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-2 flex-1 min-w-0">
            {/* Icon */}
            <div className="flex-shrink-0">
              <MinimalistBadge 
                icon={urlItem.isYouTube ? Youtube : Globe}
                tooltip={urlItem.isYouTube ? 'YouTube video' : 'Web page'}
              />
            </div>

            {/* URL Info */}
            <div className="flex-1 min-w-0">
              <div className="flex items-center space-x-2">
                <p className="font-medium text-sm text-foreground truncate">
                  {domain}
                </p>
                {urlItem.isYouTube && (
                  <MinimalistBadgeWithText
                    icon={Youtube}
                    text="YouTube"
                    tooltip="YouTube video content"
                  />
                )}
                {urlItem.isValid && (
                  <MinimalistBadge 
                    icon={CheckCircle}
                    tooltip="Valid URL"
                    className="h-3 w-3"
                  />
                )}
              </div>
              <p className="text-xs text-muted-foreground truncate">
                {urlItem.url}
              </p>
            </div>
          </div>

          {/* Remove Button */}
          <Button
            variant="ghost"
            size="sm"
            onClick={onRemove}
            className="flex-shrink-0 ml-2 h-8 w-8 p-0 text-gray-400 hover:text-red-600 hover:bg-red-50"
          >
            <X className="h-4 w-4" />
          </Button>
        </div>
      </CardContent>
    </Card>
  );
} 