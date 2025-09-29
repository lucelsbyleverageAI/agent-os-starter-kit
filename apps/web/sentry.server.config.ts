// This file configures the initialization of Sentry on the server.
// The config you add here will be used whenever the server handles a request.
// https://docs.sentry.io/platforms/javascript/guides/nextjs/

import * as Sentry from "@sentry/nextjs";

const dsn = process.env.SENTRY_DSN_WEB;

if (dsn) {
  Sentry.init({
    dsn,
    environment: process.env.SENTRY_ENVIRONMENT,
    tracesSampleRate: Number(process.env.SENTRY_TRACES_SAMPLE_RATE ?? "0.1"),
    enableLogs: process.env.NODE_ENV !== "production",
    debug: false,
    beforeSend(event) {
      const headers = (event.request && (event.request as any).headers) || undefined;
      if (headers && typeof headers === "object") {
        for (const key of Object.keys(headers)) {
          const k = key.toLowerCase();
          if (k.includes("authorization") || k.includes("api-key") || k.includes("token") || k === "cookie" || k === "x-supabase-access-token") {
            delete (headers as any)[key];
          }
        }
      }
      return event;
    },
  });
}
