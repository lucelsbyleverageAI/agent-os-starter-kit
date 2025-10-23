import { NextRequest, NextResponse } from "next/server";

const LANGCONNECT_URL = process.env.LANGCONNECT_BASE_URL || process.env.NEXT_PUBLIC_LANGCONNECT_URL || "http://localhost:8080";

export async function PUT(
  request: NextRequest,
  { params }: { params: Promise<{ collectionId: string; documentId: string }> }
) {
  try {
    // Await params before using them
    const resolvedParams = await params;
    const { collectionId, documentId } = resolvedParams;

    // Get Authorization header from request
    const authHeader = request.headers.get("Authorization");
    if (!authHeader) {
      return NextResponse.json(
        { error: "Unauthorized - No Authorization header" },
        { status: 401 }
      );
    }

    // Get form data from request
    const formData = await request.formData();

    // Forward to LangConnect
    const response = await fetch(
      `${LANGCONNECT_URL}/collections/${collectionId}/documents/${documentId}/content`,
      {
        method: "PUT",
        headers: {
          Authorization: authHeader,
        },
        body: formData,
      }
    );

    const data = await response.json();

    if (!response.ok) {
      return NextResponse.json(
        data,
        { status: response.status }
      );
    }

    return NextResponse.json(data);
  } catch (error) {
    console.error("Error updating document content:", error);
    return NextResponse.json(
      { error: "Failed to update document content" },
      { status: 500 }
    );
  }
}
