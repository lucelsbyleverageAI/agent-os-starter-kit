import React from "react";
import type { Metadata } from "next";
import "./globals.css";
import { Inter } from "next/font/google";
import { AuthProvider } from "@/providers/Auth";
import { UserRoleProvider } from "@/providers/UserRole";
import { AgentsProvider } from "@/providers/Agents";
import { NuqsAdapter } from "nuqs/adapters/next/app";
// import { MCPProvider } from "@/providers/MCP";
import { Toaster } from "@/components/ui/sonner";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "AgentOS",
  description: "AgentOS - Your AI Agent Platform",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className={inter.className}>
        <React.Suspense fallback={<div />}> 
          <NuqsAdapter>
            <AuthProvider>
              <UserRoleProvider>
                <AgentsProvider>
                  {/* <MCPProvider> */}
                    {children}
                    <Toaster />
                  {/* </MCPProvider> */}
                </AgentsProvider>
              </UserRoleProvider>
            </AuthProvider>
          </NuqsAdapter>
        </React.Suspense>
      </body>
    </html>
  );
}
