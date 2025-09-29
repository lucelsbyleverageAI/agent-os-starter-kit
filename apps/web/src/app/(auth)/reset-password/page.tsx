"use client";

import ResetPasswordInterface from "@/features/reset-password";
import { Suspense } from "react";

export default function ResetPasswordPage() {
  return (
    <Suspense fallback={<div>Loading...</div>}>
      <ResetPasswordInterface />
    </Suspense>
  );
}
