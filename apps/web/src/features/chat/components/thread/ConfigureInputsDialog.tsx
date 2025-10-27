"use client";

import { useState, useEffect } from "react";
import { useForm } from "react-hook-form";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { FormFieldRenderer } from "./FormFieldRenderer";
import { useConfigStore } from "@/features/chat/hooks/use-config-store";
import { GraphSchema } from "@langchain/langgraph-sdk";

interface ConfigureInputsDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  agentId: string;
  inputSchema: GraphSchema["input_schema"];
}

export function ConfigureInputsDialog({
  open,
  onOpenChange,
  agentId,
  inputSchema,
}: ConfigureInputsDialogProps) {
  const { getAgentConfig, updateConfig } = useConfigStore();
  const [isResetting, setIsResetting] = useState(false);

  // Extract non-message fields from schema
  const otherFields = inputSchema?.properties
    ? Object.entries(inputSchema.properties).filter(([key]) => key !== "messages")
    : [];

  // Initialize form with current config values
  const form = useForm<Record<string, any>>({
    defaultValues: {},
  });

  // Load current values from config store when dialog opens
  useEffect(() => {
    if (open && agentId) {
      const currentConfig = getAgentConfig(agentId);
      const formValues: Record<string, any> = {};

      otherFields.forEach(([fieldName, fieldSchema]) => {
        // Get value from config store, or use default from schema
        const storedValue = currentConfig[fieldName];
        const defaultValue = (fieldSchema as any)?.default;

        if (storedValue !== undefined) {
          formValues[fieldName] = storedValue;
        } else if (defaultValue !== undefined) {
          formValues[fieldName] = defaultValue;
        } else {
          // Set sensible defaults based on type
          const fieldType = (fieldSchema as any)?.type;
          if (fieldType === "boolean") {
            formValues[fieldName] = false;
          } else if (fieldType === "number" || fieldType === "integer") {
            formValues[fieldName] = 0;
          } else if (fieldType === "array") {
            formValues[fieldName] = [];
          } else {
            formValues[fieldName] = "";
          }
        }
      });

      form.reset(formValues);
    }
  }, [open, agentId, otherFields.length, getAgentConfig]);

  const handleSave = () => {
    const values = form.getValues();

    // Update config store with all field values
    otherFields.forEach(([fieldName]) => {
      const value = values[fieldName];
      if (value !== undefined) {
        updateConfig(agentId, fieldName, value);
      }
    });

    onOpenChange(false);
  };

  const handleResetToDefaults = () => {
    setIsResetting(true);
    const defaultValues: Record<string, any> = {};

    otherFields.forEach(([fieldName, fieldSchema]) => {
      const defaultValue = (fieldSchema as any)?.default;

      if (defaultValue !== undefined) {
        defaultValues[fieldName] = defaultValue;
      } else {
        // Set sensible defaults based on type
        const fieldType = (fieldSchema as any)?.type;
        if (fieldType === "boolean") {
          defaultValues[fieldName] = false;
        } else if (fieldType === "number" || fieldType === "integer") {
          defaultValues[fieldName] = 0;
        } else if (fieldType === "array") {
          defaultValues[fieldName] = [];
        } else {
          defaultValues[fieldName] = "";
        }
      }

      // Update config store
      updateConfig(agentId, fieldName, defaultValues[fieldName]);
    });

    // Reset form to default values
    form.reset(defaultValues);
    setIsResetting(false);
  };

  if (otherFields.length === 0) {
    return null;
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[500px]">
        <DialogHeader>
          <DialogTitle>Configure Additional Inputs</DialogTitle>
          <DialogDescription>
            Configure additional parameters for this agent. These settings will be used for all messages in this chat.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-4">
          {otherFields.map(([fieldName, fieldSchema]) => {
            const fieldLabel = fieldName
              .split("_")
              .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
              .join(" ");
            const fieldDescription = (fieldSchema as any)?.description;
            const isRequired = inputSchema?.required?.includes(fieldName) ?? false;

            return (
              <FormFieldRenderer
                key={fieldName}
                control={form.control}
                name={fieldName}
                property={fieldSchema}
                label={fieldLabel}
                description={fieldDescription}
                required={isRequired}
              />
            );
          })}
        </div>

        <DialogFooter className="flex-col sm:flex-row gap-2">
          <Button
            type="button"
            variant="outline"
            onClick={handleResetToDefaults}
            disabled={isResetting}
            className="sm:mr-auto"
          >
            Reset to Defaults
          </Button>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button type="button" onClick={handleSave}>
            Save
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
