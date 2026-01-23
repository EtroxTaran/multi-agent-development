import { Test, TestingModule } from "@nestjs/testing";
import { WebSocket } from "ws";
import { WebsocketService } from "./websocket.service";
import { WebSocketEventType } from "../common/enums";

// Mock WebSocket
const createMockWebSocket = (
  readyState: number = WebSocket.OPEN,
): jest.Mocked<WebSocket> =>
  ({
    readyState,
    send: jest.fn(),
    close: jest.fn(),
    on: jest.fn(),
    once: jest.fn(),
    off: jest.fn(),
    emit: jest.fn(),
    addEventListener: jest.fn(),
    removeEventListener: jest.fn(),
  }) as unknown as jest.Mocked<WebSocket>;

describe("WebsocketService", () => {
  let service: WebsocketService;

  beforeEach(async () => {
    const module: TestingModule = await Test.createTestingModule({
      providers: [WebsocketService],
    }).compile();

    service = module.get<WebsocketService>(WebsocketService);
  });

  afterEach(() => {
    jest.clearAllMocks();
  });

  describe("initialization", () => {
    it("should be defined", () => {
      expect(service).toBeDefined();
    });

    it("should start with no connections", () => {
      expect(service.getConnectionCount()).toBe(0);
      expect(service.getActiveProjects()).toEqual([]);
    });
  });

  describe("addConnection", () => {
    it("should add a connection for a project", () => {
      const mockClient = createMockWebSocket();

      service.addConnection("test-project", mockClient);

      expect(service.getConnectionCount("test-project")).toBe(1);
      expect(service.getActiveProjects()).toContain("test-project");
    });

    it("should add multiple connections for the same project", () => {
      const client1 = createMockWebSocket();
      const client2 = createMockWebSocket();

      service.addConnection("test-project", client1);
      service.addConnection("test-project", client2);

      expect(service.getConnectionCount("test-project")).toBe(2);
    });

    it("should add connections for different projects", () => {
      const client1 = createMockWebSocket();
      const client2 = createMockWebSocket();

      service.addConnection("project-a", client1);
      service.addConnection("project-b", client2);

      expect(service.getConnectionCount("project-a")).toBe(1);
      expect(service.getConnectionCount("project-b")).toBe(1);
      expect(service.getConnectionCount()).toBe(2);
      expect(service.getActiveProjects()).toEqual(["project-a", "project-b"]);
    });

    it("should not duplicate the same client", () => {
      const mockClient = createMockWebSocket();

      service.addConnection("test-project", mockClient);
      service.addConnection("test-project", mockClient);

      // Set uses unique values, so duplicates are ignored
      expect(service.getConnectionCount("test-project")).toBe(1);
    });
  });

  describe("removeConnection", () => {
    it("should remove a connection from a project", () => {
      const mockClient = createMockWebSocket();
      service.addConnection("test-project", mockClient);

      service.removeConnection("test-project", mockClient);

      expect(service.getConnectionCount("test-project")).toBe(0);
    });

    it("should remove project from active list when last client disconnects", () => {
      const mockClient = createMockWebSocket();
      service.addConnection("test-project", mockClient);

      service.removeConnection("test-project", mockClient);

      expect(service.getActiveProjects()).not.toContain("test-project");
    });

    it("should keep project active when other clients remain", () => {
      const client1 = createMockWebSocket();
      const client2 = createMockWebSocket();
      service.addConnection("test-project", client1);
      service.addConnection("test-project", client2);

      service.removeConnection("test-project", client1);

      expect(service.getConnectionCount("test-project")).toBe(1);
      expect(service.getActiveProjects()).toContain("test-project");
    });

    it("should handle removing connection from non-existent project", () => {
      const mockClient = createMockWebSocket();

      // Should not throw
      expect(() =>
        service.removeConnection("nonexistent", mockClient),
      ).not.toThrow();
    });

    it("should handle removing non-existent client from project", () => {
      const client1 = createMockWebSocket();
      const client2 = createMockWebSocket();
      service.addConnection("test-project", client1);

      // Should not throw
      expect(() =>
        service.removeConnection("test-project", client2),
      ).not.toThrow();
      expect(service.getConnectionCount("test-project")).toBe(1);
    });
  });

  describe("broadcastToProject", () => {
    it("should broadcast message to all clients in a project", () => {
      const client1 = createMockWebSocket();
      const client2 = createMockWebSocket();
      service.addConnection("test-project", client1);
      service.addConnection("test-project", client2);

      service.broadcastToProject(
        "test-project",
        WebSocketEventType.STATE_CHANGE,
        { phase: 2, status: "in_progress" },
      );

      expect(client1.send).toHaveBeenCalledTimes(1);
      expect(client2.send).toHaveBeenCalledTimes(1);

      // Verify message format
      const sentPayload = JSON.parse(client1.send.mock.calls[0][0] as string);
      expect(sentPayload).toHaveProperty(
        "type",
        WebSocketEventType.STATE_CHANGE,
      );
      expect(sentPayload).toHaveProperty("data", {
        phase: 2,
        status: "in_progress",
      });
      expect(sentPayload).toHaveProperty("timestamp");
    });

    it("should not broadcast to clients in other projects", () => {
      const clientA = createMockWebSocket();
      const clientB = createMockWebSocket();
      service.addConnection("project-a", clientA);
      service.addConnection("project-b", clientB);

      service.broadcastToProject("project-a", WebSocketEventType.ACTION, {
        action: "test",
      });

      expect(clientA.send).toHaveBeenCalledTimes(1);
      expect(clientB.send).not.toHaveBeenCalled();
    });

    it("should skip clients that are not OPEN", () => {
      const openClient = createMockWebSocket(WebSocket.OPEN);
      const closingClient = createMockWebSocket(WebSocket.CLOSING);
      const closedClient = createMockWebSocket(WebSocket.CLOSED);

      service.addConnection("test-project", openClient);
      service.addConnection("test-project", closingClient);
      service.addConnection("test-project", closedClient);

      service.broadcastToProject(
        "test-project",
        WebSocketEventType.STATE_CHANGE,
        {},
      );

      expect(openClient.send).toHaveBeenCalledTimes(1);
      expect(closingClient.send).not.toHaveBeenCalled();
      expect(closedClient.send).not.toHaveBeenCalled();
    });

    it("should do nothing when project has no connections", () => {
      // Should not throw
      expect(() =>
        service.broadcastToProject(
          "nonexistent",
          WebSocketEventType.STATE_CHANGE,
          {},
        ),
      ).not.toThrow();
    });

    it("should include timestamp in message", () => {
      const mockClient = createMockWebSocket();
      service.addConnection("test-project", mockClient);

      const before = new Date().toISOString();
      service.broadcastToProject(
        "test-project",
        WebSocketEventType.STATE_CHANGE,
        {},
      );
      const after = new Date().toISOString();

      const sentPayload = JSON.parse(
        mockClient.send.mock.calls[0][0] as string,
      );
      expect(sentPayload.timestamp >= before).toBe(true);
      expect(sentPayload.timestamp <= after).toBe(true);
    });
  });

  describe("broadcastToAll", () => {
    it("should broadcast to all clients across all projects", () => {
      const clientA = createMockWebSocket();
      const clientB = createMockWebSocket();
      const clientC = createMockWebSocket();
      service.addConnection("project-a", clientA);
      service.addConnection("project-b", clientB);
      service.addConnection("project-b", clientC);

      service.broadcastToAll(WebSocketEventType.WORKFLOW_ERROR, {
        error: "System maintenance",
      });

      expect(clientA.send).toHaveBeenCalledTimes(1);
      expect(clientB.send).toHaveBeenCalledTimes(1);
      expect(clientC.send).toHaveBeenCalledTimes(1);
    });

    it("should skip clients that are not OPEN", () => {
      const openClient = createMockWebSocket(WebSocket.OPEN);
      const closedClient = createMockWebSocket(WebSocket.CLOSED);
      service.addConnection("project-a", openClient);
      service.addConnection("project-b", closedClient);

      service.broadcastToAll(WebSocketEventType.STATE_CHANGE, {});

      expect(openClient.send).toHaveBeenCalledTimes(1);
      expect(closedClient.send).not.toHaveBeenCalled();
    });

    it("should do nothing when no connections exist", () => {
      // Should not throw
      expect(() =>
        service.broadcastToAll(WebSocketEventType.STATE_CHANGE, {}),
      ).not.toThrow();
    });
  });

  describe("getConnectionCount", () => {
    it("should return total connections when no project specified", () => {
      const client1 = createMockWebSocket();
      const client2 = createMockWebSocket();
      const client3 = createMockWebSocket();
      service.addConnection("project-a", client1);
      service.addConnection("project-b", client2);
      service.addConnection("project-b", client3);

      expect(service.getConnectionCount()).toBe(3);
    });

    it("should return project-specific count when project specified", () => {
      const client1 = createMockWebSocket();
      const client2 = createMockWebSocket();
      service.addConnection("project-a", client1);
      service.addConnection("project-b", client2);

      expect(service.getConnectionCount("project-a")).toBe(1);
      expect(service.getConnectionCount("project-b")).toBe(1);
    });

    it("should return 0 for non-existent project", () => {
      expect(service.getConnectionCount("nonexistent")).toBe(0);
    });
  });

  describe("getActiveProjects", () => {
    it("should return all projects with active connections", () => {
      const client1 = createMockWebSocket();
      const client2 = createMockWebSocket();
      service.addConnection("project-a", client1);
      service.addConnection("project-b", client2);

      const projects = service.getActiveProjects();

      expect(projects).toContain("project-a");
      expect(projects).toContain("project-b");
      expect(projects).toHaveLength(2);
    });

    it("should return empty array when no connections", () => {
      expect(service.getActiveProjects()).toEqual([]);
    });
  });
});
