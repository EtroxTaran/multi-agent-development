import { Injectable, Logger } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { WebSocket } from 'ws';
import { WebsocketService } from './websocket.service';
import { WebSocketEventType } from '../common/enums';

@Injectable()
export class OrchestratorBridgeService {
  private readonly logger = new Logger(OrchestratorBridgeService.name);
  private connections: Map<string, WebSocket> = new Map();
  private baseUrl: string;

  constructor(
    private configService: ConfigService,
    private websocketService: WebsocketService,
  ) {
    const apiUrl = this.configService.get<string>(
      'ORCHESTRATOR_API_URL',
      'http://localhost:8090',
    );
    this.baseUrl = apiUrl.replace('http', 'ws');
  }

  connectToProject(projectName: string) {
    if (this.connections.has(projectName)) {
      return;
    }

    const url = `${this.baseUrl}/projects/${projectName}/events`;
    this.logger.log(`Connecting to Orchestrator events: ${url}`);

    try {
      const ws = new WebSocket(url);

      ws.on('open', () => {
        this.logger.log(`Connected to Orchestrator events for ${projectName}`);
      });

      ws.on('message', (data) => {
        try {
          const event = JSON.parse(data.toString());
          this.handleEvent(projectName, event);
        } catch (e) {
          this.logger.error(`Failed to parse event for ${projectName}: ${e}`);
        }
      });

      ws.on('close', () => {
        this.logger.log(`Disconnected from Orchestrator events for ${projectName}`);
        this.connections.delete(projectName);
        // Simple retry logic could be added here, but for now we rely on client re-joining
      });

      ws.on('error', (error) => {
        this.logger.error(`Orchestrator WebSocket error for ${projectName}: ${error}`);
      });

      this.connections.set(projectName, ws);
    } catch (e) {
      this.logger.error(`Failed to connect to Orchestrator: ${e}`);
    }
  }

  disconnectFromProject(projectName: string) {
    const ws = this.connections.get(projectName);
    if (ws) {
      ws.close();
      this.connections.delete(projectName);
    }
  }

  private handleEvent(projectName: string, event: any) {
    // Pass-through event to frontend
    // The orchestrator-api now emits events in the format expected by the frontend
    // { type: 'state_change' | 'action' | 'workflow_error' | ..., data: ... }
    
    if (event.type && event.data) {
        // Cast to any to allow flexible event types
        this.websocketService.broadcastToProject(projectName, event.type as any, event.data);
    }
  }
}
