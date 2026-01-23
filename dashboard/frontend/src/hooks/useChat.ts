/**
 * Chat hooks for Claude integration
 */

import { useCallback, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { chatApi, createChatWebSocket } from "@/lib/api";
import type { ChatMessage } from "@/types";

// Query keys
export const chatKeys = {
  all: ["chat"] as const,
  feedback: (projectName: string, phase: number) =>
    [...chatKeys.all, "feedback", projectName, phase] as const,
};

/**
 * Hook for streaming chat with Claude
 */
export function useStreamingChat(projectName?: string) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [currentResponse, setCurrentResponse] = useState("");
  const wsRef = useRef<WebSocket | null>(null);

  const sendMessage = useCallback(
    (message: string) => {
      // Add user message
      setMessages((prev) => [
        ...prev,
        { role: "user", content: message, timestamp: new Date().toISOString() },
      ]);

      // Start streaming
      setIsStreaming(true);
      setCurrentResponse("");

      const ws = createChatWebSocket(projectName);

      ws.onopen = () => {
        ws.send(JSON.stringify({ message }));
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);

          if (data.type === "chat_chunk") {
            setCurrentResponse((prev) => prev + data.data.content);
          } else if (data.type === "chat_complete") {
            setIsStreaming(false);
            setMessages((prev) => [
              ...prev,
              {
                role: "assistant",
                content: currentResponse,
                timestamp: new Date().toISOString(),
              },
            ]);
            setCurrentResponse("");
          } else if (data.type === "chat_error") {
            setIsStreaming(false);
            setMessages((prev) => [
              ...prev,
              {
                role: "assistant",
                content: `Error: ${data.data.error}`,
                timestamp: new Date().toISOString(),
              },
            ]);
          }
        } catch (e) {
          console.error("Failed to parse chat message:", e);
        }
      };

      ws.onerror = () => {
        setIsStreaming(false);
      };

      ws.onclose = () => {
        setIsStreaming(false);
        wsRef.current = null;
      };

      wsRef.current = ws;
    },
    [projectName, currentResponse],
  );

  const stopStreaming = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    setIsStreaming(false);
  }, []);

  const clearMessages = useCallback(() => {
    setMessages([]);
    setCurrentResponse("");
  }, []);

  return {
    messages,
    currentResponse,
    isStreaming,
    sendMessage,
    stopStreaming,
    clearMessages,
  };
}

/**
 * Hook for single-shot chat messages
 */
export function useSendMessage() {
  return useMutation({
    mutationFn: ({
      message,
      projectName,
    }: {
      message: string;
      projectName?: string;
    }) => chatApi.send(message, projectName),
  });
}

/**
 * Hook for executing Claude commands
 */
export function useExecuteCommand() {
  return useMutation({
    mutationFn: ({
      command,
      args = [],
      projectName,
    }: {
      command: string;
      args?: string[];
      projectName?: string;
    }) => chatApi.executeCommand(command, args, projectName),
  });
}

/**
 * Hook for fetching phase feedback
 */
export function useFeedback(projectName: string, phase: number) {
  return useQuery({
    queryKey: chatKeys.feedback(projectName, phase),
    queryFn: () => chatApi.getFeedback(projectName, phase),
    enabled: !!projectName && (phase === 2 || phase === 4),
  });
}

/**
 * Hook for responding to escalations
 */
export function useRespondToEscalation(projectName: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      questionId,
      answer,
      additionalContext,
    }: {
      questionId: string;
      answer: string;
      additionalContext?: string;
    }) =>
      chatApi.respondToEscalation(
        projectName,
        questionId,
        answer,
        additionalContext,
      ),
    onSuccess: () => {
      // Invalidate workflow status
      queryClient.invalidateQueries({
        queryKey: ["workflow", "status", projectName],
      });
    },
  });
}
