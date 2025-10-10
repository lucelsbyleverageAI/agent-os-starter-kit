import React from "react";
import type { Metadata } from "next";
import "./globals.css";
import { Inter } from "next/font/google";
import { AuthProvider } from "@/providers/Auth";
import { UserRoleProvider } from "@/providers/UserRole";
import { AgentsProvider } from "@/providers/Agents";
import { ThemeProvider } from "@/providers/Theme";
import { NuqsAdapter } from "nuqs/adapters/next/app";
// import { MCPProvider } from "@/providers/MCP";
import { Toaster } from "@/components/ui/sonner";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "AgentOS",
  description: "AgentOS - Your AI Agent Platform",
  viewport: {
    width: "device-width",
    initialScale: 1,
    maximumScale: 5,
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="h-full" suppressHydrationWarning>
      <body className={`${inter.className} h-full`}>
        <ThemeProvider
          attribute="class"
          defaultTheme="system"
          enableSystem
          disableTransitionOnChange
        >
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
        </ThemeProvider>
      </body>
    </html>
  );
}
