import { Test, TestingModule } from "@nestjs/testing";
import { ChatController } from "./chat.controller";
import { ChatService } from "./chat.service";

describe("ChatController", () => {
  let controller: ChatController;
  let chatService: jest.Mocked<ChatService>;

  const mockChatService = {
    chat: jest.fn(),
    executeCommand: jest.fn(),
  };

  beforeEach(async () => {
    jest.clearAllMocks();

    const module: TestingModule = await Test.createTestingModule({
      controllers: [ChatController],
      providers: [{ provide: ChatService, useValue: mockChatService }],
    }).compile();

    controller = module.get<ChatController>(ChatController);
    chatService = module.get(ChatService);
  });

  describe("chat", () => {
    it("should send chat message", async () => {
      const response = { message: "Response", streaming: false };
      chatService.chat.mockResolvedValueOnce(response);

      const result = await controller.chat({ message: "Hello" });

      expect(result).toEqual(response);
      expect(chatService.chat).toHaveBeenCalledWith({ message: "Hello" });
    });

    it("should send chat message with context", async () => {
      const response = { message: "Response", streaming: false };
      chatService.chat.mockResolvedValueOnce(response);

      await controller.chat({
        message: "Help",
        projectName: "test",
        context: { data: "value" },
      });

      expect(chatService.chat).toHaveBeenCalledWith({
        message: "Help",
        projectName: "test",
        context: { data: "value" },
      });
    });
  });

  describe("executeCommand", () => {
    it("should execute command", async () => {
      const response = { success: true, output: "Done" };
      chatService.executeCommand.mockResolvedValueOnce(response);

      const result = await controller.executeCommand({
        command: "/status",
        args: [],
      });

      expect(result).toEqual(response);
      expect(chatService.executeCommand).toHaveBeenCalledWith({
        command: "/status",
        args: [],
      });
    });

    it("should execute command with arguments", async () => {
      const response = { success: true };
      chatService.executeCommand.mockResolvedValueOnce(response);

      await controller.executeCommand({
        command: "/orchestrate",
        args: ["--project", "test"],
        projectName: "test",
      });

      expect(chatService.executeCommand).toHaveBeenCalledWith({
        command: "/orchestrate",
        args: ["--project", "test"],
        projectName: "test",
      });
    });
  });
});
