import React from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Separator } from "@/components/ui/separator";
import { Label } from "@/components/ui/label";
import { MarkdownText } from "@/components/ui/markdown-text";
import { Undo2 } from "lucide-react";
import { toast } from "sonner";
import { 
  HumanInterrupt, 
  HumanResponseWithEdits, 
  SubmitType, 
  ActionRequest 
} from "./interrupt-types";
import { prettifyText, haveArgsChanged } from "@/features/chat/utils/interrupt-utils";

function ResetButton({ handleReset }: { handleReset: () => void }) {
  return (
    <Button
      onClick={handleReset}
      variant="ghost"
      size="sm"
      className="flex items-center gap-2 text-muted-foreground hover:text-destructive"
    >
      <Undo2 className="h-4 w-4" />
      <span>Reset</span>
    </Button>
  );
}

function ArgsRenderer({ args }: { args: Record<string, any> }) {
  return (
    <div className="flex w-full flex-col gap-4">
      {Object.entries(args).map(([k, v]) => {
        let value = "";
        if (["string", "number"].includes(typeof v)) {
          value = v.toString();
        } else {
          value = JSON.stringify(v, null, 2);
        }

        return (
          <div key={`args-${k}`} className="flex flex-col gap-2">
            <Label className="text-sm font-medium text-foreground">
              {prettifyText(k)}:
            </Label>
            <div className="rounded-lg bg-muted p-3 font-mono text-sm">
              <MarkdownText>{value}</MarkdownText>
            </div>
          </div>
        );
      })}
    </div>
  );
}

interface ResponseComponentProps {
  humanResponse: HumanResponseWithEdits[];
  streaming: boolean;
  showArgsInResponse: boolean;
  interruptValue: HumanInterrupt;
  onResponseChange: (change: string, response: HumanResponseWithEdits) => void;
  handleSubmit: (
    e: React.MouseEvent<HTMLButtonElement, MouseEvent> | React.KeyboardEvent,
  ) => Promise<void>;
}

function ResponseComponent({
  humanResponse,
  streaming,
  showArgsInResponse,
  interruptValue,
  onResponseChange,
  handleSubmit,
}: ResponseComponentProps) {
  const res = humanResponse.find((r) => r.type === "response");
  if (!res || typeof res.args !== "string") {
    return null;
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  return (
    <div className="flex w-full flex-col gap-4 rounded-xl border border-border bg-card p-6">
      <div className="flex w-full items-center justify-between">
        <h3 className="text-base font-semibold">Respond to assistant</h3>
        <ResetButton handleReset={() => onResponseChange("", res)} />
      </div>

      {showArgsInResponse && (
        <ArgsRenderer args={interruptValue.action_request.args} />
      )}

      <div className="flex w-full flex-col gap-2">
        <Label htmlFor="response-textarea">Response</Label>
        <Textarea
          id="response-textarea"
          disabled={streaming}
          value={res.args}
          onChange={(e) => onResponseChange(e.target.value, res)}
          onKeyDown={handleKeyDown}
          rows={4}
          placeholder="Your response here..."
          className="resize-none"
        />
      </div>

      <div className="flex w-full justify-end">
        <Button
          variant="default"
          disabled={streaming}
          onClick={handleSubmit}
        >
          Send Response
        </Button>
      </div>
    </div>
  );
}

function AcceptComponent({
  streaming,
  actionRequestArgs,
  handleSubmit,
}: {
  streaming: boolean;
  actionRequestArgs: Record<string, any>;
  handleSubmit: (
    e: React.MouseEvent<HTMLButtonElement, MouseEvent> | React.KeyboardEvent,
  ) => Promise<void>;
}) {
  return (
    <div className="flex w-full flex-col gap-4 rounded-xl border border-border bg-card p-6">
      {actionRequestArgs && Object.keys(actionRequestArgs).length > 0 && (
        <ArgsRenderer args={actionRequestArgs} />
      )}
      <Button
        variant="default"
        disabled={streaming}
        onClick={handleSubmit}
        className="w-full"
      >
        Accept
      </Button>
    </div>
  );
}

interface EditAndOrAcceptComponentProps {
  humanResponse: HumanResponseWithEdits[];
  streaming: boolean;
  initialValues: Record<string, string>;
  interruptValue: HumanInterrupt;
  onEditChange: (
    text: string | string[],
    response: HumanResponseWithEdits,
    key: string | string[],
  ) => void;
  handleSubmit: (
    e: React.MouseEvent<HTMLButtonElement, MouseEvent> | React.KeyboardEvent,
  ) => Promise<void>;
}

function EditAndOrAcceptComponent({
  humanResponse,
  streaming,
  initialValues,
  interruptValue,
  onEditChange,
  handleSubmit,
}: EditAndOrAcceptComponentProps) {
  const defaultRows = React.useRef<Record<string, number>>({});
  const editResponse = humanResponse.find((r) => r.type === "edit");
  const acceptResponse = humanResponse.find((r) => r.type === "accept");
  
  if (
    !editResponse ||
    typeof editResponse.args !== "object" ||
    !editResponse.args
  ) {
    if (acceptResponse) {
      return (
        <AcceptComponent
          actionRequestArgs={interruptValue.action_request.args}
          streaming={streaming}
          handleSubmit={handleSubmit}
        />
      );
    }
    return null;
  }

  const header = editResponse.acceptAllowed ? "Edit/Accept" : "Edit";
  let buttonText = "Submit";
  if (editResponse.acceptAllowed && !editResponse.editsMade) {
    buttonText = "Accept";
  }

  const handleReset = () => {
    if (
      !editResponse ||
      typeof editResponse.args !== "object" ||
      !editResponse.args ||
      !editResponse.args.args
    ) {
      return;
    }
    
    const keysToReset: string[] = [];
    const valuesToReset: string[] = [];
    Object.entries(initialValues).forEach(([k, v]) => {
      if (k in (editResponse.args as Record<string, any>).args) {
        const value = ["string", "number"].includes(typeof v)
          ? v
          : JSON.stringify(v, null);
        keysToReset.push(k);
        valuesToReset.push(value);
      }
    });

    if (keysToReset.length > 0 && valuesToReset.length > 0) {
      onEditChange(valuesToReset, editResponse, keysToReset);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  return (
    <div className="flex w-full flex-col gap-4 rounded-xl border border-border bg-card p-6">
      <div className="flex w-full items-center justify-between">
        <h3 className="text-base font-semibold">{header}</h3>
        <ResetButton handleReset={handleReset} />
      </div>

      {Object.entries(editResponse.args.args).map(([k, v], idx) => {
        const value = ["string", "number"].includes(typeof v)
          ? v
          : JSON.stringify(v, null);
          
        // Calculate default rows
        if (defaultRows.current[k] === undefined) {
          defaultRows.current[k] = !value.length
            ? 3
            : Math.max(Math.ceil(value.length / 40), 4);
        }
        const numRows = defaultRows.current[k] || 4;

        return (
          <div
            className="flex w-full flex-col gap-2"
            key={`edit-arg-${k}-${idx}`}
          >
            <Label htmlFor={`edit-${k}`}>{prettifyText(k)}</Label>
            <Textarea
              id={`edit-${k}`}
              disabled={streaming}
              value={value}
              onChange={(e) => onEditChange(e.target.value, editResponse, k)}
              onKeyDown={handleKeyDown}
              rows={numRows}
              className="resize-none font-mono text-sm"
            />
          </div>
        );
      })}

      <div className="flex w-full justify-end">
        <Button
          variant="default"
          disabled={streaming}
          onClick={handleSubmit}
        >
          {buttonText}
        </Button>
      </div>
    </div>
  );
}

interface InterruptInputProps {
  interruptValue: HumanInterrupt;
  humanResponse: HumanResponseWithEdits[];
  streaming: boolean;
  streamFinished: boolean;
  supportsMultipleMethods: boolean;
  acceptAllowed: boolean;
  hasEdited: boolean;
  hasAddedResponse: boolean;
  initialValues: Record<string, string>;

  setHumanResponse: React.Dispatch<React.SetStateAction<HumanResponseWithEdits[]>>;
  setSelectedSubmitType: React.Dispatch<React.SetStateAction<SubmitType | undefined>>;
  setHasAddedResponse: React.Dispatch<React.SetStateAction<boolean>>;
  setHasEdited: React.Dispatch<React.SetStateAction<boolean>>;

  handleSubmit: (
    e: React.MouseEvent<HTMLButtonElement, MouseEvent> | React.KeyboardEvent,
  ) => Promise<void>;
}

export function InterruptInput({
  interruptValue,
  humanResponse,
  streaming,
  streamFinished,
  supportsMultipleMethods,
  acceptAllowed,
  hasEdited,
  hasAddedResponse,
  initialValues,
  setHumanResponse,
  setSelectedSubmitType,
  setHasAddedResponse,
  setHasEdited,
  handleSubmit,
}: InterruptInputProps) {
  const isEditAllowed = interruptValue.config.allow_edit;
  const isResponseAllowed = interruptValue.config.allow_respond;
  const hasArgs = Object.entries(interruptValue.action_request.args).length > 0;
  const showArgsInResponse =
    hasArgs && !isEditAllowed && !acceptAllowed && isResponseAllowed;
  const showArgsOutsideActionCards =
    hasArgs && !showArgsInResponse && !isEditAllowed && !acceptAllowed;

  const onEditChange = (
    change: string | string[],
    response: HumanResponseWithEdits,
    key: string | string[],
  ) => {
    if (
      (Array.isArray(change) && !Array.isArray(key)) ||
      (!Array.isArray(change) && Array.isArray(key))
    ) {
      toast.error("Something went wrong");
      return;
    }

    let valuesChanged = true;
    if (typeof response.args === "object") {
      const updatedArgs = { ...(response.args?.args || {}) };

      if (Array.isArray(change) && Array.isArray(key)) {
        change.forEach((value, index) => {
          if (index < key.length) {
            updatedArgs[key[index]] = value;
          }
        });
      } else {
        updatedArgs[key as string] = change as string;
      }

      const haveValuesChanged = haveArgsChanged(updatedArgs, initialValues);
      valuesChanged = haveValuesChanged;
    }

    if (!valuesChanged) {
      setHasEdited(false);
      if (acceptAllowed) {
        setSelectedSubmitType("accept");
      } else if (hasAddedResponse) {
        setSelectedSubmitType("response");
      }
    } else {
      setSelectedSubmitType("edit");
      setHasEdited(true);
    }

    setHumanResponse((prev) => {
      if (typeof response.args !== "object" || !response.args) {
        console.error("Mismatched response type");
        return prev;
      }

      const newEdit: HumanResponseWithEdits = {
        type: response.type,
        args: {
          action: response.args.action,
          args:
            Array.isArray(change) && Array.isArray(key)
              ? {
                  ...response.args.args,
                  ...Object.fromEntries(key.map((k, i) => [k, change[i]])),
                }
              : {
                  ...response.args.args,
                  [key as string]: change as string,
                },
        },
      };
      
      return prev.map((p) => {
        if (
          p.type === response.type &&
          typeof p.args === "object" &&
          p.args?.action === (response.args as ActionRequest).action
        ) {
          if (p.acceptAllowed) {
            return {
              ...newEdit,
              acceptAllowed: true,
              editsMade: valuesChanged,
            };
          }
          return newEdit;
        }
        return p;
      });
    });
  };

  const onResponseChange = (
    change: string,
    response: HumanResponseWithEdits,
  ) => {
    if (!change) {
      setHasAddedResponse(false);
      if (hasEdited) {
        setSelectedSubmitType("edit");
      } else if (acceptAllowed) {
        setSelectedSubmitType("accept");
      }
    } else {
      setSelectedSubmitType("response");
      setHasAddedResponse(true);
    }

    setHumanResponse((prev) => {
      const newResponse: HumanResponseWithEdits = {
        type: response.type,
        args: change,
      };

      return prev.map((p) => {
        if (p.type === response.type) {
          if (p.acceptAllowed) {
            return {
              ...newResponse,
              acceptAllowed: true,
              editsMade: !!change,
            };
          }
          return newResponse;
        }
        return p;
      });
    });
  };

  return (
    <div className="flex w-full flex-col gap-4">
      {showArgsOutsideActionCards && (
        <div className="rounded-lg border border-border bg-card p-4">
          <ArgsRenderer args={interruptValue.action_request.args} />
        </div>
      )}

      <div className="flex w-full flex-col gap-4">
        <EditAndOrAcceptComponent
          humanResponse={humanResponse}
          streaming={streaming}
          initialValues={initialValues}
          interruptValue={interruptValue}
          onEditChange={onEditChange}
          handleSubmit={handleSubmit}
        />
        
        {supportsMultipleMethods && (
          <div className="flex items-center gap-3 my-2">
            <Separator className="flex-1" />
            <span className="text-sm text-muted-foreground">Or</span>
            <Separator className="flex-1" />
          </div>
        )}
        
        <ResponseComponent
          humanResponse={humanResponse}
          streaming={streaming}
          showArgsInResponse={showArgsInResponse}
          interruptValue={interruptValue}
          onResponseChange={onResponseChange}
          handleSubmit={handleSubmit}
        />
        
        {streaming && (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <div className="h-1.5 w-1.5 animate-pulse rounded-full bg-primary"></div>
            Running...
          </div>
        )}
        
        {streamFinished && (
          <div className="text-sm font-medium text-green-600">
            Successfully finished execution.
          </div>
        )}
      </div>
    </div>
  );
} 