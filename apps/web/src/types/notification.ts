/**
 * Notification types for the sharing system
 */

export type NotificationStatus = "pending" | "accepted" | "rejected" | "expired";

export type NotificationType = "graph_share" | "assistant_share" | "collection_share";

export interface NotificationInfo {
  id: string;
  recipient_user_id: string;
  type: NotificationType;
  resource_id: string;
  resource_type: string;
  permission_level: string;
  sender_user_id: string;
  sender_display_name?: string;
  status: NotificationStatus;
  created_at: string;
  updated_at: string;
  responded_at?: string;
  expires_at: string;
  resource_name: string;
  resource_description?: string;
}

export interface NotificationsListResponse {
  notifications: NotificationInfo[];
  total_count: number;
  pending_count: number;
}

export interface NotificationUnreadCountResponse {
  unread_count: number;
}

export interface NotificationActionRequest {
  reason?: string;
}

export interface NotificationActionResponse {
  notification_id: string;
  action: "accepted" | "rejected";
  success: boolean;
  message: string;
  permission_granted?: boolean;
}

/**
 * Notification context for providers
 */
export interface NotificationContextType {
  notifications: NotificationInfo[];
  unreadCount: number;
  isLoading: boolean;
  isError: boolean;
  error: string | null;
  
  // Actions
  fetchNotifications: () => Promise<void>;
  acceptNotification: (notificationId: string, reason?: string) => Promise<boolean>;
  rejectNotification: (notificationId: string, reason?: string) => Promise<boolean>;
  markAsRead: (notificationId: string) => void;
  
  // Filtering
  pendingNotifications: NotificationInfo[];
  acceptedNotifications: NotificationInfo[];
  rejectedNotifications: NotificationInfo[];
  
  // Debug
  debugCacheState: () => void;
} 