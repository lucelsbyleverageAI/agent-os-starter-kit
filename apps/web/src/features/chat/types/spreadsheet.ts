// Types for spreadsheet grid preview (Excel, CSV)

export interface SpreadsheetSheet {
  name: string;
  data: SpreadsheetData;
}

export interface SpreadsheetData {
  cells: (string | number | null)[][];
  merges: MergeCell[];
  colCount: number;
  rowCount: number;
}

export interface MergeCell {
  startRow: number;
  startCol: number;
  rowSpan: number;
  colSpan: number;
}

// Helper to convert column index to Excel-style letter (0 -> A, 25 -> Z, 26 -> AA)
export function getColumnLetter(index: number): string {
  let letter = "";
  let i = index;
  while (i >= 0) {
    letter = String.fromCharCode((i % 26) + 65) + letter;
    i = Math.floor(i / 26) - 1;
  }
  return letter;
}
