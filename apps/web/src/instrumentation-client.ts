// This file configures the initialization of Sentry on the client.
// The added config here will be used whenever a users loads a page in their browser.
// https://docs.sentry.io/platforms/javascript/guides/nextjs/

import * as Sentry from "@sentry/nextjs";

const dsn =
  process.env.NEXT_PUBLIC_SENTRY_DSN_WEB ||
  process.env.NEXT_PUBLIC_SENTRY_DSN ||
  process.env.SENTRY_DSN_WEB ||
  process.env.SENTRY_DSN;

if (dsn) {
  Sentry.init({
    dsn,
    integrations: [
      Sentry.replayIntegration(),
      Sentry.consoleLoggingIntegration({ levels: ["log", "warn", "error", "info", "debug"] }),
    ],
    tracesSampleRate: Number(process.env.SENTRY_TRACES_SAMPLE_RATE ?? "0.1"),
    enableLogs: process.env.NODE_ENV !== "production",
    replaysSessionSampleRate: Number(process.env.SENTRY_REPLAYS_SESSION_SAMPLE_RATE ?? "0"),
    replaysOnErrorSampleRate: Number(process.env.SENTRY_REPLAYS_ON_ERROR_SAMPLE_RATE ?? "1.0"),
    debug: false,
  });

  // Redirect stray console.* to Sentry logs in all environments when Sentry is enabled
  const original = { ...console };
  console.log = (...args) => {
    Sentry.logger.info(args.map(String).join(" "));
    if (process.env.NODE_ENV !== "production") original.log(...args);
  };
  // Note: console.info redirection removed due to linting restrictions
  console.warn = (...args) => {
    Sentry.logger.warn(args.map(String).join(" "));
    if (process.env.NODE_ENV !== "production") original.warn(...args);
  };
  console.error = (...args) => {
    Sentry.logger.error(args.map(String).join(" "));
    if (process.env.NODE_ENV !== "production") original.error(...args);
  };
  // Note: console.debug redirection removed due to linting restrictions

  if (process.env.NODE_ENV !== "production") {
    // Expose Sentry globally in development for easy console testing
    (globalThis as any).Sentry = Sentry;
  }
}

export const onRouterTransitionStart = Sentry.captureRouterTransitionStart;