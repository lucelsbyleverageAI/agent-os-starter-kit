import { useState } from "react";
import { useForm } from "react-hook-form";
import { GraphSchema } from "@langchain/langgraph-sdk";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Collapsible, CollapsibleContent } from "@/components/ui/collapsible";
import { ChevronDown, ChevronRight, Send, LoaderCircle } from "lucide-react";
import { FormFieldRenderer } from "./FormFieldRenderer";
import { useStreamContext } from "@/features/chat/providers/Stream";
import { useConfigStore } from "@/features/chat/hooks/use-config-store";
import { useAuthContext } from "@/providers/Auth";
import { useQueryState } from "nuqs";
import { cn } from "@/lib/utils";
import { getScrollbarClasses } from "@/lib/scrollbar-styles";

interface FormInputComposerProps {
  inputSchema: GraphSchema["input_schema"];
  chatWidth: string;
  isLoading: boolean;
  onStop: () => void;
  hasMessages: boolean;
}

export function FormInputComposer({
  inputSchema,
  chatWidth,
  isLoading,
  onStop,
  hasMessages,
}: FormInputComposerProps) {
  // Default to expanded state for new threads (no messages), collapsed for existing threads
  const [isExpanded, setIsExpanded] = useState(!hasMessages);
  const [hasSubmitted, setHasSubmitted] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const { session } = useAuthContext();
  const [agentId] = useQueryState("agentId");
  const stream = useStreamContext();

  // Generate default values from schema properties
  const generateDefaultValues = (schema: GraphSchema["input_schema"]): Record<string, any> => {
    const defaults: Record<string, any> = {};
    const properties = schema?.properties || {};
    
    Object.entries(properties).forEach(([fieldName, property]) => {
      if (!property || typeof property !== 'object') {
        defaults[fieldName] = "";
        return;
      }
      
      // Handle anyOf patterns (common in LangGraph schemas)
      let fieldType = property.type;
      if ('anyOf' in property && Array.isArray(property.anyOf)) {
        const nonNullTypes = property.anyOf.filter((item: any) => 
          typeof item === 'object' && item.type !== 'null'
        );
        if (nonNullTypes.length > 0 && typeof nonNullTypes[0] === 'object') {
          fieldType = nonNullTypes[0].type;
        }
      }
      
      // Set appropriate default based on type
      switch (fieldType) {
        case 'string':
          defaults[fieldName] = "";
          break;
        case 'number':
        case 'integer':
          defaults[fieldName] = 0;
          break;
        case 'boolean':
          defaults[fieldName] = false;
          break;
        case 'array':
          defaults[fieldName] = [];
          break;
        case 'object':
          defaults[fieldName] = {};
          break;
        default:
          defaults[fieldName] = "";
      }
    });
    
    return defaults;
  };

  // Initialize form with react-hook-form
  const form = useForm<Record<string, any>>({
    defaultValues: generateDefaultValues(inputSchema),
  });

  const { handleSubmit, formState, control, reset } = form;
  const { isSubmitting } = formState;

  // Handle form submission
  const onSubmit = (data: Record<string, any>) => {
    if (!agentId) {
      setSubmitError("No agent selected");
      return;
    }

    try {
      // Clear any previous errors
      setSubmitError(null);
      
      const { getAgentConfig } = useConfigStore.getState();

      // Validate that we have the required data
      if (!data || Object.keys(data).length === 0) {
        setSubmitError("Please fill in at least one field");
        return;
      }

      // Submit form data to stream
      stream.submit(data, {
        // Avoid TS error and rely on defaults; values are handled by SDK
        config: {
          configurable: getAgentConfig(agentId),
        },
        metadata: {
          supabaseAccessToken: session?.accessToken,
        },
      });

      // Mark as submitted and collapse the form
      setHasSubmitted(true);
      setIsExpanded(false);
    } catch (error) {
      console.error("Error submitting form:", error);
      setSubmitError(error instanceof Error ? error.message : "Failed to submit form");
    }
  };

  // Reset form state when expanding after submission
  const handleToggleExpanded = () => {
    if (!isExpanded && hasSubmitted) {
      reset();
      setHasSubmitted(false);
      setSubmitError(null);
    }
    setIsExpanded(!isExpanded);
  };

  // Get form fields from schema
  const properties = inputSchema?.properties || {};
  const requiredFields = inputSchema?.required || [];

  // If form was submitted and is loading, show a simple status
  if (hasSubmitted && isLoading) {
    return (
      <div className={cn("bg-transparent relative z-10 mb-4 w-full rounded-[2rem] border border-border", chatWidth)}>
        <div className="flex items-center justify-between p-4">
          <div className="flex items-center gap-3">
            <LoaderCircle className="h-4 w-4 animate-spin" />
            <span className="text-sm text-muted-foreground">
              Processing request...
            </span>
          </div>
          <Button
            onClick={onStop}
            variant="outline"
            size="sm"
          >
            Cancel
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className={cn(
      "bg-transparent relative z-10 mb-4 w-full rounded-[2rem] border border-border",
      chatWidth,
      // Add proper centering for new threads
      !hasMessages && "max-h-[70vh]",
    )}>
      <Collapsible open={isExpanded} onOpenChange={setIsExpanded}>
        {/* Collapsed state - simple input bar */}
        {!isExpanded && (
          <div 
            className="flex items-center justify-between p-4 cursor-pointer hover:bg-muted/50 transition-colors rounded-[2rem]"
            onClick={handleToggleExpanded}
          >
            <div className="flex items-center gap-3">
              <ChevronRight className="h-4 w-4 text-muted-foreground" />
              <span className="text-sm text-muted-foreground">
                {hasSubmitted ? "Modify inputs..." : "Enter inputs..."}
              </span>
            </div>
            <div className="text-xs text-muted-foreground">
              {Object.keys(properties).length} field{Object.keys(properties).length !== 1 ? 's' : ''}
            </div>
          </div>
        )}

        {/* Expanded state - full form */}
        <CollapsibleContent>
          <Card className="border-none shadow-none bg-transparent">
            <CardHeader className="pb-4">
              <CardTitle className="flex items-center text-lg">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={handleToggleExpanded}
                  className="mr-2 p-1 h-auto w-auto text-muted-foreground hover:text-foreground"
                >
                  <ChevronDown className="h-4 w-4" />
                </Button>
                Input Details
              </CardTitle>
            </CardHeader>

            <CardContent className={cn(
              // Add scrolling with max height for new threads
              !hasMessages && ["max-h-[50vh]", ...getScrollbarClasses('y')]
            )}>
              <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
                {/* Render dynamic fields */}
                {Object.entries(properties).map(([fieldName, property]) => (
                  <FormFieldRenderer<Record<string, any>>
                    key={fieldName}
                    control={control}
                    name={fieldName}
                    property={property}
                    label={fieldName.charAt(0).toUpperCase() + fieldName.slice(1)}
                    description={typeof property === 'object' && property?.description ? property.description : undefined}
                    required={requiredFields.includes(fieldName)}
                  />
                ))}

                {/* Error display */}
                {submitError && (
                  <div className="p-3 rounded-md bg-destructive/10 border border-destructive/20">
                    <p className="text-sm text-destructive">{submitError}</p>
                  </div>
                )}

                {/* Submit button */}
                <div className="flex items-center justify-between pt-4">
                  <div className="text-xs text-muted-foreground">
                    {requiredFields.length > 0 && (
                      <>Required fields marked with <span className="text-destructive">*</span></>
                    )}
                  </div>
                  
                  <div className="flex items-center gap-2">
                    <Button
                      type="button"
                      variant="outline"
                      onClick={handleToggleExpanded}
                    >
                      Cancel
                    </Button>
                    <Button
                      type="submit"
                      disabled={isSubmitting || isLoading}
                      className="min-w-[100px]"
                    >
                      {isSubmitting ? (
                        <>
                          <LoaderCircle className="h-4 w-4 animate-spin mr-2" />
                          Submitting...
                        </>
                      ) : (
                        <>
                          <Send className="h-4 w-4 mr-2" />
                          Submit
                        </>
                      )}
                    </Button>
                  </div>
                </div>
              </form>
            </CardContent>
          </Card>
        </CollapsibleContent>
      </Collapsible>
    </div>
  );
} 