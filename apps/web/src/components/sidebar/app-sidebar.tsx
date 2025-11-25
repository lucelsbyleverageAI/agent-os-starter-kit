"use client";

import * as React from "react";
import { Wrench, Bot, MessageCircle, Brain, Shield, BrainCircuit, Sparkles } from "lucide-react";

import { NavMain } from "./nav-main";
import { NavUser } from "./nav-user";
import { ChatHistory } from "./chat-history";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarRail,
} from "@/components/ui/sidebar";
import { SiteHeader } from "./sidebar-header";
import { useUserRole } from "@/providers/UserRole";

// This is sample data.
const baseNavItems = [
  {
    title: "Chat",
    url: "/",
    icon: MessageCircle,
  },
  {
    title: "Agents",
    url: "/agents",
    icon: Bot,
  },
  {
    title: "Tools",
    url: "/tools",
    icon: Wrench,
  },
  // {
  //   title: "Inbox",
  //   url: "/inbox",
  //   icon: MessageCircle,
  // },
  {
    title: "Knowledge",
    url: "/knowledge",
    icon: Brain,
  },
  {
    title: "Skills",
    url: "/skills",
    icon: Sparkles,
  },
  {
    title: "Memories",
    url: "/memories",
    icon: BrainCircuit,
  },
];

export function AppSidebar({ ...props }: React.ComponentProps<typeof Sidebar>) {
  const { isDevAdmin } = useUserRole();
  const [mounted, setMounted] = React.useState(false);

  React.useEffect(() => {
    setMounted(true);
  }, []);

  const navItems = React.useMemo(() => {
    const items = [...baseNavItems];
    // Defer role-gated items until after mount to avoid SSR/client mismatch
    if (mounted && isDevAdmin) {
      items.push({
        title: "Admin",
        url: "/admin",
        icon: Shield,
      });
    }
    return items;
  }, [mounted, isDevAdmin]);

  return (
    <Sidebar
      collapsible="icon"
      {...props}
    >
      <SiteHeader />
      <SidebarContent>
        <NavMain items={navItems} />
        <ChatHistory />
      </SidebarContent>
      <SidebarFooter>
        <NavUser />
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  );
}
