import { GraphInfo } from "@/types/agent";
import { Bot, CheckCircle2, Layers } from "lucide-react";
import { cn } from "@/lib/utils";
import _ from "lodash";

interface GraphTemplateSelectorProps {
  graphs: GraphInfo[];
  selectedGraphId?: string;
  onSelectGraph: (graphId: string) => void;
  className?: string;
}

export function GraphTemplateSelector({
  graphs,
  selectedGraphId,
  onSelectGraph,
  className,
}: GraphTemplateSelectorProps) {
  // Filter to only show graphs that are accessible and user has permissions for
  const availableGraphs = graphs.filter(
    (graph) => graph.schema_accessible && graph.user_permission_level
  );

  if (availableGraphs.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-center">
        <div className="bg-muted mx-auto flex h-16 w-16 items-center justify-center rounded-full">
          <Layers className="text-muted-foreground h-8 w-8" />
        </div>
        <h3 className="mt-4 text-lg font-semibold">No templates available</h3>
        <p className="text-muted-foreground mt-2 max-w-sm text-sm">
          You don't have permission to create agents from any templates. Contact
          your admin to get access.
        </p>
      </div>
    );
  }

  // Define custom order for graph templates
  const graphOrder = [
    "tools_agent",
    "deepagent",
    "deep_research_agent",
    "supervisor_agent",
    "n8n_agent",
  ];

  // Sort graphs by custom order
  const sortedGraphs = [...availableGraphs].sort((a, b) => {
    const indexA = graphOrder.indexOf(a.graph_id);
    const indexB = graphOrder.indexOf(b.graph_id);

    // If both are in the order array, sort by their position
    if (indexA !== -1 && indexB !== -1) {
      return indexA - indexB;
    }
    // If only A is in the order array, it comes first
    if (indexA !== -1) return -1;
    // If only B is in the order array, it comes first
    if (indexB !== -1) return 1;
    // If neither is in the order array, maintain original order
    return 0;
  });

  return (
    <div className={cn("space-y-4", className)}>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {sortedGraphs.map((graph) => {
          const isSelected = selectedGraphId === graph.graph_id;
          const graphName = graph.name || _.startCase(graph.graph_id);
          const graphDescription =
            graph.description ||
            `AI agent template with ${graph.assistants_count} active instance${graph.assistants_count !== 1 ? "s" : ""}`;

          return (
            <button
              key={graph.graph_id}
              onClick={() => onSelectGraph(graph.graph_id)}
              className={cn(
                "group relative flex flex-col items-start gap-3 rounded-lg border p-6 text-left transition-all hover:shadow-md",
                isSelected
                  ? "border-primary bg-primary/5 ring-2 ring-primary ring-offset-2"
                  : "border-border hover:border-primary/50"
              )}
            >
              {/* Selection indicator */}
              {isSelected && (
                <div className="absolute right-3 top-3">
                  <CheckCircle2 className="text-primary h-5 w-5" />
                </div>
              )}

              {/* Icon and title */}
              <div className="flex items-start gap-3">
                <div
                  className={cn(
                    "bg-muted flex h-10 w-10 shrink-0 items-center justify-center rounded-md transition-colors",
                    isSelected && "bg-primary/10"
                  )}
                >
                  <Bot
                    className={cn(
                      "text-muted-foreground h-5 w-5",
                      isSelected && "text-primary"
                    )}
                  />
                </div>
                <div className="min-w-0 flex-1">
                  <h4 className="font-semibold leading-none">{graphName}</h4>
                </div>
              </div>

              {/* Description */}
              <p className="text-muted-foreground line-clamp-3 text-sm">
                {graphDescription}
              </p>
            </button>
          );
        })}
      </div>
    </div>
  );
}
