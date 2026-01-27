/**
 * TanStack Query hooks for task operations
 */

import { useQuery } from "@tanstack/react-query";
import { tasksApi } from "@/lib/api";
import type { AuditResponse, TaskInfo, TaskListResponse } from "@/types";

// Query keys
export const taskKeys = {
  all: ["tasks"] as const,
  lists: (projectName: string) =>
    [...taskKeys.all, "list", projectName] as const,
  list: (projectName: string, status?: string) =>
    [...taskKeys.lists(projectName), { status }] as const,
  details: (projectName: string) =>
    [...taskKeys.all, "detail", projectName] as const,
  detail: (projectName: string, taskId: string) =>
    [...taskKeys.details(projectName), taskId] as const,
  history: (projectName: string, taskId: string) =>
    [...taskKeys.detail(projectName, taskId), "history"] as const,
};

/**
 * Hook to fetch all tasks for a project
 */
export function useTasks(projectName: string, status?: string) {
  return useQuery<TaskListResponse, Error>({
    queryKey: taskKeys.list(projectName, status),
    queryFn: () => tasksApi.list(projectName, status),
    enabled: !!projectName,
    refetchInterval: 30000, // Reduce to 30s fallback (WebSocket handles real-time)
    staleTime: 10000, // Data fresh for 10 seconds
  });
}

/**
 * Hook to fetch a single task
 */
export function useTask(projectName: string, taskId: string) {
  return useQuery<TaskInfo, Error>({
    queryKey: taskKeys.detail(projectName, taskId),
    queryFn: () => tasksApi.get(projectName, taskId),
    enabled: !!projectName && !!taskId,
  });
}

/**
 * Hook to fetch task audit history
 */
export function useTaskHistory(
  projectName: string,
  taskId: string,
  limit = 100,
) {
  return useQuery<AuditResponse, Error>({
    queryKey: taskKeys.history(projectName, taskId),
    queryFn: () => tasksApi.getHistory(projectName, taskId, limit),
    enabled: !!projectName && !!taskId,
  });
}
