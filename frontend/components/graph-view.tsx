"use client";

import { useEffect, useRef } from "react";
import type { GraphEntity, GraphRelation, GraphCommunity } from "@/lib/api";

export const TYPE_COLORS: Record<string, string> = {
  PERSON:       "#3b82f6",
  ORGANIZATION: "#f59e0b",
  LOCATION:     "#22c55e",
  EVENT:        "#ef4444",
  CONCEPT:      "#8b5cf6",
  PRODUCT:      "#06b6d4",
  TECHNOLOGY:   "#14b8a6",
};

const COMMUNITY_BORDERS = [
  "#fbbf24", "#34d399", "#60a5fa", "#f87171", "#a78bfa",
  "#2dd4bf", "#fb923c", "#e879f9", "#4ade80", "#38bdf8",
];

export function nodeColor(type: string): string {
  return TYPE_COLORS[type.toUpperCase()] ?? "#94a3b8";
}

interface Props {
  entities: GraphEntity[];
  relations: GraphRelation[];
  communities: GraphCommunity[];
  visibleTypes: Set<string>;
  onNodeClick: (entity: GraphEntity) => void;
}

export function GraphView({ entities, relations, communities, visibleTypes, onNodeClick }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const cyRef = useRef<any>(null);
  const onClickRef = useRef(onNodeClick);
  useEffect(() => { onClickRef.current = onNodeClick; });

  // Rebuild graph when data changes
  useEffect(() => {
    if (!containerRef.current || entities.length === 0) return;

    const memberCommunity: Record<string, number> = {};
    communities.forEach((c) => {
      c.members.forEach((m) => { memberCommunity[m] = c.community_id; });
    });

    const entityMap = new Map(entities.map((e) => [e.name, e]));

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const elements: any[] = [];

    entities.forEach((ent) => {
      const commId = memberCommunity[ent.name];
      elements.push({
        group: "nodes",
        data: {
          id: ent.name,
          label: ent.name.length > 14 ? ent.name.slice(0, 14) + "…" : ent.name,
          fullName: ent.name,
          type: ent.type.toUpperCase(),
          description: ent.description ?? "",
          page_number: ent.page_number,
          commId: commId ?? -1,
          borderColor: commId !== undefined
            ? COMMUNITY_BORDERS[commId % COMMUNITY_BORDERS.length]
            : "transparent",
        },
      });
    });

    const seenEdges = new Set<string>();
    relations.forEach((rel, i) => {
      if (!entityMap.has(rel.source) || !entityMap.has(rel.target)) return;
      const key = `${rel.source}||${rel.target}||${rel.type}`;
      if (seenEdges.has(key)) return;
      seenEdges.add(key);
      elements.push({
        group: "edges",
        data: {
          id: `e${i}`,
          source: rel.source,
          target: rel.target,
          label: rel.type.replace(/_/g, " "),
        },
      });
    });

    import("cytoscape").then(({ default: cytoscape }) => {
      cyRef.current?.destroy();

      const cy = cytoscape({
        container: containerRef.current,
        elements,
        style: [
          {
            selector: "node",
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            style: {
              "background-color": (ele: any) => nodeColor(ele.data("type")),
              label: "data(label)",
              color: "#fff",
              "font-size": "9px",
              "text-valign": "center",
              "text-halign": "center",
              "text-wrap": "wrap",
              width: 38,
              height: 38,
              "border-width": (ele: any) => (ele.data("commId") >= 0 ? 3 : 0),
              "border-color": (ele: any) => ele.data("borderColor"),
            } as any, // eslint-disable-line @typescript-eslint/no-explicit-any
          },
          {
            selector: "node:selected",
            style: {
              "border-width": 4,
              "border-color": "#f97316",
              "overlay-color": "#f97316",
              "overlay-opacity": 0.1,
            } as any,
          },
          {
            selector: "node.faded",
            style: { opacity: 0.15 },
          },
          {
            selector: "edge",
            style: {
              width: 1.5,
              "line-color": "#475569",
              "target-arrow-color": "#475569",
              "target-arrow-shape": "triangle",
              "curve-style": "bezier",
              label: "data(label)",
              "font-size": "7px",
              color: "#94a3b8",
              "text-rotation": "autorotate",
              "text-background-color": "#0f172a",
              "text-background-opacity": 0.7,
              "text-background-padding": "2px",
            } as any,
          },
          {
            selector: "edge.faded",
            style: { opacity: 0.05 },
          },
        ],
        layout: {
          name: "cose",
          animate: false,
          padding: 40,
          nodeRepulsion: () => 8000,
          edgeElasticity: () => 100,
          gravity: 0.25,
          numIter: 1000,
        } as any,
      });

      cy.on("tap", "node", (evt: any) => {
        const name = evt.target.data("fullName");
        const entity = entityMap.get(name);
        if (entity) {
          cy.elements().addClass("faded");
          evt.target.closedNeighborhood().removeClass("faded");
          onClickRef.current(entity);
        }
      });

      // Click on background → clear fading
      cy.on("tap", (evt: any) => {
        if (evt.target === cy) {
          cy.elements().removeClass("faded");
        }
      });

      cyRef.current = cy;
    });

    return () => {
      cyRef.current?.destroy();
      cyRef.current = null;
    };
  }, [entities, relations, communities]);

  // Apply / remove type filter without rebuilding the whole graph
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;
    cy.nodes().forEach((node: any) => {
      const type: string = node.data("type");
      node.style("display", visibleTypes.has(type) ? "element" : "none");
    });
  }, [visibleTypes]);

  if (entities.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-muted-foreground text-sm">
        Select a document and click "Load Graph"
      </div>
    );
  }

  return <div ref={containerRef} className="w-full h-full" />;
}
