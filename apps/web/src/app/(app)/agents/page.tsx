"use client";

import AgentsInterface from "@/features/agents";
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbList,
  BreadcrumbPage,
} from "@/components/ui/breadcrumb";

import React from "react";
import { AppHeader } from "@/components/app-header";

/**
 * The /agents page.
 * Contains the list of all agents the user has access to.
 */
export default function AgentsPage(): React.ReactNode {
  return (
    <React.Suspense fallback={<div>Loading (layout)...</div>}>
      <AppHeader>
        <Breadcrumb>
          <BreadcrumbList>
            <BreadcrumbItem>
              <BreadcrumbPage>Agents</BreadcrumbPage>
            </BreadcrumbItem>
          </BreadcrumbList>
        </Breadcrumb>
      </AppHeader>
      <AgentsInterface />
    </React.Suspense>
  );
}
