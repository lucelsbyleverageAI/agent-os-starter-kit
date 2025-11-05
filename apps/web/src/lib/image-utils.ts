/**
 * Utility functions for detecting and extracting images from tool responses
 */

export interface ExtractedImage {
  type: 'base64' | 'url' | 'storage_path';
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
    's3.amazonaws.com',
    'amazonaws.com',
    'cloudinary.com',
    'imagekit.io'
  ].some(domain => str.includes(domain));
  
  return hasImageExtension || hasImageDomain;
}

/**
 * Check if a string is a storage path (UUID/filename pattern)
 *
 * Pattern matches:
 * - {uuid}/{timestamp}_{filename}.{ext}
 * - {uuid}/{uuid}/{uuid}/{filename}.{ext}
 *
 * Examples:
 * - "456e7890-abcd-1234-efgh-567890abcdef/20250126_143022_image.png" (chat uploads)
 * - "user-id/agent-id/thread-id/e2b_code_sandbox_20250126_143022_abc123.png" (e2b outputs)
 */
export function isStoragePath(str: string): boolean {
  if (!str || typeof str !== 'string') return false;

  // Pattern: {uuid}/{...}/{filename}.{ext}
  // Must start with UUID and contain image extension
  const storagePathPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\/.+\.(png|jpg|jpeg|gif|webp|bmp|tiff|svg)$/i;

  return storagePathPattern.test(str);
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
      } else if (isStoragePath(val)) {
        // Check for storage path (e.g., "uuid/timestamp_file.png")
        // These need to be converted to signed URLs by the frontend
        if (!seenValues.has(val)) {
          seenValues.add(val);
          images.push({
            type: 'storage_path',
            value: val,
            metadata: {
              path,
              bucket: 'agent-outputs'  // Default to agent-outputs, can be overridden
            }
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
 */
export async function getImageRenderUrl(image: ExtractedImage): Promise<string> {
  switch (image.type) {
    case 'base64':
      return base64ToDataUrl(image.value);

    case 'url':
      return image.value;

    case 'storage_path':
      // Convert storage path to proxy URL that generates fresh signed URLs
      // This ensures images work even after the original signed URL would have expired
      const bucket = image.metadata?.bucket || 'agent-outputs';
      return `/api/langconnect/storage/image?path=${encodeURIComponent(image.value)}&bucket=${encodeURIComponent(bucket)}`;

    default:
      throw new Error(`Unknown image type: ${(image as any).type}`);
  }
}

/**
 * Get a display name for an image based on its metadata or value
 */
export function getImageDisplayName(image: ExtractedImage): string {
  if (image.type === 'url') {
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

// ==============================================================================
// Document Image Management Functions
// ==============================================================================

/**
 * Check if a document is an image based on its metadata
 */
export function isImageDocument(metadata: Record<string, any>): boolean {
  return metadata?.file_type === 'image';
}

/**
 * Convert a storage URI to a frontend proxy URL for displaying images
 *
 * This avoids the problem of internal Docker URLs (kong:8000) not being accessible from the browser.
 * The frontend proxy handles authentication and permission checks via LangConnect.
 *
 * @param storagePath - Storage URI (e.g., storage://collections/{uuid}/{filename})
 * @returns Frontend proxy URL (e.g., /api/langconnect/storage/image/collections/{uuid}/{filename})
 */
export function getImageProxyUrl(storagePath: string): string {
  // Parse storage URI: storage://collections/{path}
  if (!storagePath.startsWith('storage://collections/')) {
    throw new Error(`Invalid storage path format: ${storagePath}`);
  }

  // Extract the path after storage://collections/
  const path = storagePath.replace('storage://collections/', '');

  // Return frontend proxy URL
  return `/api/langconnect/storage/image/${path}`;
}

/**
 * Fetch a signed URL for accessing an image from storage
 *
 * @deprecated Use getImageProxyUrl() instead for displaying images in the browser.
 * This function returns internal Docker URLs that won't work from the browser.
 *
 * @param storagePath - Storage URI (e.g., storage://collections/{uuid}/{filename})
 * @param accessToken - User's access token for authentication (unused, kept for compatibility)
 * @param cacheBuster - Optional cache-busting value (timestamp or version) to force browser refresh
 * @returns Frontend proxy URL that works from the browser
 */
export async function getSignedImageUrl(
  storagePath: string,
  accessToken: string,
  cacheBuster?: string | number
): Promise<string> {
  // Instead of fetching a signed URL from the backend (which returns internal Docker URLs),
  // return the frontend proxy URL which handles everything server-side
  const baseUrl = getImageProxyUrl(storagePath);

  // Add cache-busting parameter if provided
  if (cacheBuster) {
    return `${baseUrl}?v=${cacheBuster}`;
  }

  return baseUrl;
}

/**
 * Get a thumbnail URL for an image
 * Currently returns the full signed URL
 *
 * In the future, could use Supabase image transformation params
 * to generate actual thumbnails on-the-fly
 *
 * @param signedUrl - Signed URL for the full image
 * @param size - Desired thumbnail size (not used yet)
 * @returns URL for the thumbnail (currently same as signed URL)
 */
export function getImageThumbnailUrl(
  signedUrl: string,
  size: number = 64
): string {
  // For now, return full URL
  // Future: Could add Supabase transform params like:
  // return `${signedUrl}&width=${size}&height=${size}`;
  return signedUrl;
}

/**
 * Replace an image document's file with a new image
 *
 * @param collectionId - Collection UUID
 * @param documentId - Document UUID
 * @param file - New image file to upload
 * @param accessToken - User's access token for authentication
 * @returns Result with success status and updated metadata
 */
export async function replaceDocumentImage(
  collectionId: string,
  documentId: string,
  file: File,
  accessToken: string
): Promise<{
  success: boolean;
  message: string;
  document_id: string;
  metadata: {
    title: string;
    description: string;
    storage_path: string;
  };
}> {
  const formData = new FormData();
  formData.append('file', file);

  const response = await fetch(
    `/api/langconnect/collections/${collectionId}/documents/${documentId}/image`,
    {
      method: 'PUT',
      headers: {
        'Authorization': `Bearer ${accessToken}`,
      },
      body: formData,
    }
  );

  if (!response.ok) {
    const error = await response.json().catch(() => ({ error: 'Failed to replace image' }));
    throw new Error(error.error || error.detail || 'Failed to replace image');
  }

  return await response.json();
}

/**
 * Batch fetch signed URLs for multiple images
 *
 * @param storagePaths - Array of storage URIs
 * @param accessToken - User's access token for authentication
 * @param cacheBuster - Optional cache-busting value (timestamp or version) to force browser refresh
 * @returns Map of storage path -> signed URL
 */
export async function batchGetSignedImageUrls(
  storagePaths: string[],
  accessToken: string,
  cacheBuster?: string | number
): Promise<Map<string, string>> {
  const urlMap = new Map<string, string>();

  // Fetch all URLs in parallel
  const promises = storagePaths.map(async (path) => {
    try {
      const url = await getSignedImageUrl(path, accessToken, cacheBuster);
      urlMap.set(path, url);
    } catch (error) {
      console.error(`Failed to fetch signed URL for ${path}:`, error);
      // Don't add to map if fetch fails
    }
  });

  await Promise.all(promises);

  return urlMap;
}
