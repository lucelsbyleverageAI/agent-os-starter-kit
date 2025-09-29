"use client";

import { useEffect, useState, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { toast } from "sonner";
import { useAuthContext } from "@/providers/Auth";
import { useAgentsContext } from "@/providers/Agents";

type RetiredGraph = {
  graph_id: string;
  status: "marked" | "pruned";
  reason?: string | null;
  notes?: string | null;
  marked_by?: string | null;
  marked_at?: string | null;
  pruned_by?: string | null;
  pruned_at?: string | null;
};

export function RetiredGraphsTable() {
  const { session } = useAuthContext();
  const agentsCtx = useAgentsContext();
  const { discoveryData } = useAgentsContext();
  const [loading, setLoading] = useState(true);
  const [rows, setRows] = useState<RetiredGraph[]>([]);
  const [availableGraphIds, setAvailableGraphIds] = useState<string[]>([]);
  const [selectedGraphId, setSelectedGraphId] = useState("");
  const [reason, setReason] = useState("");

  const graphNameById = (discoveryData?.valid_graphs || []).reduce<Record<string, string>>((acc, g) => {
    if (g?.name) acc[g.graph_id] = g.name;
    return acc;
  }, {});

  const formatGraphId = (id: string) => id.replace(/_/g, ' ').replace(/\b\w/g, (l) => l.toUpperCase());

  const fetchRows = useCallback(async () => {
    if (!session?.accessToken) return;
    setLoading(true);
    try {
      const res = await fetch(`/api/langconnect/agents/admin/retired-graphs`, {
        headers: { Authorization: `Bearer ${session.accessToken}` },
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setRows(data.retired_graphs || []);
    } catch (_e) {
      toast.error("Failed to load retired graphs");
    } finally {
      setLoading(false);
    }
  }, [session?.accessToken]);

  const prune = async (graphId: string) => {
    if (!session?.accessToken) return;
    try {
      const res = await fetch(`/api/langconnect/agents/admin/retired-graphs/${graphId}/prune`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${session.accessToken}` },
      });
      if (!res.ok) throw new Error(await res.text());
      toast.success("Graph pruned");
      fetchRows();
      // Invalidate and refresh agents so UI updates immediately
      try {
        agentsCtx.invalidateGraphDiscoveryCache();
        agentsCtx.invalidateAssistantListCache();
        agentsCtx.invalidateAllAssistantCaches();
        await agentsCtx.refreshAgents(true);
      } catch {
        // Ignore cache refresh errors
      }
    } catch (_e) {
      toast.error("Failed to prune graph");
    }
  };

  const unretire = async (graphId: string) => {
    if (!session?.accessToken) return;
    try {
      const res = await fetch(`/api/langconnect/agents/admin/retired-graphs/${graphId}/unretire`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${session.accessToken}` },
      });
      if (!res.ok) throw new Error(await res.text());
      toast.success("Graph unretired");
      fetchRows();
      try {
        agentsCtx.invalidateGraphDiscoveryCache();
        agentsCtx.invalidateAssistantListCache();
        agentsCtx.invalidateAllAssistantCaches();
        await agentsCtx.refreshAgents(true);
      } catch {
        // Ignore cache refresh errors
      }
    } catch (_e) {
      toast.error("Failed to unretire graph");
    }
  };

  const fetchAvailableGraphs = useCallback(async () => {
    if (!session?.accessToken) return;
    try {
      const res = await fetch(`/api/langconnect/agents/mirror/graphs`, {
        headers: { Authorization: `Bearer ${session.accessToken}` },
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      const retiredSet = new Set(rows.map(r => r.graph_id));
      const ids: string[] = (data.graphs || [])
        .map((g: any) => g.graph_id)
        .filter((id: string) => id && !retiredSet.has(id));
      setAvailableGraphIds(ids);
      // If current selection is no longer valid, reset it
      if (selectedGraphId && !ids.includes(selectedGraphId)) {
        setSelectedGraphId("");
      }
    } catch (_e) {
      // Silent fallback; dropdown will be empty
    }
  }, [session?.accessToken, rows, selectedGraphId]);

  useEffect(() => { fetchRows(); }, [fetchRows]);
  useEffect(() => { fetchAvailableGraphs(); }, [fetchAvailableGraphs]);

  return (
    <Card>
      <CardContent className="pt-6">
        {/* Mark new graph as retired */}
        <div className="flex items-center gap-2 mb-4">
          <Select value={selectedGraphId} onValueChange={(v) => setSelectedGraphId(v)}>
            <SelectTrigger className="w-[320px]">
              <SelectValue placeholder={availableGraphIds.length ? "Select a graph to retire" : "No available graphs"} />
            </SelectTrigger>
            <SelectContent>
              {availableGraphIds.map((id) => (
                <SelectItem key={id} value={id}>
                  {graphNameById[id] || formatGraphId(id)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Input placeholder="reason (optional)" value={reason} onChange={(e) => setReason(e.target.value)} />
          <Button
            onClick={async () => {
              if (!selectedGraphId) {
                toast.error("Select a graph");
                return;
              }
              if (!session?.accessToken) return;
              try {
                const res = await fetch(`/api/langconnect/agents/admin/retired-graphs/${encodeURIComponent(selectedGraphId)}/retire`, {
                  method: 'POST',
                  headers: { 
                    Authorization: `Bearer ${session.accessToken}`,
                    'Content-Type': 'application/json'
                  },
                  body: JSON.stringify({ reason })
                });
                if (!res.ok) throw new Error(await res.text());
                toast.success("Graph marked as retired");
                setSelectedGraphId("");
                setReason("");
                fetchRows();
                fetchAvailableGraphs();
                try {
                  agentsCtx.invalidateGraphDiscoveryCache();
                  agentsCtx.invalidateAssistantListCache();
                  agentsCtx.invalidateAllAssistantCaches();
                  await agentsCtx.refreshAgents(true);
                } catch {
                  // Ignore cache refresh errors
                }
              } catch (_e) {
                toast.error("Failed to mark as retired");
              }
            }}
            disabled={!selectedGraphId}
          >
            Mark as retired
          </Button>
        </div>

        {loading ? (
          <div className="text-sm text-muted-foreground">Loading…</div>
        ) : rows.length === 0 ? (
          <div className="text-sm text-muted-foreground">No retired graphs</div>
        ) : (
          <div className="space-y-4">
            {rows.map((r) => (
              <div key={r.graph_id} className="flex items-center justify-between border rounded p-3">
                <div className="flex flex-col">
                  <div className="font-medium">{graphNameById[r.graph_id] || formatGraphId(r.graph_id)}</div>
                  <div className="text-xs text-muted-foreground">Status: {r.status}</div>
                  {r.reason ? <div className="text-xs text-muted-foreground">Reason: {r.reason}</div> : null}
                </div>
                <div className="flex items-center gap-2">
                  {r.status === 'marked' && (
                    <>
                      <Button variant="destructive" size="sm" onClick={() => prune(r.graph_id)}>Prune now</Button>
                      <Button variant="secondary" size="sm" onClick={() => unretire(r.graph_id)}>Unretire</Button>
                    </>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}


