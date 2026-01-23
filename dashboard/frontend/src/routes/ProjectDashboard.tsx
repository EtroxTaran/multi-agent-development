/**
 * Project dashboard page
 */

import { useParams } from "@tanstack/react-router";
import { RefreshCw, Pause } from "lucide-react";
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
  Guidance,
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
      <div className="flex items-center justify-center h-64">
        <RefreshCw className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (projectError) {
    return (
      <div className="flex flex-col items-center justify-center h-64 space-y-4">
        <p className="text-destructive">
          Failed to load project: {projectError.message}
        </p>
      </div>
    );
  }

  if (!project) {
    return (
      <div className="flex flex-col items-center justify-center h-64">
        <p className="text-muted-foreground">Project not found</p>
      </div>
    );
  }

  const completedTasks = tasks?.completed || 0;
  const totalTasks = tasks?.total || 0;
  const progressPercent =
    totalTasks > 0 ? (completedTasks / totalTasks) * 100 : 0;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <div className="flex items-center space-x-3">
            <h1 className="text-3xl font-bold">{project.name}</h1>
            <Badge
              className={cn(getStatusColor(status?.status || "not_started"))}
            >
              {status?.status || "Not Started"}
            </Badge>
            {isConnected && (
              <Badge variant="outline" className="text-green-600">
                Live
              </Badge>
            )}
          </div>
          <p className="text-muted-foreground">{project.path}</p>
        </div>
        <div className="flex items-center space-x-2">
          {status?.status === "paused" && (
            <Button
              size="sm"
              onClick={() => resumeWorkflow.mutate(false)}
              disabled={resumeWorkflow.isPending}
            >
              <RefreshCw
                className={cn(
                  "h-4 w-4 mr-2",
                  resumeWorkflow.isPending && "animate-spin",
                )}
              />
              Resume
            </Button>
          )}
          {status?.status === "in_progress" && (
            <Button
              size="sm"
              variant="outline"
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
          {status?.status !== "in_progress" && status?.status !== "paused" && (
            <StartWorkflowDialog projectName={name} />
          )}
          {health && (
            <div className="flex items-center gap-1">
              <Badge
                variant="outline"
                className={cn(
                  health.status === "healthy"
                    ? "text-green-600 border-green-600"
                    : health.status === "degraded"
                      ? "text-yellow-600 border-yellow-600"
                      : "text-red-600 border-red-600",
                )}
              >
                {health.status}
              </Badge>
              <Guidance content="System health status based on agent availability and workflow errors." />
            </div>
          )}
        </div>
      </div>

      {/* Quick stats */}
      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Current Phase</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {status?.current_phase ? (
                <>
                  {status.current_phase}/5
                  <span className="text-sm font-normal text-muted-foreground ml-2">
                    {getPhaseName(status.current_phase)}
                  </span>
                </>
              ) : (
                "Not Started"
              )}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Task Progress</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {completedTasks}/{totalTasks}
            </div>
            <Progress value={progressPercent} className="mt-2" />
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Agents</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex space-x-2">
              {health?.agents &&
                Object.entries(health.agents).map(([agent, available]) => (
                  <Badge
                    key={agent}
                    variant={available ? "success" : "destructive"}
                  >
                    {agent}
                  </Badge>
                ))}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Commits</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {health?.total_commits || 0}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Phase progress */}
      <PhaseProgress
        projectName={name}
        currentPhase={status?.current_phase || 0}
        phaseStatus={status?.phase_status || {}}
      />

      <Separator />

      {/* Main content tabs */}
      <Tabs defaultValue="graph" className="space-y-4">
        <TabsList>
          <TabsTrigger value="graph">Graph</TabsTrigger>
          <TabsTrigger value="tasks">Tasks</TabsTrigger>
          <TabsTrigger value="agents">Agents</TabsTrigger>
          <TabsTrigger value="budget">Budget</TabsTrigger>
          <TabsTrigger value="chat">Chat</TabsTrigger>
          <TabsTrigger value="errors">Errors</TabsTrigger>
        </TabsList>

        <TabsContent value="graph">
          <WorkflowGraph projectName={name} />
        </TabsContent>

        <TabsContent value="tasks">
          <TaskBoard projectName={name} />
        </TabsContent>

        <TabsContent value="agents">
          <AgentFeed projectName={name} />
        </TabsContent>

        <TabsContent value="budget">
          <BudgetOverview projectName={name} />
        </TabsContent>

        <TabsContent value="chat">
          <ChatPanel projectName={name} />
        </TabsContent>

        <TabsContent value="errors">
          <ErrorPanel projectName={name} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
