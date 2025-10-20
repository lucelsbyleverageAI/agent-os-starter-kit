"use client";

import { ReactNode, useEffect, useState, useRef } from "react";
import {
  ResizablePanelGroup,
  ResizablePanel,
  ResizableHandle,
} from "@/components/ui/resizable";
import { SchemaForm } from "./components/schema-form";
import { ResponseViewer } from "./components/response-viewer";
import { Button } from "@/components/ui/button";
import { AlertTriangle, CirclePlay, Clock, StopCircle } from "lucide-react";
import { useMCPContext } from "@/providers/MCP";
import { Tool } from "@/types/tool";
import { ToolListCommand } from "../components/tool-list-command";
import _ from "lodash";
import { useQueryState } from "nuqs";
import { toast } from "sonner";

interface ToolPlaygroundProps {
  tool?: Tool;
  authRequiredMessage?: ReactNode;
}

export function ToolPlayground({
  tool: initialTool,
  authRequiredMessage,
}: ToolPlaygroundProps) {
  const { callTool, tools } = useMCPContext();
  const [selectedTool, setSelectedTool] = useState<Tool | undefined>(
    initialTool,
  );
  const [formValues, setFormValues] = useState<any>({});
  const [response, setResponse] = useState<any>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string>("");
  const [startTime, setStartTime] = useState<number | null>(null);
  const [elapsedTime, setElapsedTime] = useState<number>(0);
  const [toolQuery, setToolQuery] = useQueryState("tool");

  // Effect to load tool from URL parameter
  useEffect(() => {
    if (toolQuery && tools.length > 0) {
      const toolFromUrl = tools.find(tool => tool.name === toolQuery);
      if (toolFromUrl && toolFromUrl.name !== selectedTool?.name) {
        setSelectedTool(toolFromUrl);
        // Clear previous state when switching tools
        setFormValues({});
        setResponse(null);
        setErrorMessage("");
      }
    }
  }, [toolQuery, tools, selectedTool?.name]);

  // Refs to track the current operation
  const operationRef = useRef<{
    abortController: AbortController;
    toolPromise: Promise<any>;
  } | null>(null);

  const TOOL_TIMEOUT_MS = 5 * 60 * 1000; // 5 minutes
  const UI_TIMEOUT_MS = 6 * 60 * 1000; // 6 minutes (longer than tool timeout)

  // Timer for elapsed time display
  useEffect(() => {
    let interval: NodeJS.Timeout;
    
    if (isLoading && startTime) {
      interval = setInterval(() => {
        setElapsedTime(Date.now() - startTime);
      }, 1000);
    }

    return () => {
      if (interval) clearInterval(interval);
    };
  }, [isLoading, startTime]);

  const formatElapsedTime = (ms: number): string => {
    const seconds = Math.floor(ms / 1000);
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = seconds % 60;
    
    if (minutes > 0) {
      return `${minutes}m ${remainingSeconds}s`;
    }
    return `${remainingSeconds}s`;
  };

  const stopExecution = () => {
    if (operationRef.current) {
      operationRef.current.abortController.abort();
      operationRef.current = null;
    }
    
    setIsLoading(false);
    setStartTime(null);
    setElapsedTime(0);
    setErrorMessage("Tool execution cancelled by user");
    
    toast.error("Tool execution cancelled");
  };

  const runTool = async () => {
    if (!selectedTool) {
      toast.error("No tool selected");
      return;
    }

    // Clear previous state
    setResponse(null);
    setErrorMessage("");
    setIsLoading(true);
    const execStartTime = Date.now();
    setStartTime(execStartTime);
    setElapsedTime(0);

    // Create abort controller for this operation
    const abortController = new AbortController();
    
    try {
      // Create the tool promise
      const toolPromise = callTool({
        name: selectedTool.name,
        args: formValues,
      });

      // Store the operation reference
      operationRef.current = { abortController, toolPromise };

      // Create UI timeout promise
      const uiTimeoutPromise = new Promise((_, reject) => {
        const timeoutId = setTimeout(() => {
          reject(new Error(`UI_TIMEOUT_${UI_TIMEOUT_MS}`));
        }, UI_TIMEOUT_MS);
        
        // Clear timeout if aborted
        abortController.signal.addEventListener('abort', () => {
          clearTimeout(timeoutId);
        });
      });

      // Race between tool execution and UI timeout
      const result = await Promise.race([
        toolPromise,
        uiTimeoutPromise,
      ]);

      // If we get here, the tool completed successfully
      const completionTime = Date.now();
      const totalTime = completionTime - execStartTime;
      
      setResponse(result);
      setIsLoading(false);
      setStartTime(null);
      operationRef.current = null;
      
      toast.success(`Tool completed successfully in ${formatElapsedTime(totalTime)}`);

    } catch (error: any) {
      const errorTime = Date.now();
      const totalTime = errorTime - execStartTime;
      
      // Clear operation reference
      operationRef.current = null;
      
      // Check if this was a UI timeout
      if (error.message?.startsWith('UI_TIMEOUT_')) {
        setIsLoading(false);
        setStartTime(null);
        
        // Don't set error - show a warning instead but keep waiting
        toast.warning(
          `Tool is taking longer than expected (${formatElapsedTime(totalTime)}). ` +
          "Check the Network tab for results or try refreshing the page.",
          { duration: 10000 }
        );
        return;
      }

      // Check if operation was aborted
      if (abortController.signal.aborted) {
        return; // Already handled in stopExecution
      }

      setIsLoading(false);
      setStartTime(null);
      
      // Handle different types of errors
      let errorMsg = "An unexpected error occurred";
      
      if (error.message?.includes("Request timed out")) {
        errorMsg = `Tool execution timed out after ${formatElapsedTime(totalTime)}. The tool may still be running on the server.`;
      } else if (error.message?.includes("Failed to fetch")) {
        errorMsg = "Network error: Could not connect to the server";
      } else if (error.name === "McpError") {
        errorMsg = `MCP Error: ${error.message}`;
      } else if (error.message) {
        errorMsg = error.message;
      }
      
      setErrorMessage(errorMsg);
      console.error("Tool execution error:", error);
      
      toast.error(`Tool failed: ${errorMsg}`);
    }
  };

  const isFormValid = () => {
    if (!selectedTool?.inputSchema?.required) return true;
    
    return selectedTool.inputSchema.required.every((field) => {
      const value = formValues[field];
      return value !== undefined && value !== null && value !== "";
    });
  };

  if (authRequiredMessage) {
    return (
      <div className="flex h-full w-full items-center justify-center">
        {authRequiredMessage}
      </div>
    );
  }

  return (
    <div className="flex h-full w-full flex-col">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between border-b border-border/40 bg-background/95 p-4 backdrop-blur supports-[backdrop-filter]:bg-background/60">
        <div className="flex flex-wrap items-center gap-4">
          <h1 className="text-xl font-semibold">Tools Playground</h1>
          {selectedTool && (
            <div className="flex items-center gap-2">
              <span className="text-muted-foreground">•</span>
              <span className="font-medium">{selectedTool.name}</span>
            </div>
          )}
        </div>

        <div className="flex items-center gap-2">
          {isLoading && startTime && (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Clock className="h-4 w-4" />
              <span>Running for {formatElapsedTime(elapsedTime)}</span>
              <span className="text-xs">• Timeout: {Math.floor(TOOL_TIMEOUT_MS / 60000)} minutes</span>
            </div>
          )}
          
          <ToolListCommand
            value={selectedTool || { name: "", description: "", inputSchema: { type: "object" } }}
            setValue={(tool: Tool) => {
              setSelectedTool(tool);
              setResponse(null);
              setErrorMessage("");
              setFormValues({});
              setToolQuery(tool?.name || null);
            }}
          />
        </div>
      </div>

      {/* Content */}
      {!selectedTool ? (
        <div className="flex flex-1 items-center justify-center">
          <div className="text-center">
            <AlertTriangle className="mx-auto mb-4 h-12 w-12 text-muted-foreground" />
            <h3 className="mb-2 text-lg font-medium">No Tool Selected</h3>
            <p className="text-muted-foreground">
              Select a tool to start testing in the playground.
            </p>
          </div>
        </div>
      ) : (
        <ResizablePanelGroup
          direction="horizontal"
          className="flex-1"
        >
          {/* Left Panel - Tool Configuration */}
          <ResizablePanel
            defaultSize={40}
            minSize={30}
            maxSize={60}
          >
            <div className="flex h-full flex-col border-r">
              <div className="border-b bg-card dark:bg-card/50 px-4 py-3">
                <h2 className="font-medium">Configuration</h2>
                <p className="text-sm text-muted-foreground">
                  Configure the tool parameters
                </p>
              </div>

              <div className="flex-1 overflow-auto p-4">
                {selectedTool.inputSchema ? (
                  <SchemaForm
                    schema={selectedTool.inputSchema}
                    values={formValues}
                    onChange={setFormValues}
                  />
                ) : (
                  <div className="text-center text-muted-foreground">
                    This tool requires no configuration
                  </div>
                )}
              </div>

              <div className="border-t bg-card dark:bg-card/50 p-4">
                <Button
                  onClick={isLoading ? stopExecution : runTool}
                  disabled={!isFormValid() && !isLoading}
                  className="w-full"
                  variant={isLoading ? "destructive" : "default"}
                >
                  {isLoading ? (
                    <>
                      <StopCircle className="mr-2 h-4 w-4" />
                      Stop Execution
                    </>
                  ) : (
                    <>
                      <CirclePlay className="mr-2 h-4 w-4" />
                      Run Tool
                    </>
                  )}
                </Button>

                {!isFormValid() && !isLoading && (
                  <p className="mt-2 text-xs text-muted-foreground">
                    Please fill in all required fields
                  </p>
                )}
              </div>
            </div>
          </ResizablePanel>

          <ResizableHandle />

          {/* Right Panel - Response */}
          <ResizablePanel
            defaultSize={60}
            minSize={40}
          >
            <div className="flex h-full flex-col">
              <div className="border-b bg-card dark:bg-card/50 px-4 py-3">
                <h2 className="font-medium">Response</h2>
                <p className="text-sm text-muted-foreground">
                  Tool execution results will appear here
                </p>
              </div>

              <div className="flex-1 overflow-hidden p-4">
                <ResponseViewer
                  response={response}
                  isLoading={isLoading}
                  errorMessage={errorMessage}
                />
              </div>
            </div>
          </ResizablePanel>
        </ResizablePanelGroup>
      )}
    </div>
  );
}

// Default export for backward compatibility with existing page
export default function ToolsPlaygroundInterface(): ReactNode {
  return <ToolPlayground />;
}
