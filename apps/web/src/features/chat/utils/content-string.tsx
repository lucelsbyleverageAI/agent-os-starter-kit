import type { Message } from "@langchain/langgraph-sdk";
import type { Base64ContentBlock } from "@langchain/core/messages";

/**
 * Escapes dollar signs that appear to be currency amounts while preserving LaTeX math expressions.
 * 
 * @param text - The text to process
 * @returns Text with currency dollar signs escaped but math expressions preserved
 */
function escapeCurrencyDollarSigns(text: string): string {
  // Patterns for currency amounts that should be escaped:
  // - $X trillion/billion/million (e.g., "$21.8 trillion")
  // - $X.X trillion/billion/million 
  // - $XXX,XXX (e.g., "$100,000")
  // - $XXX (standalone currency amounts)
  
  // Use HTML entity &#36; instead of \$ to avoid markdown parsing issues
  return text
    // Escape currency amounts with large denomination words
    .replace(/\$(\d+(?:\.\d+)?)\s*(trillion|billion|million|thousand)/gi, '&#36;$1 $2')
    // Escape currency amounts with commas (e.g., $100,000)
    .replace(/\$(\d{1,3}(?:,\d{3})+(?:\.\d{2})?)\b/g, '&#36;$1')
    // Escape standalone currency amounts (but be careful not to break math)
    // Only escape if followed by space and a word, or at end of sentence
    .replace(/\$(\d+(?:\.\d+)?)\s+(?=\w)/g, '&#36;$1 ')
    .replace(/\$(\d+(?:\.\d+)?)([.!?])/g, '&#36;$1$2');
}

/**
 * Returns the content of a message as a string.
 *
 * @param content - The content of the message
 * @returns The content of the message as a string
 */
export function getContentString(content: Message["content"]): string {
  let textContent: string;
  
  if (typeof content === "string") {
    textContent = content;
  } else {
    const texts = content
      .filter((c): c is { type: "text"; text: string } => c.type === "text")
      .map((c) => c.text)
      .filter((text) => {
        // Exclude XML-wrapped document content from regular text display
        return !text.includes("<UserUploadedAttachment>");
      });
    
    // Join text blocks with a space
    textContent = texts.join(" ");
  }
  
  // Always apply currency escaping to preserve math expressions while escaping currency
  return escapeCurrencyDollarSigns(textContent);
}

/**
 * Calculate total character count for a message including text and attachment content
 * Used for cost warning purposes
 */
export function calculateMessageCharacterCount(
  textContent: string,
  contentBlocks: Base64ContentBlock[]
): number {
  let totalCharacters = textContent.length;
  
  // Add characters from attachment content
  contentBlocks.forEach(block => {
    if ((block as any).type === "text" && (block as any).text) {
      // Text blocks with extracted content (new format)
      const text = (block as any).text as string;
      if (text.includes("<UserUploadedAttachment>")) {
        // Extract content from XML wrapper
        const contentMatch = text.match(/<Content>([\s\S]*?)<\/Content>/);
        if (contentMatch) {
          totalCharacters += contentMatch[1].trim().length;
        }
      } else {
        totalCharacters += text.length;
      }
    } else if (block.type === "file" && block.source_type === "base64" && (block as any).metadata?.extracted_text) {
      // Legacy format with extracted text
      try {
        // Estimate text content from base64 data (rough approximation)
        const decodedSize = Math.floor(block.data.length * 0.75); // base64 is ~33% larger
        totalCharacters += decodedSize; // Very rough estimate
      } catch {
        // If we can't decode, skip this block
      }
    }
  });
  
  return totalCharacters;
}



// Character count threshold for warning
export const LARGE_MESSAGE_WARNING_THRESHOLD = 100000; // Show warning at 100k characters
