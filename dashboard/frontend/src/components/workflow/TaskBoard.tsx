/**
 * Task board component
 */

import { useTasks } from "@/hooks";
import {
  Badge,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  ScrollArea,
  Guidance,
} from "@/components/ui";
import { cn, getStatusColor } from "@/lib/utils";
import type { TaskInfo } from "@/types";

interface TaskBoardProps {
  projectName: string;
}

function TaskCard({ task }: { task: TaskInfo }) {
  return (
    <Card className="mb-3">
      <CardHeader className="py-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-medium">{task.title}</CardTitle>
          <Badge className={cn("text-xs", getStatusColor(task.status))}>
            {task.status}
          </Badge>
        </div>
        <CardDescription className="text-xs">{task.id}</CardDescription>
      </CardHeader>
      {(task.description || task.files_to_modify.length > 0) && (
        <CardContent className="py-2">
          {task.description && (
            <p className="text-xs text-muted-foreground line-clamp-2">
              {task.description}
            </p>
          )}
          {task.files_to_modify.length > 0 && (
            <div className="mt-2">
              <span className="text-xs text-muted-foreground">
                Files: {task.files_to_modify.length}
              </span>
            </div>
          )}
          {task.complexity_score !== undefined && (
            <div className="mt-1 flex items-center gap-1">
              <span className="text-xs text-muted-foreground">
                Complexity: {task.complexity_score.toFixed(1)}
              </span>
              <Guidance
                content="Estimated complexity score (1-10) based on task description and file changes."
                className="h-3 w-3"
              />
            </div>
          )}
        </CardContent>
      )}
    </Card>
  );
}

export function TaskBoard({ projectName }: TaskBoardProps) {
  const { data, isLoading, error } = useTasks(projectName);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-48">
        <span className="text-muted-foreground">Loading tasks...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-48">
        <span className="text-destructive">Failed to load tasks</span>
      </div>
    );
  }

  const tasks = data?.tasks || [];
  const pendingTasks = tasks.filter(
    (t) => t.status === "pending" || t.status === "blocked",
  );
  const inProgressTasks = tasks.filter((t) => t.status === "in_progress");
  const completedTasks = tasks.filter((t) => t.status === "completed");
  const failedTasks = tasks.filter((t) => t.status === "failed");

  return (
    <div className="grid gap-4 md:grid-cols-4">
      {/* Pending */}
      <div>
        <div className="mb-3 flex items-center justify-between">
          <h3 className="font-semibold">Pending</h3>
          <Badge variant="secondary">{pendingTasks.length}</Badge>
        </div>
        <ScrollArea className="h-[400px]">
          {pendingTasks.map((task) => (
            <TaskCard key={task.id} task={task} />
          ))}
          {pendingTasks.length === 0 && (
            <p className="text-sm text-muted-foreground">No pending tasks</p>
          )}
        </ScrollArea>
      </div>

      {/* In Progress */}
      <div>
        <div className="mb-3 flex items-center justify-between">
          <h3 className="font-semibold">In Progress</h3>
          <Badge variant="info">{inProgressTasks.length}</Badge>
        </div>
        <ScrollArea className="h-[400px]">
          {inProgressTasks.map((task) => (
            <TaskCard key={task.id} task={task} />
          ))}
          {inProgressTasks.length === 0 && (
            <p className="text-sm text-muted-foreground">
              No tasks in progress
            </p>
          )}
        </ScrollArea>
      </div>

      {/* Completed */}
      <div>
        <div className="mb-3 flex items-center justify-between">
          <h3 className="font-semibold">Completed</h3>
          <Badge variant="success">{completedTasks.length}</Badge>
        </div>
        <ScrollArea className="h-[400px]">
          {completedTasks.map((task) => (
            <TaskCard key={task.id} task={task} />
          ))}
          {completedTasks.length === 0 && (
            <p className="text-sm text-muted-foreground">No completed tasks</p>
          )}
        </ScrollArea>
      </div>

      {/* Failed */}
      <div>
        <div className="mb-3 flex items-center justify-between">
          <h3 className="font-semibold">Failed</h3>
          <Badge variant="destructive">{failedTasks.length}</Badge>
        </div>
        <ScrollArea className="h-[400px]">
          {failedTasks.map((task) => (
            <TaskCard key={task.id} task={task} />
          ))}
          {failedTasks.length === 0 && (
            <p className="text-sm text-muted-foreground">No failed tasks</p>
          )}
        </ScrollArea>
      </div>
    </div>
  );
}
