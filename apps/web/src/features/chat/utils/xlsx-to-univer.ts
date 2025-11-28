/**
 * Utility to convert ExcelJS workbook data to Univer's IWorkbookData format
 * Using ExcelJS instead of SheetJS for better style support
 */
import type { IWorkbookData, IWorksheetData, ICellData, IStyleData } from "@univerjs/core";
import { CellValueType } from "@univerjs/core";
import ExcelJS from "exceljs";

/**
 * Convert ExcelJS ARGB color to Univer format (#RRGGBB)
 */
function convertColor(color: Partial<ExcelJS.Color> | undefined): string | undefined {
  if (!color) return undefined;

  // Handle ARGB format (e.g., "FF4472C4" -> "#4472C4")
  if (color.argb) {
    // Strip alpha channel if present (first 2 chars)
    const rgb = color.argb.length === 8 ? color.argb.slice(2) : color.argb;
    return `#${rgb}`;
  }

  // Handle theme colors (fallback to a visible color)
  if (color.theme !== undefined) {
    // Theme colors would need a theme palette to resolve properly
    // For now, return undefined to skip
    return undefined;
  }

  return undefined;
}

/**
 * Convert ExcelJS border style to Univer border style number
 */
function convertBorderStyle(style: ExcelJS.BorderStyle | undefined): number {
  switch (style) {
    case "thin":
      return 1;
    case "medium":
      return 2;
    case "thick":
      return 3;
    case "dotted":
      return 4;
    case "dashed":
      return 5;
    case "double":
      return 6;
    default:
      return 1;
  }
}

/**
 * Convert ExcelJS cell style to Univer style format
 */
function convertStyle(cell: ExcelJS.Cell): IStyleData | null {
  const style: IStyleData = {};
  let hasStyle = false;

  // Background color (fill)
  if (cell.fill && cell.fill.type === "pattern") {
    const patternFill = cell.fill as ExcelJS.FillPattern;
    const bgColor = convertColor(patternFill.fgColor);
    if (bgColor) {
      style.bg = { rgb: bgColor };
      hasStyle = true;
    }
  }

  // Font settings
  if (cell.font) {
    if (cell.font.bold) {
      style.bl = 1;
      hasStyle = true;
    }
    if (cell.font.italic) {
      style.it = 1;
      hasStyle = true;
    }
    if (cell.font.underline) {
      style.ul = { s: 1 };
      hasStyle = true;
    }
    if (cell.font.strike) {
      style.st = { s: 1 };
      hasStyle = true;
    }
    const fontColor = convertColor(cell.font.color);
    if (fontColor) {
      style.cl = { rgb: fontColor };
      hasStyle = true;
    }
    if (cell.font.size) {
      style.fs = cell.font.size;
      hasStyle = true;
    }
    if (cell.font.name) {
      style.ff = cell.font.name;
      hasStyle = true;
    }
  }

  // Borders
  if (cell.border) {
    const bd: IStyleData["bd"] = {};
    let hasBorder = false;

    if (cell.border.top) {
      bd.t = {
        s: convertBorderStyle(cell.border.top.style),
        cl: { rgb: convertColor(cell.border.top.color) || "#000000" },
      };
      hasBorder = true;
    }
    if (cell.border.bottom) {
      bd.b = {
        s: convertBorderStyle(cell.border.bottom.style),
        cl: { rgb: convertColor(cell.border.bottom.color) || "#000000" },
      };
      hasBorder = true;
    }
    if (cell.border.left) {
      bd.l = {
        s: convertBorderStyle(cell.border.left.style),
        cl: { rgb: convertColor(cell.border.left.color) || "#000000" },
      };
      hasBorder = true;
    }
    if (cell.border.right) {
      bd.r = {
        s: convertBorderStyle(cell.border.right.style),
        cl: { rgb: convertColor(cell.border.right.color) || "#000000" },
      };
      hasBorder = true;
    }

    if (hasBorder) {
      style.bd = bd;
      hasStyle = true;
    }
  }

  // Alignment
  if (cell.alignment) {
    if (cell.alignment.horizontal) {
      const hMap: Record<string, number> = {
        left: 1,
        center: 2,
        right: 3,
        fill: 4,
        justify: 5,
      };
      if (hMap[cell.alignment.horizontal]) {
        style.ht = hMap[cell.alignment.horizontal];
        hasStyle = true;
      }
    }
    if (cell.alignment.vertical) {
      const vMap: Record<string, number> = {
        top: 1,
        middle: 2,
        bottom: 3,
      };
      if (vMap[cell.alignment.vertical]) {
        style.vt = vMap[cell.alignment.vertical];
        hasStyle = true;
      }
    }
    if (cell.alignment.wrapText) {
      style.tb = 2; // wrap
      hasStyle = true;
    }
  }

  return hasStyle ? style : null;
}

/**
 * Get cell value type for Univer
 */
function getCellValueType(cell: ExcelJS.Cell): CellValueType {
  const value = cell.value;

  if (typeof value === "number") {
    return CellValueType.NUMBER;
  }
  if (typeof value === "boolean") {
    return CellValueType.BOOLEAN;
  }
  if (value instanceof Date) {
    return CellValueType.NUMBER; // Dates are numbers in spreadsheets
  }

  return CellValueType.STRING;
}

/**
 * Extract the actual value from an ExcelJS cell
 */
function getCellValue(cell: ExcelJS.Cell): string | number | boolean | null {
  const value = cell.value;

  if (value === null || value === undefined) {
    return null;
  }

  // Handle formula results
  if (typeof value === "object" && "result" in value) {
    const formulaValue = value as ExcelJS.CellFormulaValue;
    return formulaValue.result as string | number | boolean | null ?? null;
  }

  // Handle rich text
  if (typeof value === "object" && "richText" in value) {
    const richText = value as ExcelJS.CellRichTextValue;
    return richText.richText.map((rt) => rt.text).join("");
  }

  // Handle hyperlinks
  if (typeof value === "object" && "hyperlink" in value) {
    const hyperlink = value as ExcelJS.CellHyperlinkValue;
    return hyperlink.text || hyperlink.hyperlink;
  }

  // Handle dates
  if (value instanceof Date) {
    // Convert to Excel serial date number
    const epoch = new Date(1899, 11, 30).getTime();
    return (value.getTime() - epoch) / (24 * 60 * 60 * 1000);
  }

  // Handle errors
  if (typeof value === "object" && "error" in value) {
    const errorValue = value as ExcelJS.CellErrorValue;
    return errorValue.error;
  }

  // Handle shared formula
  if (typeof value === "object" && "sharedFormula" in value) {
    const sharedFormula = value as ExcelJS.CellSharedFormulaValue;
    return sharedFormula.result as string | number | boolean | null ?? null;
  }

  return value as string | number | boolean;
}

/**
 * Extract formula from an ExcelJS cell
 * Note: Univer expects formulas WITHOUT the leading '=' sign
 */
function getCellFormula(cell: ExcelJS.Cell): string | undefined {
  const value = cell.value;

  if (typeof value === "object" && value !== null) {
    // Regular formula
    if ("formula" in value) {
      const formulaValue = value as ExcelJS.CellFormulaValue;
      const formula = formulaValue.formula;
      // Remove leading '=' if present (ExcelJS sometimes includes it)
      return formula?.startsWith("=") ? formula.slice(1) : formula;
    }
    // Shared formula
    if ("sharedFormula" in value) {
      const sharedFormula = value as ExcelJS.CellSharedFormulaValue;
      const formula = sharedFormula.sharedFormula;
      return formula?.startsWith("=") ? formula.slice(1) : formula;
    }
  }

  return undefined;
}

/**
 * Convert an ExcelJS worksheet to Univer worksheet data
 */
function convertWorksheet(
  worksheet: ExcelJS.Worksheet,
  sheetId: string,
  styles: Record<string, IStyleData>
): IWorksheetData {
  const cellData: Record<number, Record<number, ICellData>> = {};

  // Get dimensions
  const rowCount = Math.max(worksheet.rowCount || 0, 100);
  const columnCount = Math.max(worksheet.columnCount || 0, 26);

  // Get column widths
  const columnData: Record<number, { w: number }> = {};
  worksheet.columns.forEach((col, idx) => {
    if (col.width) {
      // ExcelJS width is in characters, convert to pixels (roughly 7px per character)
      columnData[idx] = { w: Math.round(col.width * 7) };
    }
  });

  // Get row heights and cell data
  const rowData: Record<number, { h: number }> = {};
  let styleCount = 0;
  let formulaCount = 0;

  worksheet.eachRow({ includeEmpty: false }, (row, rowNumber) => {
    const r = rowNumber - 1; // Convert to 0-indexed

    // Row height
    if (row.height) {
      rowData[r] = { h: row.height };
    }

    // Process cells
    row.eachCell({ includeEmpty: false }, (cell, colNumber) => {
      const c = colNumber - 1; // Convert to 0-indexed

      if (!cellData[r]) cellData[r] = {};

      const univerCell: ICellData = {};

      // Set value
      const cellValue = getCellValue(cell);
      if (cellValue !== null) {
        univerCell.v = cellValue;
      }

      // Set formula (this is key for formula bar display)
      const formula = getCellFormula(cell);
      if (formula) {
        univerCell.f = formula;
        formulaCount++;
        // Debug: Log first few formulas
        if (formulaCount <= 3) {
          console.log(`[xlsx-to-univer] Formula found at ${cell.address}: "${formula}"`);
        }
      }

      // Set type
      univerCell.t = getCellValueType(cell);

      // Convert and store style
      const style = convertStyle(cell);
      if (style) {
        const styleId = `style_${r}_${c}`;
        styles[styleId] = style;
        univerCell.s = styleId;
        styleCount++;
      }

      cellData[r][c] = univerCell;
    });
  });

  console.log(`[xlsx-to-univer] Sheet "${worksheet.name}": ${styleCount} styled cells, ${formulaCount} formulas`);

  // Convert merges
  const mergeData: Array<{
    startRow: number;
    endRow: number;
    startColumn: number;
    endColumn: number;
  }> = [];

  worksheet.model.merges?.forEach((merge) => {
    // Parse merge range like "A1:B2"
    const match = merge.match(/([A-Z]+)(\d+):([A-Z]+)(\d+)/);
    if (match) {
      const startCol = columnLetterToIndex(match[1]);
      const startRow = parseInt(match[2], 10) - 1;
      const endCol = columnLetterToIndex(match[3]);
      const endRow = parseInt(match[4], 10) - 1;

      mergeData.push({
        startRow,
        endRow,
        startColumn: startCol,
        endColumn: endCol,
      });
    }
  });

  return {
    id: sheetId,
    name: worksheet.name,
    cellData,
    rowCount,
    columnCount,
    mergeData,
    rowData,
    columnData,
    defaultColumnWidth: 88,
    defaultRowHeight: 24,
    tabColor: "",
    hidden: worksheet.state === "hidden" ? 1 : 0,
    freeze: {
      startRow: -1,
      startColumn: -1,
      xSplit: 0,
      ySplit: 0,
    },
    scrollTop: 0,
    scrollLeft: 0,
  } as IWorksheetData;
}

/**
 * Convert column letter to 0-based index (A=0, B=1, ..., Z=25, AA=26, etc.)
 */
function columnLetterToIndex(letters: string): number {
  let index = 0;
  for (let i = 0; i < letters.length; i++) {
    index = index * 26 + (letters.charCodeAt(i) - 64);
  }
  return index - 1;
}

/**
 * Convert an ArrayBuffer containing XLSX data to Univer's IWorkbookData format
 */
export async function convertXlsxToUniverData(arrayBuffer: ArrayBuffer): Promise<IWorkbookData> {
  const workbook = new ExcelJS.Workbook();
  await workbook.xlsx.load(arrayBuffer);

  console.log(`[xlsx-to-univer] ExcelJS loaded workbook with ${workbook.worksheets.length} sheets`);

  const styles: Record<string, IStyleData> = {};
  const sheets: Record<string, IWorksheetData> = {};
  const sheetOrder: string[] = [];

  // Convert each sheet
  workbook.worksheets.forEach((worksheet, index) => {
    const sheetId = `sheet_${index}`;
    sheets[sheetId] = convertWorksheet(worksheet, sheetId, styles);
    sheetOrder.push(sheetId);
  });

  console.log(`[xlsx-to-univer] Total styles extracted: ${Object.keys(styles).length}`);

  return {
    id: `workbook_${Date.now()}`,
    name: workbook.title || "Workbook",
    appVersion: "1.0.0",
    locale: "enUS",
    styles,
    sheetOrder,
    sheets,
  } as IWorkbookData;
}
