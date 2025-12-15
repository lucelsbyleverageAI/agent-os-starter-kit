"use client";

import * as React from "react";
import {
  Wrench,
  Bot,
  MessageCircle,
  Brain,
  Shield,
  BrainCircuit,
  Sparkles,
  BarChart3,
  Boxes,
} from "lucide-react";

import { NavMain, type NavItem } from "./nav-main";
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

const baseNavItems: NavItem[] = [
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
    title: "Capabilities",
    icon: Boxes,
    items: [
      {
        title: "Tools",
        url: "/tools",
        icon: Wrench,
      },
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
    ],
  },
];

export function AppSidebar({ ...props }: React.ComponentProps<typeof Sidebar>) {
  const { isDevAdmin, isBusinessAdmin } = useUserRole();
  const [mounted, setMounted] = React.useState(false);

  React.useEffect(() => {
    setMounted(true);
  }, []);

  const navItems = React.useMemo(() => {
    const items = [...baseNavItems];
    // Defer role-gated items until after mount to avoid SSR/client mismatch
    if (mounted) {
      // Usage is visible to dev_admin and business_admin
      if (isDevAdmin || isBusinessAdmin) {
        items.push({
          title: "Usage",
          url: "/usage",
          icon: BarChart3,
        });
      }
      // Admin is visible to dev_admin only
      if (isDevAdmin) {
        items.push({
          title: "Admin",
          url: "/admin",
          icon: Shield,
        });
      }
    }
    return items;
  }, [mounted, isDevAdmin, isBusinessAdmin]);

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
