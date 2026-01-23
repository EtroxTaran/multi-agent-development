import { Test, TestingModule } from "@nestjs/testing";
import { NotFoundException, BadRequestException } from "@nestjs/common";
import { WorkflowController } from "./workflow.controller";
import { WorkflowService } from "./workflow.service";
import { WorkflowStatus } from "../common/enums";
import {
  createWorkflowStatus,
  createWorkflowInProgress,
  createWorkflowHealth,
  createWorkflowStartResponse,
} from "../testing/factories";

describe("WorkflowController", () => {
  let controller: WorkflowController;
  let workflowService: jest.Mocked<WorkflowService>;

  const mockWorkflowService = {
    getStatus: jest.fn(),
    getHealth: jest.fn(),
    getGraph: jest.fn(),
    start: jest.fn(),
    resume: jest.fn(),
    pause: jest.fn(),
    rollback: jest.fn(),
    reset: jest.fn(),
  };

  beforeEach(async () => {
    jest.clearAllMocks();

    const module: TestingModule = await Test.createTestingModule({
      controllers: [WorkflowController],
      providers: [{ provide: WorkflowService, useValue: mockWorkflowService }],
    }).compile();

    controller = module.get<WorkflowController>(WorkflowController);
    workflowService = module.get(WorkflowService);
  });

  describe("initialization", () => {
    it("should be defined", () => {
      expect(controller).toBeDefined();
    });
  });

  describe("getStatus", () => {
    it("should return workflow status", async () => {
      const status = {
        mode: "langgraph",
        status: WorkflowStatus.IN_PROGRESS,
        project: "test-project",
        currentPhase: 2,
        phaseStatus: {},
      };
      workflowService.getStatus.mockResolvedValueOnce(status);

      const result = await controller.getStatus("test-project");

      expect(result).toEqual(status);
      expect(workflowService.getStatus).toHaveBeenCalledWith("test-project");
    });

    it("should throw NotFoundException when project not found", async () => {
      workflowService.getStatus.mockRejectedValueOnce(
        new NotFoundException("Project 'nonexistent' not found"),
      );

      await expect(controller.getStatus("nonexistent")).rejects.toThrow(
        NotFoundException,
      );
    });
  });

  describe("getHealth", () => {
    it("should return workflow health", async () => {
      const health = {
        status: "healthy",
        project: "test-project",
        agents: { claude: true, cursor: true, gemini: true },
        iterationCount: 0,
        langgraphEnabled: true,
        hasContext: true,
        totalCommits: 0,
      };
      workflowService.getHealth.mockResolvedValueOnce(health);

      const result = await controller.getHealth("test-project");

      expect(result).toEqual(health);
      expect(workflowService.getHealth).toHaveBeenCalledWith("test-project");
    });

    it("should throw NotFoundException when project not found", async () => {
      workflowService.getHealth.mockRejectedValueOnce(
        new NotFoundException("Project 'nonexistent' not found"),
      );

      await expect(controller.getHealth("nonexistent")).rejects.toThrow(
        NotFoundException,
      );
    });
  });

  describe("getGraph", () => {
    it("should return workflow graph", async () => {
      const graph = { nodes: [], edges: [] };
      workflowService.getGraph.mockResolvedValueOnce(graph);

      const result = await controller.getGraph("test-project");

      expect(result).toEqual(graph);
      expect(workflowService.getGraph).toHaveBeenCalledWith("test-project");
    });

    it("should throw NotFoundException when project not found", async () => {
      workflowService.getGraph.mockRejectedValueOnce(
        new NotFoundException("Project 'nonexistent' not found"),
      );

      await expect(controller.getGraph("nonexistent")).rejects.toThrow(
        NotFoundException,
      );
    });
  });

  describe("start", () => {
    it("should start workflow with default options", async () => {
      const response = {
        success: true,
        mode: "langgraph",
        paused: false,
        message: "Workflow started",
      };
      workflowService.start.mockResolvedValueOnce(response);

      const result = await controller.start("test-project", {
        startPhase: 1,
        endPhase: 5,
        skipValidation: false,
        autonomous: false,
      });

      expect(result).toEqual(response);
      expect(workflowService.start).toHaveBeenCalledWith("test-project", {
        startPhase: 1,
        endPhase: 5,
        skipValidation: false,
        autonomous: false,
      });
    });

    it("should start workflow with custom options", async () => {
      const response = { success: true, mode: "langgraph", paused: false };
      workflowService.start.mockResolvedValueOnce(response);

      await controller.start("test-project", {
        startPhase: 2,
        endPhase: 4,
        skipValidation: true,
        autonomous: true,
      });

      expect(workflowService.start).toHaveBeenCalledWith("test-project", {
        startPhase: 2,
        endPhase: 4,
        skipValidation: true,
        autonomous: true,
      });
    });

    it("should throw BadRequestException when prerequisites not met", async () => {
      workflowService.start.mockRejectedValueOnce(
        new BadRequestException("Prerequisites not met"),
      );

      await expect(
        controller.start("test", {
          startPhase: 1,
          endPhase: 5,
          skipValidation: false,
          autonomous: false,
        }),
      ).rejects.toThrow(BadRequestException);
    });

    it("should throw NotFoundException when project not found", async () => {
      workflowService.start.mockRejectedValueOnce(
        new NotFoundException("Project 'nonexistent' not found"),
      );

      await expect(
        controller.start("nonexistent", {
          startPhase: 1,
          endPhase: 5,
          skipValidation: false,
          autonomous: false,
        }),
      ).rejects.toThrow(NotFoundException);
    });
  });

  describe("resume", () => {
    it("should resume workflow without autonomous mode", async () => {
      const response = { success: true, mode: "langgraph", paused: false };
      workflowService.resume.mockResolvedValueOnce(response);

      const result = await controller.resume("test-project");

      expect(result).toEqual(response);
      expect(workflowService.resume).toHaveBeenCalledWith(
        "test-project",
        false,
      );
    });

    it("should resume workflow with autonomous mode", async () => {
      const response = { success: true, mode: "langgraph", paused: false };
      workflowService.resume.mockResolvedValueOnce(response);

      await controller.resume("test-project", true);

      expect(workflowService.resume).toHaveBeenCalledWith("test-project", true);
    });

    it("should throw NotFoundException when project not found", async () => {
      workflowService.resume.mockRejectedValueOnce(
        new NotFoundException("Project 'nonexistent' not found"),
      );

      await expect(controller.resume("nonexistent")).rejects.toThrow(
        NotFoundException,
      );
    });
  });

  describe("pause", () => {
    it("should request pause", async () => {
      const response = { message: "Pause requested" };
      workflowService.pause.mockResolvedValueOnce(response);

      const result = await controller.pause("test-project");

      expect(result).toEqual(response);
      expect(workflowService.pause).toHaveBeenCalledWith("test-project");
    });
  });

  describe("rollback", () => {
    it("should rollback to specified phase", async () => {
      const response = {
        success: true,
        rolledBackTo: "checkpoint_phase_2",
        currentPhase: 2,
        message: "Rolled back",
      };
      workflowService.rollback.mockResolvedValueOnce(response);

      const result = await controller.rollback("test-project", 2);

      expect(result).toEqual(response);
      expect(workflowService.rollback).toHaveBeenCalledWith("test-project", 2);
    });

    it("should throw BadRequestException for invalid phase", async () => {
      workflowService.rollback.mockRejectedValueOnce(
        new BadRequestException("Phase must be between 1 and 5"),
      );

      await expect(controller.rollback("test", 0)).rejects.toThrow(
        BadRequestException,
      );
    });

    it("should throw NotFoundException when project not found", async () => {
      workflowService.rollback.mockRejectedValueOnce(
        new NotFoundException("Project 'nonexistent' not found"),
      );

      await expect(controller.rollback("nonexistent", 2)).rejects.toThrow(
        NotFoundException,
      );
    });
  });

  describe("reset", () => {
    it("should reset workflow", async () => {
      const response = { message: "Workflow reset" };
      workflowService.reset.mockResolvedValueOnce(response);

      const result = await controller.reset("test-project");

      expect(result).toEqual(response);
      expect(workflowService.reset).toHaveBeenCalledWith("test-project");
    });

    it("should throw NotFoundException when project not found", async () => {
      workflowService.reset.mockRejectedValueOnce(
        new NotFoundException("Project 'nonexistent' not found"),
      );

      await expect(controller.reset("nonexistent")).rejects.toThrow(
        NotFoundException,
      );
    });
  });
});
