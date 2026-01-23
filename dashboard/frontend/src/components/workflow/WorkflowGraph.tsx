import React, { useCallback, useEffect, useMemo } from 'react';
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
  ConnectionLineType,
  useReactFlow,
  ReactFlowProvider,
} from '@xyflow/react';
import dagre from 'dagre';
import { useQuery } from '@tanstack/react-query';
import { useParams } from '@tanstack/react-router';
import { useWebSocket } from '@/hooks';
import { Loader2 } from 'lucide-react';
import '@xyflow/react/dist/style.css';

// Node Types
import { Card, CardContent } from '@/components/ui';

interface GraphDefinition {
  nodes: Array<{ id: string; type?: string; data: any }>;
  edges: Array<{ source: string; target: string; type?: string; data?: any }>;
}

// Layout helper
const getLayoutedElements = (nodes: Node[], edges: Edge[], direction = 'TB') => {
  const dagreGraph = new dagre.graphlib.Graph();
  dagreGraph.setDefaultEdgeLabel(() => ({}));

  const nodeWidth = 250;
  const nodeHeight = 80;

  dagreGraph.setGraph({ rankdir: direction });

  nodes.forEach((node) => {
    dagreGraph.setNode(node.id, { width: nodeWidth, height: nodeHeight });
  });

  edges.forEach((edge) => {
    dagreGraph.setEdge(edge.source, edge.target);
  });

  dagre.layout(dagreGraph);

  const layoutedNodes = nodes.map((node) => {
    const nodeWithPosition = dagreGraph.node(node.id);
    node.targetPosition = Position.Top;
    node.sourcePosition = Position.Bottom;

    // We are shifting the dagre node position (anchor=center center) to the top left
    // so it matches the React Flow node anchor point (top left).
    return {
      ...node,
      position: {
        x: nodeWithPosition.x - nodeWidth / 2,
        y: nodeWithPosition.y - nodeHeight / 2,
      },
    };
  });

  return { nodes: layoutedNodes, edges };
};

// Custom Node Component
const WorkflowNode = ({ data, selected }: any) => {
  const isActive = data.status === 'active';
  const isCompleted = data.status === 'completed';
  const isError = data.status === 'error';

  let borderColor = 'border-border';
  let bgColor = 'bg-card';

  if (isActive) {
    borderColor = 'border-green-500 animate-pulse';
    bgColor = 'bg-green-50/10';
  } else if (isCompleted) {
    borderColor = 'border-blue-500';
  } else if (isError) {
    borderColor = 'border-red-500';
  }

  return (
    <Card className={`w-[250px] ${borderColor} ${bgColor} transition-colors duration-300`}>
      <CardContent className="p-4 flex items-center justify-between">
        <div className="font-semibold capitalize">{data.label}</div>
        {isActive && <Loader2 className="h-4 w-4 animate-spin text-green-500" />}
        {isCompleted && <div className="h-2 w-2 rounded-full bg-blue-500" />}
      </CardContent>
    </Card>
  );
};

const nodeTypes = {
  default: WorkflowNode,
  input: WorkflowNode, // Reuse same style
  output: WorkflowNode,
};

function WorkflowGraphInner({ projectName }: { projectName: string }) {
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const { fitView } = useReactFlow();

  // Fetch graph definition
  const { data: graphData, isLoading } = useQuery<GraphDefinition>({
    queryKey: ['workflow', 'graph', projectName],
    queryFn: async () => {
      const res = await fetch(`/api/projects/${projectName}/workflow/graph`);
      if (!res.ok) throw new Error('Failed to fetch graph');
      return res.json();
    },
  });

  // WebSocket for updates
  const { lastEvent } = useWebSocket(projectName);

  // Initialize graph
  useEffect(() => {
    if (graphData) {
      const initialNodes: Node[] = graphData.nodes.map((n) => ({
        id: n.id,
        type: 'default',
        data: { label: n.data.label || n.id, status: 'idle' },
        position: { x: 0, y: 0 }, // layout will fix this
      }));

      const initialEdges: Edge[] = graphData.edges.map((e, i) => ({
        id: `e-${e.source}-${e.target}-${i}`,
        source: e.source,
        target: e.target,
        type: 'smoothstep',
        animated: true,
        markerEnd: { type: MarkerType.ArrowClosed },
        style: { stroke: '#94a3b8' },
      }));

      const layout = getLayoutedElements(initialNodes, initialEdges);
      setNodes(layout.nodes);
      setEdges(layout.edges);
      
      // Initial fit after short delay to allow layout
      setTimeout(() => fitView(), 100);
    }
  }, [graphData, setNodes, setEdges, fitView]);

  // Handle Events
  useEffect(() => {
    if (!lastEvent) return;

    if (lastEvent.type === 'node_start') {
      const nodeId = lastEvent.data?.node;
      setNodes((nds) =>
        nds.map((node) => ({
          ...node,
          data: {
            ...node.data,
            status: node.id === nodeId ? 'active' : node.data.status,
          },
        }))
      );
    } else if (lastEvent.type === 'node_end') {
      const nodeId = lastEvent.data?.node;
      setNodes((nds) =>
        nds.map((node) => ({
          ...node,
          data: {
            ...node.data,
            status: node.id === nodeId ? 'completed' : node.data.status,
          },
        }))
      );
    }
  }, [lastEvent, setNodes]);

  if (isLoading) {
    return <div className="flex h-full items-center justify-center">Loading graph...</div>;
  }

  return (
    <div className="h-[600px] w-full border rounded-lg bg-background/50 backdrop-blur-sm">
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
}

export function WorkflowGraph({ projectName }: { projectName: string }) {
  return (
    <ReactFlowProvider>
      <WorkflowGraphInner projectName={projectName} />
    </ReactFlowProvider>
  );
}
