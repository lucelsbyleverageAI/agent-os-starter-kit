"use client";

import {
  SidebarHeader,
  SidebarMenu,
  SidebarMenuItem,
  SidebarMenuButton,
} from "@/components/ui/sidebar";
import Image from "next/image";
import NextLink from "next/link";

export function SiteHeader() {
  return (
    <SidebarHeader>
      <SidebarMenu>
        <SidebarMenuItem>
          <SidebarMenuButton
            size="lg"
            asChild
            className="flex items-center justify-center gap-0"
          >
            <NextLink href="/">
              <Image 
                src="/logo_icon_round.png" 
                alt="AgentOS Logo" 
                width={24} 
                height={24} 
                className="flex-shrink-0"
              />
              <div className="grid flex-1 pl-2 text-left text-sm leading-tight transition-all group-data-[collapsible=icon]:pl-0 group-data-[collapsible=icon]:opacity-0">
                <span className="truncate font-semibold">
                  AgentOS
                </span>
              </div>
            </NextLink>
          </SidebarMenuButton>
        </SidebarMenuItem>
      </SidebarMenu>
    </SidebarHeader>
  );
}
