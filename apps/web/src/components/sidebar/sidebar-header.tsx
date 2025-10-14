"use client";

import {
  SidebarHeader,
  SidebarMenu,
  SidebarMenuItem,
  SidebarMenuButton,
  useSidebar,
} from "@/components/ui/sidebar";
import Image from "next/image";
import NextLink from "next/link";
import { useTheme } from "next-themes";
import { useEffect, useState } from "react";

export function SiteHeader() {
  const { state } = useSidebar();
  const { resolvedTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  const isCollapsed = state === "collapsed";
  const isDark = resolvedTheme === "dark";

  // Wait for component to mount to avoid hydration mismatch
  useEffect(() => {
    setMounted(true);
  }, []);

  // Use a default theme until mounted to prevent hydration mismatch
  // Default to light theme during SSR
  const logoSrc = !mounted
    ? (isCollapsed ? "/icon_light.png" : "/logo_light.png")
    : (isCollapsed
        ? (isDark ? "/icon_dark.png" : "/icon_light.png")
        : (isDark ? "/logo_dark.png" : "/logo_light.png"));

  return (
    <SidebarHeader>
      <SidebarMenu>
        <SidebarMenuItem>
          <SidebarMenuButton
            size="lg"
            asChild
          >
            <NextLink href="/" className="flex items-center justify-start">
              <Image
                src={logoSrc}
                alt="Logo"
                width={isCollapsed ? 24 : 120}
                height={24}
                className="flex-shrink-0"
                priority
              />
            </NextLink>
          </SidebarMenuButton>
        </SidebarMenuItem>
      </SidebarMenu>
    </SidebarHeader>
  );
}
