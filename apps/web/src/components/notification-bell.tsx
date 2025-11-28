"use client";

import React, { useState } from "react";
import { Bell, Check, X, User, FileIcon, BrainIcon, Sparkles } from "lucide-react";
import { useNotifications } from "@/hooks/use-notifications";
import { TooltipIconButton } from "@/components/ui/tooltip-icon-button";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { Separator } from "@/components/ui/separator";
import { getScrollbarClasses } from "@/lib/scrollbar-styles";
import { cn } from "@/lib/utils";

import { NotificationInfo, NotificationType } from "@/types/notification";
import { toast } from "sonner";
import { useRouter } from "next/navigation";

const NOTIFICATION_TYPE_ICONS: Record<NotificationType, React.ReactNode> = {
  graph_share: <BrainIcon className="h-4 w-4" />,
  assistant_share: <User className="h-4 w-4" />,
  collection_share: <FileIcon className="h-4 w-4" />,
  skill_share: <Sparkles className="h-4 w-4" />,
};

const NOTIFICATION_TYPE_LABELS: Record<NotificationType, string> = {
  graph_share: "Graph Access",
  assistant_share: "Assistant Share",
  collection_share: "Collection Share",
  skill_share: "Skill Share",
};

interface NotificationItemProps {
  notification: NotificationInfo;
  onAccept: (id: string) => Promise<void>;
  onReject: (id: string) => Promise<void>;
}

function NotificationItem({ notification, onAccept, onReject }: NotificationItemProps) {
  const [isProcessing, setIsProcessing] = useState(false);

  const handleAccept = async () => {
    setIsProcessing(true);
    try {
      await onAccept(notification.id);
      toast.success("Permission request accepted");
    } catch (_error) {
      toast.error("Failed to accept permission request");
    } finally {
      setIsProcessing(false);
    }
  };

  const handleReject = async () => {
    setIsProcessing(true);
    try {
      await onReject(notification.id);
      toast.success("Permission request rejected");
    } catch (_error) {
      toast.error("Failed to reject permission request");
    } finally {
      setIsProcessing(false);
    }
  };

  const getSenderName = () => {
    return notification.sender_display_name || notification.sender_user_id || "Unknown User";
  };

  return (
    <div className="p-3 rounded-lg hover:bg-muted/50 transition-colors border border-border/50">
      {/* Header with icon and title */}
      <div className="flex items-center gap-2 mb-2">
        <div className="p-1.5 rounded-md bg-muted/50 flex-shrink-0">
          {NOTIFICATION_TYPE_ICONS[notification.type]}
        </div>
        <span className="font-medium text-xs">
          {NOTIFICATION_TYPE_LABELS[notification.type]}
        </span>
      </div>

      {/* Details */}
      <div className="mb-3 text-xs text-muted-foreground">
        <div className="mb-1">
          <span className="font-medium text-foreground">{notification.resource_name}</span> - {notification.permission_level}
        </div>
        <div>
          From {getSenderName()}
        </div>
      </div>

      {/* Actions */}
      {notification.status === "pending" && (
        <div className="flex gap-2">
          <Button
            size="sm"
            onClick={handleAccept}
            disabled={isProcessing}
            className="h-7 px-3 text-xs flex-1"
          >
            <Check className="h-3 w-3 mr-1" />
            Accept
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={handleReject}
            disabled={isProcessing}
            className="h-7 px-3 text-xs flex-1"
          >
            <X className="h-3 w-3 mr-1" />
            Reject
          </Button>
        </div>
      )}

      {notification.status === "accepted" && (
        <div className="flex items-center gap-1 text-green-600 text-xs">
          <Check className="h-3 w-3" />
          Accepted
        </div>
      )}

      {notification.status === "rejected" && (
        <div className="flex items-center gap-1 text-red-600 text-xs">
          <X className="h-3 w-3" />
          Rejected
        </div>
      )}

      {notification.status === "expired" && (
        <div className="flex items-center gap-1 text-gray-500 text-xs">
          <Bell className="h-3 w-3" />
          Expired
        </div>
      )}
    </div>
  );
}

export function NotificationBell() {
  const {
    pendingNotifications,
    unreadCount,
    isLoading,
    acceptNotification,
    rejectNotification,
    fetchNotifications: _fetchNotifications,
  } = useNotifications();

  const [isOpen, setIsOpen] = useState(false);
  const router = useRouter();

  const handleAccept = async (notificationId: string) => {
    await acceptNotification(notificationId);
    // No need to fetchNotifications - the provider handles state updates and cache invalidation
  };

  const handleReject = async (notificationId: string) => {
    await rejectNotification(notificationId);
    // No need to fetchNotifications - the provider handles state updates
  };

  return (
    <Popover open={isOpen} onOpenChange={setIsOpen}>
      <PopoverTrigger asChild>
        <div className="relative">
          <TooltipIconButton
            tooltip="Notifications"
            variant="ghost"
            size="icon"
            className="size-6"
          >
            <Bell className="h-4 w-4" />
          </TooltipIconButton>
          {unreadCount > 0 && (
            <Badge
              variant="destructive"
              className="absolute -top-1 -right-1 h-4 w-4 p-0 flex items-center justify-center text-xs"
            >
              {unreadCount > 99 ? "99+" : unreadCount}
            </Badge>
          )}
        </div>
      </PopoverTrigger>
      <PopoverContent 
        className="w-80 p-0" 
        align="end"
        side="bottom"
        sideOffset={8}
      >
        <div className="p-4 border-b">
          <div className="flex items-center justify-between">
            <h3 className="font-semibold">Notifications</h3>
            {unreadCount > 0 && (
              <Badge variant="secondary">{unreadCount} new</Badge>
            )}
          </div>
        </div>

        <div 
          className={cn(
            "max-h-96 p-2",
            pendingNotifications.length > 0 && "overflow-y-auto",
            pendingNotifications.length > 0 && getScrollbarClasses('y')
          )}
        >
          {isLoading ? (
            <div className="flex items-center justify-center py-8">
              <div className="text-sm text-muted-foreground">Loading...</div>
            </div>
          ) : pendingNotifications.length > 0 ? (
            <div className="space-y-2">
              {pendingNotifications.map((notification) => (
                <NotificationItem
                  key={notification.id}
                  notification={notification}
                  onAccept={handleAccept}
                  onReject={handleReject}
                />
              ))}
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center py-8 text-center">
              <Bell className="h-8 w-8 text-muted-foreground mb-2" />
              <p className="text-sm text-muted-foreground">
                No new notifications
              </p>
              <p className="text-xs text-muted-foreground mt-1">
                You're all caught up!
              </p>
            </div>
          )}
        </div>

        <>
          <Separator />
          <div className="p-2">
            <Button
              variant="ghost"
              size="sm"
              className="w-full"
              onClick={() => {
                router.push('/notifications');
                setIsOpen(false);
              }}
            >
              View all notifications
            </Button>
          </div>
        </>
      </PopoverContent>
    </Popover>
  );
} 