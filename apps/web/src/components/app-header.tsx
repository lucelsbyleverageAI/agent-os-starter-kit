"use client";

import React from "react";
import { SidebarTrigger } from "@/components/ui/sidebar";
import { NotificationBell } from "@/components/notification-bell";

interface AppHeaderProps {
  children?: React.ReactNode;
  actions?: React.ReactNode;
}

export function AppHeader({ children, actions }: AppHeaderProps) {
  return (
    <header className="flex h-16 shrink-0 items-center gap-2 transition-[width,height] ease-linear group-has-[[data-collapsible=icon]]/sidebar-wrapper:h-12">
      <div className="flex items-center gap-2 px-4 flex-1">
        <SidebarTrigger className="-ml-1" />
        {children}
      </div>
      <div className="flex items-center gap-2 px-4">
        {actions}
        <NotificationBell />
      </div>
    </header>
  );
} 