import { Injectable, Logger } from "@nestjs/common";
import { WebSocket } from "ws";
import { WebSocketEventType } from "../common/enums";

interface WebSocketMessage {
  type: WebSocketEventType;
  data: Record<string, unknown>;
  timestamp: string;
}

@Injectable()
export class WebsocketService {
  private readonly logger = new Logger(WebsocketService.name);
  private connections: Map<string, Set<WebSocket>> = new Map();

  /**
   * Register a WebSocket connection for a project
   */
  addConnection(projectName: string, client: WebSocket): void {
    if (!this.connections.has(projectName)) {
      this.connections.set(projectName, new Set());
    }
    this.connections.get(projectName)!.add(client);
    this.logger.log(`Client connected to project '${projectName}'`);
  }

  /**
   * Remove a WebSocket connection for a project
   */
  removeConnection(projectName: string, client: WebSocket): void {
    const projectConnections = this.connections.get(projectName);
    if (projectConnections) {
      projectConnections.delete(client);
      if (projectConnections.size === 0) {
        this.connections.delete(projectName);
      }
      this.logger.log(`Client disconnected from project '${projectName}'`);
    }
  }

  /**
   * Broadcast a message to all clients connected to a project
   */
  broadcastToProject(
    projectName: string,
    type: WebSocketEventType,
    data: Record<string, unknown>,
  ): void {
    const projectConnections = this.connections.get(projectName);
    if (!projectConnections || projectConnections.size === 0) {
      return;
    }

    const message: WebSocketMessage = {
      type,
      data,
      timestamp: new Date().toISOString(),
    };

    const payload = JSON.stringify(message);
    let sent = 0;

    for (const client of projectConnections) {
      if (client.readyState === WebSocket.OPEN) {
        client.send(payload);
        sent++;
      }
    }

    this.logger.debug(
      `Broadcast '${type}' to ${sent}/${projectConnections.size} clients for project '${projectName}'`,
    );
  }

  /**
   * Broadcast a message to all connected clients
   */
  broadcastToAll(
    type: WebSocketEventType,
    data: Record<string, unknown>,
  ): void {
    const message: WebSocketMessage = {
      type,
      data,
      timestamp: new Date().toISOString(),
    };

    const payload = JSON.stringify(message);
    let sent = 0;
    let total = 0;

    for (const [projectName, clients] of this.connections) {
      for (const client of clients) {
        total++;
        if (client.readyState === WebSocket.OPEN) {
          client.send(payload);
          sent++;
        }
      }
    }

    this.logger.debug(`Broadcast '${type}' to ${sent}/${total} total clients`);
  }

  /**
   * Get the number of connections for a project
   */
  getConnectionCount(projectName?: string): number {
    if (projectName) {
      return this.connections.get(projectName)?.size ?? 0;
    }
    let total = 0;
    for (const clients of this.connections.values()) {
      total += clients.size;
    }
    return total;
  }

  /**
   * Get list of projects with active connections
   */
  getActiveProjects(): string[] {
    return Array.from(this.connections.keys());
  }
}
