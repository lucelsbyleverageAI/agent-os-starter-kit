"use client";

import { AdminFeature } from "@/features/admin";
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbList,
  BreadcrumbPage,
} from "@/components/ui/breadcrumb";

import { PageHeader } from "@/components/ui/page-header";
import { AppHeader } from "@/components/app-header";
import React from "react";

/**
 * The /admin page.
 * Contains the admin dashboard for managing public permissions.
 */
export default function AdminPage(): React.ReactNode {
  return (
    <React.Suspense fallback={<div>Loading (layout)...</div>}>
      <AppHeader>
        <Breadcrumb>
          <BreadcrumbList>
            <BreadcrumbItem>
              <BreadcrumbPage>Admin</BreadcrumbPage>
            </BreadcrumbItem>
          </BreadcrumbList>
        </Breadcrumb>
      </AppHeader>
      
      <div className="container mx-auto px-4 md:px-8 lg:px-12 py-6">
        <PageHeader
          title="Admin Dashboard"
          description="Manage public permissions for graphs, assistants, and collections"
        />
        
        <div className="mt-6">
          <AdminFeature />
        </div>
      </div>
    </React.Suspense>
  );
} 