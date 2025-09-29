"use client";

import ToolsInterface from "@/features/tools";
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbList,
  BreadcrumbPage,
} from "@/components/ui/breadcrumb";

import { PageHeader } from "@/components/ui/page-header";
import { MinimalistBadgeWithText } from "@/components/ui/minimalist-badge";
import { useMCPContext } from "@/providers/MCP";
import { Hash } from "lucide-react";
import React from "react";
import { AppHeader } from "@/components/app-header";

/**
 * The /tools page.
 * Contains the list of tools the user has access to.
 */
export default function ToolsPage(): React.ReactNode {
  const { tools, loading, cursor } = useMCPContext();
  
  const toolsCount = tools.length;
  const hasMore = !!cursor;

  return (
    <React.Suspense fallback={<div>Loading (layout)...</div>}>
      <AppHeader>
        <Breadcrumb>
          <BreadcrumbList>
            <BreadcrumbItem>
              <BreadcrumbPage>Tools</BreadcrumbPage>
            </BreadcrumbItem>
          </BreadcrumbList>
        </Breadcrumb>
      </AppHeader>
      
      <div className="container mx-auto px-4 py-6">
        <PageHeader
          title="Tools"
          description="Browse, inspect and test available tools for your agents"
          badge={
            !loading && (
              <MinimalistBadgeWithText
                icon={Hash}
                text={`Number of Available Tools: ${toolsCount}${hasMore ? "+" : ""}`}
              />
            )
          }
        />
        
        <div className="mt-6">
          <ToolsInterface />
        </div>
      </div>
    </React.Suspense>
  );
}
