/**
 * Dialog to view pending workflow interrupt/request details
 */

import { AlertTriangle, MessageSquare } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { getPhaseName } from "@/lib/utils";

interface ViewRequestDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  pendingInterrupt: Record<string, unknown> | null | undefined;
  currentPhase: number | undefined;
  onResume?: () => void;
  isResuming?: boolean;
}

export function ViewRequestDialog({
  open,
  onOpenChange,
  pendingInterrupt,
  currentPhase,
  onResume,
  isResuming,
}: ViewRequestDialogProps) {
  if (!pendingInterrupt) return null;

  const pausedAt = pendingInterrupt.paused_at as string[] | undefined;
  const state = pendingInterrupt.state as Record<string, unknown> | undefined;
  const question = pendingInterrupt.question as string | undefined;
  const options = pendingInterrupt.options as string[] | undefined;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <AlertTriangle className="h-5 w-5 text-yellow-500" />
            Action Required
          </DialogTitle>
          <DialogDescription>
            The workflow has paused and requires your input to continue.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-4">
          {/* Paused Location */}
          {pausedAt && pausedAt.length > 0 && (
            <div className="space-y-2">
              <h4 className="text-sm font-medium text-muted-foreground">
                Paused At
              </h4>
              <div className="flex flex-wrap gap-2">
                {pausedAt.map((node, idx) => (
                  <Badge key={idx} variant="secondary" className="capitalize">
                    {node.replace(/_/g, " ")}
                  </Badge>
                ))}
              </div>
            </div>
          )}

          {/* Current Phase */}
          {currentPhase && (
            <div className="space-y-2">
              <h4 className="text-sm font-medium text-muted-foreground">
                Current Phase
              </h4>
              <p className="text-sm">
                Phase {currentPhase}: {getPhaseName(currentPhase)}
              </p>
            </div>
          )}

          {/* Question if present */}
          {question && (
            <div className="space-y-2 p-4 rounded-lg bg-yellow-500/10 border border-yellow-500/20">
              <div className="flex items-center gap-2">
                <MessageSquare className="h-4 w-4 text-yellow-600" />
                <h4 className="text-sm font-medium">Question</h4>
              </div>
              <p className="text-sm">{question}</p>
              {options && options.length > 0 && (
                <div className="flex flex-wrap gap-2 mt-2">
                  {options.map((opt, idx) => (
                    <Badge key={idx} variant="outline">
                      {opt}
                    </Badge>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* State Summary */}
          {state && (
            <div className="space-y-2">
              <h4 className="text-sm font-medium text-muted-foreground">
                Workflow State
              </h4>
              <div className="text-xs font-mono bg-muted p-3 rounded-md overflow-x-auto max-h-48 overflow-y-auto">
                <pre>
                  {JSON.stringify(
                    {
                      discussion_complete: state.discussion_complete,
                      research_complete: state.research_complete,
                      needs_clarification: state.needs_clarification,
                      execution_mode: state.execution_mode,
                      current_phase: state.current_phase,
                    },
                    null,
                    2,
                  )}
                </pre>
              </div>
            </div>
          )}
        </div>

        <DialogFooter className="gap-2">
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Close
          </Button>
          {onResume && (
            <Button onClick={onResume} disabled={isResuming}>
              {isResuming ? "Resuming..." : "Resume Workflow"}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
