/**
 * Phase progress visualization component
 */

import { useState } from "react";
import { CheckCircle, Circle, Clock, XCircle, RotateCcw } from "lucide-react";
import {
  useStartWorkflow,
  useResumeWorkflow,
  usePauseWorkflow,
  useResetWorkflow,
  useRollbackWorkflow,
} from "@/hooks";
import {
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui";
import { cn, getPhaseName } from "@/lib/utils";

interface PhaseProgressProps {
  projectName: string;
  currentPhase: number;
  phaseStatus: Record<string, string>;
}

const phases = [1, 2, 3, 4, 5];

function getPhaseIcon(status: string) {
  switch (status?.toLowerCase()) {
    case "completed":
      return <CheckCircle className="h-6 w-6 text-green-500" />;
    case "in_progress":
      return <Clock className="h-6 w-6 text-blue-500 animate-pulse" />;
    case "failed":
      return <XCircle className="h-6 w-6 text-red-500" />;
    default:
      return <Circle className="h-6 w-6 text-gray-300" />;
  }
}

export function PhaseProgress({
  projectName,
  currentPhase,
  phaseStatus,
}: PhaseProgressProps) {
  const [rollbackPhase, setRollbackPhase] = useState<number | null>(null);

  const startWorkflow = useStartWorkflow(projectName);
  const resumeWorkflow = useResumeWorkflow(projectName);
  const pauseWorkflow = usePauseWorkflow(projectName);
  const resetWorkflow = useResetWorkflow(projectName);
  const rollbackWorkflow = useRollbackWorkflow(projectName);

  const isRunning = Object.values(phaseStatus).some((s) => s === "in_progress");
  const hasStarted = currentPhase > 0;

  const handlePhaseClick = (phase: number) => {
    // Only allow rollback to previous phases if workflow is running or has started
    if (hasStarted && phase < currentPhase) {
      setRollbackPhase(phase);
    }
  };

  const handleConfirmRollback = () => {
    if (rollbackPhase !== null) {
      rollbackWorkflow.mutate(rollbackPhase);
      setRollbackPhase(null);
    }
  };

  return (
    <>
      <Card>
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <CardTitle>Workflow Progress</CardTitle>
            <div className="flex items-center space-x-2">
              {!hasStarted && (
                <Button
                  onClick={() => startWorkflow.mutate({})}
                  disabled={startWorkflow.isPending}
                >
                  Start Workflow
                </Button>
              )}
              {hasStarted && !isRunning && (
                <Button
                  onClick={() => resumeWorkflow.mutate({ autonomous: false })}
                  disabled={resumeWorkflow.isPending}
                >
                  Resume
                </Button>
              )}
              {isRunning && (
                <Button
                  variant="outline"
                  onClick={() => pauseWorkflow.mutate()}
                  disabled={pauseWorkflow.isPending}
                >
                  Pause
                </Button>
              )}
              {hasStarted && (
                <Button
                  variant="destructive"
                  onClick={() => resetWorkflow.mutate()}
                  disabled={resetWorkflow.isPending}
                >
                  Reset
                </Button>
              )}
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-between">
            {phases.map((phase, index) => {
              const status = phaseStatus[phase.toString()] || "pending";
              const isActive = phase === currentPhase;
              const canRb = hasStarted && phase < currentPhase;

              return (
                <div
                  key={phase}
                  className={cn(
                    "flex items-center",
                    canRb && "cursor-pointer group",
                  )}
                  onClick={() => handlePhaseClick(phase)}
                >
                  <div
                    className={cn(
                      "flex flex-col items-center relative",
                      isActive && "font-semibold",
                    )}
                  >
                    {canRb && (
                      <div className="absolute -top-6 opacity-0 group-hover:opacity-100 transition-opacity text-xs font-semibold text-blue-500 flex items-center bg-white px-2 py-0.5 rounded shadow-sm border mb-1">
                        <RotateCcw className="h-3 w-3 mr-1" />
                        Rollback
                      </div>
                    )}
                    <div
                      className={cn(
                        "flex h-12 w-12 items-center justify-center rounded-full border-2 transition-all",
                        status === "completed"
                          ? "border-green-500 bg-green-50"
                          : status === "in_progress"
                            ? "border-blue-500 bg-blue-50"
                            : status === "failed"
                              ? "border-red-500 bg-red-50"
                              : "border-gray-200",
                        canRb &&
                          "group-hover:border-blue-400 group-hover:bg-blue-50",
                      )}
                    >
                      {getPhaseIcon(status)}
                    </div>
                    <span className="mt-2 text-sm">{getPhaseName(phase)}</span>
                    <span className="text-xs text-muted-foreground capitalize">
                      {status}
                    </span>
                  </div>

                  {index < phases.length - 1 && (
                    <div
                      className={cn(
                        "mx-4 h-0.5 w-16 flex-1",
                        phaseStatus[(phase + 1).toString()] === "completed" ||
                          phaseStatus[phase.toString()] === "completed"
                          ? "bg-green-500"
                          : "bg-gray-200",
                      )}
                    />
                  )}
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>

      <Dialog
        open={rollbackPhase !== null}
        onOpenChange={(open) => {
          if (!open) setRollbackPhase(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Confirm Rollback</DialogTitle>
            <DialogDescription>
              Are you sure you want to rollback to Phase {rollbackPhase}? This
              will reset progress in subsequent phases.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setRollbackPhase(null)}>
              Cancel
            </Button>
            <Button onClick={handleConfirmRollback}>Confirm Rollback</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
