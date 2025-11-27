import { NextRequest, NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";

// Allowed MIME types for document uploads
const ALLOWED_DOCUMENT_TYPES = [
  'application/pdf',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document', // .docx
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', // .xlsx
  'application/vnd.openxmlformats-officedocument.presentationml.presentation', // .pptx
  'application/msword', // .doc
  'application/vnd.ms-excel', // .xls
  'application/vnd.ms-powerpoint', // .ppt
  'text/plain',
  'text/csv',
  'text/markdown',
];

/**
 * POST /api/langconnect/storage/upload-chat-document
 *
 * Proxy endpoint to upload documents for chat messages to storage.
 * Documents are stored in the chat-uploads bucket with path: {user_id}/{timestamp}_{filename}
 *
 * Form data:
 *   - file: Document file to upload
 */
export async function POST(request: NextRequest) {
  try {
    // Get user session
    const supabase = await createClient();
    const { data: { session }, error: sessionError } = await supabase.auth.getSession();

    if (sessionError || !session) {
      return NextResponse.json(
        { error: 'Unauthorized' },
        { status: 401 }
      );
    }

    // Parse form data
    const formData = await request.formData();
    const file = formData.get('file');

    if (!file || !(file instanceof File)) {
      return NextResponse.json(
        { error: 'file is required and must be a File' },
        { status: 400 }
      );
    }

    // Validate file type
    if (!ALLOWED_DOCUMENT_TYPES.includes(file.type)) {
      return NextResponse.json(
        { error: `Invalid file type: ${file.type}. Allowed types: ${ALLOWED_DOCUMENT_TYPES.join(', ')}` },
        { status: 400 }
      );
    }

    // Validate file size (50MB limit)
    const maxSize = 50 * 1024 * 1024; // 50MB in bytes
    if (file.size > maxSize) {
      return NextResponse.json(
        { error: 'File size exceeds 50MB limit' },
        { status: 400 }
      );
    }

    // Create form data for backend
    const backendFormData = new FormData();
    backendFormData.append('file', file);

    // Call backend API
    const backendUrl = `${process.env.LANGCONNECT_BASE_URL}/storage/upload-chat-document`;

    const response = await fetch(backendUrl, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${session.access_token}`,
        // Don't set Content-Type - let fetch set it with boundary for multipart/form-data
      },
      body: backendFormData,
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({ error: 'Failed to upload document' }));
      return NextResponse.json(
        errorData,
        { status: response.status }
      );
    }

    const data = await response.json();
    return NextResponse.json(data);

  } catch (error) {
    console.error('Error in upload chat document proxy:', error);
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    );
  }
}
