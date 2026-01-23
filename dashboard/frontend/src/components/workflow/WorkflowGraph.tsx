import React, { useEffect } from "react";
import {
  ReactFlow,
  Controls,
  Background,
  useNodesState,
  useEdgesState,
  Node,
  Edge,
  Position,
  MarkerType,
  useReactFlow,
  ReactFlowProvider,
} from "@xyflow/react";
import dagre from "dagre";
import { useQuery } from "@tanstack/react-query";
import { useWebSocket } from "@/hooks";
import { Loader2 } from "lucide-react";
import "@xyflow/react/dist/style.css";

// Node Types
import { Card, CardContent, Guidance } from "@/components/ui";

interface GraphDefinition {
  nodes: Array<{ id: string; type?: string; data: any }>;
  edges: Array<{ source: string; target: string; type?: string; data?: any }>;
}

// Custom Node Component
const WorkflowNode = ({ data }: any) => {
  const isActive = data.status === "active";
  const isCompleted = data.status === "completed";
  const isError = data.status === "error";

  let borderColor = "border-border";
  let bgColor = "bg-card";

  if (isActive) {
    borderColor = "border-green-500 animate-pulse";
    bgColor = "bg-green-50/10";
  } else if (isCompleted) {
    borderColor = "border-blue-500";
  } else if (isError) {
    borderColor = "border-red-500";
  }

  return (
    <Card
      className={`w-[250px] ${borderColor} ${bgColor} transition-colors duration-300`}
    >
      <CardContent className="p-4 flex items-center justify-between">
        <div className="font-semibold capitalize">{data.label}</div>
        {isActive && (
          <Loader2 className="h-4 w-4 animate-spin text-green-500" />
        )}
        {isCompleted && <div className="h-2 w-2 rounded-full bg-blue-500" />}
      </CardContent>
    </Card>
  );
};

const RouterNode = ({ data }: any) => {
  const isActive = data.status === "active";

  let borderColor = "border-yellow-500";
  let bgColor = "bg-yellow-500/10";

  if (isActive) {
    borderColor = "border-yellow-400 animate-pulse";
    bgColor = "bg-yellow-400/20";
  }

  return (
    <div className="relative flex items-center justify-center w-16 h-16">
      <div
        className={`absolute w-12 h-12 rotate-45 border-2 ${borderColor} ${bgColor} transition-colors duration-300 z-0`}
      />
      {/* Label (if any) or icon */}
      <div className="z-10 text-[10px] font-mono text-muted-foreground">
        {data.label}
      </div>
    </div>
  );
};

const nodeTypes = {
  default: WorkflowNode,
  input: WorkflowNode, // Reuse same style
  output: WorkflowNode,
  router: RouterNode,
};

// Layout helper
const getLayoutedElements = (
  nodes: Node[],
  edges: Edge[],
  direction = "TB",
) => {
  const dagreGraph = new dagre.graphlib.Graph();
  dagreGraph.setDefaultEdgeLabel(() => ({}));

  dagreGraph.setGraph({ rankdir: direction });

  nodes.forEach((node) => {
    // Different size for routers
    const isRouter = node.type === "router";
    const width = isRouter ? 80 : 250;
    const height = isRouter ? 80 : 80;
    dagreGraph.setNode(node.id, { width, height });
  });

  edges.forEach((edge) => {
    dagreGraph.setEdge(edge.source, edge.target);
  });

  dagre.layout(dagreGraph);

  const layoutedNodes = nodes.map((node) => {
    const nodeWithPosition = dagreGraph.node(node.id);
    const isRouter = node.type === "router";
    const width = isRouter ? 80 : 250;
    const height = isRouter ? 80 : 80;

    node.targetPosition = Position.Top;
    node.sourcePosition = Position.Bottom;

    return {
      ...node,
      position: {
        x: nodeWithPosition.x - width / 2,
        y: nodeWithPosition.y - height / 2,
      },
    };
  });

  return { nodes: layoutedNodes, edges };
};

const WorkflowGraphInner = React.memo(function WorkflowGraphInner({
  projectName,
}: {
  projectName: string;
}) {
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const { fitView } = useReactFlow();

  // Fetch graph definition
  const { data: graphData, isLoading } = useQuery<GraphDefinition>({
    queryKey: ["workflow", "graph", projectName],
    queryFn: async () => {
      const res = await fetch(`/api/projects/${projectName}/workflow/graph`);
      if (!res.ok) throw new Error("Failed to fetch graph");
      return res.json();
    },
    staleTime: 5 * 60 * 1000,
  });

  // WebSocket for updates
  const { lastEvent } = useWebSocket(projectName);

  // Initialize graph
  useEffect(() => {
    if (graphData) {
      const initialNodes: Node[] = graphData.nodes.map((n) => ({
        id: n.id,
        type: n.type || "default", // Helper for router types
        data: { label: n.data.label || n.id, status: "idle" },
        position: { x: 0, y: 0 },
      }));

      const initialEdges: Edge[] = graphData.edges.map((e, i) => ({
        id: `e-${e.source}-${e.target}-${i}`,
        source: e.source,
        target: e.target,
        type: "smoothstep",
        animated: false, // Default not animated
        label: e.data?.label, // Show label
        markerEnd: { type: MarkerType.ArrowClosed },
        style: { stroke: "#94a3b8", opacity: 1 },
      }));

      const layout = getLayoutedElements(initialNodes, initialEdges);
      setNodes(layout.nodes);
      setEdges(layout.edges);

      setTimeout(() => fitView(), 100);
    }
  }, [graphData, setNodes, setEdges, fitView]);

  // Handle Events
  useEffect(() => {
    if (!lastEvent) return;

    if (lastEvent.type === "node_start") {
      const nodeId = lastEvent.data?.node;
      setNodes((nds) =>
        nds.map((node) => ({
          ...node,
          data: {
            ...node.data,
            status: node.id === nodeId ? "active" : node.data.status,
          },
        })),
      );
    } else if (lastEvent.type === "node_end") {
      const nodeId = lastEvent.data?.node;
      setNodes((nds) =>
        nds.map((node) => ({
          ...node,
          data: {
            ...node.data,
            status: node.id === nodeId ? "completed" : node.data.status,
          },
        })),
      );
    } else if (lastEvent.type === "path_decision") {
      const { router, decision } = lastEvent.data || {};
      // Highlight logic
      // 1. Find the router node and mark as active/visited
      // 2. Find the edge from router -> target (matching decision)
      // 3. Animate that edge and dim others from the same router

      // Note: decision might be node name OR raw value.
      // Our backend emits "planning" or "implementation".
      // The edge.data.label typically matches this.
      // Or edge.target matches it.

      setEdges((eds) =>
        eds.map((edge) => {
          if (typeof router === "string" && edge.source.includes(router)) {
            // simple matching for now: router="validation_router", source="validation_fan_in_router"
            // Check if this edge matches decision
            const isTaken =
              edge.data?.condition === decision ||
              edge.target === decision ||
              edge.label === decision;

            if (isTaken) {
              return {
                ...edge,
                animated: true,
                style: {
                  ...edge.style,
                  stroke: "#3b82f6",
                  strokeWidth: 2,
                  opacity: 1,
                },
              };
            } else {
              // Dim other paths from this router
              return {
                ...edge,
                animated: false,
                style: { ...edge.style, stroke: "#94a3b8", opacity: 0.3 },
              };
            }
          }
          return edge;
        }),
      );
    }
  }, [lastEvent, setNodes, setEdges]);

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        Loading graph...
      </div>
    );
  }

  return (
    <div className="h-[600px] w-full border rounded-lg bg-background/50 backdrop-blur-sm relative">
      <div className="absolute top-4 right-4 z-10">
        <Guidance
          content={
            <div className="space-y-2">
              <p className="font-semibold">Graph Legend</p>
              <div className="text-xs space-y-1">
                <div className="flex items-center gap-2">
                  <div className="w-2 h-2 rounded-full bg-green-500" />
                  <span>Active Node</span>
                </div>
                <div className="flex items-center gap-2">
                  <div className="w-2 h-2 rounded-full bg-blue-500" />
                  <span>Completed</span>
                </div>
                <div className="flex items-center gap-2">
                  <div className="w-2 h-2 rounded-full bg-red-500" />
                  <span>Error</span>
                </div>
                <div className="flex items-center gap-2">
                  <div className="w-2 h-2 rotate-45 border border-yellow-500" />
                  <span>Router/Decision</span>
                </div>
              </div>
            </div>
          }
        />
      </div>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        nodeTypes={nodeTypes}
        fitView
        attributionPosition="bottom-right"
      >
        <Controls />
        <Background color="#94a3b8" gap={16} size={1} />
      </ReactFlow>
    </div>
  );
});

export function WorkflowGraph({ projectName }: { projectName: string }) {
  return (
    <ReactFlowProvider>
      <WorkflowGraphInner projectName={projectName} />
    </ReactFlowProvider>
  );
}
