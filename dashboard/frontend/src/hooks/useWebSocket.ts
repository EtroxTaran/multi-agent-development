/**
 * WebSocket hook for real-time updates
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { createWebSocket } from "@/lib/api";
import type { WebSocketEvent } from "@/types";

import { workflowKeys } from "./useWorkflow";
import { taskKeys } from "./useTasks";

interface UseWebSocketOptions {
  onEvent?: (event: WebSocketEvent) => void;
  onError?: (error: Event) => void;
  reconnectInterval?: number;
  maxReconnectAttempts?: number;
}

/**
 * Hook for WebSocket connection with automatic reconnection
 */
export function useWebSocket(
  projectName: string | undefined,
  options: UseWebSocketOptions = {},
) {
  const {
    onEvent,
    onError,
    reconnectInterval = 3000,
    maxReconnectAttempts = 5,
  } = options;

  const [isConnected, setIsConnected] = useState(false);
  const [lastEvent, setLastEvent] = useState<WebSocketEvent | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout>();
  const queryClient = useQueryClient();

  const connect = useCallback(() => {
    if (!projectName) return;

    try {
      const ws = createWebSocket(projectName);

      ws.onopen = () => {
        setIsConnected(true);
        reconnectAttemptsRef.current = 0;
        // Immediately fetch latest status on reconnect to catch any missed HITL state
        queryClient.invalidateQueries({
          queryKey: workflowKeys.status(projectName),
        });
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data) as WebSocketEvent;
          setLastEvent(data);
          onEvent?.(data);

          // Invalidate relevant queries based on event type
          switch (data.type) {
            case "state_change":
            case "escalation":
            case "node_start":
            case "node_end":
            case "phase_change":
              // Refresh status for state changes, phase transitions, and HITL escalation events
              queryClient.invalidateQueries({
                queryKey: workflowKeys.status(projectName),
              });
              break;
            case "workflow_complete":
            case "workflow_error":
              // Invalidate both status and graph cache on completion/error
              queryClient.invalidateQueries({
                queryKey: workflowKeys.status(projectName),
              });
              queryClient.invalidateQueries({
                queryKey: ["workflow", "graph", projectName],
              });
              break;
            case "action":
              queryClient.invalidateQueries({
                queryKey: taskKeys.lists(projectName),
              });
              break;
          }
        } catch (e) {
          console.error("Failed to parse WebSocket message:", e);
        }
      };

      ws.onclose = () => {
        setIsConnected(false);
        wsRef.current = null;

        // Attempt reconnection
        if (reconnectAttemptsRef.current < maxReconnectAttempts) {
          reconnectAttemptsRef.current++;
          reconnectTimeoutRef.current = setTimeout(connect, reconnectInterval);
        }
      };

      ws.onerror = (error) => {
        console.error("WebSocket error:", error);
        onError?.(error);
      };

      wsRef.current = ws;
    } catch (e) {
      console.error("Failed to create WebSocket:", e);
    }
  }, [
    projectName,
    onEvent,
    onError,
    reconnectInterval,
    maxReconnectAttempts,
    queryClient,
  ]);

  const disconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
    }
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    setIsConnected(false);
  }, []);

  const send = useCallback((data: unknown) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(data));
    }
  }, []);

  useEffect(() => {
    connect();
    return disconnect;
  }, [connect, disconnect]);

  return {
    isConnected,
    lastEvent,
    send,
    reconnect: connect,
    disconnect,
  };
}
