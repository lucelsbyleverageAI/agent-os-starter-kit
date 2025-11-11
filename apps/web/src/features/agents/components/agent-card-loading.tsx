import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

export function AgentCardLoading() {
  return (
    <Card className="relative flex flex-col items-start gap-3 p-6">
      {/* Icon and title */}
      <div className="flex items-center gap-3 w-full">
        <Skeleton className="h-10 w-10 rounded-md" />
        <Skeleton className="h-5 w-2/3" />
      </div>

      {/* Description - 3 lines fixed height */}
      <div className="w-full space-y-2 min-h-[3.75rem]">
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-3/4" />
      </div>

      {/* Divider */}
      <div className="w-full border-t border-border" />

      {/* Footer action bar */}
      <div className="flex w-full items-center justify-between gap-3">
        {/* Left side: Tags */}
        <div className="flex items-center gap-2">
          <Skeleton className="h-5 w-16 rounded-full" />
          <Skeleton className="h-5 w-12 rounded-full" />
        </div>

        {/* Right side: Action buttons */}
        <div className="flex items-center gap-2">
          <Skeleton className="h-8 w-16" />
          <Skeleton className="h-8 w-16" />
        </div>
      </div>
    </Card>
  );
}
