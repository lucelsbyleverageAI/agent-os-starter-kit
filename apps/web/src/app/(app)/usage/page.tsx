"use client";

import UsageInterface from "@/features/usage";
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbList,
  BreadcrumbPage,
} from "@/components/ui/breadcrumb";
import React from "react";
import { AppHeader } from "@/components/app-header";

/**
 * The /usage page.
 * Contains the interface for monitoring OpenRouter API usage and costs.
 */
export default function UsagePage(): React.ReactNode {
  return (
    <React.Suspense fallback={<div>Loading...</div>}>
      <AppHeader>
        <Breadcrumb>
          <BreadcrumbList>
            <BreadcrumbItem>
              <BreadcrumbPage>Usage & Costs</BreadcrumbPage>
            </BreadcrumbItem>
          </BreadcrumbList>
        </Breadcrumb>
      </AppHeader>

      <UsageInterface />
    </React.Suspense>
  );
}
