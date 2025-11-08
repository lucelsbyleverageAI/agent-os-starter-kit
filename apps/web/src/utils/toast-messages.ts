/**
 * Centralised toast message catalogue for consistent copy across the application.
 * Uses British English spelling and consistent tone/punctuation.
 */

// Agent-related messages
export const agentMessages = {
  create: {
    success: (name: string) => ({
      title: "Agent created successfully!",
      description: `"${name}" is now available in your agents list.`,
      key: `agent:create:${name}`,
    }),
    successWithWarming: (name: string) => ({
      title: "Agent created successfully!",
      description: `"${name}" is now available. Configuration options are being prepared and will be available shortly.`,
      key: `agent:create:${name}`,
    }),
    error: () => ({
      title: "Failed to create agent",
      description: "Please try again or contact support if the problem persists.",
      key: "agent:create:error",
    }),
    registrationWarning: () => ({
      title: "Agent created with limited setup",
      description: "The agent was created but permission setup failed. You may need to refresh the page.",
    }),
  },
  update: {
    success: (name: string) => ({
      title: "Agent updated successfully!",
      description: `"${name}" has been saved with your changes.`,
      key: `agent:update:${name}`,
    }),
    error: () => ({
      title: "Failed to update agent",
      description: "Please try again or contact support if the problem persists.",
      key: "agent:update:error",
    }),
  },
  delete: {
    success: () => ({
      title: "Agent deleted successfully",
      description: "The agent has been permanently removed.",
      key: "agent:delete:success",
    }),
    error: () => ({
      title: "Failed to delete agent",
      description: "Please try again or contact support if the problem persists.",
      key: "agent:delete:error",
    }),
  },
  revoke: {
    success: () => ({
      title: "Access revoked successfully",
      description: "You no longer have access to this agent.",
      key: "agent:revoke:success",
    }),
    error: () => ({
      title: "Failed to revoke access",
      description: "Please try again or contact support if the problem persists.",
      key: "agent:revoke:error",
    }),
  },
  duplicate: {
    success: (name: string) => ({
      title: "Agent duplicated successfully!",
      description: `"${name}" has been created.`,
      key: `agent:duplicate:${name}`,
    }),
    error: () => ({
      title: "Failed to duplicate agent",
      description: "Please try again or contact support if the problem persists.",
      key: "agent:duplicate:error",
    }),
  },
  fetch: {
    error: () => ({
      title: "Failed to load agent",
      description: "Please refresh the page or try again later.",
      key: "agent:fetch:error",
    }),
  },
  refresh: {
    success: () => ({
      title: "Agents refreshed successfully",
      description: "Your agents list has been updated.",
      key: "agents:refresh:success",
    }),
    error: (error?: string) => ({
      title: "Failed to refresh agents",
      description: error || "Please try again or refresh the page.",
      key: "agents:refresh:error",
    }),
  },
  config: {
    saveSuccess: () => ({
      title: "Agent configuration saved successfully",
      description: "Your changes have been applied.",
      key: "agent:config:save:success",
    }),
    saveError: () => ({
      title: "Failed to update agent configuration",
      description: "Please try again or contact support if the problem persists.",
      key: "agent:config:save:error",
    }),
    fetchError: () => ({
      title: "Failed to get agent configuration",
      description: "Please refresh the page or try again later.",
      key: "agent:config:fetch:error",
    }),
  },
  validation: {
    nameDescriptionRequired: () => ({
      title: "Name and description are required",
      description: "Please fill in both fields before continuing.",
      key: "agent:validation:name-description",
    }),
  },
};

// Thread-related messages
export const threadMessages = {
  delete: {
    success: () => ({
      title: "Thread deleted",
      description: "The thread has been successfully deleted.",
      key: "thread:delete:success",
    }),
    error: (error?: string) => ({
      title: "Sorry, there's been an error",
      description: error || "Failed to delete thread. Please try again.",
      key: "thread:delete:error",
    }),
  },
  ignore: {
    success: () => ({
      title: "Thread ignored successfully",
      description: "The thread has been marked as ignored.",
      key: "thread:ignore:success",
    }),
    error: () => ({
      title: "Failed to ignore thread",
      description: "Please try again.",
      key: "thread:ignore:error",
    }),
  },
  resolve: {
    success: () => ({
      title: "Thread marked as resolved",
      description: "The thread has been successfully resolved.",
      key: "thread:resolve:success",
    }),
    error: () => ({
      title: "Failed to mark thread as resolved",
      description: "Please try again.",
      key: "thread:resolve:error",
    }),
  },
  fetch: {
    error: () => ({
      title: "Failed to load threads",
      description: "Please try again or refresh the page.",
      key: "threads:fetch:error",
    }),
  },
  stream: {
    error: () => ({
      title: "An error occurred. Please try again.",
      key: "thread:stream:error",
    }),
  },
  response: {
    submitSuccess: () => ({
      title: "Response submitted successfully",
      key: "thread:response:submit:success",
    }),
    submitError: () => ({
      title: "Failed to submit response",
      key: "thread:response:submit:error",
    }),
  },
};

// Notification-related messages
export const notificationMessages = {
  accept: {
    success: () => ({
      title: "Permission request accepted",
      key: "notification:accept:success",
    }),
    error: () => ({
      title: "Failed to accept permission request",
      description: "Please try again.",
      key: "notification:accept:error",
    }),
  },
  reject: {
    success: () => ({
      title: "Permission request rejected",
      key: "notification:reject:success",
    }),
    error: () => ({
      title: "Failed to reject permission request",
      description: "Please try again.",
      key: "notification:reject:error",
    }),
  },
};

// Knowledge/Collection-related messages
export const knowledgeMessages = {
  collection: {
    create: {
      success: (name: string) => ({
        title: "Collection created successfully",
        description: `"${name}" is now available.`,
        key: `collection:create:${name}`,
      }),
      successWithSharing: (name: string, sharedCount: number) => ({
        title: "Collection created and shared",
        description: `"${name}" has been shared with ${sharedCount} team member${sharedCount === 1 ? '' : 's'}.`,
        key: `collection:create:${name}`,
      }),
      warning: (name: string) => ({
        title: "Collection could not be created",
        description: `A collection named '${name}' likely already exists.`,
        key: `collection:create:warning:${name}`,
      }),
      error: () => ({
        title: "Failed to create collection",
        description: "Please try again.",
        key: "collection:create:error",
      }),
    },
    update: {
      success: (name: string) => ({
        title: "Collection updated successfully",
        description: `"${name}" has been saved with your changes.`,
        key: `collection:update:${name}`,
      }),
      error: () => ({
        title: "Failed to update collection",
        description: "Please try again.",
        key: "collection:update:error",
      }),
    },
    delete: {
      success: () => ({
        title: "Collection deleted successfully",
        description: "The collection has been permanently removed.",
        key: "collection:delete:success",
      }),
      error: () => ({
        title: "Failed to delete collection",
        description: "Please try again.",
        key: "collection:delete:error",
      }),
    },
  },
  document: {
    delete: {
      success: () => ({
        title: "Document deleted successfully",
        key: "document:delete:success",
      }),
      error: () => ({
        title: "Failed to delete document",
        description: "Please try again.",
        key: "document:delete:error",
      }),
    },
    fetch: {
      error: () => ({
        title: "Failed to load documents",
        description: "Please try again or refresh the page.",
        key: "documents:fetch:error",
      }),
    },
  },
};

// Admin-related messages
export const adminMessages = {
  initialize: {
    success: (operationsCount: number, duration: number) => ({
      title: "Platform initialised successfully!",
      description: `Completed ${operationsCount} operations in ${duration}ms.`,
      key: "admin:initialize:success",
    }),
    preview: (operationsCount: number, scenariosCount: number) => ({
      title: "Platform initialisation preview completed",
      description: `Would perform ${operationsCount} operations across ${scenariosCount} scenarios.`,
      key: "admin:initialize:preview",
    }),
    error: (error: string) => ({
      title: "Failed to initialise platform",
      description: error,
      key: "admin:initialize:error",
    }),
  },
  reverseSync: {
    success: (total: number, recreated: number, duration: number) => ({
      title: "Assistants recreated successfully!",
      description: `Recreated ${recreated} of ${total} assistants in LangGraph in ${duration}ms.`,
      key: "admin:reverse-sync:success",
    }),
    partial: (total: number, recreated: number, failed: number) => ({
      title: "Assistants partially recreated",
      description: `Recreated ${recreated} of ${total} assistants (${failed} failed). Check logs for details.`,
      key: "admin:reverse-sync:partial",
    }),
    error: (error: string) => ({
      title: "Failed to reverse sync assistants",
      description: error,
      key: "admin:reverse-sync:error",
    }),
  },
  permissionDenied: () => ({
    title: "Permission denied",
    description: "Only dev admins can perform this action.",
    key: "admin:permission:denied",
  }),
};

// Authentication-related messages
export const authMessages = {
  noSession: () => ({
    title: "Authentication required",
    description: "Please sign in to continue.",
    key: "auth:no-session",
  }),
  noAccessToken: () => ({
    title: "No access token found",
    description: "Please sign in again.",
    key: "auth:no-access-token",
  }),
  noUserId: () => ({
    title: "User ID not found",
    description: "Please sign in again.",
    key: "auth:no-user-id",
  }),
};

// Generic messages
export const genericMessages = {
  limitExceeded: (limit: number, action: string) => ({
    title: "Limit exceeded",
    description: `Cannot ${action} more than ${limit} items at a time.`,
    key: `generic:limit:${action}:${limit}`,
  }),
  notFound: (item: string) => ({
    title: `${item} not found`,
    description: "The requested item could not be found.",
    key: `generic:not-found:${item.toLowerCase()}`,
  }),
  somethingWentWrong: () => ({
    title: "Something went wrong",
    description: "Please try again or contact support if the problem persists.",
    key: "generic:something-wrong",
  }),
};
