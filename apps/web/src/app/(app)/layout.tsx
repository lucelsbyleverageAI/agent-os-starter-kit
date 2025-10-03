import type { Metadata } from "next";
import "../globals.css";
import { Inter } from "next/font/google";
import React from "react";
import { DevTools } from "@/components/DevTools";
import { DOCS_LINK } from "@/constants";
import { NotificationsProvider } from "@/providers/Notifications";
import { SidebarLayout } from "@/components/sidebar";

const _inter = Inter({
  subsets: ["latin"],
  preload: true,
  display: "swap",
});

export const metadata: Metadata = {
  title: "AgentOS",
  description: "AgentOS - Your AI Agent Platform",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const isDemoApp = process.env.NEXT_PUBLIC_DEMO_APP === "true";
  return (
    <div className="relative h-full w-full">
      <DevTools />
      {isDemoApp && (
        <div className="fixed top-0 right-0 left-0 z-10 bg-[#CFC8FE] py-2 text-center text-black shadow-md">
          You're currently using the demo application. To use your own agents,
          and run in production, check out the{" "}
          <a
            className="underline underline-offset-2"
            href={DOCS_LINK}
            target="_blank"
            rel="noopener noreferrer"
          >
            documentation
          </a>
        </div>
      )}
      <NotificationsProvider>
        <React.Suspense fallback={<div className="flex h-full w-full items-center justify-center">Loading...</div>}>
          <SidebarLayout>
            {children}
          </SidebarLayout>
        </React.Suspense>
      </NotificationsProvider>
    </div>
  );
}
