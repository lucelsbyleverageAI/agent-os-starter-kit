/**
 * Utility functions for detecting and extracting images from tool responses
 */

export interface ExtractedImage {
  type: 'base64' | 'gcp' | 'url';
  value: string;
  metadata?: any;
}

// Supported image file extensions
const IMAGE_EXTENSIONS = ['.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp', '.svg'];

/**
 * Check if a string is likely a base64-encoded image
 */
export function isBase64Image(str: string): boolean {
  return (
    typeof str === 'string' &&
    str.length > 1000 && // Base64 images are typically quite long
    /^[A-Za-z0-9+/=]+$/.test(str) &&
    !str.startsWith('http') &&
    !str.includes('/images/') &&
    !str.includes('\\') // Avoid file paths
  );
}

/**
 * Check if a string is a GCP image path (not a URL)
 */
export function isGcpImagePath(str: string): boolean {
  return (
    typeof str === 'string' &&
    /\/images\/.+\.(png|jpg|jpeg|webp|gif|bmp)$/i.test(str) &&
    !str.startsWith('http') // Not a URL
  );
}

/**
 * Check if a string is an image URL
 */
export function isImageUrl(str: string): boolean {
  return (
    typeof str === 'string' &&
    /^https?:\/\/.+\.(png|jpg|jpeg|webp|gif|bmp|svg)(\?.*)?$/i.test(str)
  );
}

/**
 * Check if a string could be an image URL (more permissive)
 * Includes URLs that might be signed URLs or contain query parameters
 */
export function isImageUrlPermissive(str: string): boolean {
  if (!str || typeof str !== 'string') return false;
  
  // Must start with http/https
  if (!str.startsWith('http')) return false;
  
  // Check for common image hosting domains or file extensions
  const hasImageExtension = IMAGE_EXTENSIONS.some(ext => 
    str.toLowerCase().includes(ext)
  );
  
  const hasImageDomain = [
    'storage.googleapis.com',
    'storage.cloud.google.com',
    's3.amazonaws.com',
    'amazonaws.com',
    'cloudinary.com',
    'imagekit.io'
  ].some(domain => str.includes(domain));
  
  return hasImageExtension || hasImageDomain;
}

/**
 * Try to parse a string as JSON or Python-like dictionary
 */
function tryParseStringData(str: string): any {
  if (!str || typeof str !== 'string') return null;
  
  try {
    // First try parsing as JSON (in case it's already valid JSON)
    return JSON.parse(str);
  } catch {
    // If JSON fails, try more sophisticated Python to JSON conversion
    try {
      const converted = convertPythonToJson(str);
      return JSON.parse(converted);
    } catch {
      return null;
    }
  }
}

/**
 * More sophisticated Python-like syntax to JSON conversion
 */
function convertPythonToJson(str: string): string {
  let result = '';
  let inSingleQuotes = false;
  let inDoubleQuotes = false;
  let escaped = false;
  
  for (let i = 0; i < str.length; i++) {
    const char = str[i];
    
    if (escaped) {
      result += char;
      escaped = false;
      continue;
    }
    
    if (char === '\\') {
      escaped = true;
      result += char;
      continue;
    }
    
    // Handle quotes and track string state
    if (char === "'" && !inDoubleQuotes) {
      inSingleQuotes = !inSingleQuotes;
      result += '"'; // Convert single quotes to double quotes
    } else if (char === '"' && !inSingleQuotes) {
      inDoubleQuotes = !inDoubleQuotes;
      // If we're inside single quotes (which become double quotes), escape inner double quotes
      if (inSingleQuotes) {
        result += '\\"';
      } else {
        result += char;
      }
    } else if (!inSingleQuotes && !inDoubleQuotes) {
      // Only apply Python->JSON conversions outside of string literals
      if (str.substring(i, i + 4) === 'True' && /\W/.test(str[i + 4] || ' ')) {
        result += 'true';
        i += 3;
      } else if (str.substring(i, i + 5) === 'False' && /\W/.test(str[i + 5] || ' ')) {
        result += 'false';
        i += 4;
      } else if (str.substring(i, i + 4) === 'None' && /\W/.test(str[i + 4] || ' ')) {
        result += 'null';
        i += 3;
      } else {
        result += char;
      }
    } else {
      // Inside a string literal - escape any unescaped double quotes if we converted from single quotes
      if (char === '"' && inSingleQuotes && !escaped) {
        result += '\\"';
      } else {
        result += char;
      }
    }
  }
  
  return result;
}

/**
 * Extract image URLs from text using regex as a fallback
 */
function extractImageUrlsFromText(text: string): ExtractedImage[] {
  const images: ExtractedImage[] = [];
  const seenUrls = new Set<string>();
  
  // Regex patterns for different types of image URLs
  const patterns = [
    // Standard HTTP/HTTPS image URLs with explicit extensions
    /https?:\/\/[^\s"',]+\.(?:png|jpg|jpeg|webp|gif|bmp|svg)(?:\?[^\s"',]*)?/gi,
    // GCP Storage URLs (more specific)
    /https?:\/\/storage\.googleapis\.com\/[^\s"',]+\.(?:png|jpg|jpeg|webp|gif|bmp)/gi,
    // Replicate delivery URLs
    /https?:\/\/replicate\.delivery\/[^\s"',]+/gi,
  ];
  
  for (const pattern of patterns) {
    const matches = text.match(pattern);
    if (matches) {
      matches.forEach(url => {
        // Clean up the URL (remove trailing punctuation)
        const cleanUrl = url.replace(/[.,;]+$/, '');
        
        if (!seenUrls.has(cleanUrl) && isImageUrlPermissive(cleanUrl)) {
          seenUrls.add(cleanUrl);
          images.push({
            type: 'url',
            value: cleanUrl,
            metadata: { path: ['(extracted from text)'], extractionMethod: 'regex' }
          });
        }
      });
    }
  }
  
  // Also look for GCP paths (without full URLs) - be more specific
  const gcpPathPattern = /['"]?(\/images\/[^\s"',]+\.(?:png|jpg|jpeg|webp|gif|bmp))['"]?/gi;
  let match;
  while ((match = gcpPathPattern.exec(text)) !== null) {
    const path = match[1]; // Get the captured group without quotes
    if (!seenUrls.has(path)) {
      seenUrls.add(path);
      images.push({
        type: 'gcp',
        value: path,
        metadata: { path: ['(extracted from text)'], extractionMethod: 'regex' }
      });
    }
  }
  
  return images;
}

/**
 * Recursively extract all images from a response object
 */
export function extractImagesFromResponse(obj: any): ExtractedImage[] {
  const images: ExtractedImage[] = [];
  const seenValues = new Set<string>(); // Track seen image values to avoid duplicates
  
  function recurse(val: any, path: string[] = []) {
    if (!val) return;
    
    if (typeof val === 'string') {
      // First check if this string contains image data directly
      if (isBase64Image(val)) {
        if (!seenValues.has(val)) {
          seenValues.add(val);
          images.push({
            type: 'base64',
            value: val,
            metadata: { path }
          });
        }
      } else if (isGcpImagePath(val)) {
        if (!seenValues.has(val)) {
          seenValues.add(val);
          images.push({
            type: 'gcp',
            value: val,
            metadata: { path }
          });
        }
      } else if (isImageUrlPermissive(val)) {
        if (!seenValues.has(val)) {
          seenValues.add(val);
          images.push({
            type: 'url',
            value: val,
            metadata: { path }
          });
        }
      } else {
        // Try to parse the string as JSON/Python data and recurse into it
        const parsed = tryParseStringData(val);
        if (parsed && typeof parsed === 'object') {
          recurse(parsed, [...path, '(parsed)']);
        } else {
          // If parsing failed, try to extract image URLs directly from the text as fallback
          // Only do this for longer strings that might contain structured data
          if (val.length > 100) {
            const extractedUrls = extractImageUrlsFromText(val);
            extractedUrls.forEach(img => {
              if (!seenValues.has(img.value)) {
                seenValues.add(img.value);
                images.push(img);
              }
            });
          }
        }
      }
    } else if (Array.isArray(val)) {
      val.forEach((item, index) => {
        recurse(item, [...path, `[${index}]`]);
      });
    } else if (typeof val === 'object') {
      Object.entries(val).forEach(([key, value]) => {
        recurse(value, [...path, key]);
      });
    }
  }
  
  recurse(obj);
  return images;
}

/**
 * Convert a base64 image to a data URL for display
 */
export function base64ToDataUrl(base64: string, mimeType: string = 'image/png'): string {
  return `data:${mimeType};base64,${base64}`;
}

/**
 * Get the URL for rendering an extracted image
 * For GCP images, this calls the API to get a signed URL
 */
export async function getImageRenderUrl(image: ExtractedImage): Promise<string> {
  switch (image.type) {
    case 'base64':
      return base64ToDataUrl(image.value);
      
    case 'url':
      return image.value;
      
    case 'gcp':
      // Check if GCP image storage is enabled in the frontend configuration
      if (process.env.NEXT_PUBLIC_IMAGE_STORAGE_ENABLED !== 'true') {
        // Return a placeholder or throw an error to indicate that GCP is not configured
        console.warn(`GCP image rendering is disabled. Cannot fetch signed URL for: ${image.value}`);
        // Return a placeholder image or a specific error indicator URL
        return '/placeholder-image.svg'; // Or an appropriate fallback
      }
      
      try {
        // Clean the filename - remove leading slash if present
        const cleanFilename = image.value.startsWith('/') ? image.value.substring(1) : image.value;
        
        const response = await fetch(
          `/api/langconnect/gcp/signed-url?filename=${encodeURIComponent(cleanFilename)}`
        );
        
        if (!response.ok) {
          const errorText = await response.text();
          console.error('GCP signed URL API error:', response.status, response.statusText, errorText);
          throw new Error(`Failed to get signed URL: ${response.statusText} (${response.status})`);
        }
        
        const data = await response.json();
        return data.url;
      } catch (error) {
        console.error('Error getting signed URL for GCP image:', image.value, error);
        throw error;
      }
      
    default:
      throw new Error(`Unknown image type: ${(image as any).type}`);
  }
}

/**
 * Get a display name for an image based on its metadata or value
 */
export function getImageDisplayName(image: ExtractedImage): string {
  if (image.type === 'gcp') {
    // Extract filename from GCP path
    const parts = image.value.split('/');
    return parts[parts.length - 1] || 'GCP Image';
  } else if (image.type === 'url') {
    // Extract filename from URL
    try {
      const url = new URL(image.value);
      const pathname = url.pathname;
      const parts = pathname.split('/');
      return parts[parts.length - 1] || 'Image';
    } catch {
      return 'Image';
    }
  } else if (image.type === 'base64') {
    return 'Base64 Image';
  }
  
  return 'Image';
}

/**
 * Get file size information if available in metadata
 */
export function getImageSize(image: ExtractedImage): string | null {
  if (image.metadata?.size_bytes) {
    const bytes = image.metadata.size_bytes;
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }
  return null;
} 