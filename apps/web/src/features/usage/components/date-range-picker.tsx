"use client";

import * as React from "react";
import { format, subDays, startOfDay, endOfDay } from "date-fns";
import { Calendar as CalendarIcon } from "lucide-react";
import { DateRange } from "react-day-picker";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Calendar } from "@/components/ui/calendar";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";

interface DateRangePickerProps {
  value: DateRange | undefined;
  onChange: (range: DateRange | undefined) => void;
  className?: string;
}

const presets = [
  { label: "Today", days: 1 },
  { label: "Yesterday", days: -1 }, // Special case: -1 means yesterday only
  { label: "Last 7 days", days: 7 },
  { label: "Last 30 days", days: 30 },
  { label: "Last 90 days", days: 90 },
];

export function DateRangePicker({
  value,
  onChange,
  className,
}: DateRangePickerProps) {
  const [open, setOpen] = React.useState(false);
  // Track internal selection state for proper start->end flow
  const [internalRange, setInternalRange] = React.useState<DateRange | undefined>(value);

  // Sync internal state when external value changes
  React.useEffect(() => {
    setInternalRange(value);
  }, [value]);

  const handlePresetClick = (days: number) => {
    const today = new Date();
    let newRange: DateRange;

    if (days === -1) {
      // Yesterday only
      const yesterday = subDays(today, 1);
      newRange = {
        from: startOfDay(yesterday),
        to: endOfDay(yesterday),
      };
    } else if (days === 1) {
      // Today only
      newRange = {
        from: startOfDay(today),
        to: endOfDay(today),
      };
    } else {
      // Last N days (including today)
      newRange = {
        from: startOfDay(subDays(today, days - 1)),
        to: endOfDay(today),
      };
    }

    setInternalRange(newRange);
    onChange(newRange);
    setOpen(false);
  };

  const handleSelect = (range: DateRange | undefined) => {
    setInternalRange(range);

    // Only close and apply when both dates are selected AND they're different
    // (react-day-picker sets from=to on first click)
    if (range?.from && range?.to && range.from.getTime() !== range.to.getTime()) {
      onChange(range);
      setOpen(false);
    }
  };

  const handleOpenChange = (newOpen: boolean) => {
    if (newOpen) {
      // When opening, always start fresh - user picks start date first
      setInternalRange(undefined);
    } else {
      // When closing without completing selection, revert to original value
      if (!internalRange?.from || !internalRange?.to) {
        setInternalRange(value);
      }
    }
    setOpen(newOpen);
  };

  return (
    <div className={cn("grid gap-2", className)}>
      <Popover open={open} onOpenChange={handleOpenChange}>
        <PopoverTrigger asChild>
          <Button
            variant="outline"
            className={cn(
              "w-[280px] justify-start text-left font-normal",
              !value && "text-muted-foreground"
            )}
          >
            <CalendarIcon className="mr-2 h-4 w-4" />
            {value?.from ? (
              value.to ? (
                <>
                  {format(value.from, "MMM d, yyyy")} -{" "}
                  {format(value.to, "MMM d, yyyy")}
                </>
              ) : (
                format(value.from, "MMM d, yyyy")
              )
            ) : (
              <span>Pick a date range</span>
            )}
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-auto p-0" align="end" sideOffset={4}>
          <div className="flex">
            <div className="flex flex-col gap-1 border-r p-3 bg-muted/30">
              <p className="text-xs font-medium text-muted-foreground mb-2 px-2">
                Presets
              </p>
              {presets.map((preset) => (
                <Button
                  key={preset.days}
                  variant="ghost"
                  size="sm"
                  className="justify-start text-sm h-8"
                  onClick={() => handlePresetClick(preset.days)}
                >
                  {preset.label}
                </Button>
              ))}
            </div>
            <div className="p-3">
              <div className="text-xs text-muted-foreground mb-2 text-center">
                {!internalRange?.from ? (
                  "Select start date"
                ) : !internalRange?.to || internalRange.from.getTime() === internalRange.to.getTime() ? (
                  "Select end date"
                ) : (
                  "Range selected"
                )}
              </div>
              <Calendar
                mode="range"
                defaultMonth={internalRange?.from || value?.from}
                selected={internalRange}
                onSelect={handleSelect}
                numberOfMonths={2}
                disabled={{ after: new Date() }}
                classNames={{
                  months: "flex flex-col sm:flex-row gap-4",
                  month: "space-y-4",
                  month_caption: "flex justify-center pt-1 relative items-center h-7",
                  caption_label: "text-sm font-medium",
                  nav: "flex items-center gap-1",
                  button_previous: "absolute left-1 h-7 w-7 bg-transparent p-0 opacity-50 hover:opacity-100",
                  button_next: "absolute right-1 h-7 w-7 bg-transparent p-0 opacity-50 hover:opacity-100",
                  table: "w-full border-collapse",
                  weekdays: "flex",
                  weekday: "text-muted-foreground w-8 font-normal text-[0.8rem] text-center",
                  week: "flex w-full mt-2",
                  day: "h-8 w-8 p-0 font-normal text-center text-sm relative",
                  day_button: "h-8 w-8 p-0 font-normal hover:bg-accent hover:text-accent-foreground rounded-md",
                  selected: "bg-primary text-primary-foreground hover:bg-primary hover:text-primary-foreground focus:bg-primary focus:text-primary-foreground",
                  today: "bg-accent text-accent-foreground",
                  outside: "text-muted-foreground opacity-50",
                  disabled: "text-muted-foreground opacity-50",
                  range_middle: "bg-accent rounded-none",
                  range_start: "rounded-l-md bg-primary text-primary-foreground",
                  range_end: "rounded-r-md bg-primary text-primary-foreground",
                  hidden: "invisible",
                }}
              />
            </div>
          </div>
        </PopoverContent>
      </Popover>
    </div>
  );
}
