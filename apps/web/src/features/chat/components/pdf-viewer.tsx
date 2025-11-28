"use client";

import React, { useState, useEffect, useRef } from "react";
import { Loader2, AlertCircle } from "lucide-react";

// Types for PDF.js
interface PDFDocumentProxy {
  numPages: number;
  getPage: (pageNum: number) => Promise<PDFPageProxy>;
}

interface PDFPageProxy {
  getViewport: (options: { scale: number }) => { width: number; height: number };
  render: (options: { canvasContext: CanvasRenderingContext2D; viewport: { width: number; height: number } }) => { promise: Promise<void> };
}

interface PDFJSLib {
  getDocument: (options: { data: ArrayBuffer }) => { promise: Promise<PDFDocumentProxy> };
  GlobalWorkerOptions: { workerSrc: string };
}

declare global {
  interface Window {
    pdfjsLib?: PDFJSLib;
  }
}

interface PdfViewerProps {
  data: ArrayBuffer;
  numPages: number | null;
  onLoadSuccess: (numPages: number) => void;
}

export function PdfViewer({ data, numPages, onLoadSuccess }: PdfViewerProps) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pages, setPages] = useState<string[]>([]);
  const [totalPages, setTotalPages] = useState<number>(0);
  const containerRef = useRef<HTMLDivElement>(null);

  // Store callback in ref to avoid dependency issues
  const onLoadSuccessRef = useRef(onLoadSuccess);
  useEffect(() => {
    onLoadSuccessRef.current = onLoadSuccess;
  }, [onLoadSuccess]);

  // Track data identity to prevent re-processing the same PDF
  const dataIdRef = useRef<string | null>(null);

  // Load PDF.js from CDN and render PDF
  useEffect(() => {
    if (!data || data.byteLength === 0) return;

    // Generate stable ID from ArrayBuffer properties to detect same PDF
    const dataId = `${data.byteLength}-${new Uint8Array(data.slice(0, 16)).join(",")}`;

    // Prevent re-processing if same PDF was already successfully loaded
    // dataIdRef is only set after successful load, so this check is safe
    if (dataIdRef.current === dataId) {
      console.log("[PDF Viewer] Same PDF already loaded, skipping");
      return;
    }

    // Copy the ArrayBuffer to prevent detachment issues
    const dataCopy = data.slice(0);
    console.log("[PDF Viewer] Copied ArrayBuffer, size:", dataCopy.byteLength);

    let cancelled = false;

    const loadAndRenderPdf = async () => {
      try {
        // Load PDF.js from CDN if not already loaded
        if (!window.pdfjsLib) {
          console.log("[PDF Viewer] Loading PDF.js from CDN...");

          // Load the legacy build (non-module) which attaches to window.pdfjsLib
          await new Promise<void>((resolve, reject) => {
            const script = document.createElement("script");
            script.src = "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js";
            script.onload = () => {
              console.log("[PDF Viewer] PDF.js script loaded");
              resolve();
            };
            script.onerror = () => reject(new Error("Failed to load PDF.js"));
            document.head.appendChild(script);
          });

        }

        console.log("[PDF Viewer] After script load, cancelled:", cancelled);
        if (cancelled) return;

        // Debug: Check what's on window after script load
        console.log("[PDF Viewer] window.pdfjsLib:", window.pdfjsLib);
        console.log("[PDF Viewer] window keys with pdf:", Object.keys(window).filter(k => k.toLowerCase().includes('pdf')));

        const pdfjsLib = window.pdfjsLib;

        // Set worker after confirming pdfjsLib exists
        if (pdfjsLib) {
          pdfjsLib.GlobalWorkerOptions.workerSrc =
            "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js";
        }
        if (!pdfjsLib) {
          throw new Error("PDF.js not loaded");
        }

        console.log("[PDF Viewer] Loading PDF document...");
        const loadingTask = pdfjsLib.getDocument({ data: dataCopy });
        const pdf = await loadingTask.promise;

        if (cancelled) return;

        console.log("[PDF Viewer] PDF loaded, pages:", pdf.numPages);
        setTotalPages(pdf.numPages);
        // Use ref to call callback without dependency
        onLoadSuccessRef.current?.(pdf.numPages);

        // Render each page to canvas and convert to image
        const pageImages: string[] = [];
        const scale = 1.5; // Render at 1.5x for better quality

        for (let i = 1; i <= pdf.numPages; i++) {
          if (cancelled) return;

          const page = await pdf.getPage(i);
          const viewport = page.getViewport({ scale });

          const canvas = document.createElement("canvas");
          const context = canvas.getContext("2d");
          if (!context) continue;

          canvas.width = viewport.width;
          canvas.height = viewport.height;

          await page.render({
            canvasContext: context,
            viewport,
          }).promise;

          pageImages.push(canvas.toDataURL("image/png"));
          console.log(`[PDF Viewer] Rendered page ${i}/${pdf.numPages}`);
        }

        if (cancelled) return;

        // Mark this PDF as successfully loaded
        dataIdRef.current = dataId;
        setPages(pageImages);
        setLoading(false);
      } catch (err) {
        console.error("[PDF Viewer] Error:", err);
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load PDF");
          setLoading(false);
        }
      }
    };

    loadAndRenderPdf();

    return () => {
      cancelled = true;
    };
    // Only data as dependency - onLoadSuccess is stored in ref
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data]);

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center h-full py-8">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        <p className="text-sm text-muted-foreground mt-2">Loading PDF...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-full py-8 text-destructive">
        <AlertCircle className="h-8 w-8 mb-2" />
        <p className="text-sm">{error}</p>
      </div>
    );
  }

  return (
    <div ref={containerRef} className="h-full overflow-auto bg-[#f3f4f6]">
      <div className="flex flex-col items-center p-6">
        {pages.map((pageDataUrl, index) => (
          <div
            key={index}
            className="relative mb-4 bg-white border border-gray-200 shadow-sm"
            style={{ maxWidth: "800px", width: "100%" }}
          >
            <img
              src={pageDataUrl}
              alt={`Page ${index + 1}`}
              className="w-full h-auto"
            />
            {/* Page number overlay */}
            <div className="absolute bottom-3 left-1/2 -translate-x-1/2 text-xs text-gray-500 bg-white/90 px-3 py-1 rounded-full">
              Page {index + 1} of {totalPages}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
