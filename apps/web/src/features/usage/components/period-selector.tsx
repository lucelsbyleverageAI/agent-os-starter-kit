"use client";

import { Button } from "@/components/ui/button";
import { UsagePeriod } from "../hooks/use-usage-breakdown";
import { cn } from "@/lib/utils";

interface PeriodSelectorProps {
  value: UsagePeriod;
  onChange: (period: UsagePeriod) => void;
}

const periods: { value: UsagePeriod; label: string }[] = [
  { value: "day", label: "Today" },
  { value: "week", label: "This Week" },
  { value: "month", label: "This Month" },
  { value: "all", label: "All Time" },
];

export function PeriodSelector({ value, onChange }: PeriodSelectorProps) {
  return (
    <div className="flex gap-1 bg-muted p-1 rounded-lg">
      {periods.map((period) => (
        <Button
          key={period.value}
          variant="ghost"
          size="sm"
          onClick={() => onChange(period.value)}
          className={cn(
            "px-3 py-1 h-8",
            value === period.value
              ? "bg-background shadow-sm"
              : "hover:bg-background/50"
          )}
        >
          {period.label}
        </Button>
      ))}
    </div>
  );
}
