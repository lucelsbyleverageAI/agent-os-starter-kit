# Skills DeepAgent File Sharing Implementation Plan

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Background & Context](#background--context)
3. [Current Architecture](#current-architecture)
4. [Requirements](#requirements)
5. [Solution Architecture](#solution-architecture)
6. [Detailed Implementation](#detailed-implementation)
7. [File Changes Summary](#file-changes-summary)
8. [Implementation Order](#implementation-order)
9. [Testing Checklist](#testing-checklist)

---

## Executive Summary

This document outlines the implementation plan for bi-directional file sharing between users and the Skills DeepAgent:

1. **User → Agent**: Users can upload images and documents (Excel, Word, PDF, PowerPoint) which are stored in Supabase Storage and transferred to the E2B sandbox for agent processing
2. **Agent → User**: Agents can explicitly "publish" files they create, making them available for preview and download in the chat UI

The approach is inspired by Claude AI's file handling pattern where agents explicitly publish outputs rather than exposing the entire sandbox filesystem.

---

## Background & Context

### What is Skills DeepAgent?

Skills DeepAgent is an agent template that extends the base DeepAgent with:
- **E2B Sandbox**: A cloud-based execution environment where agents can run Python code, process documents, and create files
- **Skills System**: Modular capability packages uploaded to `/sandbox/skills/` that provide domain-specific instructions and tools
- **Sandbox-only Filesystem**: Unlike the base DeepAgent which uses in-memory state for files, Skills DeepAgent uses the real E2B sandbox filesystem

### The Problem

Currently, the Skills DeepAgent has limited file sharing capabilities:

**User → Agent Issues:**
- Documents are extracted to markdown text only - the agent cannot access the original binary files
- This prevents the agent from modifying Excel files, editing PowerPoints, or processing PDFs with Python libraries
- Images are passed to the model for vision but aren't available in the sandbox for image processing

**Agent → User Issues:**
- Files created by the agent in the sandbox are invisible to users
- No way to preview, download, or even see what files exist
- If an agent creates a report, the user has no way to access it

### Design Inspiration

Claude AI (claude.ai) handles this elegantly:
- When an agent creates a document, it calls a tool to "publish" it
- A card appears in the chat with the file name and download button
- Clicking the card opens a side panel with a preview
- Files are explicitly shared rather than exposing the whole filesystem

This approach:
- Gives agents control over what users see
- Provides clean UI for file access
- Avoids complexity of filesystem synchronization

---

## Current Architecture

### Skills DeepAgent State Model

```python
# langgraph/src/agent_platform/agents/deepagents/skills_deepagent/state.py

class SkillsDeepAgentState(AgentState):
    """State for Skills DeepAgent - NO files field, all files in sandbox."""
    todos: NotRequired[list[Todo]]
    # Note: No 'files' field - this is intentional
```

### Sandbox Directory Structure

```
/sandbox/
├── skills/           # Read-only skill packages (uploaded on thread start)
├── user_uploads/     # User uploaded files
├── shared/           # Inter-agent communication
│   ├── research/
│   └── drafts/
├── outputs/          # Agent-created deliverables
└── workspace/        # Scratch space
```

### Current File Upload Flow

1. User uploads file in chat composer
2. Frontend calls `/documents/extract/text` to extract markdown preview
3. Markdown wrapped in `<UserUploadedAttachment>` XML
4. `file_attachment_processing.py` parses XML and writes markdown to `/sandbox/user_uploads/{filename}.md`
5. Agent sees the text preview but NOT the original binary file

### Key Files

| File | Purpose |
|------|---------|
| `langgraph/src/agent_platform/agents/deepagents/skills_deepagent/state.py` | State schema |
| `langgraph/src/agent_platform/agents/deepagents/skills_deepagent/sandbox_tools.py` | E2B sandbox management |
| `langgraph/src/agent_platform/agents/deepagents/skills_deepagent/file_attachment_processing.py` | Upload handling |
| `langgraph/src/agent_platform/agents/deepagents/skills_deepagent/graph.py` | Agent graph definition |
| `apps/web/src/hooks/use-file-upload.tsx` | Frontend upload logic |
| `apps/web/src/features/chat/components/thread/messages/tools/` | Tool UI component registry |

---

## Requirements

### User → Agent File Sharing

#### Images
- [ ] Upload original image to Supabase Storage
- [ ] Transfer image to `/sandbox/user_uploads/` for Python processing (PIL, etc.)
- [ ] Keep image content block for model vision capability
- [ ] Add hidden XML note with sandbox location (not visible in chat UI)

#### Documents (PDF, Word, Excel, PowerPoint, CSV)
- [ ] Upload original binary to Supabase Storage
- [ ] Transfer binary to `/sandbox/user_uploads/` (not just markdown)
- [ ] Extract text preview for agent awareness
- [ ] Add hidden XML note with sandbox location and preview

### Agent → User File Sharing

- [ ] New tool: `publish_file_to_user(file_path, display_name, description)`
- [ ] Upload published files to Supabase Storage (`deepagent-outputs` bucket)
- [ ] Use permanent storage paths (not expiring signed URLs)
- [ ] Track published files in agent state
- [ ] Support file updates/revisions (same display_name = update)

### Frontend UI

- [ ] Tool UI component showing file card when agent publishes
- [ ] Download button on card
- [ ] Click card (not button) opens preview side panel
- [ ] Preview support for: images, PDF, text/markdown
- [ ] "Download to view" fallback for complex formats (DOCX, XLSX, PPTX)

---

## Solution Architecture

### High-Level Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                        USER UPLOAD FLOW                              │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  User uploads file                                                   │
│         │                                                            │
│         ▼                                                            │
│  Frontend uploads to Supabase Storage                                │
│  (chat-uploads/{user_id}/{thread_id}/{filename})                    │
│         │                                                            │
│         ▼                                                            │
│  Message created with:                                               │
│  - Image content block (for vision) OR text preview                 │
│  - Hidden XML with storage path + sandbox path                      │
│         │                                                            │
│         ▼                                                            │
│  LangGraph receives message                                          │
│         │                                                            │
│         ▼                                                            │
│  file_attachment_processing.py:                                      │
│  - Parses XML                                                        │
│  - Downloads from Supabase Storage                                   │
│  - Writes binary to /sandbox/user_uploads/                          │
│         │                                                            │
│         ▼                                                            │
│  Agent can now process files with Python libraries                   │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                       AGENT OUTPUT FLOW                              │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  Agent creates file in sandbox                                       │
│  (e.g., /sandbox/outputs/report.docx)                               │
│         │                                                            │
│         ▼                                                            │
│  Agent calls publish_file_to_user(                                   │
│      file_path="/sandbox/outputs/report.docx",                      │
│      display_name="Quarterly Report",                                │
│      description="Analysis of Q3 performance"                        │
│  )                                                                   │
│         │                                                            │
│         ▼                                                            │
│  Tool implementation:                                                │
│  1. Reads file from sandbox                                          │
│  2. Uploads to Supabase Storage                                      │
│     (deepagent-outputs/{thread_id}/{filename})                      │
│  3. Updates state.published_files                                    │
│  4. Returns success with storage_path                                │
│         │                                                            │
│         ▼                                                            │
│  Frontend renders PublishFileTool component:                         │
│  - Card with file icon, name, description                           │
│  - Download button                                                   │
│  - Click to open preview sheet                                       │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### Storage Strategy

**Why Supabase Storage for everything:**
- Consistent pattern for images, documents, and outputs
- Avoids large base64 payloads in LangGraph thread state
- Files persist beyond sandbox lifetime
- RLS-protected access (user must own thread)
- Permanent paths (no expiring signed URLs in our UI)

**Buckets:**
| Bucket | Purpose | Access |
|--------|---------|--------|
| `chat-uploads` | User uploaded files | Owner only |
| `deepagent-outputs` | Agent published files | Owner only |
| `skills` | Skill packages | Permission-based |

### State Model Changes

```python
class PublishedFile(TypedDict):
    """A file published to the user for download/preview."""
    display_name: str           # User-friendly name
    description: str            # Brief description
    filename: str               # Original filename
    file_type: str              # Extension (e.g., ".docx")
    mime_type: str              # MIME type
    file_size: int              # Size in bytes
    storage_path: str           # Supabase storage path
    sandbox_path: str           # Original sandbox path
    published_at: str           # ISO timestamp


class SkillsDeepAgentState(AgentState):
    todos: NotRequired[list[Todo]]
    published_files: Annotated[NotRequired[List[PublishedFile]], published_files_reducer]
```

The `published_files_reducer` handles updates by `display_name` - if the agent publishes a file with the same display name, it updates rather than duplicates.

---

## Detailed Implementation

### Part 1: User Upload Flow

#### 1.1 Frontend Changes (`use-file-upload.tsx`)

**Current behavior:**
- Extracts text via `/documents/extract/text`
- Creates `<UserUploadedAttachment>` XML with text content

**New behavior:**
1. Upload original binary to Supabase Storage
2. Extract text preview (existing)
3. Create new XML format with storage path

**Image upload message format:**
```typescript
[
  {
    type: "image",
    source: {
      type: "url",
      url: "storage://chat-uploads/user123/thread456/screenshot.png"
    }
  },
  {
    type: "text",
    text: `User's message here...

<UserUploadedImage hidden="true">
  <FileName>screenshot.png</FileName>
  <FileType>image/png</FileType>
  <StoragePath>chat-uploads/user123/thread456/screenshot.png</StoragePath>
  <SandboxPath>/sandbox/user_uploads/screenshot.png</SandboxPath>
</UserUploadedImage>`
  }
]
```

**Document upload message format:**
```typescript
[
  {
    type: "text",
    text: `User's message here...

<UserUploadedDocument hidden="true">
  <FileName>quarterly_report.xlsx</FileName>
  <FileType>application/vnd.openxmlformats-officedocument.spreadsheetml.sheet</FileType>
  <StoragePath>chat-uploads/user123/thread456/quarterly_report.xlsx</StoragePath>
  <SandboxPath>/sandbox/user_uploads/quarterly_report.xlsx</SandboxPath>
  <Preview>
Sheet1: Revenue | Q1 | Q2 | Q3 | Q4
Row 1: North | 125000 | 132000 | 141000 | 156000
... (first 20 rows)
  </Preview>
</UserUploadedDocument>`
  }
]
```

#### 1.2 Backend Changes (`file_attachment_processing.py`)

**Current behavior:**
- Parses `<UserUploadedAttachment>` XML
- Writes markdown content to sandbox

**New behavior:**
1. Parse both `<UserUploadedImage>` and `<UserUploadedDocument>` XML
2. Download binary from Supabase Storage using storage path
3. Write binary to sandbox at specified path

```python
def extract_file_attachments_to_sandbox(
    state: Annotated[SkillsDeepAgentState, InjectedState],
    thread_id: str,
    supabase_client: Any,  # Injected
) -> Command:
    """Extract file attachments and write to sandbox."""

    messages = state.get("messages", [])
    latest_message = messages[-1] if messages else None

    if not isinstance(latest_message, HumanMessage):
        return Command(update={})

    message_content = get_message_text(latest_message)

    # Parse image uploads
    for match in re.finditer(r'<UserUploadedImage[^>]*>(.*?)</UserUploadedImage>', message_content, re.DOTALL):
        storage_path = extract_xml_field(match.group(1), 'StoragePath')
        sandbox_path = extract_xml_field(match.group(1), 'SandboxPath')

        if storage_path and sandbox_path:
            # Download from Supabase Storage
            file_data = supabase_client.storage.from_("chat-uploads").download(storage_path)

            # Write to sandbox
            sandbox = get_sandbox(thread_id)
            sandbox.files.write(sandbox_path, file_data)

    # Parse document uploads (similar pattern)
    for match in re.finditer(r'<UserUploadedDocument[^>]*>(.*?)</UserUploadedDocument>', message_content, re.DOTALL):
        # Same download and write logic
        pass

    return Command(update={})
```

#### 1.3 Supported File Types

| Extension | MIME Type | Preview Method |
|-----------|-----------|----------------|
| `.png`, `.jpg`, `.jpeg`, `.gif`, `.webp` | image/* | Model vision |
| `.pdf` | application/pdf | Text extraction via Docling |
| `.docx` | application/vnd.openxmlformats-officedocument.wordprocessingml.document | Text extraction |
| `.xlsx`, `.xls` | application/vnd.openxmlformats-officedocument.spreadsheetml.sheet | Cell preview (first N rows) |
| `.pptx` | application/vnd.openxmlformats-officedocument.presentationml.presentation | Slide titles |
| `.csv` | text/csv | First N rows |
| `.txt`, `.md` | text/plain | First N characters |

---

### Part 2: Agent Output Flow

#### 2.1 New Tool: `publish_file_to_user`

**Location:** `langgraph/src/agent_platform/agents/deepagents/skills_deepagent/tools/publish_file.py`

```python
from langchain_core.tools import tool, InjectedToolCallId
from langgraph.types import Command
from langchain_core.messages import ToolMessage
from typing import Annotated
from datetime import datetime
import json
import os

from ..state import PublishedFile


MIME_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".csv": "text/csv",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
}


def create_publish_file_tool(thread_id: str, sandbox: Any, supabase_client: Any):
    """Create publish_file_to_user tool bound to thread context."""

    @tool
    def publish_file_to_user(
        file_path: str,
        display_name: str,
        description: str = "",
        tool_call_id: Annotated[str, InjectedToolCallId] = None
    ) -> Command:
        """
        Make a file from the sandbox available to the user for preview and download.

        This tool uploads the file from the sandbox to permanent storage and
        displays a download card in the chat. Use this when you've created a
        file that the user should be able to access.

        If you publish a file with the same display_name as a previous file,
        it will update/replace that file (useful for revisions).

        Args:
            file_path: Path to the file in sandbox (e.g., /sandbox/outputs/report.docx)
            display_name: User-friendly name shown in the UI (e.g., "Quarterly Report")
            description: Brief description of what the file contains

        Returns:
            Confirmation with file metadata

        Examples:
            # Publish a newly created report
            publish_file_to_user(
                file_path="/sandbox/outputs/analysis.docx",
                display_name="Market Analysis Report",
                description="Comprehensive analysis of Q3 market trends"
            )

            # Update a previously published file
            publish_file_to_user(
                file_path="/sandbox/outputs/budget_v2.xlsx",
                display_name="Budget Spreadsheet",  # Same name = update
                description="Updated with your requested changes"
            )
        """
        try:
            # 1. Read file from sandbox
            file_content = sandbox.files.read(file_path, format="bytes")

            # 2. Determine file metadata
            filename = os.path.basename(file_path)
            extension = os.path.splitext(filename)[1].lower()
            mime_type = MIME_TYPES.get(extension, "application/octet-stream")
            file_size = len(file_content)

            # 3. Upload to Supabase Storage (permanent path)
            storage_path = f"deepagent-outputs/{thread_id}/{filename}"

            supabase_client.storage.from_("deepagent-outputs").upload(
                storage_path,
                file_content,
                {"content-type": mime_type, "upsert": "true"}
            )

            # 4. Build published file entry
            published_file: PublishedFile = {
                "display_name": display_name,
                "description": description,
                "filename": filename,
                "file_type": extension,
                "mime_type": mime_type,
                "file_size": file_size,
                "storage_path": storage_path,
                "sandbox_path": file_path,
                "published_at": datetime.utcnow().isoformat()
            }

            # 5. Return Command that updates state AND sends tool message
            return Command(
                update={
                    "published_files": [published_file],  # Reducer handles merge
                    "messages": [
                        ToolMessage(
                            content=json.dumps({
                                "success": True,
                                "display_name": display_name,
                                "description": description,
                                "filename": filename,
                                "file_type": extension,
                                "file_size": file_size,
                                "storage_path": storage_path
                            }),
                            tool_call_id=tool_call_id
                        )
                    ]
                }
            )

        except Exception as e:
            return Command(
                update={
                    "messages": [
                        ToolMessage(
                            content=json.dumps({
                                "success": False,
                                "error": str(e)
                            }),
                            tool_call_id=tool_call_id
                        )
                    ]
                }
            )

    return publish_file_to_user
```

#### 2.2 Storage Bucket Setup

**Migration:** `database/migrations/langconnect/xxx_create_deepagent_outputs_bucket.sql`

```sql
-- Create deepagent-outputs bucket for agent published files
INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES (
    'deepagent-outputs',
    'deepagent-outputs',
    false,  -- Private, require authentication
    104857600,  -- 100MB limit
    ARRAY[
        'application/pdf',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'application/vnd.openxmlformats-officedocument.presentationml.presentation',
        'text/plain',
        'text/markdown',
        'text/csv',
        'image/png',
        'image/jpeg',
        'image/gif',
        'image/webp',
        'application/octet-stream'
    ]
);

-- RLS Policy: Users can read files from threads they own
-- Path format: deepagent-outputs/{thread_id}/{filename}
CREATE POLICY "Users can read own thread outputs"
ON storage.objects FOR SELECT
USING (
    bucket_id = 'deepagent-outputs' AND
    EXISTS (
        SELECT 1 FROM langconnect.threads t
        WHERE t.thread_id = (string_to_array(name, '/'))[2]
        AND t.user_id = auth.uid()::text
    )
);

-- RLS Policy: Service role can write (used by LangGraph agent)
CREATE POLICY "Service role can write outputs"
ON storage.objects FOR INSERT
WITH CHECK (
    bucket_id = 'deepagent-outputs' AND
    auth.role() = 'service_role'
);

CREATE POLICY "Service role can update outputs"
ON storage.objects FOR UPDATE
USING (
    bucket_id = 'deepagent-outputs' AND
    auth.role() = 'service_role'
);
```

#### 2.3 LangConnect Endpoint

**File:** `apps/langconnect/langconnect/api/storage.py`

```python
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
import io

router = APIRouter()


@router.get("/storage/thread-file")
async def get_thread_file(
    storage_path: str = Query(..., description="Storage path (deepagent-outputs/{thread_id}/{filename})"),
    user: AuthUser = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client)
) -> StreamingResponse:
    """
    Download a file from thread outputs.

    Validates user owns the thread before allowing access.
    Uses permanent storage path (not signed URL) to ensure links don't expire.
    """
    # Validate path format
    parts = storage_path.split("/")
    if len(parts) < 3 or parts[0] != "deepagent-outputs":
        raise HTTPException(400, "Invalid storage path format")

    thread_id = parts[1]
    filename = parts[-1]

    # Verify user owns this thread
    thread = await threads_db.get_thread_by_id(thread_id)
    if not thread or thread.user_id != user.id:
        raise HTTPException(403, "Access denied - you don't own this thread")

    try:
        # Download file from storage
        file_data = supabase.storage.from_("deepagent-outputs").download(storage_path)

        # Determine MIME type
        mime_type = get_mime_type_from_filename(filename)

        return StreamingResponse(
            io.BytesIO(file_data),
            media_type=mime_type,
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Cache-Control": "private, max-age=3600"  # Cache for 1 hour
            }
        )
    except Exception as e:
        raise HTTPException(404, f"File not found: {str(e)}")


def get_mime_type_from_filename(filename: str) -> str:
    """Get MIME type from filename extension."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    mime_types = {
        "pdf": "application/pdf",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "csv": "text/csv",
        "txt": "text/plain",
        "md": "text/markdown",
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "gif": "image/gif",
    }
    return mime_types.get(ext, "application/octet-stream")
```

---

### Part 3: Frontend Implementation

#### 3.1 Tool UI Component

**File:** `apps/web/src/features/chat/components/thread/messages/tools/registry/components/PublishFileTool.tsx`

```typescript
import React, { useCallback, useState } from "react";
import { ToolComponentProps } from "../../types";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Download, CheckCircle, Loader2, AlertCircle, FileText } from "lucide-react";
import { MinimalistBadge } from "@/components/ui/minimalist-badge";
import { FilePreviewSheet } from "@/features/chat/components/file-preview-sheet";

// File type icons mapping
const FILE_ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
  ".pdf": FileText,  // Could use specific PDF icon
  ".docx": FileText, // Could use Word icon
  ".xlsx": FileText, // Could use Excel icon
  ".pptx": FileText, // Could use PowerPoint icon
  // Add more as needed
};

interface PublishFileResult {
  success: boolean;
  display_name: string;
  description?: string;
  filename: string;
  file_type: string;
  file_size: number;
  storage_path: string;
  error?: string;
}

export function PublishFileTool({
  toolCall,
  toolResult,
  state,
  streaming
}: ToolComponentProps) {
  const [isDownloading, setIsDownloading] = useState(false);
  const [previewOpen, setPreviewOpen] = useState(false);

  // Parse tool result
  let resultData: PublishFileResult | null = null;
  let errorMessage: string | null = null;

  if (toolResult?.content) {
    try {
      const rawContent = toolResult.content;
      const content = Array.isArray(rawContent) ? rawContent[0] : rawContent;

      if (typeof content === "string") {
        const parsed = JSON.parse(content);
        if (parsed.success) {
          resultData = parsed;
        } else {
          errorMessage = parsed.error || "Failed to publish file";
        }
      } else if (typeof content === "object") {
        if ((content as PublishFileResult).success) {
          resultData = content as PublishFileResult;
        } else {
          errorMessage = (content as PublishFileResult).error || "Failed to publish file";
        }
      }
    } catch {
      errorMessage = "Failed to parse tool result";
    }
  }

  // Download handler - uses LangConnect endpoint
  const handleDownload = useCallback(async (e: React.MouseEvent) => {
    e.stopPropagation(); // Prevent card click
    if (!resultData?.storage_path) return;

    setIsDownloading(true);
    try {
      const response = await fetch(
        `/api/langconnect/storage/thread-file?storage_path=${encodeURIComponent(resultData.storage_path)}`
      );

      if (!response.ok) {
        throw new Error(`Download failed: ${response.statusText}`);
      }

      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = resultData.filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (error) {
      console.error("Download error:", error);
      alert("Failed to download file. Please try again.");
    } finally {
      setIsDownloading(false);
    }
  }, [resultData]);

  // Card click handler - opens preview
  const handleCardClick = useCallback(() => {
    if (resultData) {
      setPreviewOpen(true);
    }
  }, [resultData]);

  // Get appropriate file icon
  const FileIcon = resultData
    ? (FILE_ICONS[resultData.file_type] || FileText)
    : FileText;

  // Loading state
  if (state === "loading" || streaming) {
    return (
      <Card className="w-full max-w-md p-4">
        <div className="flex items-center gap-3">
          <MinimalistBadge
            icon={Loader2}
            tooltip="Publishing file"
            className="animate-spin"
          />
          <div>
            <h3 className="font-medium text-foreground">Publishing File...</h3>
            <p className="text-sm text-muted-foreground">
              Preparing file for download
            </p>
          </div>
        </div>
      </Card>
    );
  }

  // Error state
  if (state === "error" || errorMessage) {
    return (
      <Card className="w-full max-w-md p-4">
        <div className="flex items-center gap-3">
          <MinimalistBadge icon={AlertCircle} tooltip="Error" />
          <div>
            <h3 className="font-medium text-foreground">Error Publishing File</h3>
            <p className="text-sm text-destructive">
              {errorMessage || "An error occurred"}
            </p>
          </div>
        </div>
      </Card>
    );
  }

  // Success state - clickable card with download button
  if (resultData) {
    return (
      <>
        <Card
          className="w-full max-w-md p-4 cursor-pointer hover:bg-accent/50 transition-colors"
          onClick={handleCardClick}
        >
          <div className="flex items-center gap-3">
            {/* File icon */}
            <div className="flex-shrink-0 p-3 bg-muted rounded-lg">
              <FileIcon className="h-8 w-8 text-muted-foreground" />
            </div>

            {/* File info */}
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <MinimalistBadge icon={CheckCircle} tooltip="File ready" />
                <h3 className="font-medium text-foreground truncate">
                  {resultData.display_name}
                </h3>
              </div>
              <p className="text-sm text-muted-foreground">
                {resultData.file_type.toUpperCase().replace(".", "")} · {formatFileSize(resultData.file_size)}
              </p>
              {resultData.description && (
                <p className="text-sm text-muted-foreground truncate mt-1">
                  {resultData.description}
                </p>
              )}
            </div>

            {/* Download button */}
            <Button
              onClick={handleDownload}
              variant="outline"
              size="sm"
              disabled={isDownloading}
              className="flex-shrink-0"
            >
              <Download className="h-4 w-4 mr-2" />
              {isDownloading ? "..." : "Download"}
            </Button>
          </div>
        </Card>

        {/* Preview sheet */}
        <FilePreviewSheet
          open={previewOpen}
          onClose={() => setPreviewOpen(false)}
          file={{
            displayName: resultData.display_name,
            filename: resultData.filename,
            fileType: resultData.file_type,
            storagePath: resultData.storage_path,
            fileSize: resultData.file_size,
            description: resultData.description,
          }}
        />
      </>
    );
  }

  return null;
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
```

#### 3.2 Register Tool Component

**File:** `apps/web/src/features/chat/components/thread/messages/tools/registry/index.ts`

```typescript
import { PublishFileTool } from "./components/PublishFileTool";

export const TOOL_REGISTRY: ToolRegistry = {
  // ... existing entries ...

  // Publish file tool for skills_deepagent
  "*:publish_file_to_user": {
    component: PublishFileTool,
  },
};
```

#### 3.3 File Preview Sheet

**File:** `apps/web/src/features/chat/components/file-preview-sheet.tsx`

```typescript
import React, { useEffect, useState } from "react";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { Download, Loader2 } from "lucide-react";

interface FilePreviewSheetProps {
  open: boolean;
  onClose: () => void;
  file: {
    displayName: string;
    filename: string;
    fileType: string;
    storagePath: string;
    fileSize: number;
    description?: string;
  };
}

export function FilePreviewSheet({ open, onClose, file }: FilePreviewSheetProps) {
  const [content, setContent] = useState<Blob | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Fetch file content when opened
  useEffect(() => {
    if (open && !content) {
      setLoading(true);
      setError(null);

      fetch(`/api/langconnect/storage/thread-file?storage_path=${encodeURIComponent(file.storagePath)}`)
        .then(res => {
          if (!res.ok) throw new Error("Failed to fetch file");
          return res.blob();
        })
        .then(setContent)
        .catch(err => setError(err.message))
        .finally(() => setLoading(false));
    }
  }, [open, file.storagePath, content]);

  // Reset content when file changes
  useEffect(() => {
    setContent(null);
  }, [file.storagePath]);

  const handleDownload = async () => {
    if (!content) return;

    const url = URL.createObjectURL(content);
    const a = document.createElement("a");
    a.href = url;
    a.download = file.filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  return (
    <Sheet open={open} onOpenChange={(isOpen) => !isOpen && onClose()}>
      <SheetContent side="right" className="w-[600px] sm:w-[800px] sm:max-w-none">
        <SheetHeader className="flex flex-row items-center justify-between pb-4 border-b">
          <div className="flex-1">
            <SheetTitle>{file.displayName}</SheetTitle>
            <SheetDescription>
              {file.filename} · {formatFileSize(file.fileSize)}
              {file.description && ` · ${file.description}`}
            </SheetDescription>
          </div>
          <Button variant="outline" size="sm" onClick={handleDownload} disabled={!content}>
            <Download className="h-4 w-4 mr-2" />
            Download
          </Button>
        </SheetHeader>

        <div className="mt-4 h-[calc(100vh-140px)] overflow-auto">
          {loading && (
            <div className="flex items-center justify-center h-full">
              <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            </div>
          )}

          {error && (
            <div className="flex items-center justify-center h-full">
              <p className="text-destructive">{error}</p>
            </div>
          )}

          {!loading && !error && content && (
            <FilePreviewContent
              fileType={file.fileType}
              content={content}
              filename={file.filename}
            />
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}

interface FilePreviewContentProps {
  fileType: string;
  content: Blob;
  filename: string;
}

function FilePreviewContent({ fileType, content, filename }: FilePreviewContentProps) {
  const [textContent, setTextContent] = useState<string | null>(null);
  const [objectUrl, setObjectUrl] = useState<string | null>(null);

  useEffect(() => {
    // Create object URL for binary content
    const url = URL.createObjectURL(content);
    setObjectUrl(url);

    // For text-based files, also read as text
    if ([".txt", ".md", ".csv", ".json"].includes(fileType)) {
      content.text().then(setTextContent);
    }

    return () => {
      URL.revokeObjectURL(url);
    };
  }, [content, fileType]);

  // Image preview
  if ([".png", ".jpg", ".jpeg", ".gif", ".webp"].includes(fileType)) {
    return (
      <div className="flex items-center justify-center h-full">
        <img
          src={objectUrl || ""}
          alt={filename}
          className="max-w-full max-h-full object-contain"
        />
      </div>
    );
  }

  // PDF preview
  if (fileType === ".pdf" && objectUrl) {
    return (
      <iframe
        src={objectUrl}
        className="w-full h-full border-0"
        title={filename}
      />
    );
  }

  // Text/Markdown/CSV preview
  if ([".txt", ".md", ".csv", ".json"].includes(fileType) && textContent) {
    return (
      <pre className="p-4 bg-muted rounded-lg overflow-auto text-sm font-mono whitespace-pre-wrap">
        {textContent}
      </pre>
    );
  }

  // Fallback for unsupported types (DOCX, XLSX, PPTX)
  return (
    <div className="flex flex-col items-center justify-center h-full gap-4 text-center">
      <p className="text-muted-foreground">
        Preview not available for {fileType.toUpperCase().replace(".", "")} files.
      </p>
      <p className="text-sm text-muted-foreground">
        Click the Download button to view this file.
      </p>
    </div>
  );
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
```

---

## File Changes Summary

### Backend - LangGraph

| File | Action | Description |
|------|--------|-------------|
| `skills_deepagent/state.py` | **MODIFY** | Add `PublishedFile` type, `published_files` field, and reducer |
| `skills_deepagent/tools/__init__.py` | **CREATE** | Tools module init |
| `skills_deepagent/tools/publish_file.py` | **CREATE** | `publish_file_to_user` tool implementation |
| `skills_deepagent/file_attachment_processing.py` | **MODIFY** | Handle new XML formats, download from storage |
| `skills_deepagent/graph.py` | **MODIFY** | Add `publish_file_to_user` tool to agent |

### Backend - LangConnect

| File | Action | Description |
|------|--------|-------------|
| `api/storage.py` | **MODIFY** | Add `/storage/thread-file` endpoint |
| `database/migrations/xxx_deepagent_outputs_bucket.sql` | **CREATE** | Storage bucket and RLS policies |

### Frontend - Web

| File | Action | Description |
|------|--------|-------------|
| `hooks/use-file-upload.tsx` | **MODIFY** | Upload binary to storage, create XML blocks |
| `tools/registry/components/PublishFileTool.tsx` | **CREATE** | Tool UI component |
| `tools/registry/components/index.ts` | **MODIFY** | Export PublishFileTool |
| `tools/registry/index.ts` | **MODIFY** | Register publish_file_to_user |
| `components/file-preview-sheet.tsx` | **CREATE** | Side panel preview component |

### Frontend - API Routes

| File | Action | Description |
|------|--------|-------------|
| `app/api/langconnect/storage/thread-file/route.ts` | **CREATE** | Proxy to LangConnect storage endpoint |

---

## Implementation Order

### Sprint 1: Upload Infrastructure (Backend Focus)

**Goal:** Enable binary file uploads to sandbox

1. **Modify `use-file-upload.tsx`**
   - Add binary upload to Supabase Storage for all file types
   - Generate new XML format (`<UserUploadedImage>`, `<UserUploadedDocument>`)
   - Keep existing text preview extraction

2. **Modify `file_attachment_processing.py`**
   - Parse new XML formats
   - Download binaries from Supabase Storage
   - Write to sandbox filesystem

3. **Test:** Upload Excel file → Verify binary appears in `/sandbox/user_uploads/`

### Sprint 2: Publish Tool (Backend Focus)

**Goal:** Enable agent to publish files

1. **Modify `state.py`**
   - Add `PublishedFile` TypedDict
   - Add `published_files` field with reducer
   - Implement `published_files_reducer`

2. **Create `tools/publish_file.py`**
   - Implement `create_publish_file_tool` factory
   - Handle file reading, storage upload, state update

3. **Create storage bucket**
   - Run migration for `deepagent-outputs` bucket
   - Set up RLS policies

4. **Add LangConnect endpoint**
   - Implement `/storage/thread-file`
   - Validate thread ownership

5. **Modify `graph.py`**
   - Create and add publish tool to agent

6. **Test:** Agent creates file → Calls publish → File in storage, state updated

### Sprint 3: Tool UI Component (Frontend Focus)

**Goal:** Display published files in chat

1. **Create `PublishFileTool.tsx`**
   - Loading, error, success states
   - Download button with storage path fetch
   - Click card to open preview

2. **Register in tool registry**
   - Add `"*:publish_file_to_user"` entry

3. **Create `file-preview-sheet.tsx`**
   - Side panel component
   - Preview content by file type
   - Download button

4. **Create API proxy route**
   - `app/api/langconnect/storage/thread-file/route.ts`

5. **Test:** Published file → Card appears → Download works → Preview opens

### Sprint 4: Polish & Edge Cases

1. **Handle file revisions** (same display_name updates)
2. **Add file type icons**
3. **Improve preview for more types**
4. **Error handling and loading states**
5. **Optional: Published files list sidebar**

---

## Testing Checklist

### User Upload Flow

- [ ] Image upload stores binary in Supabase Storage
- [ ] Image appears in `/sandbox/user_uploads/` as binary
- [ ] Image content block works for model vision
- [ ] `<UserUploadedImage>` XML not visible in chat UI
- [ ] Document upload stores binary in Supabase Storage
- [ ] Document appears in `/sandbox/user_uploads/` as binary
- [ ] Document preview text visible to agent
- [ ] `<UserUploadedDocument>` XML not visible in chat UI
- [ ] Agent can read Excel with pandas/openpyxl
- [ ] Agent can process PDF with pypdf/pdfplumber
- [ ] Agent can modify Word doc with python-docx

### Agent Output Flow

- [ ] `publish_file_to_user` tool available to agent
- [ ] Tool reads file from sandbox correctly
- [ ] Tool uploads to `deepagent-outputs` bucket
- [ ] Tool returns correct metadata
- [ ] `published_files` state updated
- [ ] Duplicate display_name updates rather than duplicates
- [ ] Tool error handled gracefully

### Frontend UI

- [ ] PublishFileTool component renders on tool call
- [ ] Loading state shows during publish
- [ ] Error state shows on failure
- [ ] Success state shows file card
- [ ] Download button fetches from storage endpoint
- [ ] Card click opens preview sheet
- [ ] Preview works for images
- [ ] Preview works for PDF
- [ ] Preview works for text/markdown
- [ ] "Download to view" fallback for DOCX/XLSX/PPTX
- [ ] File size formatted correctly

### Security

- [ ] Storage RLS prevents access to other users' files
- [ ] LangConnect endpoint validates thread ownership
- [ ] Storage paths don't allow path traversal

---

## Appendix: XML Format Reference

### UserUploadedImage

```xml
<UserUploadedImage hidden="true">
  <FileName>screenshot.png</FileName>
  <FileType>image/png</FileType>
  <StoragePath>chat-uploads/user123/thread456/abc_screenshot.png</StoragePath>
  <SandboxPath>/sandbox/user_uploads/screenshot.png</SandboxPath>
</UserUploadedImage>
```

### UserUploadedDocument

```xml
<UserUploadedDocument hidden="true">
  <FileName>quarterly_report.xlsx</FileName>
  <FileType>application/vnd.openxmlformats-officedocument.spreadsheetml.sheet</FileType>
  <StoragePath>chat-uploads/user123/thread456/def_quarterly_report.xlsx</StoragePath>
  <SandboxPath>/sandbox/user_uploads/quarterly_report.xlsx</SandboxPath>
  <Preview>
Sheet1: Revenue | Q1 | Q2 | Q3 | Q4
Row 1: North | 125000 | 132000 | 141000 | 156000
Row 2: South | 98000 | 103000 | 115000 | 122000
... (first 20 rows)
  </Preview>
</UserUploadedDocument>
```

### PublishedFile (Tool Result)

```json
{
  "success": true,
  "display_name": "Quarterly Report",
  "description": "Analysis of Q3 performance",
  "filename": "report.docx",
  "file_type": ".docx",
  "file_size": 45678,
  "storage_path": "deepagent-outputs/thread123/report.docx"
}
```
