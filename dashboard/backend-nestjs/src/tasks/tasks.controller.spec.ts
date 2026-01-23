import { Test, TestingModule } from "@nestjs/testing";
import { NotFoundException } from "@nestjs/common";
import { TasksController } from "./tasks.controller";
import { TasksService } from "./tasks.service";
import { TaskStatus } from "../common/enums";
import { createTask, createTaskListResponse } from "../testing/factories";

describe("TasksController", () => {
  let controller: TasksController;
  let tasksService: jest.Mocked<TasksService>;

  const mockTasksService = {
    getTasks: jest.fn(),
    getTask: jest.fn(),
    getHistory: jest.fn(),
  };

  beforeEach(async () => {
    jest.clearAllMocks();

    const module: TestingModule = await Test.createTestingModule({
      controllers: [TasksController],
      providers: [{ provide: TasksService, useValue: mockTasksService }],
    }).compile();

    controller = module.get<TasksController>(TasksController);
    tasksService = module.get(TasksService);
  });

  describe("getTasks", () => {
    it("should return task list", async () => {
      const task = createTask({
        id: "T1",
        title: "Test",
        status: TaskStatus.PENDING,
      });
      const tasks = createTaskListResponse([task]);
      tasksService.getTasks.mockResolvedValueOnce(tasks);

      const result = await controller.getTasks("test-project");

      expect(result).toEqual(tasks);
      expect(tasksService.getTasks).toHaveBeenCalledWith("test-project");
    });
  });

  describe("getTask", () => {
    it("should return task details", async () => {
      const task = createTask({
        id: "T1",
        title: "Test",
        status: TaskStatus.PENDING,
      });
      tasksService.getTask.mockResolvedValueOnce(task);

      const result = await controller.getTask("test", "T1");

      expect(result).toEqual(task);
      expect(tasksService.getTask).toHaveBeenCalledWith("test", "T1");
    });
  });

  describe("getTaskHistory", () => {
    it("should return task history with default limit", async () => {
      const history = { entries: [], total: 0 };
      tasksService.getHistory.mockResolvedValueOnce(history);

      const result = await controller.getTaskHistory("test", "T1");

      expect(result).toEqual(history);
      expect(tasksService.getHistory).toHaveBeenCalledWith(
        "test",
        "T1",
        undefined,
      );
    });

    it("should return task history with custom limit", async () => {
      const history = { entries: [], total: 0 };
      tasksService.getHistory.mockResolvedValueOnce(history);

      await controller.getTaskHistory("test", "T1", 50);

      expect(tasksService.getHistory).toHaveBeenCalledWith("test", "T1", 50);
    });
  });
});
