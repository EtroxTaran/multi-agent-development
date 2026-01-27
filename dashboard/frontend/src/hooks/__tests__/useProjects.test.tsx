/**
 * Tests for useProjects hooks
 */

import { describe, it, expect, vi } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  useProjects,
  useProjectsWithStatus,
  useProject,
  useWorkspaceFolders,
  useInitProject,
  useDeleteProject,
  projectKeys,
} from "../useProjects";
import { server } from "@/test/mocks/server";
import { http, HttpResponse } from "msw";

function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
}

function createWrapper(queryClient?: QueryClient) {
  const client = queryClient ?? createTestQueryClient();
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
}

describe("projectKeys", () => {
  it("should generate correct key for all", () => {
    expect(projectKeys.all).toEqual(["projects"]);
  });

  it("should generate correct key for list", () => {
    expect(projectKeys.list()).toEqual(["projects", "list"]);
  });

  it("should generate correct key for detail", () => {
    expect(projectKeys.detail("my-project")).toEqual([
      "projects",
      "detail",
      "my-project",
    ]);
  });

  it("should generate correct key for folders", () => {
    expect(projectKeys.folders()).toEqual(["projects", "folders"]);
  });
});

describe("useProjects", () => {
  it("should fetch all projects", async () => {
    const { result } = renderHook(() => useProjects(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.data).toEqual([
      expect.objectContaining({
        name: "test-project",
        path: expect.any(String),
      }),
      expect.objectContaining({
        name: "active-project",
        path: expect.any(String),
      }),
    ]);
  });

  it("should have staleTime of 30 seconds", async () => {
    const { result } = renderHook(() => useProjects(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    // The hook has staleTime: 1000 * 30
    expect(result.current.isStale).toBe(false);
  });
});

describe("useProjectsWithStatus", () => {
  it("should fetch projects and enrich with real-time status", async () => {
    const { result } = renderHook(() => useProjectsWithStatus(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
      expect(result.current.isLoadingStatuses).toBe(false);
    });

    // Projects should be enriched with status data
    expect(result.current.data).toHaveLength(2);
    expect(result.current.data[0]).toEqual(
      expect.objectContaining({
        name: "test-project",
        workflow_status: expect.any(String),
        current_phase: expect.any(Number),
      }),
    );
  });

  it("should merge status data with project data", async () => {
    // Override status endpoint to return specific status
    server.use(
      http.get("/api/projects/:name/status", ({ params }) => {
        return HttpResponse.json({
          status: params.name === "test-project" ? "in_progress" : "idle",
          mode: "langgraph",
          current_phase: params.name === "test-project" ? 3 : 1,
          phase_status: {},
        });
      }),
    );

    const { result } = renderHook(() => useProjectsWithStatus(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
      expect(result.current.isLoadingStatuses).toBe(false);
    });

    // Find the test-project
    const testProject = result.current.data.find(
      (p) => p.name === "test-project",
    );
    expect(testProject?.workflow_status).toBe("in_progress");
    expect(testProject?.current_phase).toBe(3);
  });

  it("should handle empty project list", async () => {
    server.use(
      http.get("/api/projects", () => {
        return HttpResponse.json([]);
      }),
    );

    const { result } = renderHook(() => useProjectsWithStatus(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.data).toEqual([]);
    expect(result.current.isLoadingStatuses).toBe(false);
  });
});

describe("useProject", () => {
  it("should fetch a single project", async () => {
    const { result } = renderHook(() => useProject("test-project"), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.data).toEqual(
      expect.objectContaining({
        name: "test-project",
        path: "/projects/test-project",
        files: expect.any(Object),
        phases: expect.any(Object),
      }),
    );
  });

  it("should not fetch when name is empty", () => {
    const { result } = renderHook(() => useProject(""), {
      wrapper: createWrapper(),
    });

    expect(result.current.fetchStatus).toBe("idle");
  });

  it("should handle project not found", async () => {
    server.use(
      http.get("/api/projects/:name", () => {
        return HttpResponse.json(
          { error: "Project not found" },
          { status: 404 },
        );
      }),
    );

    const { result } = renderHook(() => useProject("nonexistent"), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
  });
});

describe("useWorkspaceFolders", () => {
  it("should fetch workspace folders", async () => {
    server.use(
      http.get("/api/projects/workspace/folders", () => {
        return HttpResponse.json([
          { name: "project-a", path: "/workspace/project-a", is_project: true },
          {
            name: "project-b",
            path: "/workspace/project-b",
            is_project: false,
          },
        ]);
      }),
    );

    const { result } = renderHook(() => useWorkspaceFolders(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.data).toEqual([
      expect.objectContaining({ name: "project-a", is_project: true }),
      expect.objectContaining({ name: "project-b", is_project: false }),
    ]);
  });
});

describe("useInitProject", () => {
  it("should initialize a project", async () => {
    const queryClient = createTestQueryClient();
    const { result } = renderHook(() => useInitProject(), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      await result.current.mutateAsync("new-project");
    });

    expect(result.current.isSuccess).toBe(true);
    expect(result.current.data).toEqual({
      success: true,
      project_dir: "/projects/new-project",
    });
  });

  it("should invalidate project lists after init", async () => {
    const queryClient = createTestQueryClient();
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

    const { result } = renderHook(() => useInitProject(), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      await result.current.mutateAsync("new-project");
    });

    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: projectKeys.lists(),
    });
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: projectKeys.folders(),
    });
  });

  it("should handle init error", async () => {
    server.use(
      http.post("/api/projects/:name/init", () => {
        return HttpResponse.json(
          { error: "Project already exists" },
          { status: 400 },
        );
      }),
    );

    const { result } = renderHook(() => useInitProject(), {
      wrapper: createWrapper(),
    });

    await act(async () => {
      try {
        await result.current.mutateAsync("existing-project");
      } catch {
        // Expected
      }
    });

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
  });
});

describe("useDeleteProject", () => {
  it("should delete a project", async () => {
    const queryClient = createTestQueryClient();
    const { result } = renderHook(() => useDeleteProject(), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      await result.current.mutateAsync({ name: "test-project" });
    });

    expect(result.current.isSuccess).toBe(true);
    expect(result.current.data).toEqual({ message: "Project deleted" });
  });

  it("should delete project with source removal", async () => {
    const { result } = renderHook(() => useDeleteProject(), {
      wrapper: createWrapper(),
    });

    await act(async () => {
      await result.current.mutateAsync({
        name: "test-project",
        removeSource: true,
      });
    });

    expect(result.current.isSuccess).toBe(true);
  });

  it("should invalidate queries and remove detail after delete", async () => {
    const queryClient = createTestQueryClient();
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");
    const removeSpy = vi.spyOn(queryClient, "removeQueries");

    const { result } = renderHook(() => useDeleteProject(), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      await result.current.mutateAsync({ name: "test-project" });
    });

    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: projectKeys.lists(),
    });
    expect(removeSpy).toHaveBeenCalledWith({
      queryKey: projectKeys.detail("test-project"),
    });
  });
});
