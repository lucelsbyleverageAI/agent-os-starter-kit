"use client";

import React, { useState } from "react";
import { AppHeader } from "@/components/app-header";
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbList,
  BreadcrumbPage,
} from "@/components/ui/breadcrumb";
import { PageHeader } from "@/components/ui/page-header";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { useNotifications } from "@/hooks/use-notifications";
import { NotificationInfo, NotificationType } from "@/types/notification";
import { 
  User, 
  FileIcon, 
  BrainIcon, 
  Check, 
  X, 
  Bell
} from "lucide-react";
import { notify } from "@/utils/toast";
import { notificationMessages } from "@/utils/toast-messages";

const NOTIFICATION_TYPE_ICONS: Record<NotificationType, React.ReactNode> = {
  graph_share: <BrainIcon className="h-5 w-5" />,
  assistant_share: <User className="h-5 w-5" />,
  collection_share: <FileIcon className="h-5 w-5" />,
};

const NOTIFICATION_TYPE_LABELS: Record<NotificationType, string> = {
  graph_share: "Graph Access",
  assistant_share: "Assistant Share",
  collection_share: "Collection Share",
};

/**
 * The /notifications page.
 * Contains the full interface for managing notifications.
 */
export default function NotificationsPage(): React.ReactNode {
  const { 
    notifications,
    pendingNotifications,
    acceptedNotifications,
    rejectedNotifications,
    isLoading,
    acceptNotification,
    rejectNotification
  } = useNotifications();

  const [processingIds, setProcessingIds] = useState<Set<string>>(new Set());

  const handleAccept = async (notificationId: string) => {
    setProcessingIds(prev => new Set(prev).add(notificationId));
    try {
      await acceptNotification(notificationId);
      const message = notificationMessages.accept.success();
      notify.success(message.title, { key: message.key });
    } catch (_error) {
      const message = notificationMessages.accept.error();
      notify.error(message.title, { 
        description: message.description,
        key: message.key 
      });
    } finally {
      setProcessingIds(prev => {
        const newSet = new Set(prev);
        newSet.delete(notificationId);
        return newSet;
      });
    }
  };

  const handleReject = async (notificationId: string) => {
    setProcessingIds(prev => new Set(prev).add(notificationId));
    try {
      await rejectNotification(notificationId);
      const message = notificationMessages.reject.success();
      notify.success(message.title, { key: message.key });
    } catch (_error) {
      const message = notificationMessages.reject.error();
      notify.error(message.title, { 
        description: message.description,
        key: message.key 
      });
    } finally {
      setProcessingIds(prev => {
        const newSet = new Set(prev);
        newSet.delete(notificationId);
        return newSet;
      });
    }
  };

  const getSenderName = (notification: NotificationInfo) => {
    return notification.sender_display_name || notification.sender_user_id || "Unknown User";
  };

  const NotificationCard = ({ notification }: { notification: NotificationInfo }) => {
    const isProcessing = processingIds.has(notification.id);
    const isPending = notification.status === "pending";

    return (
      <Card className="mb-3 p-4">
        <CardContent className="p-0">
          {/* Header with icon and title */}
          <div className="flex items-center gap-2 mb-3">
            <div className="p-1.5 rounded-md bg-muted/50 flex-shrink-0">
              {NOTIFICATION_TYPE_ICONS[notification.type]}
            </div>
            <span className="font-medium text-sm">
              {NOTIFICATION_TYPE_LABELS[notification.type]}
            </span>
          </div>

          {/* Details */}
          <div className="mb-4 text-sm text-muted-foreground">
            <div className="mb-1">
              <span className="font-medium text-foreground">{notification.resource_name}</span> - {notification.permission_level}
            </div>
            <div>
              From {getSenderName(notification)}
            </div>
            {notification.resource_description && (
              <div className="mt-1 text-xs">
                {notification.resource_description}
              </div>
            )}
          </div>

          {/* Actions and Status */}
          {isPending && (
            <div className="flex gap-2">
              <Button
                size="sm"
                onClick={() => handleAccept(notification.id)}
                disabled={isProcessing}
                className="h-8 px-3 text-xs"
              >
                <Check className="h-3 w-3 mr-1" />
                Accept
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={() => handleReject(notification.id)}
                disabled={isProcessing}
                className="h-8 px-3 text-xs"
              >
                <X className="h-3 w-3 mr-1" />
                Reject
              </Button>
            </div>
          )}

          {notification.status === "accepted" && (
            <div className="flex items-center gap-1 text-green-600 text-xs">
              <Check className="h-3 w-3" />
              <span>Accepted</span>
            </div>
          )}

          {notification.status === "rejected" && (
            <div className="flex items-center gap-1 text-red-600 text-xs">
              <X className="h-3 w-3" />
              <span>Rejected</span>
            </div>
          )}

          {notification.status === "expired" && (
            <div className="flex items-center gap-1 text-gray-500 text-xs">
              <Bell className="h-3 w-3" />
              <span>Expired</span>
            </div>
          )}
        </CardContent>
      </Card>
    );
  };

  const EmptyState = ({ message }: { message: string }) => (
    <div className="text-center py-12">
      <div className="text-muted-foreground">{message}</div>
    </div>
  );

  return (
    <React.Suspense fallback={<div>Loading...</div>}>
      <AppHeader>
        <Breadcrumb>
          <BreadcrumbList>
            <BreadcrumbItem>
              <BreadcrumbPage>Notifications</BreadcrumbPage>
            </BreadcrumbItem>
          </BreadcrumbList>
        </Breadcrumb>
      </AppHeader>
      
      <div className="container mx-auto px-4 py-6">
        <PageHeader
          title="Notifications"
          description="Manage your sharing requests and permissions"
        />
        
        <div className="mt-6">
          <Tabs defaultValue="pending" className="w-full">
            <TabsList className="grid w-full grid-cols-4">
              <TabsTrigger value="pending">
                Pending ({pendingNotifications.length})
              </TabsTrigger>
              <TabsTrigger value="accepted">
                Accepted ({acceptedNotifications.length})
              </TabsTrigger>
              <TabsTrigger value="rejected">
                Rejected ({rejectedNotifications.length})
              </TabsTrigger>
              <TabsTrigger value="all">
                All ({notifications.length})
              </TabsTrigger>
            </TabsList>
            
            <TabsContent value="pending" className="mt-6">
              {isLoading ? (
                <div className="text-center py-6">Loading notifications...</div>
              ) : pendingNotifications.length === 0 ? (
                <EmptyState message="No pending notifications" />
              ) : (
                <div>
                  {pendingNotifications.map((notification) => (
                    <NotificationCard key={notification.id} notification={notification} />
                  ))}
                </div>
              )}
            </TabsContent>
            
            <TabsContent value="accepted" className="mt-6">
              {isLoading ? (
                <div className="text-center py-6">Loading notifications...</div>
              ) : acceptedNotifications.length === 0 ? (
                <EmptyState message="No accepted notifications" />
              ) : (
                <div>
                  {acceptedNotifications.map((notification) => (
                    <NotificationCard key={notification.id} notification={notification} />
                  ))}
                </div>
              )}
            </TabsContent>
            
            <TabsContent value="rejected" className="mt-6">
              {isLoading ? (
                <div className="text-center py-6">Loading notifications...</div>
              ) : rejectedNotifications.length === 0 ? (
                <EmptyState message="No rejected notifications" />
              ) : (
                <div>
                  {rejectedNotifications.map((notification) => (
                    <NotificationCard key={notification.id} notification={notification} />
                  ))}
                </div>
              )}
            </TabsContent>
            
            <TabsContent value="all" className="mt-6">
              {isLoading ? (
                <div className="text-center py-6">Loading notifications...</div>
              ) : notifications.length === 0 ? (
                <EmptyState message="No notifications yet" />
              ) : (
                <div>
                  {notifications.map((notification) => (
                    <NotificationCard key={notification.id} notification={notification} />
                  ))}
                </div>
              )}
            </TabsContent>
          </Tabs>
        </div>
      </div>
    </React.Suspense>
  );
} 