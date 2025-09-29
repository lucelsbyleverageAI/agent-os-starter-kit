"use client";

import { useTheme } from "next-themes";
import { Toaster as Sonner, ToasterProps } from "sonner";

const Toaster = ({ ...props }: ToasterProps) => {
  const { theme = "system" } = useTheme();

  return (
    <Sonner
      theme={theme as ToasterProps["theme"]}
      className="toaster group"
      closeButton
      richColors
      style={
        {
          "--normal-bg": "hsl(var(--popover))",
          "--normal-text": "hsl(var(--popover-foreground))",
          "--normal-border": "hsl(var(--border))",
          "--success-bg": "hsl(var(--primary))",
          "--success-text": "hsl(var(--primary-foreground))",
          "--error-bg": "hsl(var(--destructive))",
          "--error-text": "hsl(var(--destructive-foreground))",
          "--warning-bg": "hsl(var(--muted))",
          "--warning-text": "hsl(var(--muted-foreground))",
          "--info-bg": "hsl(var(--secondary))",
          "--info-text": "hsl(var(--secondary-foreground))",
        } as React.CSSProperties
      }
      toastOptions={{
        style: {
          background: "hsl(var(--popover))",
          border: "1px solid hsl(var(--border))",
          color: "hsl(var(--popover-foreground))",
        },
        className: "group toast group-[.toaster]:bg-popover group-[.toaster]:text-popover-foreground group-[.toaster]:border-border group-[.toaster]:shadow-lg",
        descriptionClassName: "group-[.toast]:text-muted-foreground",
      }}
      {...props}
    />
  );
};

export { Toaster };
