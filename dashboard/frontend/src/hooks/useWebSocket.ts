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
            // Task events - invalidate task queries
            case "task_start":
            case "task_complete":
            case "task_failed":
            case "action":
              queryClient.invalidateQueries({
                queryKey: taskKeys.lists(projectName),
              });
              if (data.data.task_id) {
                queryClient.invalidateQueries({
                  queryKey: taskKeys.detail(
                    projectName,
                    data.data.task_id as string,
                  ),
                });
              }
              break;

            // Phase/Node events - invalidate workflow status
            case "phase_start":
            case "phase_end":
            case "phase_change":
            case "node_start":
            case "node_end":
            case "state_change":
              queryClient.invalidateQueries({
                queryKey: workflowKeys.status(projectName),
              });
              break;

            // Workflow lifecycle
            case "workflow_start":
            case "workflow_complete":
            case "workflow_error":
              queryClient.invalidateQueries({
                queryKey: workflowKeys.status(projectName),
              });
              queryClient.invalidateQueries({
                queryKey: workflowKeys.health(projectName),
              });
              queryClient.invalidateQueries({
                queryKey: ["workflow", "graph", projectName],
              });
              queryClient.invalidateQueries({
                queryKey: taskKeys.lists(projectName),
              });
              break;

            case "workflow_paused":
            case "workflow_resumed":
            case "pause_requested":
              queryClient.invalidateQueries({
                queryKey: workflowKeys.status(projectName),
              });
              break;

            // Errors and escalations
            case "error_occurred":
              queryClient.invalidateQueries({
                queryKey: workflowKeys.status(projectName),
              });
              queryClient.invalidateQueries({
                queryKey: workflowKeys.health(projectName),
              });
              break;

            case "escalation_required":
            case "escalation":
              queryClient.invalidateQueries({
                queryKey: workflowKeys.status(projectName),
              });
              break;

            // Agent events
            case "agent_start":
            case "agent_complete":
              queryClient.invalidateQueries({
                queryKey: workflowKeys.health(projectName),
              });
              break;

            // Ralph iteration
            case "ralph_iteration":
              if (data.data.task_id) {
                queryClient.invalidateQueries({
                  queryKey: taskKeys.detail(
                    projectName,
                    data.data.task_id as string,
                  ),
                });
              }
              break;

            // Metrics
            case "metrics_update":
              queryClient.invalidateQueries({
                queryKey: ["budget", projectName],
              });
              break;

            case "heartbeat":
            case "path_decision":
              // No action needed
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
