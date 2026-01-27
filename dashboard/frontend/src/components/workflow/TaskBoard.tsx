/**
 * Task board component with filtering and search
 */

import { useState, useMemo } from "react";
import { Search, Filter } from "lucide-react";
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
  Input,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui";
import { cn, getStatusColor } from "@/lib/utils";
import type { TaskInfo } from "@/types";

function getComplexityLevel(score?: number): string {
  if (score === undefined) return "";
  if (score <= 3) return "low";
  if (score <= 6) return "medium";
  return "high";
}

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
  const [searchQuery, setSearchQuery] = useState("");
  const [complexityFilter, setComplexityFilter] = useState<string>("all");

  // Filter tasks based on search and complexity
  const filteredTasks = useMemo(() => {
    const tasks = data?.tasks || [];
    return tasks.filter((task) => {
      // Search filter
      const matchesSearch =
        searchQuery === "" ||
        task.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
        task.description?.toLowerCase().includes(searchQuery.toLowerCase()) ||
        task.id.toLowerCase().includes(searchQuery.toLowerCase());

      // Complexity filter
      const matchesComplexity =
        complexityFilter === "all" ||
        getComplexityLevel(task.complexity_score).toLowerCase() ===
          complexityFilter;

      return matchesSearch && matchesComplexity;
    });
  }, [data?.tasks, searchQuery, complexityFilter]);

  // Group filtered tasks by status
  const pendingTasks = filteredTasks.filter(
    (t) => t.status === "pending" || t.status === "blocked",
  );
  const inProgressTasks = filteredTasks.filter(
    (t) => t.status === "in_progress",
  );
  const completedTasks = filteredTasks.filter((t) => t.status === "completed");
  const failedTasks = filteredTasks.filter((t) => t.status === "failed");

  if (isLoading) {
    return (
      <div
        className="flex items-center justify-center h-48"
        role="status"
        aria-label="Loading tasks"
      >
        <span className="text-muted-foreground">Loading tasks...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-48" role="alert">
        <span className="text-destructive">Failed to load tasks</span>
      </div>
    );
  }

  const totalTasks = data?.tasks?.length || 0;
  const filteredCount = filteredTasks.length;

  return (
    <div className="space-y-4">
      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1">
          <Search
            className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground"
            aria-hidden="true"
          />
          <Input
            type="search"
            placeholder="Search tasks..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-9"
            aria-label="Search tasks"
          />
        </div>
        <div className="flex items-center gap-2">
          <Filter
            className="h-4 w-4 text-muted-foreground"
            aria-hidden="true"
          />
          <Select value={complexityFilter} onValueChange={setComplexityFilter}>
            <SelectTrigger
              className="w-[140px]"
              aria-label="Filter by complexity"
            >
              <SelectValue placeholder="Complexity" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All</SelectItem>
              <SelectItem value="low">Low</SelectItem>
              <SelectItem value="medium">Medium</SelectItem>
              <SelectItem value="high">High</SelectItem>
            </SelectContent>
          </Select>
        </div>
        {(searchQuery || complexityFilter !== "all") && (
          <div className="text-sm text-muted-foreground self-center">
            Showing {filteredCount} of {totalTasks}
          </div>
        )}
      </div>

      {/* Task Columns - Responsive grid */}
      <div className="grid gap-4 grid-cols-1 sm:grid-cols-2 lg:grid-cols-4">
        {/* Pending */}
        <div>
          <div className="mb-3 flex items-center justify-between">
            <h3 className="font-semibold">Pending</h3>
            <Badge variant="secondary">{pendingTasks.length}</Badge>
          </div>
          <ScrollArea className="h-[300px] sm:h-[400px]">
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
          <ScrollArea className="h-[300px] sm:h-[400px]">
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
          <ScrollArea className="h-[300px] sm:h-[400px]">
            {completedTasks.map((task) => (
              <TaskCard key={task.id} task={task} />
            ))}
            {completedTasks.length === 0 && (
              <p className="text-sm text-muted-foreground">
                No completed tasks
              </p>
            )}
          </ScrollArea>
        </div>

        {/* Failed */}
        <div>
          <div className="mb-3 flex items-center justify-between">
            <h3 className="font-semibold">Failed</h3>
            <Badge variant="destructive">{failedTasks.length}</Badge>
          </div>
          <ScrollArea className="h-[300px] sm:h-[400px]">
            {failedTasks.map((task) => (
              <TaskCard key={task.id} task={task} />
            ))}
            {failedTasks.length === 0 && (
              <p className="text-sm text-muted-foreground">No failed tasks</p>
            )}
          </ScrollArea>
        </div>
      </div>
    </div>
  );
}
