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
    // Poll faster when workflow is active, slower when idle
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "in_progress" ||
        status === "starting" ||
        status === "paused"
        ? 5000 // 5 seconds when active
        : 30000; // 30 seconds when idle
    },
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
    onMutate: async () => {
      // Cancel any outgoing refetches to avoid overwriting optimistic update
      await queryClient.cancelQueries({
        queryKey: workflowKeys.status(projectName),
      });

      // Snapshot the previous value
      const previousStatus = queryClient.getQueryData<WorkflowStatusResponse>(
        workflowKeys.status(projectName),
      );

      // Optimistically update to "starting" status
      queryClient.setQueryData<WorkflowStatusResponse>(
        workflowKeys.status(projectName),
        (old) => ({
          ...old,
          mode: old?.mode || "langgraph",
          phase_status: old?.phase_status || {},
          status: "starting" as const,
        }),
      );

      // Return context with the snapshotted value
      return { previousStatus };
    },
    onError: (_err, _variables, context) => {
      // If mutation fails, roll back to the previous value
      if (context?.previousStatus) {
        queryClient.setQueryData(
          workflowKeys.status(projectName),
          context.previousStatus,
        );
      }
    },
    onSuccess: () => {
      // Immediately refetch to get actual status
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
    mutationFn: (humanResponse?: Record<string, any>) =>
      workflowApi.resume(projectName, {
        autonomous: false,
        humanResponse,
      }),
    onMutate: async () => {
      // Cancel any outgoing refetches to avoid overwriting optimistic update
      await queryClient.cancelQueries({
        queryKey: workflowKeys.status(projectName),
      });

      // Snapshot the previous value
      const previousStatus = queryClient.getQueryData<WorkflowStatusResponse>(
        workflowKeys.status(projectName),
      );

      // Optimistically update to "in_progress" status
      queryClient.setQueryData<WorkflowStatusResponse>(
        workflowKeys.status(projectName),
        (old) => ({
          ...old,
          mode: old?.mode || "langgraph",
          phase_status: old?.phase_status || {},
          status: "in_progress" as const,
          pending_interrupt: undefined, // Clear interrupt on resume
        }),
      );

      // Return context with the snapshotted value
      return { previousStatus };
    },
    onError: (_err, _variables, context) => {
      // If mutation fails, roll back to the previous value
      if (context?.previousStatus) {
        queryClient.setQueryData(
          workflowKeys.status(projectName),
          context.previousStatus,
        );
      }
    },
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
