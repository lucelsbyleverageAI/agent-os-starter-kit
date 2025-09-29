import { startCase } from "lodash";

export function prettifyText(action: string) {
  return startCase(action.replace(/_/g, " "));
}

export function haveArgsChanged(
  args: unknown,
  initialValues: Record<string, string>,
): boolean {
  if (typeof args !== "object" || !args) {
    return false;
  }

  const currentValues = args as Record<string, string>;

  return Object.entries(currentValues).some(([key, value]) => {
    const valueString = ["string", "number"].includes(typeof value)
      ? value.toString()
      : JSON.stringify(value, null);
    return initialValues[key] !== valueString;
  });
}

export function isComplexValue(value: any): boolean {
  return Array.isArray(value) || (typeof value === "object" && value !== null);
} 