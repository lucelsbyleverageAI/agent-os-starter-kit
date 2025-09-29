"use client";

import SignupInterface from "@/features/signup";
import { Suspense } from "react";

export default function SignupPage() {
  return (
    <Suspense fallback={<div>Loading...</div>}>
      <SignupInterface />
    </Suspense>
  );
}
