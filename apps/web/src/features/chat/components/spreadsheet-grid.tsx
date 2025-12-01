"use client";

import React, { useMemo } from "react";
import { cn } from "@/lib/utils";
import { type SpreadsheetData, type MergeCell, getColumnLetter } from "../types/spreadsheet";

interface SpreadsheetGridProps {
  data: SpreadsheetData;
  maxHeight?: string;
}

// Build lookup structures for merged cells
function buildMergeLookups(merges: MergeCell[]) {
  // Map of "row,col" -> merge info for the start cell
  const mergeStarts = new Map<string, { rowSpan: number; colSpan: number }>();
  // Set of "row,col" for cells that are covered (not the start cell)
  const coveredCells = new Set<string>();

  for (const merge of merges) {
    const key = `${merge.startRow},${merge.startCol}`;
    mergeStarts.set(key, { rowSpan: merge.rowSpan, colSpan: merge.colSpan });

    // Mark all cells in the merge range (except start) as covered
    for (let r = merge.startRow; r < merge.startRow + merge.rowSpan; r++) {
      for (let c = merge.startCol; c < merge.startCol + merge.colSpan; c++) {
        if (r !== merge.startRow || c !== merge.startCol) {
          coveredCells.add(`${r},${c}`);
        }
      }
    }
  }

  return { mergeStarts, coveredCells };
}

export function SpreadsheetGrid({ data, maxHeight = "calc(100vh - 280px)" }: SpreadsheetGridProps) {
  const { cells, merges, colCount, rowCount } = data;

  const { mergeStarts, coveredCells } = useMemo(
    () => buildMergeLookups(merges),
    [merges]
  );

  // Generate column indices array
  const columns = useMemo(
    () => Array.from({ length: colCount }, (_, i) => i),
    [colCount]
  );

  // Generate row indices array
  const rows = useMemo(
    () => Array.from({ length: rowCount }, (_, i) => i),
    [rowCount]
  );

  if (rowCount === 0 || colCount === 0) {
    return (
      <div className="flex items-center justify-center h-32 text-muted-foreground text-sm">
        No data to display
      </div>
    );
  }

  return (
    <div
      className="overflow-auto border border-border rounded-md"
      style={{ maxHeight }}
    >
      <table className="w-full border-collapse text-sm">
        {/* Column headers (A, B, C...) */}
        <thead className="sticky top-0 z-20">
          <tr>
            {/* Corner cell (row number header) */}
            <th className="sticky left-0 z-30 bg-muted border border-border p-1.5 text-center font-medium text-muted-foreground w-12 min-w-[48px]">
              {/* Empty corner */}
            </th>
            {columns.map((colIndex) => (
              <th
                key={colIndex}
                className="bg-muted border border-border p-1.5 text-center font-medium text-muted-foreground min-w-[80px]"
              >
                {getColumnLetter(colIndex)}
              </th>
            ))}
          </tr>
        </thead>

        <tbody>
          {rows.map((rowIndex) => (
            <tr key={rowIndex}>
              {/* Row number */}
              <td className="sticky left-0 z-10 bg-muted border border-border p-1.5 text-center text-xs text-muted-foreground font-mono w-12 min-w-[48px]">
                {rowIndex + 1}
              </td>
              {columns.map((colIndex) => {
                const key = `${rowIndex},${colIndex}`;

                // Skip cells that are covered by a merge
                if (coveredCells.has(key)) {
                  return null;
                }

                // Get cell value
                const cellValue = cells[rowIndex]?.[colIndex];
                const displayValue = cellValue != null ? String(cellValue) : "";

                // Check if this is a merge start cell
                const mergeInfo = mergeStarts.get(key);

                return (
                  <td
                    key={colIndex}
                    rowSpan={mergeInfo?.rowSpan}
                    colSpan={mergeInfo?.colSpan}
                    className={cn(
                      "bg-background border border-border p-1.5 text-foreground min-w-[80px] max-w-[300px] truncate",
                      mergeInfo && "align-top"
                    )}
                    title={displayValue.length > 40 ? displayValue : undefined}
                  >
                    {displayValue}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
