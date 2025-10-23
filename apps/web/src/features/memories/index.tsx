"use client";

import type React from "react";
import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/ui/page-header";
import { MinimalistBadgeWithText } from "@/components/ui/minimalist-badge";
import { useMemoriesContext } from "./providers/Memories";
import { MemoriesTable } from "./components/memories-table";
import { AddMemoryDialog } from "./components/add-memory-dialog";
import { Brain, Plus } from "lucide-react";

export default function MemoriesInterface() {
  const {
    memories,
    loading,
    initialSearchExecuted,
    fetchMemories,
  } = useMemoriesContext();

  const [showAddMemoryDialog, setShowAddMemoryDialog] = useState(false);
  const [serviceError, setServiceError] = useState<string | null>(null);

  const handleMemoryChanged = async () => {
    // Refresh memories when a memory is added, updated, or deleted
    await fetchMemories();
  };

  // Check service health on mount
  useEffect(() => {
    const checkServiceHealth = async () => {
      try {
        const response = await fetch('/api/langconnect/memory/health', {
          method: 'GET',
          credentials: 'include',
        });
        
        if (response.ok) {
          const result = await response.json();
          if (!result.service_available) {
            setServiceError(result.message || 'Memory service is not available');
          }
        } else {
          setServiceError('Unable to check memory service status');
        }
      } catch (error) {
        console.error('Health check failed:', error);
        setServiceError('Memory service health check failed');
      }
    };

    if (initialSearchExecuted && memories.length === 0) {
      checkServiceHealth();
    }
  }, [initialSearchExecuted, memories.length]);

  // Show service error if memory service is not available
  if (serviceError && initialSearchExecuted && memories.length === 0) {
    return (
      <div className="container mx-auto px-4 md:px-8 lg:px-12 py-6">
        <PageHeader
          title="Memories"
          description="Manage your AI memories that help agents remember information about you across conversations"
        />
        
        <div className="mt-6 flex flex-col items-center justify-center rounded-lg border border-dashed p-8 text-center">
          <div className="bg-muted mx-auto flex h-20 w-20 items-center justify-center rounded-full">
            <Brain className="text-muted-foreground h-10 w-10" />
          </div>
          <h2 className="mt-6 text-xl font-semibold">Memory Service Unavailable</h2>
          <p className="text-muted-foreground mt-2 mb-4 text-center max-w-md">
            {serviceError}
          </p>
          <p className="text-sm text-muted-foreground">
            Please check your server configuration or contact your administrator.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="container mx-auto px-4 md:px-8 lg:px-12 py-6">
      <PageHeader
        title="Memories"
        description="Manage your AI memories that help agents remember information about you across conversations"
        badge={
          initialSearchExecuted && (
            <MinimalistBadgeWithText
              icon={Brain}
              text={`${memories.length} ${memories.length === 1 ? 'memory' : 'memories'}`}
              tooltip={`You have ${memories.length} memories stored`}
            />
          )
        }
        action={
          <Button onClick={() => setShowAddMemoryDialog(true)}>
            <Plus className="mr-2 h-4 w-4" />
            Create Memory
          </Button>
        }
      />
      
      <div className="mt-6">
        <MemoriesTable
          memories={memories}
          loading={loading}
          onMemoryDeleted={handleMemoryChanged}
          onMemoriesChanged={handleMemoryChanged}
        />
      </div>

      <AddMemoryDialog
        open={showAddMemoryDialog}
        onOpenChange={setShowAddMemoryDialog}
      />
    </div>
  );
}
