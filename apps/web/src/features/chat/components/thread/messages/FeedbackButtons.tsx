"use client";

import { ThumbsUp, ThumbsDown } from "lucide-react";
import { useState, useEffect } from "react";
import { toast } from "sonner";

import { TooltipIconButton } from "@/components/ui/tooltip-icon-button";
import { cn } from "@/lib/utils";
import { getSupabaseClient } from "@/lib/auth/supabase-client";
import { FeedbackDialog } from "./FeedbackDialog";

interface FeedbackButtonsProps {
  messageId: string;
  threadId: string;
  runId?: string; // Optional: LangSmith run_id if available
  disabled?: boolean;
}

type FeedbackScore = 1 | -1 | null;

export function FeedbackButtons({
  messageId,
  threadId,
  runId,
  disabled = false,
}: FeedbackButtonsProps) {
  const [feedback, setFeedback] = useState<FeedbackScore>(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [dialogType, setDialogType] = useState<"positive" | "negative">("positive");
  const [pendingScore, setPendingScore] = useState<FeedbackScore>(null);
  const [isLoading, setIsLoading] = useState(false);

  // Load existing feedback on mount
  useEffect(() => {
    const loadFeedback = async () => {
      try {
        const supabase = getSupabaseClient();
        const { data: { session } } = await supabase.auth.getSession();

        if (!session?.access_token) {
          console.warn("No session available for feedback loading");
          return;
        }

        const response = await fetch(
          `/api/langconnect/feedback/messages/${messageId}`,
          {
            headers: {
              "Authorization": `Bearer ${session.access_token}`,
            },
          }
        );

        if (response.ok) {
          const data = await response.json();
          if (data && data.score !== 0) {
            setFeedback(data.score as FeedbackScore);
          }
        }
      } catch (error) {
        console.error("Failed to load existing feedback:", error);
      }
    };

    loadFeedback();
  }, [messageId]);

  const handleFeedbackClick = (score: 1 | -1) => {
    if (feedback === score) {
      // If clicking the same button, remove feedback
      submitFeedback(0);
    } else {
      // Set pending score and open dialog - don't update feedback until submitted
      setDialogType(score === 1 ? "positive" : "negative");
      setPendingScore(score);
      setDialogOpen(true);
    }
  };

  const submitFeedback = async (
    score: number,
    comment?: string,
    category?: string
  ) => {
    setIsLoading(true);

    try {
      const supabase = getSupabaseClient();
      const { data: { session }, error: sessionError } = await supabase.auth.getSession();

      if (sessionError || !session?.access_token) {
        toast.error("Authentication required. Please sign in.");
        setIsLoading(false);
        return;
      }

      const response = await fetch("/api/langconnect/feedback/messages", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${session.access_token}`,
        },
        body: JSON.stringify({
          message_id: messageId,
          thread_id: threadId,
          run_id: runId,
          score,
          comment,
          category,
        }),
      });

      if (!response.ok) {
        throw new Error("Failed to submit feedback");
      }

      const data = await response.json();

      // Update local state
      if (score === 0) {
        setFeedback(null);
        toast.success("Feedback removed");
      } else {
        setFeedback(score as FeedbackScore);
        toast.success(
          data.langsmith_synced
            ? "Feedback submitted"
            : "Feedback submitted (not synced to LangSmith)"
        );
      }
    } catch (error) {
      console.error("Feedback submission error:", error);
      toast.error("Failed to submit feedback. Please try again.");
      // Revert optimistic update
      setFeedback(null);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <>
      <div className="flex items-center gap-0.5">
        <TooltipIconButton
          onClick={() => handleFeedbackClick(1)}
          variant="ghost"
          tooltip="Good response"
          disabled={disabled || isLoading}
          className={cn(
            "transition-all duration-200",
            feedback === 1 &&
              "text-green-600 bg-green-50 hover:bg-green-100 dark:bg-green-950 dark:hover:bg-green-900"
          )}
        >
          <ThumbsUp
            className={cn(
              "h-4 w-4 transition-all duration-200",
              feedback === 1 && "fill-current"
            )}
          />
        </TooltipIconButton>

        <TooltipIconButton
          onClick={() => handleFeedbackClick(-1)}
          variant="ghost"
          tooltip="Bad response"
          disabled={disabled || isLoading}
          className={cn(
            "transition-all duration-200",
            feedback === -1 &&
              "text-red-600 bg-red-50 hover:bg-red-100 dark:bg-red-950 dark:hover:bg-red-900"
          )}
        >
          <ThumbsDown
            className={cn(
              "h-4 w-4 transition-all duration-200",
              feedback === -1 && "fill-current"
            )}
          />
        </TooltipIconButton>
      </div>

      <FeedbackDialog
        open={dialogOpen}
        onOpenChange={(open) => {
          setDialogOpen(open);
          // If closing without submitting, clear pending score
          if (!open) {
            setPendingScore(null);
          }
        }}
        type={dialogType}
        onSubmit={(comment, category) => {
          submitFeedback(pendingScore!, comment, category);
          setPendingScore(null);
          setDialogOpen(false);
        }}
        onSkip={() => {
          // Just submit without comment
          submitFeedback(pendingScore!);
          setPendingScore(null);
          setDialogOpen(false);
        }}
      />
    </>
  );
}
