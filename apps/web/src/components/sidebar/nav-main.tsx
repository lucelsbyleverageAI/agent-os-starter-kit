"use client";

import * as React from "react";
import { ChevronRight, type LucideIcon } from "lucide-react";
import { usePathname } from "next/navigation";

import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import {
  SidebarGroup,
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarMenuSub,
  SidebarMenuSubButton,
  SidebarMenuSubItem,
  useSidebar,
} from "@/components/ui/sidebar";
import NextLink from "next/link";
import { cn } from "@/lib/utils";

export type NavItem = {
  title: string;
  url?: string;
  icon?: LucideIcon;
  items?: {
    title: string;
    url: string;
    icon?: LucideIcon;
  }[];
};

function CollapsibleNavItem({
  item,
  hasActiveChild,
}: {
  item: NavItem;
  hasActiveChild: boolean;
}) {
  const pathname = usePathname();
  const { state, setOpen } = useSidebar();
  const isCollapsed = state === "collapsed";
  const [isOpen, setIsOpen] = React.useState(hasActiveChild);

  const handleClick = (e: React.MouseEvent) => {
    if (isCollapsed) {
      // Prevent the collapsible from toggling - we'll control it manually
      e.preventDefault();
      // Expand the sidebar and always open this section
      setOpen(true);
      setIsOpen(true);
    }
    // When not collapsed, let the CollapsibleTrigger handle toggling naturally
  };

  return (
    <Collapsible
      asChild
      open={isOpen}
      onOpenChange={setIsOpen}
      className="group/collapsible"
    >
      <SidebarMenuItem>
        <CollapsibleTrigger asChild>
          <SidebarMenuButton tooltip={item.title} onClick={handleClick}>
            {item.icon && <item.icon />}
            <span>{item.title}</span>
            <ChevronRight className="ml-auto transition-transform duration-200 group-data-[state=open]/collapsible:rotate-90 group-data-[collapsible=icon]:hidden" />
          </SidebarMenuButton>
        </CollapsibleTrigger>
        <CollapsibleContent>
          <SidebarMenuSub>
            {item.items?.map((subItem) => {
              const isSubActive = pathname === subItem.url;
              return (
                <SidebarMenuSubItem key={subItem.title}>
                  <SidebarMenuSubButton asChild isActive={isSubActive}>
                    <NextLink href={subItem.url} prefetch={false}>
                      {subItem.icon && <subItem.icon />}
                      <span>{subItem.title}</span>
                    </NextLink>
                  </SidebarMenuSubButton>
                </SidebarMenuSubItem>
              );
            })}
          </SidebarMenuSub>
        </CollapsibleContent>
      </SidebarMenuItem>
    </Collapsible>
  );
}

export function NavMain({ items }: { items: NavItem[] }) {
  const pathname = usePathname();

  return (
    <SidebarGroup>
      <SidebarGroupLabel>Platform</SidebarGroupLabel>
      <SidebarMenu>
        {items.map((item, index) => {
          // Check if this item or any of its sub-items is active
          const isActive = item.url ? pathname === item.url : false;
          const hasActiveChild =
            item.items?.some((sub) => pathname === sub.url) ?? false;

          // If item has sub-items, render as collapsible
          if (item.items && item.items.length > 0) {
            return (
              <CollapsibleNavItem
                key={`${item.title}-${index}`}
                item={item}
                hasActiveChild={hasActiveChild}
              />
            );
          }

          // Regular item without sub-items
          return (
            <SidebarMenuItem
              key={`${item.title}-${index}`}
              className={cn(
                isActive &&
                  "bg-sidebar-accent text-sidebar-accent-foreground rounded-sm"
              )}
              suppressHydrationWarning
            >
              <SidebarMenuButton tooltip={item.title} asChild>
                <NextLink href={item.url || "#"} prefetch={false}>
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
