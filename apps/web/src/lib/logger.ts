import * as Sentry from "@sentry/nextjs";

function toMessage(args: unknown[]): string {
  return args
    .map((a) => {
      if (typeof a === "string") return a;
      try {
        return JSON.stringify(a);
      } catch {
        return String(a);
      }
    })
    .join(" ");
}

export const logger = {
  log: (...args: unknown[]) => {
    Sentry.logger.info(toMessage(args), { payload: args });
    if (process.env.NODE_ENV !== "production") {
      // Mirror to console only in development
       
      console.log(...args);
    }
  },

  warn: (...args: unknown[]) => {
    Sentry.logger.warn(toMessage(args), { payload: args });
    if (process.env.NODE_ENV !== "production") {
       
      console.warn(...args);
    }
  },

  error: (...args: unknown[]) => {
    const error = args.find((arg) => arg instanceof Error);
    if (error) {
      Sentry.captureException(error, {
        extra: {
          "Original Arguments": args.filter((arg) => !(arg instanceof Error)),
        },
      });
    } else {
      Sentry.logger.error(toMessage(args), { payload: args });
    }
    
    if (process.env.NODE_ENV !== "production") {
       
      console.error(...args);
    }
  },

  debug: (...args: unknown[]) => {
    Sentry.logger.debug?.(toMessage(args), { payload: args });
    // Intentionally do not mirror debug to console to keep noise low
  },
};

export function breadcrumb(category: string, data?: Record<string, unknown>, level: Sentry.SeverityLevel = "info") {
  Sentry.addBreadcrumb({ category, level, data });
}


