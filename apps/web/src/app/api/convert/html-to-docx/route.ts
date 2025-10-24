import { NextRequest, NextResponse } from "next/server";
import HTMLtoDOCX from "html-to-docx";

// Force Node.js runtime (not Edge)
export const runtime = "nodejs";

/**
 * API endpoint to convert HTML to DOCX
 * POST /api/convert/html-to-docx
 * Body: { html: string, filename?: string }
 * Returns: DOCX file as blob
 */
export async function POST(request: NextRequest) {
  try {
    const { html, filename = "document" } = await request.json();

    if (!html || typeof html !== "string") {
      return NextResponse.json(
        { error: "HTML content is required and must be a string" },
        { status: 400 }
      );
    }

    // Generate DOCX buffer using html-to-docx with enhanced options
    const docxBuffer = await HTMLtoDOCX(html, null, {
      table: {
        row: { cantSplit: true },
      },
      footer: false,
      pageNumber: false,
      font: "Calibri",
      fontSize: 22, // 11pt in half-points (22/2 = 11)
      margins: {
        top: 1440, // 1 inch in twips (1440 twips = 1 inch)
        right: 1440,
        bottom: 1440,
        left: 1440,
      },
      lineNumber: false,
    });

    // Return the DOCX file
    return new NextResponse(docxBuffer, {
      status: 200,
      headers: {
        "Content-Type":
          "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "Content-Disposition": `attachment; filename="${filename}.docx"`,
      },
    });
  } catch (error) {
    console.error("Error converting HTML to DOCX:", error);
    return NextResponse.json(
      { error: "Failed to convert HTML to DOCX" },
      { status: 500 }
    );
  }
}
