/**
 * NodeDetailsDrawer - Slide-out panel for detailed node information
 *
 * Shows comprehensive details when a node is clicked, including
 * description, assigned agent, status, and action buttons.
 */

import {
  X,
  RefreshCw,
  ScrollText,
  Clock,
  UserCircle,
  AlertCircle,
  CheckCircle2,
  Loader2,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";

interface NodeDetailsDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  node: {
    id: string;
    label: string;
    status: string;
    phase: number;
    subgraph?: string;
    agent?: string;
    description?: string;
  } | null;
  onRetry?: (nodeId: string) => void;
  onViewLogs?: (nodeId: string) => void;
}

const statusConfig: Record<
  string,
  { icon: React.ReactNode; color: string; label: string }
> = {
  idle: {
    icon: <Clock className="h-4 w-4" />,
    color: "text-muted-foreground bg-muted/50",
    label: "Waiting",
  },
  active: {
    icon: <Loader2 className="h-4 w-4 animate-spin" />,
    color: "text-green-600 bg-green-500/10",
    label: "Running",
  },
  in_progress: {
    icon: <Loader2 className="h-4 w-4 animate-spin" />,
    color: "text-green-600 bg-green-500/10",
    label: "In Progress",
  },
  completed: {
    icon: <CheckCircle2 className="h-4 w-4" />,
    color: "text-blue-600 bg-blue-500/10",
    label: "Completed",
  },
  failed: {
    icon: <AlertCircle className="h-4 w-4" />,
    color: "text-red-600 bg-red-500/10",
    label: "Failed",
  },
  paused: {
    icon: <Clock className="h-4 w-4" />,
    color: "text-orange-600 bg-orange-500/10",
    label: "Paused",
  },
};

const phaseNames: Record<number, string> = {
  1: "Planning",
  2: "Validation",
  3: "Implementation",
  4: "Verification",
  5: "Completion",
  0: "Error Handling",
};

const agentInfo: Record<string, { name: string; color: string }> = {
  claude: {
    name: "Claude (Anthropic)",
    color: "bg-purple-500/20 text-purple-600",
  },
  cursor: { name: "Cursor AI", color: "bg-blue-500/20 text-blue-600" },
  gemini: { name: "Gemini (Google)", color: "bg-green-500/20 text-green-600" },
};

export function NodeDetailsDrawer({
  isOpen,
  onClose,
  node,
  onRetry,
  onViewLogs,
}: NodeDetailsDrawerProps) {
  if (!node) return null;

  const status = statusConfig[node.status] || statusConfig.idle;
  const agent = node.agent ? agentInfo[node.agent] : null;

  return (
    <>
      {/* Backdrop */}
      {isOpen && (
        <div
          className="fixed inset-0 bg-black/20 backdrop-blur-sm z-40"
          onClick={onClose}
        />
      )}

      {/* Drawer */}
      <div
        className={cn(
          "fixed top-0 right-0 h-full w-[400px] bg-background border-l shadow-2xl z-50",
          "transform transition-transform duration-300 ease-in-out",
          isOpen ? "translate-x-0" : "translate-x-full",
        )}
      >
        <div className="flex flex-col h-full">
          {/* Header */}
          <div className="flex items-center justify-between p-4 border-b">
            <div className="flex items-center gap-3">
              <div className={cn("p-2 rounded-lg", status.color)}>
                {status.icon}
              </div>
              <div>
                <h2 className="font-bold">{node.label}</h2>
                <p className="text-xs text-muted-foreground">
                  Phase {node.phase}: {phaseNames[node.phase]}
                </p>
              </div>
            </div>
            <Button variant="ghost" size="icon" onClick={onClose}>
              <X className="h-4 w-4" />
            </Button>
          </div>

          {/* Content */}
          <ScrollArea className="flex-1">
            <div className="p-4 space-y-6">
              {/* Status */}
              <div className="space-y-2">
                <h3 className="text-xs font-semibold text-muted-foreground uppercase">
                  Status
                </h3>
                <Badge className={cn("text-sm px-3 py-1", status.color)}>
                  {status.icon}
                  <span className="ml-2">{status.label}</span>
                </Badge>
              </div>

              <Separator />

              {/* Description */}
              {node.description && (
                <div className="space-y-2">
                  <h3 className="text-xs font-semibold text-muted-foreground uppercase">
                    What This Does
                  </h3>
                  <p className="text-sm">{node.description}</p>
                </div>
              )}

              <Separator />

              {/* Assigned Agent */}
              {agent && (
                <div className="space-y-2">
                  <h3 className="text-xs font-semibold text-muted-foreground uppercase">
                    Assigned Agent
                  </h3>
                  <div className="flex items-center gap-2">
                    <UserCircle className="h-5 w-5" />
                    <Badge variant="outline" className={agent.color}>
                      {agent.name}
                    </Badge>
                  </div>
                </div>
              )}

              {/* Subgraph */}
              {node.subgraph && (
                <div className="space-y-2">
                  <h3 className="text-xs font-semibold text-muted-foreground uppercase">
                    Part Of
                  </h3>
                  <Badge variant="secondary" className="capitalize">
                    {node.subgraph.replace(/_/g, " ")} Pipeline
                  </Badge>
                </div>
              )}

              <Separator />

              {/* Technical Details */}
              <div className="space-y-2">
                <h3 className="text-xs font-semibold text-muted-foreground uppercase">
                  Technical Details
                </h3>
                <div className="text-xs font-mono bg-muted/50 p-3 rounded-md">
                  <p>Node ID: {node.id}</p>
                  <p>Phase: {node.phase}</p>
                  {node.subgraph && <p>Subgraph: {node.subgraph}</p>}
                  {node.agent && <p>Agent: {node.agent}</p>}
                </div>
              </div>
            </div>
          </ScrollArea>

          {/* Actions */}
          <div className="p-4 border-t bg-muted/30">
            <div className="flex gap-2">
              {onViewLogs && (
                <Button
                  variant="outline"
                  className="flex-1"
                  onClick={() => onViewLogs(node.id)}
                >
                  <ScrollText className="h-4 w-4 mr-2" />
                  View Logs
                </Button>
              )}
              {node.status === "failed" && onRetry && (
                <Button
                  variant="default"
                  className="flex-1"
                  onClick={() => onRetry(node.id)}
                >
                  <RefreshCw className="h-4 w-4 mr-2" />
                  Retry Node
                </Button>
              )}
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
