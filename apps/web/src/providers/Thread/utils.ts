import { Thread, ThreadState } from "@langchain/langgraph-sdk";
import { HumanInterrupt, ThreadData } from "@/components/agent-inbox/types";
import { IMPROPER_SCHEMA } from "@/constants";

/**
 * Sanitizes a JSON string by removing or escaping control characters
 * that can cause JSON.parse() to fail with "Bad control character in string literal"
 *
 * This is particularly important for streaming contexts where large amounts of data
 * may contain unescaped control characters.
 */
function sanitizeJsonString(str: string): string {
  // Replace control characters (ASCII 0-31 except whitespace) with escaped versions
  // Keep: \t (tab, 9), \n (newline, 10), \r (carriage return, 13)
  // Remove or escape others that aren't valid in JSON strings
  return str.replace(/[\x00-\x08\x0B\x0C\x0E-\x1F]/g, '');
}

/**
 * Safely parses JSON with control character sanitization
 * Falls back to returning null if parsing fails after sanitization
 */
function safeJsonParse<T = any>(value: string): T | null {
  try {
    const sanitized = sanitizeJsonString(value);
    return JSON.parse(sanitized);
  } catch (error) {
    console.warn('Failed to parse JSON even after sanitization:', error);
    return null;
  }
}

// TODO: Delete this once interrupt issue fixed.
export const tmpCleanInterrupts = (interrupts: Record<string, any[]>) => {
  return Object.fromEntries(
    Object.entries(interrupts).map(([k, v]) => {
      if (Array.isArray(v[0] && v[0]?.[1])) {
        return [k, v?.[0][1]];
      }
      return [k, v];
    }),
  );
};

export function getInterruptFromThread(
  thread: Thread,
): HumanInterrupt[] | undefined {
  try {
    if (thread.interrupts && Object.values(thread.interrupts).length > 0) {
      const result = Object.values(thread.interrupts).flatMap((interrupt) => {
        try {
          // Handle case when interrupt is a direct array with structure as first item
          if (Array.isArray(interrupt) && interrupt.length > 0) {
            // Case 1: Array with nested structure [0][1].value
            if (Array.isArray(interrupt[0])) {
              if (!interrupt[0]?.[1]) {
                return {
                  action_request: { action: IMPROPER_SCHEMA, args: {} },
                  config: {
                    allow_ignore: true,
                    allow_respond: false,
                    allow_edit: false,
                    allow_accept: false,
                  },
                } as HumanInterrupt;
              }
              return interrupt[0][1].value as HumanInterrupt;
            }

            // Case 2: First item has a value property
            if (interrupt[0]?.value !== undefined) {
              const value = interrupt[0].value;

              // Handle case where value is a valid JSON string
              if (
                typeof value === "string" &&
                (value.startsWith("[") || value.startsWith("{"))
              ) {
                try {
                  const parsed = safeJsonParse(value);

                  // Parsed is an array of interrupts
                  if (Array.isArray(parsed)) {
                    if (
                      parsed.length > 0 &&
                      parsed[0] &&
                      typeof parsed[0] === "object" &&
                      "action_request" in parsed[0] &&
                      "config" in parsed[0]
                    ) {
                      return parsed as HumanInterrupt[];
                    }
                  }
                  // Parsed is a single interrupt
                  else if (
                    parsed &&
                    typeof parsed === "object" &&
                    "action_request" in parsed &&
                    "config" in parsed
                  ) {
                    return parsed as HumanInterrupt;
                  }
                } catch (_) {
                  // Failed to parse as JSON, continue normal processing
                }
              }

              // Check if value itself is an interrupt object or array
              if (Array.isArray(value)) {
                if (
                  value.length > 0 &&
                  value[0] &&
                  typeof value[0] === "object" &&
                  "action_request" in value[0] &&
                  "config" in value[0]
                ) {
                  return value as HumanInterrupt[];
                }
              } else if (
                value &&
                typeof value === "object" &&
                "action_request" in value &&
                "config" in value
              ) {
                return value as HumanInterrupt;
              }
            }

            // Case 3: First item is directly the interrupt object
            if (
              interrupt[0] &&
              typeof interrupt[0] === "object" &&
              "action_request" in interrupt[0] &&
              "config" in interrupt[0]
            ) {
              return interrupt[0] as HumanInterrupt;
            }

            // Process all items and handle direct interrupt array
            const values = interrupt.flatMap((i) => {
              if (
                i &&
                typeof i === "object" &&
                "action_request" in i &&
                "config" in i
              ) {
                return i as unknown as HumanInterrupt;
              } else if (i?.value) {
                // Check if it's a valid HumanInterrupt structure
                const value = i.value as any;

                if (!value || typeof value !== "object") {
                  return {
                    action_request: { action: IMPROPER_SCHEMA, args: {} },
                    config: {
                      allow_ignore: true,
                      allow_respond: false,
                      allow_edit: false,
                      allow_accept: false,
                    },
                  } as HumanInterrupt;
                }

                // If value is array, check if it contains valid interrupts
                if (Array.isArray(value)) {
                  if (
                    value.length > 0 &&
                    value[0]?.action_request?.action &&
                    value[0]?.config
                  ) {
                    return value as HumanInterrupt[];
                  }
                }

                // Check if value is a direct interrupt object
                if (value?.action_request?.action && value?.config) {
                  return value as HumanInterrupt;
                }

                return {
                  action_request: { action: IMPROPER_SCHEMA, args: {} },
                  config: {
                    allow_ignore: true,
                    allow_respond: false,
                    allow_edit: false,
                    allow_accept: false,
                  },
                } as HumanInterrupt;
              }

              return {
                action_request: { action: IMPROPER_SCHEMA, args: {} },
                config: {
                  allow_ignore: true,
                  allow_respond: false,
                  allow_edit: false,
                  allow_accept: false,
                },
              } as HumanInterrupt;
            });

            return values;
          }

          // Default fallback
          return {
            action_request: { action: IMPROPER_SCHEMA, args: {} },
            config: {
              allow_ignore: true,
              allow_respond: false,
              allow_edit: false,
              allow_accept: false,
            },
          } as HumanInterrupt;
        } catch (_) {
          return {
            action_request: { action: IMPROPER_SCHEMA, args: {} },
            config: {
              allow_ignore: true,
              allow_respond: false,
              allow_edit: false,
              allow_accept: false,
            },
          } as HumanInterrupt;
        }
      });

      return result;
    }
  } catch (error) {
    console.error("Error parsing interrupts from thread:", error);
  }

  return undefined;
}

export function processInterruptedThread<
  ThreadValues extends Record<string, any>,
>(thread: Thread<ThreadValues>): ThreadData<ThreadValues> | undefined {
  try {
    const interrupts = getInterruptFromThread(thread);
    if (interrupts && interrupts.length > 0) {
      return {
        status: "interrupted",
        thread,
        interrupts,
        invalidSchema: interrupts.some(
          (interrupt) =>
            interrupt?.action_request?.action === IMPROPER_SCHEMA ||
            !interrupt?.action_request?.action,
        ),
      };
    }
  } catch (error) {
    console.error("Error processing interrupted thread:", error);
  }
  return undefined;
}

export function processThreadWithoutInterrupts<
  ThreadValues extends Record<string, any>,
>(
  thread: Thread<ThreadValues>,
  state: { thread_state: ThreadState<ThreadValues>; thread_id: string },
): ThreadData<ThreadValues> {
  return {
    status: thread.status,
    thread,
    interrupts: undefined,
    invalidSchema: false,
  };
} 