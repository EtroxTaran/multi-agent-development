/**
 * Tests for useChat hooks
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  useStreamingChat,
  useSendMessage,
  useExecuteCommand,
  useFeedback,
  useRespondToEscalation,
  chatKeys,
} from "../useChat";

// Mock createChatWebSocket
vi.mock("@/lib/api", async (importOriginal) => {
  const original = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...original,
    createChatWebSocket: vi.fn(() => ({
      onopen: null,
      onclose: null,
      onmessage: null,
      onerror: null,
      send: vi.fn(),
      close: vi.fn(),
      readyState: 1,
    })),
  };
});

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

describe("chatKeys", () => {
  it("should generate correct key for all", () => {
    expect(chatKeys.all).toEqual(["chat"]);
  });

  it("should generate correct key for feedback", () => {
    expect(chatKeys.feedback("my-project", 2)).toEqual([
      "chat",
      "feedback",
      "my-project",
      2,
    ]);
  });
});

describe("useStreamingChat", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("should initialize with empty state", () => {
    const { result } = renderHook(() => useStreamingChat("test-project"));

    expect(result.current.messages).toEqual([]);
    expect(result.current.currentResponse).toBe("");
    expect(result.current.isStreaming).toBe(false);
  });

  it("should send message and add user message to list", async () => {
    const { createChatWebSocket } = await import("@/lib/api");
    const mockWs = {
      onopen: null as ((event: Event) => void) | null,
      onclose: null as ((event: CloseEvent) => void) | null,
      onmessage: null as ((event: MessageEvent) => void) | null,
      onerror: null as ((event: Event) => void) | null,
      send: vi.fn(),
      close: vi.fn(),
      readyState: 1,
    };
    vi.mocked(createChatWebSocket).mockReturnValue(
      mockWs as unknown as WebSocket,
    );

    const { result } = renderHook(() => useStreamingChat("test-project"));

    act(() => {
      result.current.sendMessage("Hello, Claude!");
    });

    expect(result.current.messages).toHaveLength(1);
    expect(result.current.messages[0]).toEqual({
      role: "user",
      content: "Hello, Claude!",
      timestamp: expect.any(String),
    });
    expect(result.current.isStreaming).toBe(true);
  });

  it("should handle chat_chunk events and accumulate response (stale closure fix)", async () => {
    const { createChatWebSocket } = await import("@/lib/api");
    const mockWs = {
      onopen: null as ((event: Event) => void) | null,
      onclose: null as ((event: CloseEvent) => void) | null,
      onmessage: null as ((event: MessageEvent) => void) | null,
      onerror: null as ((event: Event) => void) | null,
      send: vi.fn(),
      close: vi.fn(),
      readyState: 1,
    };
    vi.mocked(createChatWebSocket).mockReturnValue(
      mockWs as unknown as WebSocket,
    );

    const { result } = renderHook(() => useStreamingChat("test-project"));

    // Send message
    act(() => {
      result.current.sendMessage("Hello");
    });

    // Simulate connection
    act(() => {
      mockWs.onopen?.(new Event("open"));
    });

    // Simulate multiple chunks
    act(() => {
      mockWs.onmessage?.(
        new MessageEvent("message", {
          data: JSON.stringify({
            type: "chat_chunk",
            data: { content: "Hello" },
          }),
        }),
      );
    });

    act(() => {
      mockWs.onmessage?.(
        new MessageEvent("message", {
          data: JSON.stringify({
            type: "chat_chunk",
            data: { content: " there!" },
          }),
        }),
      );
    });

    // The currentResponse should accumulate
    expect(result.current.currentResponse).toBe("Hello there!");
  });

  it("should handle chat_complete and add assistant message (stale closure fix)", async () => {
    const { createChatWebSocket } = await import("@/lib/api");
    const mockWs = {
      onopen: null as ((event: Event) => void) | null,
      onclose: null as ((event: CloseEvent) => void) | null,
      onmessage: null as ((event: MessageEvent) => void) | null,
      onerror: null as ((event: Event) => void) | null,
      send: vi.fn(),
      close: vi.fn(),
      readyState: 1,
    };
    vi.mocked(createChatWebSocket).mockReturnValue(
      mockWs as unknown as WebSocket,
    );

    const { result } = renderHook(() => useStreamingChat("test-project"));

    // Send message
    act(() => {
      result.current.sendMessage("Hello");
    });

    // Simulate connection
    act(() => {
      mockWs.onopen?.(new Event("open"));
    });

    // Simulate chunks
    act(() => {
      mockWs.onmessage?.(
        new MessageEvent("message", {
          data: JSON.stringify({
            type: "chat_chunk",
            data: { content: "Hi!" },
          }),
        }),
      );
    });

    // Simulate completion - this tests the stale closure fix
    act(() => {
      mockWs.onmessage?.(
        new MessageEvent("message", {
          data: JSON.stringify({ type: "chat_complete" }),
        }),
      );
    });

    // After completion, assistant message should have the accumulated content
    await waitFor(() => {
      expect(result.current.isStreaming).toBe(false);
    });

    expect(result.current.messages).toHaveLength(2); // user + assistant
    expect(result.current.messages[1]).toEqual({
      role: "assistant",
      content: "Hi!", // Should have the full accumulated content
      timestamp: expect.any(String),
    });
    expect(result.current.currentResponse).toBe("");
  });

  it("should handle chat_error events", async () => {
    const { createChatWebSocket } = await import("@/lib/api");
    const mockWs = {
      onopen: null as ((event: Event) => void) | null,
      onclose: null as ((event: CloseEvent) => void) | null,
      onmessage: null as ((event: MessageEvent) => void) | null,
      onerror: null as ((event: Event) => void) | null,
      send: vi.fn(),
      close: vi.fn(),
      readyState: 1,
    };
    vi.mocked(createChatWebSocket).mockReturnValue(
      mockWs as unknown as WebSocket,
    );

    const { result } = renderHook(() => useStreamingChat("test-project"));

    act(() => {
      result.current.sendMessage("Hello");
    });

    act(() => {
      mockWs.onopen?.(new Event("open"));
    });

    act(() => {
      mockWs.onmessage?.(
        new MessageEvent("message", {
          data: JSON.stringify({
            type: "chat_error",
            data: { error: "Rate limited" },
          }),
        }),
      );
    });

    expect(result.current.isStreaming).toBe(false);
    expect(result.current.messages[1].content).toBe("Error: Rate limited");
  });

  it("should stop streaming and close WebSocket", async () => {
    const { createChatWebSocket } = await import("@/lib/api");
    const mockWs = {
      onopen: null as ((event: Event) => void) | null,
      onclose: null as ((event: CloseEvent) => void) | null,
      onmessage: null as ((event: MessageEvent) => void) | null,
      onerror: null as ((event: Event) => void) | null,
      send: vi.fn(),
      close: vi.fn(),
      readyState: 1,
    };
    vi.mocked(createChatWebSocket).mockReturnValue(
      mockWs as unknown as WebSocket,
    );

    const { result } = renderHook(() => useStreamingChat("test-project"));

    act(() => {
      result.current.sendMessage("Hello");
    });

    act(() => {
      result.current.stopStreaming();
    });

    expect(mockWs.close).toHaveBeenCalled();
    expect(result.current.isStreaming).toBe(false);
  });

  it("should clear messages", () => {
    const { result } = renderHook(() => useStreamingChat("test-project"));

    // Manually set some state (simulating previous conversation)
    act(() => {
      result.current.clearMessages();
    });

    expect(result.current.messages).toEqual([]);
    expect(result.current.currentResponse).toBe("");
  });
});

describe("useSendMessage", () => {
  it("should send a message", async () => {
    const { result } = renderHook(() => useSendMessage(), {
      wrapper: createWrapper(),
    });

    await act(async () => {
      await result.current.mutateAsync({
        message: "Test message",
        projectName: "test-project",
      });
    });

    expect(result.current.isSuccess).toBe(true);
    expect(result.current.data).toEqual({
      message: "Response",
      streaming: false,
    });
  });
});

describe("useExecuteCommand", () => {
  it("should execute a command", async () => {
    const { result } = renderHook(() => useExecuteCommand(), {
      wrapper: createWrapper(),
    });

    await act(async () => {
      await result.current.mutateAsync({
        command: "status",
        args: [],
        projectName: "test-project",
      });
    });

    expect(result.current.isSuccess).toBe(true);
    expect(result.current.data).toEqual({
      success: true,
      output: "Command executed",
    });
  });
});

describe("useFeedback", () => {
  it("should fetch feedback for phase 2", async () => {
    const { result } = renderHook(() => useFeedback("test-project", 2), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.data).toEqual({ feedback: "All good" });
  });

  it("should fetch feedback for phase 4", async () => {
    const { result } = renderHook(() => useFeedback("test-project", 4), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
  });

  it("should not fetch for other phases", () => {
    const { result } = renderHook(() => useFeedback("test-project", 1), {
      wrapper: createWrapper(),
    });

    expect(result.current.fetchStatus).toBe("idle");
  });

  it("should not fetch when projectName is empty", () => {
    const { result } = renderHook(() => useFeedback("", 2), {
      wrapper: createWrapper(),
    });

    expect(result.current.fetchStatus).toBe("idle");
  });
});

describe("useRespondToEscalation", () => {
  it("should respond to escalation", async () => {
    const queryClient = createTestQueryClient();
    const { result } = renderHook(
      () => useRespondToEscalation("test-project"),
      { wrapper: createWrapper(queryClient) },
    );

    await act(async () => {
      await result.current.mutateAsync({
        questionId: "q1",
        answer: "approved",
        additionalContext: "Looks good",
      });
    });

    expect(result.current.isSuccess).toBe(true);
    expect(result.current.data).toEqual({
      message: "Response recorded",
      question_id: "q1",
    });
  });

  it("should invalidate workflow status after responding", async () => {
    const queryClient = createTestQueryClient();
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

    const { result } = renderHook(
      () => useRespondToEscalation("test-project"),
      { wrapper: createWrapper(queryClient) },
    );

    await act(async () => {
      await result.current.mutateAsync({
        questionId: "q1",
        answer: "approved",
      });
    });

    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: ["workflow", "status", "test-project"],
    });
  });
});
