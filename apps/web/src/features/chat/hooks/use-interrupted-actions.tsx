import { useState, useRef, useEffect, KeyboardEvent } from "react";
import { toast } from "sonner";
import { useStreamContext } from "@/features/chat/providers/Stream";
import { HumanInterrupt, HumanResponse, HumanResponseWithEdits, SubmitType } from "../components/thread/messages/interrupt-types";
import { Message } from "@langchain/langgraph-sdk";

function createDefaultHumanResponse(
  interrupt: HumanInterrupt,
  initialHumanInterruptEditValue: React.MutableRefObject<Record<string, string>>,
): {
  responses: HumanResponseWithEdits[];
  defaultSubmitType: SubmitType | undefined;
  hasAccept: boolean;
} {
  const responses: HumanResponseWithEdits[] = [];
  
  if (interrupt.config.allow_edit) {
    if (interrupt.config.allow_accept) {
      Object.entries(interrupt.action_request.args).forEach(([k, v]) => {
        let stringValue = "";
        if (typeof v === "string") {
          stringValue = v;
        } else {
          stringValue = JSON.stringify(v, null);
        }

        if (
          !initialHumanInterruptEditValue.current ||
          !(k in initialHumanInterruptEditValue.current)
        ) {
          initialHumanInterruptEditValue.current = {
            ...initialHumanInterruptEditValue.current,
            [k]: stringValue,
          };
        }
      });
      responses.push({
        type: "edit",
        args: interrupt.action_request,
        acceptAllowed: true,
        editsMade: false,
      });
    } else {
      responses.push({
        type: "edit",
        args: interrupt.action_request,
        acceptAllowed: false,
      });
    }
  }
  
  if (interrupt.config.allow_respond) {
    responses.push({
      type: "response",
      args: "",
    });
  }

  if (interrupt.config.allow_ignore) {
    responses.push({
      type: "ignore",
      args: null,
    });
  }

  // Set the submit type priority: accept > response > edit
  const acceptAllowedConfig = interrupt.config.allow_accept;
  const hasResponse = responses.find((r) => r.type === "response");
  const hasAccept = responses.find((r) => r.acceptAllowed) || acceptAllowedConfig;
  const hasEdit = responses.find((r) => r.type === "edit");

  let defaultSubmitType: SubmitType | undefined;
  if (hasAccept) {
    defaultSubmitType = "accept";
  } else if (hasResponse) {
    defaultSubmitType = "response";
  } else if (hasEdit) {
    defaultSubmitType = "edit";
  }

  if (acceptAllowedConfig && !responses.find((r) => r.type === "accept")) {
    responses.push({
      type: "accept",
      args: null,
    });
  }

  return { responses, defaultSubmitType, hasAccept: !!hasAccept };
}

interface UseInterruptedActionsInput {
  interrupt: HumanInterrupt;
}

interface UseInterruptedActionsValue {
  // Actions
  handleSubmit: (
    e: React.MouseEvent<HTMLButtonElement, MouseEvent> | KeyboardEvent,
  ) => Promise<void>;
  handleIgnore: (
    e: React.MouseEvent<HTMLButtonElement, MouseEvent>,
  ) => Promise<void>;
  handleResolve: (
    e: React.MouseEvent<HTMLButtonElement, MouseEvent>,
  ) => Promise<void>;

  // State values
  streaming: boolean;
  streamFinished: boolean;
  loading: boolean;
  supportsMultipleMethods: boolean;
  hasEdited: boolean;
  hasAddedResponse: boolean;
  acceptAllowed: boolean;
  humanResponse: HumanResponseWithEdits[];
  selectedSubmitType: SubmitType | undefined;

  // State setters
  setSelectedSubmitType: React.Dispatch<React.SetStateAction<SubmitType | undefined>>;
  setHumanResponse: React.Dispatch<React.SetStateAction<HumanResponseWithEdits[]>>;
  setHasAddedResponse: React.Dispatch<React.SetStateAction<boolean>>;
  setHasEdited: React.Dispatch<React.SetStateAction<boolean>>;

  // Refs
  initialHumanInterruptEditValue: React.MutableRefObject<Record<string, string>>;
}

export function useInterruptedActions({
  interrupt,
}: UseInterruptedActionsInput): UseInterruptedActionsValue {
  const thread = useStreamContext();
  const [humanResponse, setHumanResponse] = useState<HumanResponseWithEdits[]>([]);
  const [loading, setLoading] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const [streamFinished, setStreamFinished] = useState(false);
  const initialHumanInterruptEditValue = useRef<Record<string, string>>({});
  const [selectedSubmitType, setSelectedSubmitType] = useState<SubmitType>();
  const [hasEdited, setHasEdited] = useState(false);
  const [hasAddedResponse, setHasAddedResponse] = useState(false);
  const [acceptAllowed, setAcceptAllowed] = useState(false);

  useEffect(() => {
    try {
      const { responses, defaultSubmitType, hasAccept } =
        createDefaultHumanResponse(interrupt, initialHumanInterruptEditValue);
      setSelectedSubmitType(defaultSubmitType);
      setHumanResponse(responses);
      setAcceptAllowed(hasAccept);
    } catch (e) {
      console.error("Error formatting and setting human response state", e);
    }
  }, [interrupt]);

  const resumeRun = (response: HumanResponse[]): boolean => {
    try {
      
      thread.submit(
        { messages: thread.messages }, // Pass existing messages to backend
        {
          command: {
            resume: response,
          },
          streamMode: ["values"],
          optimisticValues: (prev: { messages?: Message[] }) => {
            const result = {
              ...prev,
              messages: thread.messages, // Preserve locally
            };
            return result;
          },
        },
      );
      return true;
    } catch (e: any) {
      console.error("Error sending human response", e);
      return false;
    }
  };

  const handleSubmit = async (
    e: React.MouseEvent<HTMLButtonElement, MouseEvent> | KeyboardEvent,
  ) => {
    e.preventDefault();
    
    if (!humanResponse) {
      toast.error("Please enter a response.");
      return;
    }

    let errorOccurred = false;
    initialHumanInterruptEditValue.current = {};

    if (
      humanResponse.some((r) => ["response", "edit", "accept"].includes(r.type))
    ) {
      setStreamFinished(false);

      try {
        const humanResponseInput: HumanResponse[] = humanResponse.flatMap(
          (r) => {
            if (r.type === "edit") {
              if (r.acceptAllowed && !r.editsMade) {
                return {
                  type: "accept",
                  args: r.args,
                };
              } else {
                return {
                  type: "edit",
                  args: r.args,
                };
              }
            }

            if (r.type === "response" && !r.args) {
              return [];
            }
            return {
              type: r.type,
              args: r.args,
            };
          },
        );

        const input = humanResponseInput.find(
          (r) => r.type === selectedSubmitType,
        );
        if (!input) {
          toast.error("No response found.");
          return;
        }

        setLoading(true);
        setStreaming(true);
        const resumedSuccessfully = resumeRun([input]);
        if (!resumedSuccessfully) {
          return;
        }

        toast.success("Response submitted successfully.");

        if (!errorOccurred) {
          setStreamFinished(true);
        }
      } catch (e: any) {
        console.error("Error sending human response", e);

        toast.error("Failed to submit response.");
        errorOccurred = true;
        setStreaming(false);
        setStreamFinished(false);
      }

      if (!errorOccurred) {
        setStreaming(false);
        setStreamFinished(false);
      }
    } else {
      setLoading(true);
      resumeRun(humanResponse);
      toast.success("Response submitted successfully.");
    }

    setLoading(false);
  };

  const handleIgnore = async (
    e: React.MouseEvent<HTMLButtonElement, MouseEvent>,
  ) => {
    e.preventDefault();

    const ignoreResponse = humanResponse.find((r) => r.type === "ignore");
    if (!ignoreResponse) {
      toast.error("The selected thread does not support ignoring.");
      return;
    }

    setLoading(true);
    initialHumanInterruptEditValue.current = {};

    resumeRun([ignoreResponse]);
    setLoading(false);
    toast.success("Successfully ignored thread");
  };

  const handleResolve = async (
    e: React.MouseEvent<HTMLButtonElement, MouseEvent>,
  ) => {
    e.preventDefault();

    setLoading(true);
    initialHumanInterruptEditValue.current = {};

    try {
      thread.submit(
        {},
        {
          command: {
            goto: "__end__",
          },
        },
      );

      toast.success("Marked thread as resolved.");
    } catch (e) {
      console.error("Error marking thread as resolved", e);
      toast.error("Failed to mark thread as resolved.");
    }

    setLoading(false);
  };

  const supportsMultipleMethods =
    humanResponse.filter(
      (r) => r.type === "edit" || r.type === "accept" || r.type === "response",
    ).length > 1;

  return {
    handleSubmit,
    handleIgnore,
    handleResolve,
    humanResponse,
    streaming,
    streamFinished,
    loading,
    supportsMultipleMethods,
    hasEdited,
    hasAddedResponse,
    acceptAllowed,
    selectedSubmitType,
    setSelectedSubmitType,
    setHumanResponse,
    setHasAddedResponse,
    setHasEdited,
    initialHumanInterruptEditValue,
  };
} 