/**
 * TanStack Query hooks for project operations
 */

import {
  useMutation,
  useQuery,
  useQueries,
  useQueryClient,
} from "@tanstack/react-query";
import { projectsApi, workflowApi } from "@/lib/api";
import type { FolderInfo, ProjectStatus, ProjectSummary } from "@/types";
import { workflowKeys } from "./useWorkflow";

// Query keys
export const projectKeys = {
  all: ["projects"] as const,
  lists: () => [...projectKeys.all, "list"] as const,
  list: () => projectKeys.lists(),
  details: () => [...projectKeys.all, "detail"] as const,
  detail: (name: string) => [...projectKeys.details(), name] as const,
  folders: () => [...projectKeys.all, "folders"] as const,
};

/**
 * Hook to fetch all projects
 */
export function useProjects() {
  return useQuery<ProjectSummary[], Error>({
    queryKey: projectKeys.list(),
    queryFn: projectsApi.list,
    staleTime: 1000 * 30, // 30 seconds
  });
}

/**
 * Hook to fetch all projects with real-time workflow status
 * This enriches the project list with live status from LangGraph checkpoints
 */
export function useProjectsWithStatus() {
  const projectsQuery = useProjects();
  const projects = projectsQuery.data ?? [];

  // Fetch real-time status for each project
  const statusQueries = useQueries({
    queries: projects.map((project) => ({
      queryKey: workflowKeys.status(project.name),
      queryFn: () => workflowApi.getStatus(project.name),
      staleTime: 5000, // 5 seconds for active status
      enabled: !!project.name,
    })),
  });

  // Merge projects with their real-time status
  const enrichedProjects = projects.map((project, index) => {
    const statusData = statusQueries[index]?.data;
    return {
      ...project,
      // Override stale workflow_status with real-time status
      workflow_status:
        statusData?.status ?? project.workflow_status ?? "not_started",
      // Add current phase from real-time data if available
      current_phase: statusData?.current_phase ?? project.current_phase,
    };
  });

  // Determine overall loading state
  const isLoadingStatuses = statusQueries.some((q) => q.isLoading);

  return {
    ...projectsQuery,
    data: enrichedProjects,
    isLoadingStatuses,
  };
}

/**
 * Hook to fetch a single project
 */
export function useProject(name: string) {
  return useQuery<ProjectStatus, Error>({
    queryKey: projectKeys.detail(name),
    queryFn: () => projectsApi.get(name),
    enabled: !!name,
    staleTime: 10000, // 10 seconds
  });
}

/**
 * Hook to fetch workspace folders
 */
export function useWorkspaceFolders() {
  return useQuery<FolderInfo[], Error>({
    queryKey: projectKeys.folders(),
    queryFn: projectsApi.listFolders,
  });
}

/**
 * Hook to initialize a project
 */
export function useInitProject() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (name: string) => projectsApi.init(name),
    onSuccess: () => {
      // Invalidate project lists
      queryClient.invalidateQueries({ queryKey: projectKeys.lists() });
      queryClient.invalidateQueries({ queryKey: projectKeys.folders() });
    },
  });
}

/**
 * Hook to delete a project
 */
export function useDeleteProject() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      name,
      removeSource = false,
    }: {
      name: string;
      removeSource?: boolean;
    }) => projectsApi.delete(name, removeSource),
    onSuccess: (_, { name }) => {
      // Invalidate project lists and remove detail
      queryClient.invalidateQueries({ queryKey: projectKeys.lists() });
      queryClient.invalidateQueries({ queryKey: projectKeys.folders() });
      queryClient.removeQueries({ queryKey: projectKeys.detail(name) });
    },
  });
}
