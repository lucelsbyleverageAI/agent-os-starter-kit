"use client";

import SigninInterface from "@/features/signin";
import { Suspense } from "react";

export default function SigninPage() {
  return (
    <Suspense fallback={<div>Loading...</div>}>
      <SigninInterface />
    </Suspense>
  );
}
