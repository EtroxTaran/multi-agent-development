import React, { useEffect } from "react";
import {
  ReactFlow,
  Controls,
  Background,
  MiniMap,
  Handle,
  useNodesState,
  useEdgesState,
  Node,
  Edge,
  Position,
  MarkerType,
  useReactFlow,
  ReactFlowProvider,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import dagre from "dagre";
import { useQuery } from "@tanstack/react-query";
import { useWebSocket } from "@/hooks";
import {
  BrainCircuit,
  Code,
  CheckCircle,
  Flag,
  ShieldCheck,
  Loader2,
  GitBranch,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, Guidance } from "@/components/ui";

// Icons for phases
const PhaseIcons: Record<string, React.ReactNode> = {
  planning: <BrainCircuit className="h-5 w-5" />,
  validation: <ShieldCheck className="h-5 w-5" />,
  implementation: <Code className="h-5 w-5" />,
  verification: <CheckCircle className="h-5 w-5" />,
  completion: <Flag className="h-5 w-5" />,
  default: <BrainCircuit className="h-5 w-5" />,
};

// Explanations for each phase ("explain it to a kid" style)
const PhaseDescriptions: Record<string, string> = {
  planning: "We create a blueprint for what to build.",
  validation: "We check if the plan makes sense.",
  implementation: "We write the code to build it.",
  verification: "We test it to make sure it works.",
  completion: "We finish up and show you the result.",
  default: "Working on your project...",
};

interface GraphDefinition {
  nodes: Array<{ id: string; type?: string; data: any }>;
  edges: Array<{ source: string; target: string; type?: string; data?: any }>;
}

const getStatusColor = (status: string) => {
  switch (status) {
    case "completed":
      return "border-blue-500 bg-blue-50/50 dark:bg-blue-900/10";
    case "active":
      return "border-green-500 bg-green-50/50 dark:bg-green-900/10 shadow-[0_0_15px_-3px_rgba(34,197,94,0.4)]";
    case "failed":
      return "border-red-500 bg-red-50/50 dark:bg-red-900/10";
    case "paused":
      return "border-orange-500 bg-orange-50/50 dark:bg-orange-900/10";
    default:
      return "border-border/50 bg-card/50"; // idle
  }
};

const WorkflowNode = ({ data }: any) => {
  const status = data.status || "idle";
  const label = data.label.toLowerCase();

  // Determine icon based on label content
  let icon = PhaseIcons.default;
  let description = PhaseDescriptions.default;

  if (label.includes("plan")) {
    icon = PhaseIcons.planning;
    description = PhaseDescriptions.planning;
  } else if (label.includes("valid") || label.includes("check")) {
    icon = PhaseIcons.validation;
    description = PhaseDescriptions.validation;
  } else if (label.includes("implement") || label.includes("exec")) {
    icon = PhaseIcons.implementation;
    description = PhaseDescriptions.implementation;
  } else if (label.includes("verif") || label.includes("test")) {
    icon = PhaseIcons.verification;
    description = PhaseDescriptions.verification;
  } else if (label.includes("complete") || label.includes("finish")) {
    icon = PhaseIcons.completion;
    description = PhaseDescriptions.completion;
  }

  const isActive = status === "active" || status === "in_progress";
  const colors = getStatusColor(status);

  return (
    <div className="relative">
      {/* Target Handle - receives incoming edges */}
      <Handle
        type="target"
        position={Position.Top}
        className="!w-3 !h-3 !bg-slate-400 !border-2 !border-background"
      />

      <Card
        className={cn(
          "w-[280px] transition-all duration-300 backdrop-blur-sm",
          colors,
          isActive && "scale-105 ring-2 ring-green-500/20",
        )}
      >
        <CardContent className="p-4">
          <div className="flex items-start justify-between gap-3">
            <div
              className={cn(
                "p-2 rounded-lg bg-background/80 shadow-sm shrink-0",
                isActive && "text-green-600 dark:text-green-400",
                status === "completed" && "text-blue-600 dark:text-blue-400",
              )}
            >
              {icon}
            </div>
            <div className="flex-1 min-w-0">
              <h3 className="font-semibold tracking-tight text-sm capitalize truncate mb-1">
                {data.label}
              </h3>
              <p className="text-[10px] text-muted-foreground leading-snug line-clamp-2 mb-2">
                {description}
              </p>
              <div className="flex items-center gap-2">
                <Badge
                  variant={status === "active" ? "default" : "secondary"}
                  className="text-[10px] uppercase px-1.5 h-5"
                >
                  {status.replace("_", " ")}
                </Badge>
                {isActive && (
                  <Loader2 className="h-3 w-3 animate-spin text-muted-foreground" />
                )}
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Source Handle - sends outgoing edges */}
      <Handle
        type="source"
        position={Position.Bottom}
        className="!w-3 !h-3 !bg-slate-400 !border-2 !border-background"
      />
    </div>
  );
};

const RouterNode = ({ data }: any) => {
  const status = data.status;
  const isActive = status === "active" || status === "visiting";

  return (
    <div className="relative flex items-center justify-center w-20 h-20 group">
      {/* Target Handle - receives incoming edges */}
      <Handle
        type="target"
        position={Position.Top}
        className="!w-3 !h-3 !bg-yellow-500 !border-2 !border-background"
      />

      {/* Outer Glow */}
      <div
        className={cn(
          "absolute inset-0 bg-yellow-500/20 rounded-lg rotate-45 transition-all duration-500",
          isActive
            ? "opacity-100 scale-110 blur-md"
            : "opacity-0 group-hover:opacity-50",
        )}
      />

      {/* Main Diamond */}
      <div
        className={cn(
          "absolute w-14 h-14 rotate-45 border-2 bg-background shadow-lg transition-all duration-300 flex items-center justify-center",
          isActive
            ? "border-yellow-500 scale-110"
            : "border-muted-foreground/30 hover:border-yellow-500/50",
        )}
      >
        <div className="-rotate-45 text-yellow-500">
          <GitBranch className="h-6 w-6" />
        </div>
      </div>

      {/* Label */}
      <div className="absolute -bottom-8 whitespace-nowrap z-10">
        <span className="text-[10px] font-mono font-medium text-muted-foreground bg-background/90 px-2 py-0.5 rounded border shadow-sm">
          {data.label || "Router"}
        </span>
      </div>

      {/* Source Handle - sends outgoing edges */}
      <Handle
        type="source"
        position={Position.Bottom}
        className="!w-3 !h-3 !bg-yellow-500 !border-2 !border-background"
      />
    </div>
  );
};

const nodeTypes = {
  default: WorkflowNode,
  input: WorkflowNode,
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
      const res = await fetch(`/api/projects/${projectName}/graph`);
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
      const initialNodes: Node[] = graphData.nodes.map((n: any) => ({
        id: n.id,
        type: n.type || "default", // Helper for router types
        data: { label: n.data.label || n.id, status: n.data.status || "idle" },
        position: { x: 0, y: 0 },
      }));

      const initialEdges: Edge[] = graphData.edges.map((e: any, i: number) => ({
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
        defaultEdgeOptions={{
          type: "smoothstep",
          markerEnd: { type: MarkerType.ArrowClosed, color: "#64748b" },
          style: { strokeWidth: 2, stroke: "#64748b" },
        }}
        fitView
        fitViewOptions={{ padding: 0.2, maxZoom: 1.5 }}
        minZoom={0.1}
        maxZoom={2}
        proOptions={{ hideAttribution: true }}
        panOnScroll
        zoomOnScroll
        zoomOnPinch
        panOnDrag
      >
        <Controls showInteractive={false} />
        <MiniMap
          nodeColor={(node) => {
            if (node.type === "router") return "#eab308";
            if (node.data?.status === "completed") return "#3b82f6";
            if (node.data?.status === "active") return "#22c55e";
            if (node.data?.status === "error") return "#ef4444";
            return "#94a3b8";
          }}
          maskColor="rgba(0, 0, 0, 0.3)"
          className="!bg-background/80 border rounded-lg"
        />
        <Background color="#64748b" gap={20} size={1} />
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
