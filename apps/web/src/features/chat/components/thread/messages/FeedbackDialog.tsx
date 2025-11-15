"use client";

import { useState } from "react";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";

interface FeedbackDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  type: "positive" | "negative";
  onSubmit: (comment?: string, category?: string) => void;
  onSkip: () => void;
}

const POSITIVE_CATEGORIES = [
  { value: "helpful", label: "Helpful" },
  { value: "accurate", label: "Accurate" },
  { value: "well_formatted", label: "Well formatted" },
  { value: "complete", label: "Complete response" },
];

const NEGATIVE_CATEGORIES = [
  { value: "incorrect", label: "Incorrect information" },
  { value: "not_helpful", label: "Not helpful" },
  { value: "incomplete", label: "Incomplete response" },
  { value: "formatting", label: "Formatting issues" },
  { value: "irrelevant", label: "Irrelevant to my question" },
];

export function FeedbackDialog({
  open,
  onOpenChange,
  type,
  onSubmit,
  onSkip,
}: FeedbackDialogProps) {
  const [comment, setComment] = useState("");
  const [category, setCategory] = useState<string>();

  const categories = type === "positive" ? POSITIVE_CATEGORIES : NEGATIVE_CATEGORIES;
  const title = type === "positive" ? "What did you like?" : "What went wrong?";
  const description =
    type === "positive"
      ? "Help us understand what made this response helpful."
      : "Help us improve by sharing what could be better.";

  const handleSubmit = () => {
    onSubmit(comment || undefined, category);
    // Reset form
    setComment("");
    setCategory(undefined);
  };

  const handleSkip = () => {
    onSkip();
    // Reset form
    setComment("");
    setCategory(undefined);
  };

  const handleOpenChange = (newOpen: boolean) => {
    if (!newOpen) {
      // Reset form when closing
      setComment("");
      setCategory(undefined);
    }
    onOpenChange(newOpen);
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-[500px]">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-4">
          <div className="space-y-3">
            <Label className="text-sm font-medium">
              Category <span className="text-muted-foreground">(optional)</span>
            </Label>
            <RadioGroup value={category} onValueChange={setCategory}>
              <div className="space-y-2">
                {categories.map((cat) => (
                  <div key={cat.value} className="flex items-center space-x-2">
                    <RadioGroupItem value={cat.value} id={cat.value} />
                    <Label
                      htmlFor={cat.value}
                      className="font-normal cursor-pointer text-sm"
                    >
                      {cat.label}
                    </Label>
                  </div>
                ))}
              </div>
            </RadioGroup>
          </div>

          <div className="space-y-2">
            <Label htmlFor="comment" className="text-sm font-medium">
              Additional feedback{" "}
              <span className="text-muted-foreground">(optional)</span>
            </Label>
            <Textarea
              id="comment"
              placeholder="Tell us more..."
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              rows={4}
              className="resize-none"
            />
          </div>
        </div>

        <DialogFooter className="gap-2 sm:gap-0">
          <Button variant="ghost" onClick={handleSkip} type="button">
            Skip
          </Button>
          <Button onClick={handleSubmit} type="button">
            Submit Feedback
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
