/**
 * Project dashboard page
 */

import { useParams } from "@tanstack/react-router";
import { RefreshCw, Pause, GitBranch, GitCommit, Activity } from "lucide-react";
import {
  useProject,
  useWorkflowStatus,
  useWorkflowHealth,
  useTasks,
  useWebSocket,
  useResumeWorkflow,
  usePauseWorkflow,
} from "@/hooks";
import {
  Badge,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  Progress,
  Separator,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
  AlertBanner,
} from "@/components/ui";
import { StartWorkflowDialog } from "@/components/workflow/StartWorkflowDialog";
import { PhaseProgress } from "@/components/workflow/PhaseProgress";
import { TaskBoard } from "@/components/workflow/TaskBoard";
import { WorkflowGraph } from "@/components/workflow/WorkflowGraph";
import { AgentFeed } from "@/components/agents/AgentFeed";
import { BudgetOverview } from "@/components/budget/BudgetOverview";
import { ChatPanel } from "@/components/chat/ChatPanel";
import { ErrorPanel } from "@/components/errors/ErrorPanel";
import { cn, getStatusColor, getPhaseName } from "@/lib/utils";

export function ProjectDashboard() {
  const { name } = useParams({ from: "/project/$name" });

  const {
    data: project,
    isLoading: projectLoading,
    error: projectError,
  } = useProject(name);
  const { data: status, isLoading: statusLoading } = useWorkflowStatus(name);
  const { data: health } = useWorkflowHealth(name);
  const { data: tasks } = useTasks(name);
  const resumeWorkflow = useResumeWorkflow(name);
  const pauseWorkflow = usePauseWorkflow(name);

  // Connect to WebSocket for real-time updates
  const { isConnected } = useWebSocket(name);

  if (projectLoading || statusLoading) {
    return (
      <div className="flex items-center justify-center h-[50vh]">
        <RefreshCw className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (projectError) {
    return (
      <div className="flex flex-col items-center justify-center h-[50vh] space-y-4">
        <p className="text-destructive font-medium">
          Failed to load project: {projectError.message}
        </p>
      </div>
    );
  }

  if (!project) {
    return (
      <div className="flex flex-col items-center justify-center h-[50vh]">
        <p className="text-muted-foreground">Project not found</p>
      </div>
    );
  }

  const completedTasks = tasks?.completed || 0;
  const totalTasks = tasks?.total || 0;
  const progressPercent =
    totalTasks > 0 ? (completedTasks / totalTasks) * 100 : 0;

  return (
    <div className="space-y-8 animate-fade-in-up">
      {/* Header Area */}
      <div className="flex flex-col gap-6">
        {/* Top Bar */}
        <div className="flex items-start justify-between">
          <div className="space-y-1">
            <div className="flex items-center gap-3">
              <h1 className="text-3xl font-bold tracking-tight">
                {project.name}
              </h1>
              <Badge
                className={cn(
                  "uppercase text-xs font-bold tracking-wider px-2 py-0.5",
                  getStatusColor(status?.status || "not_started"),
                )}
              >
                {status?.status?.replace(/_/g, " ") || "Not Started"}
              </Badge>
              {isConnected && (
                <div className="flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-green-500/10 text-green-600 text-xs font-medium border border-green-500/20">
                  <span className="relative flex h-2 w-2">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
                    <span className="relative inline-flex rounded-full h-2 w-2 bg-green-500"></span>
                  </span>
                  Live
                </div>
              )}
            </div>

            <div className="flex items-center gap-4 text-sm text-muted-foreground">
              <span className="font-mono">{project.path}</span>
              {project.git_info && (
                <>
                  <span className="text-border">|</span>
                  <span className="flex items-center gap-1">
                    <GitBranch className="h-3.5 w-3.5" />
                    {project.git_info.branch}
                  </span>
                  <span className="flex items-center gap-1 font-mono text-xs bg-muted px-1.5 py-0.5 rounded">
                    <GitCommit className="h-3 w-3" />
                    {project.git_info.commit}
                  </span>
                  {project.git_info.is_dirty && (
                    <Badge
                      variant="outline"
                      className="text-[10px] h-5 border-yellow-500 text-yellow-600"
                    >
                      Dirty
                    </Badge>
                  )}
                </>
              )}
            </div>
          </div>

          <div className="flex items-center gap-2">
            {status?.status === "paused" && (
              <Button
                variant="default"
                onClick={() => resumeWorkflow.mutate(false)}
                disabled={resumeWorkflow.isPending}
                className="shadow-lg shadow-primary/20"
              >
                <RefreshCw
                  className={cn(
                    "h-4 w-4 mr-2",
                    resumeWorkflow.isPending && "animate-spin",
                  )}
                />
                Resume Workflow
              </Button>
            )}
            {status?.status === "in_progress" && (
              <Button
                variant="secondary"
                onClick={() => pauseWorkflow.mutate()}
                disabled={pauseWorkflow.isPending}
              >
                <Pause
                  className={cn(
                    "h-4 w-4 mr-2",
                    pauseWorkflow.isPending && "animate-spin",
                  )}
                />
                Pause
              </Button>
            )}
            {status?.status !== "in_progress" &&
              status?.status !== "paused" && (
                <StartWorkflowDialog projectName={name} />
              )}
          </div>
        </div>

        {/* Global Alerts / Status Banner */}
        {status?.pending_interrupt && (
          <AlertBanner
            variant="warning"
            title="Action Required"
            action={
              <Button size="sm" variant="outline" className="bg-background">
                View Request
              </Button>
            }
          >
            The workflow has paused for human validaton. Please review the
            pending request.
          </AlertBanner>
        )}
      </div>

      {/* Metrics Grid */}
      <div className="grid gap-4 md:grid-cols-4">
        <Card className="bg-gradient-to-br from-card to-secondary/30">
          <CardHeader className="pb-2">
            <CardDescription className="flex items-center gap-2">
              <Activity className="h-4 w-4" /> Current Phase
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {status?.current_phase ? (
                <>
                  {status.current_phase}
                  <span className="text-muted-foreground text-lg font-normal">
                    /5
                  </span>
                </>
              ) : (
                "--"
              )}
            </div>
            <div className="text-xs text-muted-foreground mt-1 truncate">
              {status?.current_phase
                ? getPhaseName(status.current_phase)
                : "Not started"}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Task Completion</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {completedTasks}
              <span className="text-muted-foreground text-lg font-normal">
                /{totalTasks}
              </span>
            </div>
            <Progress value={progressPercent} className="mt-2 h-1.5" />
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Agent Availability</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-1.5">
              {health?.agents &&
                Object.entries(health.agents).map(([agent, available]) => (
                  <Badge
                    key={agent}
                    variant={available ? "secondary" : "destructive"}
                    className={cn(
                      "text-[10px]",
                      available &&
                        "bg-green-500/10 text-green-700 dark:text-green-400 hover:bg-green-500/20",
                    )}
                  >
                    {agent}
                  </Badge>
                ))}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardDescription>System Health</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-2">
              <div
                className={cn(
                  "h-2.5 w-2.5 rounded-full",
                  health?.status === "healthy"
                    ? "bg-green-500"
                    : health?.status === "degraded"
                      ? "bg-yellow-500"
                      : "bg-red-500",
                )}
              />
              <span className="font-medium capitalize">
                {health?.status || "Unknown"}
              </span>
            </div>
            <div className="text-xs text-muted-foreground mt-1">
              {health?.total_commits || 0} commits recorded
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Phase Timeline */}
      <PhaseProgress
        projectName={name}
        currentPhase={status?.current_phase || 0}
        phaseStatus={status?.phase_status || {}}
      />

      <Separator className="my-6" />

      {/* Main Content Tabs */}
      <Tabs defaultValue="graph" className="space-y-6">
        <div className="flex items-center justify-between">
          <TabsList className="bg-muted/60 p-1">
            <TabsTrigger value="graph" className="rounded-sm">
              Workflow
            </TabsTrigger>
            <TabsTrigger value="tasks" className="rounded-sm">
              Tasks
            </TabsTrigger>
            <TabsTrigger value="agents" className="rounded-sm">
              Agents
            </TabsTrigger>
            <TabsTrigger value="budget" className="rounded-sm">
              Budget
            </TabsTrigger>
            <TabsTrigger value="chat" className="rounded-sm">
              Chat
            </TabsTrigger>
            <TabsTrigger value="errors" className="rounded-sm">
              Errors
            </TabsTrigger>
          </TabsList>
        </div>

        <div className="min-h-[500px] border rounded-lg bg-card/50 backdrop-blur-sm p-1">
          <TabsContent value="graph" className="m-0 h-full p-4">
            <WorkflowGraph projectName={name} />
          </TabsContent>

          <TabsContent value="tasks" className="m-0 h-full p-4">
            <TaskBoard projectName={name} />
          </TabsContent>

          <TabsContent value="agents" className="m-0 h-full p-4">
            <AgentFeed projectName={name} />
          </TabsContent>

          <TabsContent value="budget" className="m-0 h-full p-4">
            <BudgetOverview projectName={name} />
          </TabsContent>

          <TabsContent value="chat" className="m-0 h-full p-4">
            <ChatPanel projectName={name} />
          </TabsContent>

          <TabsContent value="errors" className="m-0 h-full p-4">
            <ErrorPanel projectName={name} />
          </TabsContent>
        </div>
      </Tabs>
    </div>
  );
}
