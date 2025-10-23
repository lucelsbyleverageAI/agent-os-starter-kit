import * as React from "react";

import { cn } from "@/lib/utils";

function Input({ className, type, ...props }: React.ComponentProps<"input">) {
  return (
    <input
      type={type}
      data-slot="input"
      className={cn(
        "flex h-9 w-full min-w-0 rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-xs transition-colors duration-150",
        "placeholder:text-muted-foreground",
        "focus-visible:outline-ring focus-visible:outline-2 focus-visible:outline-offset-0 focus-visible:border-ring",
        "disabled:cursor-not-allowed disabled:opacity-50",
        "dark:border-muted-foreground/50 dark:bg-black/40",
        "file:inline-flex file:h-7 file:border-0 file:bg-transparent file:text-sm file:font-medium file:text-foreground",
        className,
      )}
      {...props}
    />
  );
}

export { Input };
