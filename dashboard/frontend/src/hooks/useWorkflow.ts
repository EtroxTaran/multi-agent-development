/**
 * TanStack Query hooks for workflow operations
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { workflowApi } from "@/lib/api";
import type { WorkflowHealthResponse, WorkflowStatusResponse } from "@/types";

// Query keys
export const workflowKeys = {
  all: ["workflow"] as const,
  status: (projectName: string) =>
    [...workflowKeys.all, "status", projectName] as const,
  health: (projectName: string) =>
    [...workflowKeys.all, "health", projectName] as const,
};

/**
 * Hook to fetch workflow status
 */
export function useWorkflowStatus(projectName: string) {
  return useQuery<WorkflowStatusResponse, Error>({
    queryKey: workflowKeys.status(projectName),
    queryFn: () => workflowApi.getStatus(projectName),
    enabled: !!projectName,
    refetchInterval: 30000, // Poll every 30 seconds (rely on WebSocket for real-time)
  });
}

/**
 * Hook to fetch workflow health
 */
export function useWorkflowHealth(projectName: string) {
  return useQuery<WorkflowHealthResponse, Error>({
    queryKey: workflowKeys.health(projectName),
    queryFn: () => workflowApi.getHealth(projectName),
    enabled: !!projectName,
    refetchInterval: 60000, // Poll every 60 seconds
  });
}

/**
 * Hook to start workflow
 */
export function useStartWorkflow(projectName: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (options?: {
      start_phase?: number;
      end_phase?: number;
      skip_validation?: boolean;
      autonomous?: boolean;
    }) => workflowApi.start(projectName, options),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: workflowKeys.status(projectName),
      });
      queryClient.invalidateQueries({
        queryKey: workflowKeys.health(projectName),
      });
    },
  });
}

/**
 * Hook to resume workflow
 */
export function useResumeWorkflow(projectName: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (autonomous: boolean = false) =>
      workflowApi.resume(projectName, autonomous),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: workflowKeys.status(projectName),
      });
      queryClient.invalidateQueries({
        queryKey: workflowKeys.health(projectName),
      });
    },
  });
}

/**
 * Hook to pause workflow
 */
export function usePauseWorkflow(projectName: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => workflowApi.pause(projectName),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: workflowKeys.status(projectName),
      });
    },
  });
}

/**
 * Hook to rollback workflow
 */
export function useRollbackWorkflow(projectName: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (phase: number) => workflowApi.rollback(projectName, phase),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: workflowKeys.status(projectName),
      });
      queryClient.invalidateQueries({
        queryKey: workflowKeys.health(projectName),
      });
    },
  });
}

/**
 * Hook to reset workflow
 */
export function useResetWorkflow(projectName: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => workflowApi.reset(projectName),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: workflowKeys.status(projectName),
      });
      queryClient.invalidateQueries({
        queryKey: workflowKeys.health(projectName),
      });
    },
  });
}
