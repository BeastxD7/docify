"use client";

import { Suspense, useEffect, useState, useCallback } from "react";
import { useSearchParams } from "next/navigation";
import { Share2, RefreshCw, GitBranch, Tag, Info } from "lucide-react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { GraphView, nodeColor } from "@/components/graph-view";
import {
  listDocuments,
  getEntities,
  getRelations,
  getCommunities,
  type Document,
  type GraphEntity,
  type GraphCommunity,
} from "@/lib/api";

function GraphPageInner() {
  const searchParams = useSearchParams();
  const [docs, setDocs] = useState<Document[]>([]);
  const [selectedDocId, setSelectedDocId] = useState(searchParams.get("doc") ?? "");
  const [entities, setEntities] = useState<GraphEntity[]>([]);
  const [relations, setRelations] = useState<{ source: string; target: string; type: string; chunk_index: number | null }[]>([]);
  const [communities, setCommunities] = useState<GraphCommunity[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedEntity, setSelectedEntity] = useState<GraphEntity | null>(null);
  const [visibleTypes, setVisibleTypes] = useState<Set<string>>(new Set());

  const allTypes = [...new Set(entities.map((e) => e.type.toUpperCase()))].sort();

  useEffect(() => {
    listDocuments()
      .then((r) => setDocs(r.data))
      .catch(() => toast.error("Failed to load documents"));
  }, []);

  // Pre-select doc from URL query param
  useEffect(() => {
    const docId = searchParams.get("doc");
    if (docId) setSelectedDocId(docId);
  }, [searchParams]);

  async function loadGraph() {
    if (!selectedDocId) return;
    setLoading(true);
    setSelectedEntity(null);
    setEntities([]);
    setRelations([]);
    setCommunities([]);
    try {
      const [entRes, relRes, commRes] = await Promise.all([
        getEntities(selectedDocId),
        getRelations(selectedDocId),
        getCommunities(selectedDocId),
      ]);
      setEntities(entRes.data.entities);
      setRelations(relRes.data.relations);
      setCommunities(commRes.data.communities);
      setVisibleTypes(new Set(entRes.data.entities.map((e) => e.type.toUpperCase())));
      toast.success(
        `${entRes.data.count} entities · ${relRes.data.count} relations · ${commRes.data.count} communities`,
      );
    } catch (e: unknown) {
      toast.error((e as Error).message ?? "Failed to load graph");
    } finally {
      setLoading(false);
    }
  }

  function toggleType(type: string) {
    setVisibleTypes((prev) => {
      const next = new Set(prev);
      if (next.has(type)) next.delete(type);
      else next.add(type);
      return next;
    });
  }

  const handleNodeClick = useCallback((entity: GraphEntity) => {
    setSelectedEntity(entity);
  }, []);

  const completedDocs = docs.filter((d) => d.graph_status === "completed");

  return (
    <div className="flex flex-col h-full gap-4">
      {/* Header */}
      <div className="flex items-center gap-3 flex-wrap shrink-0">
        <div className="flex-1 min-w-0">
          <h2 className="text-xl font-semibold">Knowledge Graph</h2>
          <p className="text-xs text-muted-foreground">
            {entities.length > 0
              ? `${entities.length} entities · ${relations.length} relations · ${communities.length} communities`
              : "Select a document to explore its knowledge graph"}
          </p>
        </div>

        <select
          className="border border-border rounded-md px-3 py-1.5 text-sm bg-background text-foreground min-w-[200px]"
          value={selectedDocId}
          onChange={(e) => setSelectedDocId(e.target.value)}
        >
          <option value="">— Select document —</option>
          {completedDocs.map((d) => (
            <option key={d.id} value={d.id}>
              {d.filename}
            </option>
          ))}
          {completedDocs.length === 0 && docs.length > 0 && (
            <option disabled>No graph-ready documents yet</option>
          )}
        </select>

        <Button onClick={loadGraph} disabled={!selectedDocId || loading} size="sm">
          {loading ? (
            <RefreshCw className="h-4 w-4 animate-spin mr-1.5" />
          ) : (
            <Share2 className="h-4 w-4 mr-1.5" />
          )}
          {loading ? "Loading…" : "Load Graph"}
        </Button>
      </div>

      {/* Main split */}
      <div className="flex flex-1 gap-4 min-h-0">
        {/* Graph canvas */}
        <div className="flex-1 rounded-lg border border-border bg-card overflow-hidden">
          <GraphView
            entities={entities}
            relations={relations}
            communities={communities}
            visibleTypes={visibleTypes}
            onNodeClick={handleNodeClick}
          />
        </div>

        {/* Side panel */}
        <div className="w-64 flex flex-col gap-3 shrink-0 overflow-y-auto">
          {/* Type legend + filter */}
          {allTypes.length > 0 && (
            <Card>
              <CardContent className="p-3">
                <p className="text-xs font-semibold text-muted-foreground mb-2 flex items-center gap-1.5">
                  <Tag className="h-3 w-3" /> ENTITY TYPES
                </p>
                <div className="flex flex-col gap-0.5">
                  {allTypes.map((type) => {
                    const active = visibleTypes.has(type);
                    const count = entities.filter((e) => e.type.toUpperCase() === type).length;
                    return (
                      <button
                        key={type}
                        onClick={() => toggleType(type)}
                        className="flex items-center gap-2 text-xs rounded px-1.5 py-1 hover:bg-accent transition-colors w-full text-left"
                      >
                        <span
                          className="w-2.5 h-2.5 rounded-full shrink-0 transition-opacity"
                          style={{ backgroundColor: nodeColor(type), opacity: active ? 1 : 0.25 }}
                        />
                        <span className={active ? "text-foreground" : "text-muted-foreground line-through"}>
                          {type}
                        </span>
                        <span className="ml-auto text-muted-foreground tabular-nums">{count}</span>
                      </button>
                    );
                  })}
                </div>
              </CardContent>
            </Card>
          )}

          {/* Selected entity detail */}
          {selectedEntity ? (
            <Card>
              <CardContent className="p-3 flex flex-col gap-2">
                <p className="text-xs font-semibold text-muted-foreground flex items-center gap-1.5">
                  <Info className="h-3 w-3" /> ENTITY
                </p>
                <div className="flex items-start gap-2">
                  <span
                    className="w-2.5 h-2.5 rounded-full shrink-0 mt-1"
                    style={{ backgroundColor: nodeColor(selectedEntity.type) }}
                  />
                  <div className="min-w-0">
                    <p className="font-medium text-sm break-words">{selectedEntity.name}</p>
                    <Badge variant="secondary" className="text-xs mt-0.5">
                      {selectedEntity.type}
                    </Badge>
                  </div>
                </div>
                {selectedEntity.description && (
                  <p className="text-xs text-muted-foreground leading-relaxed">
                    {selectedEntity.description}
                  </p>
                )}
                {selectedEntity.page_number != null && (
                  <p className="text-xs text-muted-foreground">Page {selectedEntity.page_number}</p>
                )}
              </CardContent>
            </Card>
          ) : entities.length > 0 ? (
            <p className="text-xs text-muted-foreground px-1">Click a node to inspect it</p>
          ) : null}

          {/* Communities */}
          {communities.length > 0 && (
            <Card>
              <CardContent className="p-3">
                <p className="text-xs font-semibold text-muted-foreground mb-2 flex items-center gap-1.5">
                  <GitBranch className="h-3 w-3" /> COMMUNITIES ({communities.length})
                </p>
                <div className="flex flex-col gap-3">
                  {communities.slice(0, 6).map((c) => (
                    <div key={c.community_id} className="text-xs">
                      <p className="font-medium text-foreground mb-0.5">{c.size} entities</p>
                      <p className="text-muted-foreground leading-relaxed line-clamp-3">
                        {c.summary}
                      </p>
                    </div>
                  ))}
                  {communities.length > 6 && (
                    <p className="text-xs text-muted-foreground">
                      +{communities.length - 6} more communities
                    </p>
                  )}
                </div>
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}

export default function GraphPage() {
  return (
    <Suspense fallback={<div className="flex items-center justify-center h-full text-muted-foreground text-sm">Loading…</div>}>
      <GraphPageInner />
    </Suspense>
  );
}
