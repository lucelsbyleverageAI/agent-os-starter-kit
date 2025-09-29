"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

export const AccessDeniedRedirect = () => {
  const router = useRouter();

  useEffect(() => {
    router.push("/");
  }, [router]);

  return null; // Or render a "Redirecting..." message
}; 