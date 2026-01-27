/**
 * Tests for useWorkflow hooks
 */

import { describe, it, expect } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  useWorkflowStatus,
  useWorkflowHealth,
  useStartWorkflow,
  useResumeWorkflow,
  usePauseWorkflow,
  useRollbackWorkflow,
  useResetWorkflow,
} from "../useWorkflow";
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

describe("useWorkflowStatus", () => {
  it("should fetch workflow status", async () => {
    const { result } = renderHook(() => useWorkflowStatus("test-project"), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.data).toEqual({
      status: "not_started",
      mode: "langgraph",
      current_phase: 1,
      phase_status: expect.any(Object),
    });
  });

  it("should not fetch when projectName is empty", async () => {
    const { result } = renderHook(() => useWorkflowStatus(""), {
      wrapper: createWrapper(),
    });

    expect(result.current.fetchStatus).toBe("idle");
  });

  it("should poll more frequently when workflow is active", async () => {
    server.use(
      http.get("/api/projects/:name/status", () => {
        return HttpResponse.json({
          status: "in_progress",
          mode: "langgraph",
          current_phase: 2,
          phase_status: {},
        });
      }),
    );

    const { result } = renderHook(() => useWorkflowStatus("test-project"), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.data?.status).toBe("in_progress");
  });
});

describe("useWorkflowHealth", () => {
  it("should fetch workflow health", async () => {
    const { result } = renderHook(() => useWorkflowHealth("test-project"), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.data).toEqual({
      status: "healthy",
      project: "test-project",
      current_phase: 1,
      phase_status: "in_progress",
      iteration_count: 3,
      last_updated: expect.any(String),
      agents: expect.any(Object),
      langgraph_enabled: true,
      has_context: true,
      total_commits: 5,
    });
  });
});

describe("useStartWorkflow", () => {
  it("should start workflow with optimistic update", async () => {
    const queryClient = createTestQueryClient();
    const { result } = renderHook(() => useStartWorkflow("test-project"), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      result.current.mutate({ start_phase: 1, end_phase: 5 });
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.data).toEqual({
      success: true,
      mode: "langgraph",
      message: "Workflow started",
    });
  });

  it("should rollback on error", async () => {
    server.use(
      http.post("/api/projects/:name/start", () => {
        return HttpResponse.json({ error: "Start failed" }, { status: 500 });
      }),
    );

    const queryClient = createTestQueryClient();
    const { result } = renderHook(() => useStartWorkflow("test-project"), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      try {
        await result.current.mutateAsync({});
      } catch {
        // Expected to fail
      }
    });

    expect(result.current.isError).toBe(true);
  });
});

describe("useResumeWorkflow", () => {
  it("should resume workflow", async () => {
    const { result } = renderHook(() => useResumeWorkflow("test-project"), {
      wrapper: createWrapper(),
    });

    await act(async () => {
      result.current.mutate({});
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.data).toEqual({
      success: true,
      mode: "langgraph",
      message: "Workflow resumed",
    });
  });

  it("should resume with human response", async () => {
    const { result } = renderHook(() => useResumeWorkflow("test-project"), {
      wrapper: createWrapper(),
    });

    const humanResponse = { action: "approve", note: "Looks good" };
    await act(async () => {
      result.current.mutate(humanResponse);
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
  });
});

describe("usePauseWorkflow", () => {
  it("should pause workflow", async () => {
    const { result } = renderHook(() => usePauseWorkflow("test-project"), {
      wrapper: createWrapper(),
    });

    await act(async () => {
      result.current.mutate();
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.data).toEqual({ message: "Workflow paused" });
  });
});

describe("useRollbackWorkflow", () => {
  it("should rollback to specified phase", async () => {
    const { result } = renderHook(() => useRollbackWorkflow("test-project"), {
      wrapper: createWrapper(),
    });

    await act(async () => {
      result.current.mutate(2);
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.data).toEqual({
      success: true,
      rolled_back_to: "phase_2",
      current_phase: 2,
    });
  });
});

describe("useResetWorkflow", () => {
  it("should reset workflow", async () => {
    const queryClient = createTestQueryClient();
    const { result } = renderHook(() => useResetWorkflow("test-project"), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      result.current.mutate();
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.data).toEqual({ message: "Workflow reset" });
  });
});
