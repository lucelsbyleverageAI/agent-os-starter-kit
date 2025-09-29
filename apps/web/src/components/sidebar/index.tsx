"use client";

import { SidebarProvider, SidebarInset } from "@/components/ui/sidebar";
import { AppSidebar } from "./app-sidebar";
import { MCPProvider } from "@/providers/MCP";
import { KnowledgeProvider } from "@/features/knowledge/providers/Knowledge";

export function SidebarLayout({ children }: { children: React.ReactNode }) {
  return (
    <SidebarProvider>
      <MCPProvider>
        <KnowledgeProvider>
          <AppSidebar />
          <SidebarInset>{children}</SidebarInset>
        </KnowledgeProvider>
      </MCPProvider>
    </SidebarProvider>
  );
}
