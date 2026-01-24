/**
 * JourneyPanel - Real-time workflow storytelling sidebar
 *
 * Displays human-readable explanations of what's happening in the workflow,
 * including current step, next steps, and completed steps timeline.
 */

import { useState } from "react";
import {
  ChevronDown,
  ChevronUp,
  Loader2,
  CheckCircle2,
  ArrowRight,
  Clock,
  Target,
  Activity,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { ScrollArea } from "@/components/ui/scroll-area";

interface WorkflowNode {
  id: string;
  label: string;
  status: string;
  phase: number;
  description?: string;
  agent?: string;
}

interface JourneyPanelProps {
  currentPhase: number;
  phaseName: string;
  activeNode?: WorkflowNode;
  completedNodes: WorkflowNode[];
  upcomingNodes: WorkflowNode[];
  totalSteps: number;
  completedSteps: number;
  isRunning: boolean;
}

const phaseDescriptions: Record<number, string> = {
  1: "We're analyzing your requirements and creating a plan.",
  2: "We're validating the plan with multiple AI reviewers.",
  3: "We're implementing the code based on the approved plan.",
  4: "We're verifying the implementation meets requirements.",
  5: "We're wrapping up and preparing the final deliverables.",
  0: "We're handling an issue that needs attention.",
};

const agentColors: Record<string, string> = {
  claude: "bg-purple-500/20 text-purple-600",
  cursor: "bg-blue-500/20 text-blue-600",
  gemini: "bg-green-500/20 text-green-600",
};

export function JourneyPanel({
  currentPhase,
  phaseName,
  activeNode,
  completedNodes,
  upcomingNodes,
  totalSteps,
  completedSteps,
  isRunning,
}: JourneyPanelProps) {
  const [showHistory, setShowHistory] = useState(false);
  const progressPercent =
    totalSteps > 0 ? (completedSteps / totalSteps) * 100 : 0;

  return (
    <Card className="h-full bg-card/95 backdrop-blur-sm border-l-4 border-l-primary/50">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Target className="h-5 w-5 text-primary" />
            <h3 className="font-bold text-lg">Workflow Journey</h3>
          </div>
          {isRunning && (
            <Badge variant="default" className="animate-pulse">
              <Activity className="h-3 w-3 mr-1" />
              Live
            </Badge>
          )}
        </div>
        <p className="text-sm text-muted-foreground mt-1">
          {phaseDescriptions[currentPhase] || "Working on your project..."}
        </p>
      </CardHeader>

      <CardContent className="space-y-4">
        {/* Phase Progress */}
        <div className="space-y-2">
          <div className="flex items-center justify-between text-sm">
            <span className="font-medium">
              Phase {currentPhase}/5: {phaseName}
            </span>
            <span className="text-muted-foreground">
              Step {completedSteps}/{totalSteps}
            </span>
          </div>
          <Progress value={progressPercent} className="h-2" />
        </div>

        {/* Current Step */}
        {activeNode && (
          <div className="p-4 rounded-lg bg-green-500/10 border border-green-500/30">
            <div className="flex items-start gap-3">
              <div className="p-2 rounded-full bg-green-500/20">
                <Loader2 className="h-4 w-4 text-green-600 animate-spin" />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <h4 className="font-semibold text-sm text-green-700 dark:text-green-400">
                    NOW
                  </h4>
                  {activeNode.agent && (
                    <Badge
                      variant="outline"
                      className={cn(
                        "text-[9px] px-1.5 h-4 capitalize",
                        agentColors[activeNode.agent],
                      )}
                    >
                      {activeNode.agent}
                    </Badge>
                  )}
                </div>
                <p className="font-medium mt-1">{activeNode.label}</p>
                {activeNode.description && (
                  <p className="text-sm text-muted-foreground mt-1">
                    {activeNode.description}
                  </p>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Up Next */}
        {upcomingNodes.length > 0 && (
          <div className="space-y-2">
            <h4 className="text-xs font-semibold text-muted-foreground uppercase flex items-center gap-1">
              <ArrowRight className="h-3 w-3" />
              Up Next
            </h4>
            <div className="space-y-1.5">
              {upcomingNodes.slice(0, 3).map((node, i) => (
                <div
                  key={node.id}
                  className={cn(
                    "flex items-center gap-2 p-2 rounded-md text-sm",
                    i === 0 ? "bg-muted/50" : "opacity-60",
                  )}
                >
                  <div className="w-1.5 h-1.5 rounded-full bg-muted-foreground/40" />
                  <span className="truncate">{node.label}</span>
                </div>
              ))}
              {upcomingNodes.length > 3 && (
                <p className="text-xs text-muted-foreground pl-4">
                  +{upcomingNodes.length - 3} more steps
                </p>
              )}
            </div>
          </div>
        )}

        {/* Completed Steps */}
        {completedNodes.length > 0 && (
          <div className="space-y-2">
            <button
              onClick={() => setShowHistory(!showHistory)}
              className="w-full flex items-center justify-between text-xs font-semibold text-muted-foreground uppercase hover:text-foreground transition-colors"
            >
              <span className="flex items-center gap-1">
                <CheckCircle2 className="h-3 w-3" />
                Completed ({completedNodes.length})
              </span>
              {showHistory ? (
                <ChevronUp className="h-3 w-3" />
              ) : (
                <ChevronDown className="h-3 w-3" />
              )}
            </button>

            {showHistory && (
              <ScrollArea className="h-[200px]">
                <div className="space-y-1.5 pr-3">
                  {completedNodes.map((node) => (
                    <div
                      key={node.id}
                      className="flex items-center gap-2 p-2 rounded-md text-sm bg-blue-500/5"
                    >
                      <CheckCircle2 className="h-3.5 w-3.5 text-blue-500 shrink-0" />
                      <span className="truncate">{node.label}</span>
                      {node.agent && (
                        <Badge
                          variant="outline"
                          className={cn(
                            "text-[8px] px-1 h-3.5 capitalize ml-auto shrink-0",
                            agentColors[node.agent],
                          )}
                        >
                          {node.agent}
                        </Badge>
                      )}
                    </div>
                  ))}
                </div>
              </ScrollArea>
            )}
          </div>
        )}

        {/* Idle State */}
        {!isRunning && !activeNode && completedNodes.length === 0 && (
          <div className="text-center py-8 text-muted-foreground">
            <Clock className="h-8 w-8 mx-auto mb-2 opacity-50" />
            <p className="text-sm">Workflow not started</p>
            <p className="text-xs mt-1">Click "Start Workflow" to begin</p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
