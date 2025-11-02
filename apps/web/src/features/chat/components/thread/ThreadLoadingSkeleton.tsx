/**
 * ThreadLoadingSkeleton
 *
 * Loading skeleton displayed while switching between threads.
 * Shows placeholder message bubbles similar to Claude/ChatGPT UX pattern.
 * Provides immediate visual feedback to users that thread is loading.
 */

import { Skeleton } from "@/components/ui/skeleton";

export function ThreadLoadingSkeleton() {
  return (
    <div className="flex flex-col gap-4 px-4 py-8 md:px-8">
      {/* Loading indicator text */}
      <div className="flex items-center justify-center gap-2 py-4 text-sm text-muted-foreground">
        <div className="h-4 w-4 animate-spin rounded-full border-2 border-muted-foreground border-t-transparent" />
        <span>Loading conversation...</span>
      </div>

      {/* Human message skeleton (right-aligned) */}
      <div className="flex justify-end">
        <Skeleton className="h-16 w-3/4 max-w-2xl rounded-2xl" />
      </div>

      {/* AI message skeleton (left-aligned, longer) */}
      <div className="flex justify-start">
        <Skeleton className="h-24 w-5/6 max-w-3xl rounded-2xl" />
      </div>

      {/* Human message skeleton (right-aligned) */}
      <div className="flex justify-end">
        <Skeleton className="h-12 w-2/3 max-w-xl rounded-2xl" />
      </div>

      {/* AI message skeleton (left-aligned) */}
      <div className="flex justify-start">
        <Skeleton className="h-20 w-4/5 max-w-3xl rounded-2xl" />
      </div>
    </div>
  );
}
