"use client";

import { type LucideIcon } from "lucide-react";
import { usePathname } from "next/navigation";

import {
  SidebarGroup,
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar";
import NextLink from "next/link";
import { cn } from "@/lib/utils";

export function NavMain({
  items,
}: {
  items: {
    title: string;
    url: string;
    icon?: LucideIcon;
  }[];
}) {
  const pathname = usePathname();

  return (
    <SidebarGroup>
      <SidebarGroupLabel>Platform</SidebarGroupLabel>
      <SidebarMenu>
        {items.map((item, index) => {
          const isActive = pathname === item.url;
          return (
            <SidebarMenuItem
              key={`${item.title}-${index}`}
              className={cn(
                isActive && "bg-sidebar-accent text-sidebar-accent-foreground rounded-sm"
              )}
              suppressHydrationWarning
            >
              <SidebarMenuButton tooltip={item.title} asChild>
                <NextLink href={item.url} prefetch={false}>
                  {item.icon && <item.icon />}
                  <span>{item.title}</span>
                </NextLink>
              </SidebarMenuButton>
            </SidebarMenuItem>
          );
        })}
      </SidebarMenu>
    </SidebarGroup>
  );
}
