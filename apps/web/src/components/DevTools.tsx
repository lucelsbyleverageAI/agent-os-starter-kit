"use client";

import Script from "next/script";
import { useEffect, useState } from "react";

export function DevTools() {
  const [isClient, setIsClient] = useState(false);

  useEffect(() => {
    setIsClient(true);
  }, []);

  // Only render on client side and in development
  if (!isClient || process.env.NODE_ENV === "production") {
    return null;
  }

  return (
    <Script
      src="//unpkg.com/react-scan/dist/auto.global.js"
      strategy="afterInteractive"
      crossOrigin="anonymous"
    />
  );
} 