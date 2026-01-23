import { Injectable, Logger } from "@nestjs/common";
import { ConfigService } from "@nestjs/config";
import { WebsocketService } from "./websocket.service";
import { OrchestratorClientService } from "../orchestrator-client/orchestrator-client.service";
import { WebSocketEventType } from "../common/enums";

@Injectable()
export class OrchestratorBridgeService {
  private readonly logger = new Logger(OrchestratorBridgeService.name);
  private subscribedProjects: Set<string> = new Set();

  constructor(
    private configService: ConfigService,
    private websocketService: WebsocketService,
    private orchestratorClient: OrchestratorClientService,
  ) {
    // Listen to all events from the client service
    this.orchestratorClient.on("event", (projectName, event) => {
      this.handleEvent(projectName, event);
    });
  }

  connectToProject(projectName: string) {
    if (this.subscribedProjects.has(projectName)) {
      return;
    }
    this.logger.log(`Subscribed to Orchestrator events for ${projectName}`);
    this.subscribedProjects.add(projectName);
  }

  disconnectFromProject(projectName: string) {
    if (this.subscribedProjects.has(projectName)) {
      this.logger.log(
        `Unsubscribed from Orchestrator events for ${projectName}`,
      );
      this.subscribedProjects.delete(projectName);
    }
  }

  private handleEvent(projectName: string, event: any) {
    if (!this.subscribedProjects.has(projectName)) return;

    // Pass-through event to frontend
    if (event.type && event.data) {
      this.websocketService.broadcastToProject(
        projectName,
        event.type as any, // Cast to match enum or string
        event.data,
      );
    }
  }
}
