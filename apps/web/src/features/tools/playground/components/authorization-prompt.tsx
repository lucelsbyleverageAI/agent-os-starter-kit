"use client";

import { Info } from "lucide-react";
import { Button } from "@/components/ui/button";

interface AuthorizationPromptProps {
  authUrl: string;
}

export function AuthorizationPrompt({ authUrl }: AuthorizationPromptProps) {
  const handleAuthorize = () => {
    window.open(authUrl, "_blank", "noopener,noreferrer");
  };

  return (
    <div className="flex flex-col items-center justify-center rounded-lg border border-blue-200 bg-blue-50 p-8 text-center w-full max-w-full">
      <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-blue-100">
        <Info className="h-6 w-6 text-blue-600" />
      </div>

      <h3 className="mb-2 text-lg font-semibold text-blue-900">
        Authorization is required. Please click the link to authorize.
      </h3>

      <p className="mb-4 text-sm text-blue-700">
        After authenticating, please run the tool again.
      </p>

      <Button
        onClick={handleAuthorize}
        className="mb-3 bg-blue-600 hover:bg-blue-700 text-white"
      >
        Authorize
      </Button>

      <div className="mt-2 max-w-full overflow-hidden">
        <a
          href={authUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="text-xs text-blue-600 hover:text-blue-800 underline break-all"
        >
          {authUrl}
        </a>
      </div>
    </div>
  );
}
