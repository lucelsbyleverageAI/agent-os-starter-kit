/**
 * Utility for converting markdown content to Word document (DOCX) format
 * Uses server-side API for conversion to avoid Node.js module issues in browser
 */

/**
 * Convert markdown content to DOCX and trigger download
 * Calls server-side API endpoint for conversion
 * @param content - Markdown content to convert
 * @param filename - Output filename (without .docx extension)
 */
export async function downloadMarkdownAsDocx(
  content: string,
  filename: string
): Promise<void> {
  try {
    // Call server-side API to convert markdown to DOCX
    const response = await fetch("/api/convert/markdown-to-docx", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ content, filename }),
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(
        errorData.error || `Conversion failed: ${response.statusText}`
      );
    }

    // Get the blob from response
    const blob = await response.blob();

    // Create download link
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${filename}.docx`;
    document.body.appendChild(link);
    link.click();

    // Cleanup
    setTimeout(() => {
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
    }, 100);
  } catch (error) {
    console.error("Error generating DOCX:", error);
    throw error;
  }
}

/**
 * Download content as markdown file
 * @param content - Markdown content to download
 * @param filename - Output filename (without extension)
 */
export function downloadAsMarkdown(content: string, filename: string): void {
  try {
    const blob = new Blob([content], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${filename}.md`;
    document.body.appendChild(link);
    link.click();

    // Cleanup
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  } catch (error) {
    console.error("Error downloading markdown:", error);
    throw error;
  }
}
