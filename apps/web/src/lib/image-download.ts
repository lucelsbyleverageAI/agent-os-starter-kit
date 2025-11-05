/**
 * Utility functions for downloading images from the storage API
 */

/**
 * Extracts the filename from a storage path or URL
 * @param storagePath - The storage path (e.g., "collections/uuid/image.png")
 * @param fallbackName - Fallback name if extraction fails
 * @returns The extracted filename with extension
 */
function extractFilename(storagePath: string, fallbackName: string = "document"): string {
  try {
    // Extract filename from path (get last segment after /)
    const segments = storagePath.split('/');
    const filename = segments[segments.length - 1];

    if (filename && filename.includes('.')) {
      return filename;
    }

    // If no extension found, try to get it from the path
    const extension = storagePath.match(/\.(png|jpg|jpeg|gif|webp|svg|bmp)$/i)?.[1];
    if (extension) {
      return `${fallbackName}.${extension}`;
    }

    return `${fallbackName}.png`; // Default fallback
  } catch (error) {
    console.error("Error extracting filename:", error);
    return `${fallbackName}.png`;
  }
}

/**
 * Detects the image format from storage path or content type
 * @param storagePath - The storage path
 * @param contentType - Optional content-type header
 * @returns The file extension (e.g., "png", "jpg")
 */
export function detectImageFormat(storagePath: string, contentType?: string): string {
  // Try to extract from storage path first
  const pathMatch = storagePath.match(/\.(png|jpg|jpeg|gif|webp|svg|bmp)$/i);
  if (pathMatch) {
    return pathMatch[1].toLowerCase();
  }

  // Try to extract from content-type
  if (contentType) {
    const typeMatch = contentType.match(/image\/(png|jpg|jpeg|gif|webp|svg|bmp)/i);
    if (typeMatch) {
      return typeMatch[1].toLowerCase();
    }
  }

  // Default fallback
  return "png";
}

/**
 * Downloads an image from the storage API
 * @param imageUrl - The image URL (usually the proxy API URL)
 * @param documentName - The document name to use for the downloaded file
 * @param storagePath - The storage path (used for filename extraction)
 * @throws Error if download fails
 */
export async function downloadImage(
  imageUrl: string,
  documentName: string,
  storagePath?: string
): Promise<void> {
  try {
    // Fetch the image
    const response = await fetch(imageUrl);

    if (!response.ok) {
      throw new Error(`Failed to fetch image: ${response.statusText}`);
    }

    // Get the blob
    const blob = await response.blob();

    // Determine filename
    let filename: string;
    if (storagePath) {
      filename = extractFilename(storagePath, documentName);
    } else {
      // Try to detect format from content-type
      const contentType = response.headers.get('content-type');
      const format = detectImageFormat(documentName, contentType || undefined);

      // Remove any existing extension and add the detected one
      const nameWithoutExt = documentName.replace(/\.[^/.]+$/, "");
      filename = `${nameWithoutExt}.${format}`;
    }

    // Create download link and trigger download
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();

    // Cleanup
    document.body.removeChild(link);
    window.URL.revokeObjectURL(url);
  } catch (error) {
    console.error("Image download failed:", error);
    throw error;
  }
}

/**
 * Gets a human-readable format label for display in UI
 * @param storagePath - The storage path
 * @returns A formatted string like "PNG", "JPG", etc.
 */
export function getImageFormatLabel(storagePath: string): string {
  const format = detectImageFormat(storagePath);
  return format.toUpperCase();
}
