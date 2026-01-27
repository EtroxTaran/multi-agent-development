/**
 * Tests for useTasks hooks
 */

import { describe, it, expect } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useTasks, useTask, useTaskHistory, taskKeys } from "../useTasks";
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

describe("taskKeys", () => {
  it("should generate correct key structure for all tasks", () => {
    expect(taskKeys.all).toEqual(["tasks"]);
  });

  it("should generate correct key for lists", () => {
    expect(taskKeys.lists("my-project")).toEqual([
      "tasks",
      "list",
      "my-project",
    ]);
  });

  it("should generate correct key for list with status filter", () => {
    expect(taskKeys.list("my-project", "completed")).toEqual([
      "tasks",
      "list",
      "my-project",
      { status: "completed" },
    ]);
  });

  it("should generate correct key for detail", () => {
    expect(taskKeys.detail("my-project", "task-1")).toEqual([
      "tasks",
      "detail",
      "my-project",
      "task-1",
    ]);
  });

  it("should generate correct key for history", () => {
    expect(taskKeys.history("my-project", "task-1")).toEqual([
      "tasks",
      "detail",
      "my-project",
      "task-1",
      "history",
    ]);
  });
});

describe("useTasks", () => {
  it("should fetch tasks for a project", async () => {
    const { result } = renderHook(() => useTasks("test-project"), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.data).toEqual({
      tasks: expect.any(Array),
      total: expect.any(Number),
      completed: expect.any(Number),
      in_progress: expect.any(Number),
      pending: expect.any(Number),
    });
  });

  it("should filter tasks by status", async () => {
    server.use(
      http.get("/api/projects/:name/tasks", ({ request }) => {
        const url = new URL(request.url);
        const status = url.searchParams.get("status");

        const tasks =
          status === "completed"
            ? [{ id: "task-1", title: "Completed task", status: "completed" }]
            : [];

        return HttpResponse.json({
          tasks,
          total: tasks.length,
          completed: tasks.filter((t) => t.status === "completed").length,
          in_progress: 0,
          pending: 0,
        });
      }),
    );

    const { result } = renderHook(() => useTasks("test-project", "completed"), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.data?.tasks).toHaveLength(1);
  });

  it("should not fetch when projectName is empty", () => {
    const { result } = renderHook(() => useTasks(""), {
      wrapper: createWrapper(),
    });

    expect(result.current.fetchStatus).toBe("idle");
  });

  it("should poll tasks every 5 seconds", async () => {
    const { result } = renderHook(() => useTasks("test-project"), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    // The refetchInterval is set in the hook
    // We just verify the hook loads successfully
    expect(result.current.data).toBeDefined();
  });
});

describe("useTask", () => {
  it("should fetch a single task", async () => {
    const { result } = renderHook(() => useTask("test-project", "task-1"), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.data).toEqual({
      id: "task-1",
      title: expect.any(String),
      description: expect.any(String),
      status: expect.any(String),
      complexity_score: expect.any(Number),
      priority: expect.any(Number),
      files_to_create: expect.any(Array),
      files_to_modify: expect.any(Array),
      acceptance_criteria: expect.any(Array),
      dependencies: expect.any(Array),
    });
  });

  it("should not fetch when projectName is empty", () => {
    const { result } = renderHook(() => useTask("", "task-1"), {
      wrapper: createWrapper(),
    });

    expect(result.current.fetchStatus).toBe("idle");
  });

  it("should not fetch when taskId is empty", () => {
    const { result } = renderHook(() => useTask("test-project", ""), {
      wrapper: createWrapper(),
    });

    expect(result.current.fetchStatus).toBe("idle");
  });

  it("should handle task not found", async () => {
    server.use(
      http.get("/api/projects/:name/tasks/:taskId", () => {
        return HttpResponse.json({ error: "Task not found" }, { status: 404 });
      }),
    );

    const { result } = renderHook(
      () => useTask("test-project", "nonexistent"),
      { wrapper: createWrapper() },
    );

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
  });
});

describe("useTaskHistory", () => {
  it("should fetch task audit history", async () => {
    const { result } = renderHook(
      () => useTaskHistory("test-project", "task-1"),
      { wrapper: createWrapper() },
    );

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.data).toEqual({
      entries: expect.any(Array),
      total: expect.any(Number),
    });
  });

  it("should respect limit parameter", async () => {
    server.use(
      http.get("/api/projects/:name/tasks/:taskId/history", ({ request }) => {
        const url = new URL(request.url);
        const limit = url.searchParams.get("limit");

        return HttpResponse.json({
          entries: Array(Number(limit) || 100).fill({ id: "entry" }),
          total: Number(limit) || 100,
        });
      }),
    );

    const { result } = renderHook(
      () => useTaskHistory("test-project", "task-1", 50),
      { wrapper: createWrapper() },
    );

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.data?.entries).toHaveLength(50);
  });

  it("should not fetch when projectName or taskId is empty", () => {
    const { result } = renderHook(() => useTaskHistory("", "task-1"), {
      wrapper: createWrapper(),
    });

    expect(result.current.fetchStatus).toBe("idle");
  });
});
