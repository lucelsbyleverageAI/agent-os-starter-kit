import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { LucideIcon } from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

const emptyStateVariants = cva(
  "flex flex-col items-center justify-center text-center transition-colors duration-150",
  {
    variants: {
      size: {
        sm: "py-8 px-4 gap-3",
        default: "py-12 px-6 gap-4",
        lg: "py-16 px-8 gap-5",
      },
    },
    defaultVariants: {
      size: "default",
    },
  },
);

const emptyStateIconVariants = cva(
  "rounded-full bg-muted/30 flex items-center justify-center text-muted-foreground mb-2",
  {
    variants: {
      size: {
        sm: "h-10 w-10",
        default: "h-12 w-12",
        lg: "h-16 w-16",
      },
    },
    defaultVariants: {
      size: "default",
    },
  },
);

const emptyStateTitleVariants = cva("font-semibold text-foreground", {
  variants: {
    size: {
      sm: "text-base",
      default: "text-lg",
      lg: "text-xl",
    },
  },
  defaultVariants: {
    size: "default",
  },
});

const emptyStateDescriptionVariants = cva("text-muted-foreground", {
  variants: {
    size: {
      sm: "text-xs max-w-xs",
      default: "text-sm max-w-sm",
      lg: "text-base max-w-md",
    },
  },
  defaultVariants: {
    size: "default",
  },
});

export interface EmptyStateProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof emptyStateVariants> {
  icon?: LucideIcon;
  iconClassName?: string;
  title: string;
  description?: string;
  action?: {
    label: string;
    onClick: () => void;
    variant?: "default" | "outline" | "ghost" | "brand";
  };
}

function EmptyState({
  className,
  size,
  icon: Icon,
  iconClassName,
  title,
  description,
  action,
  ...props
}: EmptyStateProps) {
  return (
    <div className={cn(emptyStateVariants({ size }), className)} {...props}>
      {Icon && (
        <div className={cn(emptyStateIconVariants({ size }))}>
          <Icon
            className={cn(
              size === "sm" ? "h-5 w-5" : size === "lg" ? "h-8 w-8" : "h-6 w-6",
              iconClassName,
            )}
          />
        </div>
      )}
      <div className="space-y-2">
        <h3 className={cn(emptyStateTitleVariants({ size }))}>{title}</h3>
        {description && (
          <p className={cn(emptyStateDescriptionVariants({ size }))}>
            {description}
          </p>
        )}
      </div>
      {action && (
        <Button
          onClick={action.onClick}
          variant={action.variant || "default"}
          size={size === "sm" ? "sm" : "default"}
          className="mt-2"
        >
          {action.label}
        </Button>
      )}
    </div>
  );
}

export { EmptyState };
