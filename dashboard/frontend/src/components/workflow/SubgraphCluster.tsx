/**
 * SubgraphCluster - Collapsible container for grouped workflow nodes
 *
 * Displays a cluster of related nodes (e.g., Fixer Pipeline, Validation Fan-Out)
 * that can be expanded/collapsed for better graph readability.
 */

import { useState } from "react";
import {
  ChevronDown,
  ChevronRight,
  Wrench,
  ShieldCheck,
  CheckCircle,
  Sparkles,
  BookOpen,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader } from "@/components/ui/card";

interface SubgraphClusterProps {
  id: string;
  name: string;
  nodes: Array<{
    id: string;
    status: string;
    label: string;
    description?: string;
  }>;
  onNodeClick?: (nodeId: string) => void;
  defaultExpanded?: boolean;
}

const subgraphIcons: Record<string, React.ReactNode> = {
  fixer: <Wrench className="h-4 w-4" />,
  validation: <ShieldCheck className="h-4 w-4" />,
  verification: <CheckCircle className="h-4 w-4" />,
  quality: <Sparkles className="h-4 w-4" />,
  research: <BookOpen className="h-4 w-4" />,
};

const subgraphColors: Record<string, string> = {
  fixer: "border-orange-500/50 bg-orange-50/30 dark:bg-orange-900/10",
  validation: "border-blue-500/50 bg-blue-50/30 dark:bg-blue-900/10",
  verification: "border-green-500/50 bg-green-50/30 dark:bg-green-900/10",
  quality: "border-purple-500/50 bg-purple-50/30 dark:bg-purple-900/10",
  research: "border-cyan-500/50 bg-cyan-50/30 dark:bg-cyan-900/10",
};

const subgraphTitles: Record<string, string> = {
  fixer: "Fixer Pipeline",
  validation: "Validation Fan-Out",
  verification: "Verification Fan-Out",
  quality: "Quality Gates",
  research: "Research & Analysis",
};

export function SubgraphCluster({
  id: _id,
  name,
  nodes,
  onNodeClick,
  defaultExpanded = false,
}: SubgraphClusterProps) {
  const [isExpanded, setIsExpanded] = useState(defaultExpanded);

  const completedCount = nodes.filter((n) => n.status === "completed").length;
  const activeCount = nodes.filter(
    (n) => n.status === "active" || n.status === "in_progress",
  ).length;
  const totalCount = nodes.length;

  const isActive = activeCount > 0;
  const isCompleted = completedCount === totalCount && totalCount > 0;

  const icon = subgraphIcons[name] || subgraphIcons.fixer;
  const colors = subgraphColors[name] || subgraphColors.fixer;
  const title = subgraphTitles[name] || name;

  return (
    <Card
      className={cn(
        "w-[320px] transition-all duration-300 border-2 backdrop-blur-sm cursor-pointer",
        colors,
        isActive && "ring-2 ring-green-500/30 shadow-lg shadow-green-500/10",
        isCompleted && "ring-1 ring-blue-500/30",
      )}
      onClick={() => setIsExpanded(!isExpanded)}
    >
      <CardHeader className="pb-2 pt-3 px-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div
              className={cn(
                "p-1.5 rounded-md bg-background/80 shadow-sm",
                isActive && "text-green-600",
                isCompleted && "text-blue-600",
              )}
            >
              {icon}
            </div>
            <div>
              <h4 className="font-semibold text-sm">{title}</h4>
              <p className="text-[10px] text-muted-foreground">
                {completedCount}/{totalCount} completed
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {isActive && (
              <Badge
                variant="default"
                className="text-[9px] px-1.5 h-4 bg-green-500"
              >
                Active
              </Badge>
            )}
            {isCompleted && (
              <Badge
                variant="secondary"
                className="text-[9px] px-1.5 h-4 bg-blue-500/20 text-blue-600"
              >
                Done
              </Badge>
            )}
            {isExpanded ? (
              <ChevronDown className="h-4 w-4 text-muted-foreground" />
            ) : (
              <ChevronRight className="h-4 w-4 text-muted-foreground" />
            )}
          </div>
        </div>
      </CardHeader>

      {isExpanded && (
        <CardContent className="pt-0 pb-3 px-4">
          <div className="space-y-1.5 mt-2 border-t pt-2">
            {nodes.map((node) => (
              <div
                key={node.id}
                onClick={(e) => {
                  e.stopPropagation();
                  onNodeClick?.(node.id);
                }}
                className={cn(
                  "flex items-center gap-2 p-2 rounded-md text-xs transition-colors",
                  "hover:bg-background/60 cursor-pointer",
                  node.status === "active" && "bg-green-500/10",
                  node.status === "completed" && "bg-blue-500/10",
                )}
              >
                <div
                  className={cn(
                    "w-2 h-2 rounded-full shrink-0",
                    node.status === "completed" && "bg-blue-500",
                    node.status === "active" && "bg-green-500 animate-pulse",
                    node.status === "failed" && "bg-red-500",
                    node.status === "idle" && "bg-muted-foreground/30",
                  )}
                />
                <div className="flex-1 min-w-0">
                  <p className="font-medium truncate">{node.label}</p>
                  {node.description && (
                    <p className="text-[9px] text-muted-foreground truncate">
                      {node.description}
                    </p>
                  )}
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      )}
    </Card>
  );
}
