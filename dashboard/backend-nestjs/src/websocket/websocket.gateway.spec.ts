import { Test, TestingModule } from "@nestjs/testing";
import { WebSocket, Server } from "ws";
import { WebsocketGateway } from "./websocket.gateway";
import { WebsocketService } from "./websocket.service";
import { OrchestratorBridgeService } from "./orchestrator-bridge.service";
import { WebSocketEventType } from "../common/enums";

// Mock WebSocket
const createMockWebSocket = (): jest.Mocked<WebSocket> =>
  ({
    readyState: WebSocket.OPEN,
    send: jest.fn(),
    close: jest.fn(),
    on: jest.fn(),
    once: jest.fn(),
    off: jest.fn(),
  }) as unknown as jest.Mocked<WebSocket>;

// Mock Server
const createMockServer = (): jest.Mocked<Server> =>
  ({
    clients: new Set(),
    on: jest.fn(),
    close: jest.fn(),
  }) as unknown as jest.Mocked<Server>;

describe("WebsocketGateway", () => {
  let gateway: WebsocketGateway;
  let websocketService: jest.Mocked<WebsocketService>;
  let orchestratorBridge: jest.Mocked<OrchestratorBridgeService>;

  const mockWebsocketService = {
    addConnection: jest.fn(),
    removeConnection: jest.fn(),
    getConnectionCount: jest.fn().mockReturnValue(0),
    broadcastToProject: jest.fn(),
    broadcastToAll: jest.fn(),
    getActiveProjects: jest.fn().mockReturnValue([]),
  };

  const mockOrchestratorBridge = {
    connectToProject: jest.fn(),
    disconnectFromProject: jest.fn(),
  };

  beforeEach(async () => {
    jest.clearAllMocks();

    const module: TestingModule = await Test.createTestingModule({
      providers: [
        WebsocketGateway,
        { provide: WebsocketService, useValue: mockWebsocketService },
        {
          provide: OrchestratorBridgeService,
          useValue: mockOrchestratorBridge,
        },
      ],
    }).compile();

    gateway = module.get<WebsocketGateway>(WebsocketGateway);
    websocketService = module.get(WebsocketService);
    orchestratorBridge = module.get(OrchestratorBridgeService);

    // Initialize the server
    gateway.server = createMockServer();
  });

  describe("initialization", () => {
    it("should be defined", () => {
      expect(gateway).toBeDefined();
    });
  });

  describe("lifecycle hooks", () => {
    describe("afterInit", () => {
      it("should log initialization", () => {
        const mockServer = createMockServer();

        // Should not throw
        expect(() => gateway.afterInit(mockServer)).not.toThrow();
      });
    });

    describe("handleConnection", () => {
      it("should initialize client metadata", () => {
        const mockClient = createMockWebSocket();

        gateway.handleConnection(mockClient);

        // Client should be tracked but not yet associated with a project
        // The metadata map is private, so we verify behavior through handleJoinProject
      });

      it("should handle multiple client connections", () => {
        const client1 = createMockWebSocket();
        const client2 = createMockWebSocket();

        expect(() => gateway.handleConnection(client1)).not.toThrow();
        expect(() => gateway.handleConnection(client2)).not.toThrow();
      });
    });

    describe("handleDisconnect", () => {
      it("should clean up client when not in a project", () => {
        const mockClient = createMockWebSocket();
        gateway.handleConnection(mockClient);

        gateway.handleDisconnect(mockClient);

        expect(websocketService.removeConnection).not.toHaveBeenCalled();
      });

      it("should remove connection when client was in a project", () => {
        const mockClient = createMockWebSocket();
        gateway.handleConnection(mockClient);
        gateway.handleJoinProject({ projectName: "test-project" }, mockClient);

        gateway.handleDisconnect(mockClient);

        expect(websocketService.removeConnection).toHaveBeenCalledWith(
          "test-project",
          mockClient,
        );
      });

      it("should disconnect from orchestrator when last client leaves", () => {
        const mockClient = createMockWebSocket();
        gateway.handleConnection(mockClient);
        gateway.handleJoinProject({ projectName: "test-project" }, mockClient);
        mockWebsocketService.getConnectionCount.mockReturnValueOnce(0);

        gateway.handleDisconnect(mockClient);

        expect(orchestratorBridge.disconnectFromProject).toHaveBeenCalledWith(
          "test-project",
        );
      });

      it("should not disconnect from orchestrator when other clients remain", () => {
        const mockClient = createMockWebSocket();
        gateway.handleConnection(mockClient);
        gateway.handleJoinProject({ projectName: "test-project" }, mockClient);
        mockWebsocketService.getConnectionCount.mockReturnValueOnce(1);

        gateway.handleDisconnect(mockClient);

        expect(orchestratorBridge.disconnectFromProject).not.toHaveBeenCalled();
      });
    });
  });

  describe("message handlers", () => {
    describe("handleJoinProject", () => {
      it("should join a project successfully", () => {
        const mockClient = createMockWebSocket();
        gateway.handleConnection(mockClient);

        const result = gateway.handleJoinProject(
          { projectName: "test-project" },
          mockClient,
        );

        expect(result).toEqual({
          event: "joined",
          data: { success: true, projectName: "test-project" },
        });
        expect(websocketService.addConnection).toHaveBeenCalledWith(
          "test-project",
          mockClient,
        );
        expect(orchestratorBridge.connectToProject).toHaveBeenCalledWith(
          "test-project",
        );
      });

      it("should leave previous project when joining a new one", () => {
        const mockClient = createMockWebSocket();
        gateway.handleConnection(mockClient);
        gateway.handleJoinProject({ projectName: "project-a" }, mockClient);

        // Reset mocks
        jest.clearAllMocks();
        mockWebsocketService.getConnectionCount.mockReturnValueOnce(0);

        gateway.handleJoinProject({ projectName: "project-b" }, mockClient);

        expect(websocketService.removeConnection).toHaveBeenCalledWith(
          "project-a",
          mockClient,
        );
        expect(orchestratorBridge.disconnectFromProject).toHaveBeenCalledWith(
          "project-a",
        );
        expect(websocketService.addConnection).toHaveBeenCalledWith(
          "project-b",
          mockClient,
        );
      });

      it("should not leave current project when re-joining same project", () => {
        const mockClient = createMockWebSocket();
        gateway.handleConnection(mockClient);
        gateway.handleJoinProject({ projectName: "test-project" }, mockClient);

        jest.clearAllMocks();

        gateway.handleJoinProject({ projectName: "test-project" }, mockClient);

        // Should not try to leave since it's the same project
        expect(websocketService.removeConnection).not.toHaveBeenCalled();
      });
    });

    describe("handleLeaveProject", () => {
      it("should leave project successfully", () => {
        const mockClient = createMockWebSocket();
        gateway.handleConnection(mockClient);
        gateway.handleJoinProject({ projectName: "test-project" }, mockClient);

        jest.clearAllMocks();
        mockWebsocketService.getConnectionCount.mockReturnValueOnce(0);

        const result = gateway.handleLeaveProject(mockClient);

        expect(result).toEqual({
          event: "left",
          data: { success: true },
        });
        expect(websocketService.removeConnection).toHaveBeenCalledWith(
          "test-project",
          mockClient,
        );
      });

      it("should disconnect from orchestrator when last client leaves", () => {
        const mockClient = createMockWebSocket();
        gateway.handleConnection(mockClient);
        gateway.handleJoinProject({ projectName: "test-project" }, mockClient);

        jest.clearAllMocks();
        mockWebsocketService.getConnectionCount.mockReturnValueOnce(0);

        gateway.handleLeaveProject(mockClient);

        expect(orchestratorBridge.disconnectFromProject).toHaveBeenCalledWith(
          "test-project",
        );
      });

      it("should handle leave when client is not in a project", () => {
        const mockClient = createMockWebSocket();
        gateway.handleConnection(mockClient);

        const result = gateway.handleLeaveProject(mockClient);

        expect(result).toEqual({
          event: "left",
          data: { success: true },
        });
        expect(websocketService.removeConnection).not.toHaveBeenCalled();
      });
    });

    describe("handlePing", () => {
      it("should return pong with timestamp", () => {
        const before = new Date().toISOString();
        const result = gateway.handlePing();
        const after = new Date().toISOString();

        expect(result.event).toBe("pong");
        expect(result.data.timestamp >= before).toBe(true);
        expect(result.data.timestamp <= after).toBe(true);
      });
    });
  });

  describe("broadcast methods", () => {
    describe("broadcastStateChange", () => {
      it("should broadcast state change to project", () => {
        const state = { phase: 2, status: "in_progress" };

        gateway.broadcastStateChange("test-project", state);

        expect(websocketService.broadcastToProject).toHaveBeenCalledWith(
          "test-project",
          WebSocketEventType.STATE_CHANGE,
          state,
        );
      });
    });

    describe("broadcastAction", () => {
      it("should broadcast action to project", () => {
        const action = { name: "planning", node: "plan_feature" };

        gateway.broadcastAction("test-project", action);

        expect(websocketService.broadcastToProject).toHaveBeenCalledWith(
          "test-project",
          WebSocketEventType.ACTION,
          action,
        );
      });
    });

    describe("broadcastEscalation", () => {
      it("should broadcast escalation to project", () => {
        const escalation = {
          type: "approval_required",
          message: "Please review the plan",
          options: ["approve", "reject"],
        };

        gateway.broadcastEscalation("test-project", escalation);

        expect(websocketService.broadcastToProject).toHaveBeenCalledWith(
          "test-project",
          WebSocketEventType.ESCALATION,
          escalation,
        );
      });
    });

    describe("broadcastWorkflowComplete", () => {
      it("should broadcast workflow completion to project", () => {
        const result = { summary: "Feature implemented successfully" };

        gateway.broadcastWorkflowComplete("test-project", result);

        expect(websocketService.broadcastToProject).toHaveBeenCalledWith(
          "test-project",
          WebSocketEventType.WORKFLOW_COMPLETE,
          result,
        );
      });
    });

    describe("broadcastWorkflowError", () => {
      it("should broadcast workflow error to project", () => {
        gateway.broadcastWorkflowError("test-project", "Task T1 failed");

        expect(websocketService.broadcastToProject).toHaveBeenCalledWith(
          "test-project",
          WebSocketEventType.WORKFLOW_ERROR,
          { error: "Task T1 failed" },
        );
      });
    });
  });
});
