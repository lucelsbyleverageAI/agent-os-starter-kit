// Minimal detector for raw JSON streamed from backend agents.
// Goal: hide any raw JSON payload (objects/arrays) from conversational rendering
// during streaming, unless it is intentionally shown as a fenced code block.

export type StructuredJsonDetectionResult = {
  isLikely: boolean;
  confidence: number; // 0..1
};

export type StructuredJsonDetectionOptions = {
  partial?: boolean; // kept for API compatibility, not required by minimal detector
};

function hasCodeFence(text: string): boolean {
  // Avoid suppressing code blocks / fenced JSON intended for display
  return text.includes("```");
}

function startsJsonish(text: string): boolean {
  const t = text.trimStart();
  return t.startsWith("{") || t.startsWith("[");
}

// No heavy heuristics: we flag any raw JSON-looking content, letting the
// rendering layer decide what to do. This maximises suppression of control JSON
// without manual allowlists.

export function isStructuredControlJson(
  text: string,
  opts?: StructuredJsonDetectionOptions,
): StructuredJsonDetectionResult {
  const trimmed = (text || "").trim();
  if (trimmed.length === 0) return { isLikely: false, confidence: 0 };

  // Never suppress fenced code blocks or obvious prose wrappers
  if (hasCodeFence(trimmed)) return { isLikely: false, confidence: 0 };

  if (startsJsonish(trimmed)) {
    return { isLikely: true, confidence: 1 };
  }

  return { isLikely: false, confidence: 0 };
}


