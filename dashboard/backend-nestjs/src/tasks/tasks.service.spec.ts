import { Test, TestingModule } from "@nestjs/testing";
import { NotFoundException } from "@nestjs/common";
import { TasksService } from "./tasks.service";
import { OrchestratorClientService } from "../orchestrator-client/orchestrator-client.service";
import { TaskStatus } from "../common/enums";
import {
  createMockOrchestratorClient,
  MockResponses,
} from "../testing/mocks/orchestrator-client.mock";
import { createTask, createTaskListResponse } from "../testing/factories";

describe("TasksService", () => {
  let service: TasksService;
  let orchestratorClient: jest.Mocked<OrchestratorClientService>;

  beforeEach(async () => {
    const mockClient = createMockOrchestratorClient();

    const module: TestingModule = await Test.createTestingModule({
      providers: [
        TasksService,
        { provide: OrchestratorClientService, useValue: mockClient },
      ],
    }).compile();

    service = module.get<TasksService>(TasksService);
    orchestratorClient = module.get(OrchestratorClientService);
  });

  afterEach(() => {
    jest.clearAllMocks();
  });

  describe("getTasks", () => {
    it("should return task list with counts", async () => {
      orchestratorClient.getTasks.mockResolvedValueOnce(
        MockResponses.taskListResponse,
      );

      const result = await service.getTasks("test-project");

      expect(result.total).toBe(3);
      expect(result.completed).toBe(1);
      expect(result.inProgress).toBe(1);
      expect(result.pending).toBe(1);
    });

    it("should map task fields correctly", async () => {
      orchestratorClient.getTasks.mockResolvedValueOnce({
        tasks: [
          {
            id: "T1",
            title: "Test Task",
            description: "A test",
            status: "in_progress",
            priority: 1,
            dependencies: ["T0"],
            files_to_create: ["src/test.ts"],
            files_to_modify: ["src/index.ts"],
            acceptance_criteria: ["Must work"],
            complexity_score: 3.5,
            created_at: "2024-01-01T00:00:00Z",
            started_at: "2024-01-01T01:00:00Z",
          },
        ],
      });

      const result = await service.getTasks("test");

      expect(result.tasks[0]).toEqual({
        id: "T1",
        title: "Test Task",
        description: "A test",
        status: TaskStatus.IN_PROGRESS,
        priority: 1,
        dependencies: ["T0"],
        filesToCreate: ["src/test.ts"],
        filesToModify: ["src/index.ts"],
        acceptanceCriteria: ["Must work"],
        complexityScore: 3.5,
        createdAt: "2024-01-01T00:00:00Z",
        startedAt: "2024-01-01T01:00:00Z",
        completedAt: undefined,
        error: undefined,
      });
    });

    it("should return empty list when no tasks", async () => {
      orchestratorClient.getTasks.mockResolvedValueOnce({ tasks: [] });

      const result = await service.getTasks("test");

      expect(result.tasks).toEqual([]);
      expect(result.total).toBe(0);
    });

    it("should throw NotFoundException when project not found", async () => {
      orchestratorClient.getTasks.mockRejectedValueOnce(new Error("not found"));

      await expect(service.getTasks("nonexistent")).rejects.toThrow(
        NotFoundException,
      );
    });
  });

  describe("getTask", () => {
    it("should return task details", async () => {
      orchestratorClient.getTask.mockResolvedValueOnce(
        MockResponses.taskDetailResponse,
      );

      const result = await service.getTask("test-project", "T1");

      expect(result.id).toBe("T1");
      expect(result.title).toBe("Implement user authentication");
    });

    it("should throw NotFoundException when task not found", async () => {
      orchestratorClient.getTask.mockRejectedValueOnce(new Error("not found"));

      await expect(service.getTask("test", "T99")).rejects.toThrow(
        NotFoundException,
      );
    });
  });

  describe("getHistory", () => {
    it("should return task history", async () => {
      orchestratorClient.getTaskHistory.mockResolvedValueOnce(
        MockResponses.taskHistoryResponse,
      );

      const result = await service.getHistory("test", "T1");

      expect(result.entries).toHaveLength(2);
      expect(result.total).toBe(2);
    });

    it("should pass limit parameter", async () => {
      orchestratorClient.getTaskHistory.mockResolvedValueOnce({
        entries: [],
        total: 0,
      });

      await service.getHistory("test", "T1", 50);

      expect(orchestratorClient.getTaskHistory).toHaveBeenCalledWith(
        "test",
        "T1",
        50,
      );
    });

    it("should use default limit of 100", async () => {
      orchestratorClient.getTaskHistory.mockResolvedValueOnce({
        entries: [],
        total: 0,
      });

      await service.getHistory("test", "T1");

      expect(orchestratorClient.getTaskHistory).toHaveBeenCalledWith(
        "test",
        "T1",
        100,
      );
    });

    it("should throw NotFoundException when task not found", async () => {
      orchestratorClient.getTaskHistory.mockRejectedValueOnce(
        new Error("not found"),
      );

      await expect(service.getHistory("test", "T99")).rejects.toThrow(
        NotFoundException,
      );
    });
  });
});
