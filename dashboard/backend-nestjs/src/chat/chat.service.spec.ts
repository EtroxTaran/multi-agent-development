import { Test, TestingModule } from "@nestjs/testing";
import { ChatService } from "./chat.service";
import { OrchestratorClientService } from "../orchestrator-client/orchestrator-client.service";
import {
  createMockOrchestratorClient,
  MockResponses,
} from "../testing/mocks/orchestrator-client.mock";

describe("ChatService", () => {
  let service: ChatService;
  let orchestratorClient: jest.Mocked<OrchestratorClientService>;

  beforeEach(async () => {
    const mockClient = createMockOrchestratorClient();

    const module: TestingModule = await Test.createTestingModule({
      providers: [
        ChatService,
        { provide: OrchestratorClientService, useValue: mockClient },
      ],
    }).compile();

    service = module.get<ChatService>(ChatService);
    orchestratorClient = module.get(OrchestratorClientService);
  });

  afterEach(() => {
    jest.clearAllMocks();
  });

  describe("chat", () => {
    it("should send chat message", async () => {
      orchestratorClient.chat.mockResolvedValueOnce(MockResponses.chatResponse);

      const result = await service.chat({ message: "Hello" });

      expect(result.message).toBeDefined();
      expect(orchestratorClient.chat).toHaveBeenCalledWith(
        "Hello",
        undefined,
        undefined,
      );
    });

    it("should send chat message with project context", async () => {
      orchestratorClient.chat.mockResolvedValueOnce(MockResponses.chatResponse);

      await service.chat({
        message: "What is the status?",
        projectName: "test-project",
      });

      expect(orchestratorClient.chat).toHaveBeenCalledWith(
        "What is the status?",
        "test-project",
        undefined,
      );
    });

    it("should send chat message with additional context", async () => {
      orchestratorClient.chat.mockResolvedValueOnce(MockResponses.chatResponse);

      await service.chat({
        message: "Help",
        projectName: "test",
        context: { phase: 2 },
      });

      expect(orchestratorClient.chat).toHaveBeenCalledWith("Help", "test", {
        phase: 2,
      });
    });

    it("should re-throw errors", async () => {
      orchestratorClient.chat.mockRejectedValueOnce(
        new Error("Connection failed"),
      );

      await expect(service.chat({ message: "Hello" })).rejects.toThrow(
        "Connection failed",
      );
    });
  });

  describe("executeCommand", () => {
    it("should execute command", async () => {
      orchestratorClient.executeCommand.mockResolvedValueOnce(
        MockResponses.commandSuccessResponse,
      );

      const result = await service.executeCommand({
        command: "/status",
        args: [],
      });

      expect(result.success).toBe(true);
      expect(orchestratorClient.executeCommand).toHaveBeenCalledWith(
        "/status",
        [],
        undefined,
      );
    });

    it("should execute command with arguments", async () => {
      orchestratorClient.executeCommand.mockResolvedValueOnce(
        MockResponses.commandSuccessResponse,
      );

      await service.executeCommand({
        command: "/orchestrate",
        args: ["--project", "test"],
      });

      expect(orchestratorClient.executeCommand).toHaveBeenCalledWith(
        "/orchestrate",
        ["--project", "test"],
        undefined,
      );
    });

    it("should execute command with project context", async () => {
      orchestratorClient.executeCommand.mockResolvedValueOnce(
        MockResponses.commandSuccessResponse,
      );

      await service.executeCommand({
        command: "/start",
        args: [],
        projectName: "test-project",
      });

      expect(orchestratorClient.executeCommand).toHaveBeenCalledWith(
        "/start",
        [],
        "test-project",
      );
    });

    it("should re-throw errors", async () => {
      orchestratorClient.executeCommand.mockRejectedValueOnce(
        new Error("Command failed"),
      );

      await expect(
        service.executeCommand({ command: "/invalid", args: [] }),
      ).rejects.toThrow("Command failed");
    });
  });
});
