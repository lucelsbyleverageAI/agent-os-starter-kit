import type { Base64ContentBlock } from "@langchain/core/messages";
import { toast } from "sonner";
// Returns a Promise of a typed multimodal block for images or PDFs
export async function fileToContentBlock(
  file: File,
): Promise<Base64ContentBlock> {
  const supportedImageTypes = [
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
  ];
  const supportedFileTypes = [...supportedImageTypes, "application/pdf"];

  if (!supportedFileTypes.includes(file.type)) {
    toast.error(
      `Unsupported file type: ${file.type}. Supported types are: ${supportedFileTypes.join(", ")}`,
    );
    return Promise.reject(new Error(`Unsupported file type: ${file.type}`));
  }

  const data = await fileToBase64(file);

  if (supportedImageTypes.includes(file.type)) {
    return {
      type: "image",
      source_type: "base64",
      mime_type: file.type,
      data,
      metadata: { name: file.name },
    };
  }

  // PDF
  return {
    type: "file",
    source_type: "base64",
    mime_type: "application/pdf",
    data,
    metadata: { filename: file.name },
  };
}

// Helper to convert File to base64 string
export async function fileToBase64(file: File): Promise<string> {
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onloadend = () => {
      const result = reader.result as string;
      // Remove the data:...;base64, prefix
      resolve(result.split(",")[1]);
    };
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

export function isBase64ContentBlock(
  block: unknown,
): block is Base64ContentBlock {
  if (typeof block !== "object" || block === null || !("type" in block))
    return false;

  const blockType = (block as { type: unknown }).type;

  // Text block (for extracted document content)
  if (blockType === "text") {
    const text = (block as { text?: unknown }).text;
    // Accept text blocks that contain our XML format or have extracted_text metadata
    if (typeof text === "string" &&
        (text.includes("<UserUploadedAttachment>") ||
         (block as any).metadata?.extracted_text)) {
      return true;
    }
  }

  const sourceType = (block as { source_type?: unknown }).source_type;
  const mimeType = (block as { mime_type?: unknown }).mime_type;

  // Image blocks with storage paths (new approach)
  if (blockType === "image" && sourceType === "url") {
    const url = (block as { url?: unknown }).url;
    // Accept image blocks with storage paths
    if (typeof url === "string" && url.length > 0) {
      return true;
    }
  }

  // Basic type checks for base64 blocks
  if (
    !["file", "image"].includes(String(blockType)) ||
    sourceType !== "base64" ||
    typeof mimeType !== "string"
  ) {
    return false;
  }

  // Image block (base64 - legacy)
  if (
    blockType === "image" &&
    mimeType.startsWith("image/")
  ) {
    return true;
  }

  // File block (PDF or processed document)
  if (
    blockType === "file" &&
    (mimeType === "application/pdf" || (block as any).metadata?.extracted_text)
  ) {
    return true;
  }

  return false;
}
