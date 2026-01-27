import { useState } from "react";
import { Play, CheckCircle2 } from "lucide-react";
import {
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  AlertBanner,
} from "@/components/ui";
import { useStartWorkflow } from "@/hooks";

interface StartWorkflowDialogProps {
  projectName: string;
}

export function StartWorkflowDialog({ projectName }: StartWorkflowDialogProps) {
  const [open, setOpen] = useState(false);
  const [startPhase, setStartPhase] = useState(1);
  const [endPhase, setEndPhase] = useState(5);
  const [skipValidation, setSkipValidation] = useState(false);
  const [autonomous, setAutonomous] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  const startWorkflow = useStartWorkflow(projectName);

  const handleStart = async () => {
    setError(null);
    setSuccess(false);
    try {
      await startWorkflow.mutateAsync({
        start_phase: startPhase,
        end_phase: endPhase,
        skip_validation: skipValidation,
        autonomous: autonomous,
      });
      // Show success state briefly before closing
      setSuccess(true);
      setTimeout(() => {
        setOpen(false);
        setSuccess(false);
      }, 1200);
    } catch (err: unknown) {
      console.error("Failed to start workflow", err);
      const message =
        err instanceof Error ? err.message : "Failed to start workflow";
      setError(message);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm">
          <Play className="h-4 w-4 mr-2" aria-hidden="true" />
          Start Workflow
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-[425px]">
        <DialogHeader>
          <DialogTitle>Start Workflow</DialogTitle>
          <DialogDescription>
            Configure workflow execution options.
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 py-4">
          {error && (
            <AlertBanner
              variant="destructive"
              title="Failed to start"
              className="mb-4"
            >
              {error}
            </AlertBanner>
          )}
          <div className="grid grid-cols-4 items-center gap-4">
            <label
              htmlFor="startPhase"
              className="text-right text-sm font-medium"
            >
              Start Phase
            </label>
            <select
              id="startPhase"
              className="col-span-3 flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background"
              value={startPhase}
              onChange={(e) => setStartPhase(Number(e.target.value))}
            >
              <option value={1}>1. Planning</option>
              <option value={2}>2. Validation</option>
              <option value={3}>3. Implementation</option>
              <option value={4}>4. Verification</option>
              <option value={5}>5. Completion</option>
            </select>
          </div>
          <div className="grid grid-cols-4 items-center gap-4">
            <label
              htmlFor="endPhase"
              className="text-right text-sm font-medium"
            >
              End Phase
            </label>
            <select
              id="endPhase"
              className="col-span-3 flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background"
              value={endPhase}
              onChange={(e) => setEndPhase(Number(e.target.value))}
            >
              <option value={1}>1. Planning</option>
              <option value={2}>2. Validation</option>
              <option value={3}>3. Implementation</option>
              <option value={4}>4. Verification</option>
              <option value={5}>5. Completion</option>
            </select>
          </div>
          <div className="grid grid-cols-4 items-center gap-4">
            <label
              htmlFor="skipValidation"
              className="text-right text-sm font-medium"
            >
              Skip Validation
            </label>
            <div className="col-span-3 flex items-center space-x-2">
              <input
                type="checkbox"
                id="skipValidation"
                className="h-4 w-4 rounded border-gray-300"
                checked={skipValidation}
                onChange={(e) => setSkipValidation(e.target.checked)}
              />
              <span className="text-sm text-muted-foreground">
                Skip phase 2 checks
              </span>
            </div>
          </div>
          <div className="grid grid-cols-4 items-center gap-4">
            <label
              htmlFor="autonomous"
              className="text-right text-sm font-medium"
            >
              Autonomous
            </label>
            <div className="col-span-3 flex items-center space-x-2">
              <input
                type="checkbox"
                id="autonomous"
                className="h-4 w-4 rounded border-gray-300"
                checked={autonomous}
                onChange={(e) => setAutonomous(e.target.checked)}
              />
              <span className="text-sm text-muted-foreground">
                Run without human pauses
              </span>
            </div>
          </div>
        </div>
        <DialogFooter>
          {success ? (
            <div
              className="flex items-center gap-2 text-green-600 font-medium animate-fade-in-up"
              role="status"
            >
              <CheckCircle2 className="h-5 w-5" aria-hidden="true" />
              Started! Launching workflow...
            </div>
          ) : (
            <>
              <Button
                variant="outline"
                onClick={() => setOpen(false)}
                disabled={startWorkflow.isPending}
              >
                Cancel
              </Button>
              <Button onClick={handleStart} disabled={startWorkflow.isPending}>
                {startWorkflow.isPending ? "Starting..." : "Start"}
              </Button>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
