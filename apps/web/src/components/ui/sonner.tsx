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
      position="bottom-right"
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
          backdropFilter: "blur(12px)",
          WebkitBackdropFilter: "blur(12px)",
          opacity: 1,
          boxShadow: "0 8px 32px rgba(0, 0, 0, 0.12), 0 2px 8px rgba(0, 0, 0, 0.08)",
        },
        className: "group toast group-[.toaster]:bg-popover group-[.toaster]:text-popover-foreground group-[.toaster]:border-border group-[.toaster]:shadow-xl group-[.toaster]:backdrop-blur-xl",
        descriptionClassName: "group-[.toast]:text-muted-foreground group-[.toast]:opacity-90",
      }}
      {...props}
    />
  );
};

export { Toaster };
