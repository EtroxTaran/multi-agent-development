import {
  WebSocketGateway,
  WebSocketServer,
  SubscribeMessage,
  OnGatewayInit,
  OnGatewayConnection,
  OnGatewayDisconnect,
  MessageBody,
  ConnectedSocket,
} from "@nestjs/websockets";
import { Logger } from "@nestjs/common";
import { Server, WebSocket } from "ws";
import { WebsocketService } from "./websocket.service";
import { OrchestratorBridgeService } from "./orchestrator-bridge.service";
import { WebSocketEventType } from "../common/enums";

interface JoinProjectMessage {
  projectName: string;
}

interface ClientMetadata {
  projectName?: string;
}

@WebSocketGateway({
  path: "/api/ws",
  cors: {
    origin: "*",
    credentials: true,
  },
})
export class WebsocketGateway
  implements OnGatewayInit, OnGatewayConnection, OnGatewayDisconnect
{
  private readonly logger = new Logger(WebsocketGateway.name);
  private clientMetadata: Map<WebSocket, ClientMetadata> = new Map();

  @WebSocketServer()
  server!: Server;

  constructor(
    private readonly websocketService: WebsocketService,
    private readonly orchestratorBridge: OrchestratorBridgeService,
  ) {}

  afterInit(server: Server): void {
    this.logger.log("WebSocket Gateway initialized");
  }

  handleConnection(client: WebSocket): void {
    this.clientMetadata.set(client, {});
    this.logger.log("New WebSocket client connected");
  }

  handleDisconnect(client: WebSocket): void {
    const metadata = this.clientMetadata.get(client);
    if (metadata?.projectName) {
      this.websocketService.removeConnection(metadata.projectName, client);

      // If no more clients for this project, disconnect from orchestrator
      if (
        this.websocketService.getConnectionCount(metadata.projectName) === 0
      ) {
        this.orchestratorBridge.disconnectFromProject(metadata.projectName);
      }
    }
    this.clientMetadata.delete(client);
    this.logger.log("WebSocket client disconnected");
  }

  @SubscribeMessage("join")
  handleJoinProject(
    @MessageBody() data: JoinProjectMessage,
    @ConnectedSocket() client: WebSocket,
  ): { event: string; data: { success: boolean; projectName: string } } {
    const { projectName } = data;

    // Remove from previous project if any
    const metadata = this.clientMetadata.get(client);
    if (metadata?.projectName && metadata.projectName !== projectName) {
      this.websocketService.removeConnection(metadata.projectName, client);
      if (
        this.websocketService.getConnectionCount(metadata.projectName) === 0
      ) {
        this.orchestratorBridge.disconnectFromProject(metadata.projectName);
      }
    }

    // Join new project
    this.websocketService.addConnection(projectName, client);
    this.clientMetadata.set(client, { projectName });

    // Connect to orchestrator events for this project
    this.orchestratorBridge.connectToProject(projectName);

    return {
      event: "joined",
      data: { success: true, projectName },
    };
  }

  @SubscribeMessage("leave")
  handleLeaveProject(@ConnectedSocket() client: WebSocket): {
    event: string;
    data: { success: boolean };
  } {
    const metadata = this.clientMetadata.get(client);
    if (metadata?.projectName) {
      this.websocketService.removeConnection(metadata.projectName, client);

      if (
        this.websocketService.getConnectionCount(metadata.projectName) === 0
      ) {
        this.orchestratorBridge.disconnectFromProject(metadata.projectName);
      }

      this.clientMetadata.set(client, {});
    }

    return {
      event: "left",
      data: { success: true },
    };
  }

  @SubscribeMessage("ping")
  handlePing(): { event: string; data: { timestamp: string } } {
    return {
      event: "pong",
      data: { timestamp: new Date().toISOString() },
    };
  }

  /**
   * Broadcast workflow state change to a project
   */
  broadcastStateChange(
    projectName: string,
    state: Record<string, unknown>,
  ): void {
    this.websocketService.broadcastToProject(
      projectName,
      WebSocketEventType.STATE_CHANGE,
      state,
    );
  }

  /**
   * Broadcast action event to a project
   */
  broadcastAction(projectName: string, action: Record<string, unknown>): void {
    this.websocketService.broadcastToProject(
      projectName,
      WebSocketEventType.ACTION,
      action,
    );
  }

  /**
   * Broadcast escalation to a project
   */
  broadcastEscalation(
    projectName: string,
    escalation: Record<string, unknown>,
  ): void {
    this.websocketService.broadcastToProject(
      projectName,
      WebSocketEventType.ESCALATION,
      escalation,
    );
  }

  /**
   * Broadcast workflow completion to a project
   */
  broadcastWorkflowComplete(
    projectName: string,
    result: Record<string, unknown>,
  ): void {
    this.websocketService.broadcastToProject(
      projectName,
      WebSocketEventType.WORKFLOW_COMPLETE,
      result,
    );
  }

  /**
   * Broadcast workflow error to a project
   */
  broadcastWorkflowError(projectName: string, error: string): void {
    this.websocketService.broadcastToProject(
      projectName,
      WebSocketEventType.WORKFLOW_ERROR,
      { error },
    );
  }
}
