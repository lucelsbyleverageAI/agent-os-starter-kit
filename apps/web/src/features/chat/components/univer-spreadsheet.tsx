"use client";

import React, { useEffect, useRef, useCallback, useState } from "react";
import { Loader2 } from "lucide-react";

// Univer core imports
import { Univer, LocaleType, UniverInstanceType, IWorkbookData } from "@univerjs/core";
import { defaultTheme } from "@univerjs/design";
import { UniverRenderEnginePlugin } from "@univerjs/engine-render";
import { UniverUIPlugin } from "@univerjs/ui";
import { UniverDocsPlugin } from "@univerjs/docs";
import { UniverDocsUIPlugin } from "@univerjs/docs-ui";
import { UniverSheetsPlugin } from "@univerjs/sheets";
import { UniverSheetsUIPlugin } from "@univerjs/sheets-ui";
import { UniverSheetsFormulaPlugin } from "@univerjs/sheets-formula";
import { UniverSheetsFormulaUIPlugin } from "@univerjs/sheets-formula-ui";

// Univer locale data
import DesignEnUS from "@univerjs/design/locale/en-US";
import UIEnUS from "@univerjs/ui/locale/en-US";
import DocsUIEnUS from "@univerjs/docs-ui/locale/en-US";
import SheetsEnUS from "@univerjs/sheets/locale/en-US";
import SheetsUIEnUS from "@univerjs/sheets-ui/locale/en-US";
import SheetsFormulaUIEnUS from "@univerjs/sheets-formula-ui/locale/en-US";

// Univer CSS imports
import "@univerjs/design/lib/index.css";
import "@univerjs/ui/lib/index.css";
import "@univerjs/docs-ui/lib/index.css";
import "@univerjs/sheets-ui/lib/index.css";
import "@univerjs/sheets-formula-ui/lib/index.css";

// Converter utility
import { convertXlsxToUniverData } from "../utils/xlsx-to-univer";

interface UniverSpreadsheetProps {
  /** Raw Excel file data as ArrayBuffer */
  data: ArrayBuffer;
  /** Optional height override */
  height?: string;
}

export function UniverSpreadsheet({ data, height = "100%" }: UniverSpreadsheetProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const univerRef = useRef<Univer | null>(null);
  const initializingRef = useRef(false);
  const [workbookData, setWorkbookData] = useState<IWorkbookData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Convert XLSX data to Univer format (async)
  useEffect(() => {
    if (!data) {
      setIsLoading(false);
      return;
    }

    let cancelled = false;

    const convert = async () => {
      try {
        setIsLoading(true);
        setError(null);
        const result = await convertXlsxToUniverData(data);
        if (!cancelled) {
          setWorkbookData(result);
        }
      } catch (err) {
        console.error("[UniverSpreadsheet] Error converting XLSX:", err);
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to parse Excel file");
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
      }
    };

    convert();

    return () => {
      cancelled = true;
    };
  }, [data]);

  // Initialize Univer
  const initUniver = useCallback(() => {
    if (!containerRef.current || !workbookData || initializingRef.current) return;
    if (univerRef.current) return; // Already initialized

    initializingRef.current = true;

    try {
      // Create Univer instance with locale data
      const univer = new Univer({
        theme: defaultTheme,
        locale: LocaleType.EN_US,
        locales: {
          [LocaleType.EN_US]: {
            ...DesignEnUS,
            ...UIEnUS,
            ...DocsUIEnUS,
            ...SheetsEnUS,
            ...SheetsUIEnUS,
            ...SheetsFormulaUIEnUS,
          },
        },
      });

      // Register core plugins
      univer.registerPlugin(UniverRenderEnginePlugin);
      univer.registerPlugin(UniverUIPlugin, {
        container: containerRef.current,
        header: true,     // Keep header for formula bar
        toolbar: false,   // Hide the toolbar with formatting options
        contextMenu: false, // Hide right-click context menu (read-only)
      });

      // Register docs plugins (required by sheets-ui for cell editor)
      univer.registerPlugin(UniverDocsPlugin);
      univer.registerPlugin(UniverDocsUIPlugin);

      // Register sheets plugins
      univer.registerPlugin(UniverSheetsPlugin);
      univer.registerPlugin(UniverSheetsUIPlugin);
      univer.registerPlugin(UniverSheetsFormulaPlugin);
      univer.registerPlugin(UniverSheetsFormulaUIPlugin);

      // Create workbook from converted data in read-only mode
      const unitData = {
        ...workbookData,
        // Disable editing at the workbook level
        editable: false,
      };
      univer.createUnit(UniverInstanceType.UNIVER_SHEET, unitData);

      univerRef.current = univer;
    } catch (err) {
      console.error("[UniverSpreadsheet] Error initializing Univer:", err);
    } finally {
      initializingRef.current = false;
    }
  }, [workbookData]);

  // Initialize on mount, dispose on unmount
  useEffect(() => {
    // Small delay to ensure DOM is ready
    const timer = setTimeout(() => {
      initUniver();
    }, 100);

    return () => {
      clearTimeout(timer);
      if (univerRef.current) {
        try {
          univerRef.current.dispose();
        } catch {
          // Ignore disposal errors
        }
        univerRef.current = null;
      }
    };
  }, [initUniver]);

  // Show loading while converting
  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  // Show error
  if (error) {
    return (
      <div className="flex items-center justify-center h-full text-destructive">
        <p>{error}</p>
      </div>
    );
  }

  // Show loading if no data yet
  if (!workbookData) {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className="univer-container"
      style={{
        width: "100%",
        height,
        minHeight: "400px",
      }}
    />
  );
}
