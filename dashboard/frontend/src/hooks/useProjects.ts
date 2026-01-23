/**
 * TanStack Query hooks for project operations
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { projectsApi } from "@/lib/api";
import type { FolderInfo, ProjectStatus, ProjectSummary } from "@/types";

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
