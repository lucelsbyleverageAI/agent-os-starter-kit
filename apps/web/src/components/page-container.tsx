import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const pageContainerVariants = cva(
  "w-full transition-colors duration-150",
  {
    variants: {
      variant: {
        default: "mx-auto max-w-[var(--page-max-width)] px-6",
        centered: "mx-auto max-w-[var(--content-max-width)] px-6",
        card: "mx-auto max-w-[var(--card-max-width)] px-6",
        full: "px-6",
        narrow: "mx-auto max-w-3xl px-6",
      },
      spacing: {
        none: "",
        sm: "py-4",
        default: "py-6",
        lg: "py-8",
        xl: "py-12",
      },
    },
    defaultVariants: {
      variant: "default",
      spacing: "default",
    },
  },
);

export interface PageContainerProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof pageContainerVariants> {
  as?: "div" | "section" | "article" | "main";
}

function PageContainer({
  className,
  variant,
  spacing,
  as: Component = "div",
  ...props
}: PageContainerProps) {
  return (
    <Component
      className={cn(pageContainerVariants({ variant, spacing }), className)}
      {...props}
    />
  );
}

export { PageContainer, pageContainerVariants };
