import { NextRequest, NextResponse } from "next/server";
import HTMLtoDOCX from "html-to-docx";

// Force Node.js runtime (not Edge)
export const runtime = "nodejs";

/**
 * Convert markdown text to enhanced HTML
 * Supports: headings, bold, italic, lists, code blocks, tables, horizontal rules, and paragraphs
 */
function markdownToHtml(markdown: string): string {
  // Sanitize input
  if (!markdown || typeof markdown !== 'string') {
    return '<p>No content available</p>';
  }

  let html = markdown.trim();

  // Horizontal rules (--- or ***)
  html = html.replace(/^[\s]*[-*]{3,}[\s]*$/gm, "<hr/>");

  // Tables (basic markdown table support)
  html = html.replace(
    /(\|[^\n]+\|\r?\n)((?:\|[-: ]+\|[-: |]*\r?\n))(\|[^\n]+\|\r?\n?)+/g,
    (match) => {
      const lines = match.trim().split("\n");
      if (lines.length < 2) return match;

      const headers = lines[0]
        .split("|")
        .filter((cell) => cell.trim())
        .map((cell) => `<th>${cell.trim()}</th>`)
        .join("");

      const rows = lines
        .slice(2)
        .map((line) => {
          const cells = line
            .split("|")
            .filter((cell) => cell.trim())
            .map((cell) => `<td>${cell.trim()}</td>`)
            .join("");
          return `<tr>${cells}</tr>`;
        })
        .join("");

      return `<table><thead><tr>${headers}</tr></thead><tbody>${rows}</tbody></table>`;
    }
  );

  // Code blocks (triple backticks)
  html = html.replace(/```[\s\S]*?```/g, (match) => {
    const codeContent = match.replace(/```/g, "").trim();
    return `<pre><code>${escapeHtml(codeContent)}</code></pre>`;
  });

  // Inline code (backticks)
  html = html.replace(/`([^`]+)`/g, "<code>$1</code>");

  // Bold (**text** and __text__)
  html = html.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/__([^_]+)__/g, "<strong>$1</strong>");

  // Italic (*text* and _text_)
  html = html.replace(/\*([^*\n]+)\*/g, "<em>$1</em>");
  html = html.replace(/_([^_\n]+)_/g, "<em>$1</em>");

  // Headers (h1-h6)
  html = html.replace(/^#### (.*?)$/gm, "<h4>$1</h4>");
  html = html.replace(/^### (.*?)$/gm, "<h3>$1</h3>");
  html = html.replace(/^## (.*?)$/gm, "<h2>$1</h2>");
  html = html.replace(/^# (.*?)$/gm, "<h1>$1</h1>");

  // Unordered lists
  html = html.replace(/^[\s]*[-*+] (.*?)$/gm, "<li>$1</li>");
  html = html.replace(/(<li>[\s\S]*?<\/li>)/, (match) => {
    if (!match.includes("<ul>") && !match.includes("<ol>")) {
      return `<ul>${match}</ul>`;
    }
    return match;
  });

  // Ordered lists
  html = html.replace(/^[\s]*\d+\. (.*?)$/gm, "<li>$1</li>");

  // Line breaks - convert multiple newlines to paragraphs
  const paragraphs = html.split(/\n\n+/).filter((p) => p.trim());
  html = paragraphs
    .map((para) => {
      const trimmed = para.trim();
      if (!trimmed) return '';

      // Skip if already a block element
      if (
        trimmed.startsWith("<") &&
        (trimmed.match(/<(h[1-6]|ul|ol|pre|table|hr|li)[\s>]/i))
      ) {
        return trimmed;
      }
      // Wrap in paragraph if it's plain text or inline elements only
      if (trimmed && !trimmed.startsWith("<p")) {
        // Clean up any stray newlines within the paragraph
        const cleanPara = trimmed.replace(/\n/g, ' ');
        return `<p>${cleanPara}</p>`;
      }
      return trimmed;
    })
    .filter(p => p)
    .join("\n");

  return html;
}

/**
 * Escape HTML special characters
 */
function escapeHtml(text: string): string {
  const map: Record<string, string> = {
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#039;",
  };
  return text.replace(/[&<>"']/g, (char) => map[char]);
}

/**
 * API endpoint to convert markdown to DOCX
 * POST /api/convert/markdown-to-docx
 * Body: { content: string, filename?: string }
 * Returns: DOCX file as blob
 */
export async function POST(request: NextRequest) {
  try {
    const { content, filename = "document" } = await request.json();

    console.log(`📄 Converting markdown to DOCX: "${filename}"`);
    console.log(`📏 Content length: ${content?.length || 0} characters`);

    if (!content || typeof content !== "string") {
      return NextResponse.json(
        { error: "Content is required and must be a string" },
        { status: 400 }
      );
    }

    // Convert markdown to HTML
    const htmlContent = markdownToHtml(content);
    console.log(`✅ Markdown converted to HTML: ${htmlContent.length} characters`);

    if (!htmlContent) {
      return NextResponse.json(
        { error: "Failed to convert markdown to HTML" },
        { status: 500 }
      );
    }

    // Create complete HTML document with simplified, compatible styling
    const html = `
      <!DOCTYPE html>
      <html>
        <head>
          <meta charset='utf-8'>
          <style>
            body {
              font-family: Inter, system-ui, -apple-system, BlinkMacSystemFont, sans-serif;
              font-size: 12pt;
              line-height: 1.7;
              color: #1f2937;
            }
            h1 {
              font-size: 24pt;
              font-weight: 700;
              color: #111827;
              margin-top: 20pt;
              margin-bottom: 12pt;
              letter-spacing: -0.02em;
            }
            h2 {
              font-size: 18pt;
              font-weight: 600;
              color: #374151;
              margin-top: 18pt;
              margin-bottom: 10pt;
              letter-spacing: -0.01em;
            }
            h3 {
              font-size: 14pt;
              font-weight: 600;
              color: #4b5563;
              margin-top: 14pt;
              margin-bottom: 8pt;
            }
            h4 {
              font-size: 12pt;
              font-weight: 600;
              color: #6b7280;
              margin-top: 12pt;
              margin-bottom: 6pt;
            }
            p {
              margin-bottom: 10pt;
              margin-top: 0pt;
            }
            ul, ol {
              margin-bottom: 12pt;
              margin-top: 8pt;
              padding-left: 28pt;
            }
            li {
              margin-bottom: 6pt;
              line-height: 1.6;
            }
            strong {
              font-weight: bold;
            }
            em {
              font-style: italic;
            }
            code {
              font-family: 'SF Mono', 'Monaco', 'Consolas', 'Liberation Mono', 'Courier New', monospace;
              background-color: #f3f4f6;
              padding: 2pt 4pt;
              border-radius: 3pt;
              font-size: 10.5pt;
            }
            pre {
              background-color: #f9fafb;
              padding: 14pt;
              margin: 12pt 0pt;
              border: 1px solid #e5e7eb;
              border-radius: 4pt;
            }
            pre code {
              background-color: transparent;
              padding: 0;
            }
            table {
              border-collapse: collapse;
              width: 100%;
              margin: 12pt 0pt;
              border: 0.75px solid #e5e5e5;
            }
            th {
              background-color: #f3f4f6;
              color: #1f2937;
              font-weight: 600;
              padding: 10pt 12pt;
              border: 0.75px solid #e5e5e5;
              text-align: left;
              border-bottom: 2px solid #d1d5db;
            }
            td {
              padding: 8pt 12pt;
              border: 0.75px solid #e5e5e5;
              background-color: white;
            }
            tr:nth-child(even) td {
              background-color: #fafafa;
            }
            hr {
              border: none;
              border-top: 1px solid #e5e7eb;
              margin: 20pt 0pt;
            }
          </style>
        </head>
        <body>
          ${htmlContent}
        </body>
      </html>
    `;

    // Generate DOCX buffer using html-to-docx with simplified options
    console.log(`🔄 Generating DOCX from HTML...`);
    let docxBuffer;
    try {
      docxBuffer = await HTMLtoDOCX(html, null, {
        table: {
          row: { cantSplit: true },
        },
        footer: false,
        pageNumber: false,
      });

      if (!docxBuffer) {
        throw new Error("HTMLtoDOCX returned empty buffer");
      }
      console.log(`✅ DOCX buffer generated successfully`);
    } catch (docxError) {
      console.error("❌ HTMLtoDOCX conversion error:", docxError);
      return NextResponse.json(
        {
          error: "Failed to generate DOCX file",
          details: docxError instanceof Error ? docxError.message : String(docxError)
        },
        { status: 500 }
      );
    }

    // Ensure buffer is properly formatted
    let buffer: Buffer;
    try {
      buffer = Buffer.isBuffer(docxBuffer) ? docxBuffer : Buffer.from(docxBuffer);

      // Validate buffer size
      if (buffer.length === 0) {
        throw new Error("Generated DOCX buffer is empty");
      }
      console.log(`✅ Buffer created: ${buffer.length} bytes`);
    } catch (bufferError) {
      console.error("❌ Buffer conversion error:", bufferError);
      return NextResponse.json(
        {
          error: "Failed to create document buffer",
          details: bufferError instanceof Error ? bufferError.message : String(bufferError)
        },
        { status: 500 }
      );
    }

    // Return the DOCX file
    console.log(`📦 Returning DOCX file: ${filename}.docx (${buffer.length} bytes)`);
    return new NextResponse(buffer, {
      status: 200,
      headers: {
        "Content-Type":
          "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "Content-Disposition": `attachment; filename="${encodeURIComponent(filename)}.docx"`,
        "Content-Length": buffer.length.toString(),
      },
    });
  } catch (error) {
    console.error("Error converting markdown to DOCX:", error);
    console.error("Error details:", error instanceof Error ? error.message : String(error));
    console.error("Stack trace:", error instanceof Error ? error.stack : "No stack trace");

    return NextResponse.json(
      {
        error: "Failed to convert markdown to DOCX",
        details: error instanceof Error ? error.message : String(error)
      },
      { status: 500 }
    );
  }
}
