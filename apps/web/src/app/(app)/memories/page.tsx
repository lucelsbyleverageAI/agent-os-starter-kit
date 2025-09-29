"use client";

import MemoriesInterface from "@/features/memories";
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbList,
  BreadcrumbPage,
} from "@/components/ui/breadcrumb";

import React from "react";
import { AppHeader } from "@/components/app-header";
import { MemoriesProvider } from "@/features/memories/providers/Memories";

/**
 * The /memories page.
 * Contains the interface for managing AI memories.
 */
export default function MemoriesPage(): React.ReactNode {
  return (
    <React.Suspense fallback={<div>Loading (layout)...</div>}>
      <AppHeader>
        <Breadcrumb>
          <BreadcrumbList>
            <BreadcrumbItem>
              <BreadcrumbPage>Memories</BreadcrumbPage>
            </BreadcrumbItem>
          </BreadcrumbList>
        </Breadcrumb>
      </AppHeader>
      
      <MemoriesProvider>
        <MemoriesInterface />
      </MemoriesProvider>
    </React.Suspense>
  );
}
