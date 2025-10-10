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

export function SiteHeader() {
  const { state } = useSidebar();
  const { theme } = useTheme();

  const isCollapsed = state === "collapsed";
  const isDark = theme === "dark";

  // Determine which logo to show
  const logoSrc = isCollapsed
    ? isDark ? "/icon_dark.png" : "/icon_light.png"
    : isDark ? "/logo_dark.png" : "/logo_light.png";

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
