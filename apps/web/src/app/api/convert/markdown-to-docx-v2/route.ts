import { NextRequest, NextResponse } from "next/server";
import {
  Document,
  Packer,
  Paragraph,
  TextRun,
  HeadingLevel,
} from "docx";

// Force Node.js runtime (not Edge)
export const runtime = "nodejs";

/**
 * Parse markdown and convert to docx Document structure
 */
function markdownToDocx(markdown: string): Document {
  const lines = markdown.split("\n");
  const paragraphs: Paragraph[] = [];
  let inCodeBlock = false;
  let codeBlockContent: string[] = [];
  let errorCount = 0;
  const MAX_ERRORS = 10;

  for (let i = 0; i < lines.length; i++) {
    try {
      const line = lines[i];

      // Skip if we've hit too many errors
      if (errorCount >= MAX_ERRORS) {
        console.warn(`Too many parsing errors, stopping at line ${i}`);
        break;
      }

    // Handle code blocks
    if (line.trim().startsWith("```")) {
      if (inCodeBlock) {
        // End of code block - add all collected lines
        paragraphs.push(
          new Paragraph({
            children: [
              new TextRun({
                text: codeBlockContent.join("\n"),
                font: "Courier New",
                size: 20,
              }),
            ],
            spacing: { before: 200, after: 200 },
            shading: {
              fill: "F3F4F6",
            },
          })
        );
        codeBlockContent = [];
        inCodeBlock = false;
      } else {
        inCodeBlock = true;
      }
      continue;
    }

    if (inCodeBlock) {
      codeBlockContent.push(line);
      continue;
    }

    // Skip empty lines
    if (!line.trim()) {
      paragraphs.push(new Paragraph({ text: "" }));
      continue;
    }

    // Headings
    if (line.startsWith("# ")) {
      paragraphs.push(
        new Paragraph({
          text: line.substring(2),
          heading: HeadingLevel.HEADING_1,
          spacing: { before: 400, after: 200 },
        })
      );
      continue;
    }

    if (line.startsWith("## ")) {
      paragraphs.push(
        new Paragraph({
          text: line.substring(3),
          heading: HeadingLevel.HEADING_2,
          spacing: { before: 300, after: 150 },
        })
      );
      continue;
    }

    if (line.startsWith("### ")) {
      paragraphs.push(
        new Paragraph({
          text: line.substring(4),
          heading: HeadingLevel.HEADING_3,
          spacing: { before: 240, after: 120 },
        })
      );
      continue;
    }

    if (line.startsWith("#### ")) {
      paragraphs.push(
        new Paragraph({
          text: line.substring(5),
          heading: HeadingLevel.HEADING_4,
          spacing: { before: 200, after: 100 },
        })
      );
      continue;
    }

    // Lists
    if (line.trim().match(/^[-*+]\s/)) {
      const text = line.trim().substring(2);
      paragraphs.push(
        new Paragraph({
          text: text,
          bullet: { level: 0 },
          spacing: { before: 100, after: 100 },
        })
      );
      continue;
    }

    if (line.trim().match(/^\d+\.\s/)) {
      const text = line.trim().replace(/^\d+\.\s/, "");
      // Use simple text with number instead of numbering scheme
      paragraphs.push(
        new Paragraph({
          text: text,
          spacing: { before: 100, after: 100 },
          indent: { left: 360 },
        })
      );
      continue;
    }

    // Horizontal rules
    if (line.trim().match(/^[-*_]{3,}$/)) {
      paragraphs.push(
        new Paragraph({
          border: {
            bottom: {
              color: "E5E7EB",
              space: 1,
              style: "single",
              size: 6,
            },
          },
          spacing: { before: 200, after: 200 },
        })
      );
      continue;
    }

      // Regular paragraph with inline formatting
      // Truncate very long lines to prevent issues
      const truncatedLine = line.length > 5000 ? line.substring(0, 5000) + "..." : line;
      const textRuns = parseInlineFormatting(truncatedLine);
      paragraphs.push(
        new Paragraph({
          children: textRuns,
          spacing: { before: 100, after: 100 },
        })
      );
    } catch (error) {
      errorCount++;
      console.warn(`Error parsing line ${i}:`, error);
      // Add as plain text paragraph on error
      try {
        paragraphs.push(new Paragraph({ text: lines[i] || "" }));
      } catch (_e) {
        // Skip this line entirely if even plain text fails
        console.error(`Failed to add line ${i} even as plain text`);
      }
    }
  }

  // Ensure we have at least one paragraph
  if (paragraphs.length === 0) {
    paragraphs.push(new Paragraph({ text: "Document content could not be parsed" }));
  }

  console.log(`📊 Parsed ${lines.length} lines into ${paragraphs.length} paragraphs (${errorCount} errors)`);

  return new Document({
    sections: [
      {
        properties: {},
        children: paragraphs,
      },
    ],
  });
}

/**
 * Parse inline formatting (bold, italic, code) - simplified and safer
 */
function parseInlineFormatting(text: string): TextRun[] {
  try {
    // For safety with large documents, if text is very long, just return plain text
    if (text.length > 10000) {
      return [new TextRun({ text })];
    }

    const runs: TextRun[] = [];
    let remaining = text;

    // Process bold first (**text** or __text__)
    remaining = remaining.replace(/\*\*(.+?)\*\*/g, (match, content) => {
      const placeholder = `__BOLD_${runs.length}__`;
      runs.push(new TextRun({ text: content, bold: true }));
      return placeholder;
    });

    remaining = remaining.replace(/__(.+?)__/g, (match, content) => {
      const placeholder = `__BOLD_${runs.length}__`;
      runs.push(new TextRun({ text: content, bold: true }));
      return placeholder;
    });

    // Process italic (*text* or _text_)
    remaining = remaining.replace(/\*(.+?)\*/g, (match, content) => {
      const placeholder = `__ITALIC_${runs.length}__`;
      runs.push(new TextRun({ text: content, italics: true }));
      return placeholder;
    });

    remaining = remaining.replace(/_(.+?)_/g, (match, content) => {
      const placeholder = `__ITALIC_${runs.length}__`;
      runs.push(new TextRun({ text: content, italics: true }));
      return placeholder;
    });

    // Process inline code (`code`)
    remaining = remaining.replace(/`(.+?)`/g, (match, content) => {
      const placeholder = `__CODE_${runs.length}__`;
      runs.push(
        new TextRun({
          text: content,
          font: "Courier New",
          size: 20,
        })
      );
      return placeholder;
    });

    // Now split by placeholders and add plain text runs
    const finalRuns: TextRun[] = [];
    const parts = remaining.split(/(__(?:BOLD|ITALIC|CODE)_\d+__)/);

    for (const part of parts) {
      if (part.startsWith("__BOLD_") || part.startsWith("__ITALIC_") || part.startsWith("__CODE_")) {
        const idx = parseInt(part.match(/_(\d+)__/)?.[1] || "0");
        if (runs[idx]) {
          finalRuns.push(runs[idx]);
        }
      } else if (part) {
        finalRuns.push(new TextRun({ text: part }));
      }
    }

    return finalRuns.length > 0 ? finalRuns : [new TextRun({ text })];
  } catch (error) {
    // If parsing fails, return plain text
    console.warn("Failed to parse inline formatting, using plain text:", error);
    return [new TextRun({ text })];
  }
}

/**
 * API endpoint to convert markdown to DOCX using docx library
 * POST /api/convert/markdown-to-docx-v2
 * Body: { content: string, filename?: string }
 * Returns: DOCX file as blob
 */
export async function POST(request: NextRequest) {
  try {
    const { content, filename = "document" } = await request.json();

    console.log(`📄 Converting markdown to DOCX (v2): "${filename}"`);
    console.log(`📏 Content length: ${content?.length || 0} characters`);

    if (!content || typeof content !== "string") {
      return NextResponse.json(
        { error: "Content is required and must be a string" },
        { status: 400 }
      );
    }

    // Convert markdown to Document
    console.log(`🔄 Parsing markdown...`);
    const startParse = Date.now();
    const doc = markdownToDocx(content);
    const parseDuration = Date.now() - startParse;
    console.log(`✅ Parsing complete in ${parseDuration}ms`);

    // Generate DOCX buffer
    console.log(`🔄 Generating DOCX buffer...`);
    const startPack = Date.now();
    const buffer = await Packer.toBuffer(doc);
    const packDuration = Date.now() - startPack;

    console.log(`✅ DOCX generated: ${buffer.length} bytes in ${packDuration}ms`);

    // Validate the buffer
    if (buffer.length < 1000) {
      console.warn(`⚠️ Warning: DOCX buffer seems too small (${buffer.length} bytes)`);
    }

    // Return the DOCX file
    return new NextResponse(buffer, {
      status: 200,
      headers: {
        "Content-Type":
          "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "Content-Disposition": `attachment; filename="${encodeURIComponent(
          filename
        )}.docx"`,
        "Content-Length": buffer.length.toString(),
      },
    });
  } catch (error) {
    console.error("❌ Error converting markdown to DOCX:", error);
    console.error(
      "Error details:",
      error instanceof Error ? error.message : String(error)
    );
    console.error(
      "Stack trace:",
      error instanceof Error ? error.stack : "No stack trace"
    );

    return NextResponse.json(
      {
        error: "Failed to convert markdown to DOCX",
        details: error instanceof Error ? error.message : String(error),
      },
      { status: 500 }
    );
  }
}
