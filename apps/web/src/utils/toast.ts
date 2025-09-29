import { toast as sonnerToast } from "sonner";

// Deduplication mechanism
const recentToasts = new Map<string, number>();
const DEDUPE_WINDOW = 3000; // 3 seconds

interface ToastOptions {
  key?: string;
  title?: string;
  description?: string | React.ReactNode;
  duration?: number;
  richColors?: boolean;
  closeButton?: boolean;
}

interface NotifyOptions extends Omit<ToastOptions, 'key'> {
  key?: string;
}

// Clean up old entries from the deduplication map
function cleanupRecentToasts() {
  const now = Date.now();
  for (const [key, timestamp] of recentToasts.entries()) {
    if (now - timestamp > DEDUPE_WINDOW) {
      recentToasts.delete(key);
    }
  }
}

// Check if a toast should be deduplicated
function shouldDedupe(key?: string): boolean {
  if (!key) return false;
  
  cleanupRecentToasts();
  const now = Date.now();
  
  if (recentToasts.has(key)) {
    const lastShown = recentToasts.get(key)!;
    if (now - lastShown < DEDUPE_WINDOW) {
      return true; // Skip this toast
    }
  }
  
  recentToasts.set(key, now);
  return false;
}

// Default options for different toast types
const DEFAULT_OPTIONS = {
  richColors: true,
  closeButton: true,
} as const;

const TYPE_DEFAULTS = {
  success: { duration: 3000 },
  error: { duration: 7000 },
  warning: { duration: 5000 },
  info: { duration: 4000 },
} as const;

function createToast(
  type: 'success' | 'error' | 'warning' | 'info',
  message: string,
  options: NotifyOptions = {}
) {
  const { key, title, description, duration, richColors, closeButton, ...rest } = options;
  
  // Check for deduplication
  if (shouldDedupe(key)) {
    return;
  }
  
  const finalOptions = {
    ...DEFAULT_OPTIONS,
    ...TYPE_DEFAULTS[type],
    duration,
    richColors: richColors ?? DEFAULT_OPTIONS.richColors,
    closeButton: closeButton ?? DEFAULT_OPTIONS.closeButton,
    ...rest,
  };
  
  // If we have a title and description, show them properly
  if (title && description) {
    return sonnerToast[type](title, {
      description,
      ...finalOptions,
    });
  }
  
  // If we have a description but no title, use the message as title
  if (description && !title) {
    return sonnerToast[type](message, {
      description,
      ...finalOptions,
    });
  }
  
  // Just show the message
  return sonnerToast[type](message, finalOptions);
}

export const notify = {
  success: (message: string, options?: NotifyOptions) => 
    createToast('success', message, options),
  
  error: (message: string, options?: NotifyOptions) => 
    createToast('error', message, options),
  
  warning: (message: string, options?: NotifyOptions) => 
    createToast('warning', message, options),
  
  info: (message: string, options?: NotifyOptions) => 
    createToast('info', message, options),
  
  // Generic toast function for custom types
  toast: (message: string, options: ToastOptions & { type?: 'success' | 'error' | 'warning' | 'info' } = {}) => {
    const { type = 'info', key, ...restOptions } = options;
    return createToast(type, message, { key, ...restOptions });
  },
};

// Export the raw sonner toast for edge cases where the utility doesn't fit
export { sonnerToast as rawToast };
