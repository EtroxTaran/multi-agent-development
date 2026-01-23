import { Test, TestingModule } from "@nestjs/testing";
import { NotFoundException, BadRequestException } from "@nestjs/common";
import { WorkflowService } from "./workflow.service";
import { OrchestratorClientService } from "../orchestrator-client/orchestrator-client.service";
import { WorkflowStatus } from "../common/enums";
import {
  createMockOrchestratorClient,
  MockResponses,
} from "../testing/mocks/orchestrator-client.mock";
import {
  createWorkflowStatus,
  createWorkflowInProgress,
  createWorkflowPaused,
  createWorkflowCompleted,
  createWorkflowHealth,
  createWorkflowStartResponse,
} from "../testing/factories";

describe("WorkflowService", () => {
  let service: WorkflowService;
  let orchestratorClient: jest.Mocked<OrchestratorClientService>;

  beforeEach(async () => {
    const mockClient = createMockOrchestratorClient();

    const module: TestingModule = await Test.createTestingModule({
      providers: [
        WorkflowService,
        { provide: OrchestratorClientService, useValue: mockClient },
      ],
    }).compile();

    service = module.get<WorkflowService>(WorkflowService);
    orchestratorClient = module.get(OrchestratorClientService);
  });

  afterEach(() => {
    jest.clearAllMocks();
  });

  describe("initialization", () => {
    it("should be defined", () => {
      expect(service).toBeDefined();
    });
  });

  describe("getStatus", () => {
    it("should return workflow status - not started", async () => {
      orchestratorClient.getWorkflowStatus.mockResolvedValueOnce(
        MockResponses.workflowNotStartedResponse,
      );

      const result = await service.getStatus("test-project");

      expect(result.status).toBe(WorkflowStatus.NOT_STARTED);
      expect(result.mode).toBe("langgraph");
    });

    it("should return workflow status - in progress", async () => {
      orchestratorClient.getWorkflowStatus.mockResolvedValueOnce(
        MockResponses.workflowInProgressResponse,
      );

      const result = await service.getStatus("test-project");

      expect(result.status).toBe(WorkflowStatus.IN_PROGRESS);
      expect(result.currentPhase).toBe(2);
    });

    it("should return workflow status - paused with pending interrupt", async () => {
      orchestratorClient.getWorkflowStatus.mockResolvedValueOnce(
        MockResponses.workflowPausedResponse,
      );

      const result = await service.getStatus("test-project");

      expect(result.status).toBe(WorkflowStatus.PAUSED);
      expect(result.pendingInterrupt).toBeDefined();
    });

    it("should return workflow status - completed", async () => {
      orchestratorClient.getWorkflowStatus.mockResolvedValueOnce(
        MockResponses.workflowCompletedResponse,
      );

      const result = await service.getStatus("test-project");

      expect(result.status).toBe(WorkflowStatus.COMPLETED);
      expect(result.currentPhase).toBe(5);
    });

    it("should map snake_case to camelCase", async () => {
      orchestratorClient.getWorkflowStatus.mockResolvedValueOnce({
        mode: "langgraph",
        status: "in_progress",
        project: "test",
        current_phase: 3,
        phase_status: { "1": "completed", "2": "completed" },
        pending_interrupt: null,
        message: "Running",
      });

      const result = await service.getStatus("test");

      expect(result.currentPhase).toBe(3);
      expect(result.phaseStatus).toEqual({
        "1": "completed",
        "2": "completed",
      });
    });

    it("should use default values for missing fields", async () => {
      orchestratorClient.getWorkflowStatus.mockResolvedValueOnce({});

      const result = await service.getStatus("test");

      expect(result.mode).toBe("langgraph");
      expect(result.status).toBe(WorkflowStatus.NOT_STARTED);
      expect(result.phaseStatus).toEqual({});
    });

    it("should throw NotFoundException when project not found", async () => {
      orchestratorClient.getWorkflowStatus.mockRejectedValueOnce(
        new Error("HTTP 404: Not Found"),
      );

      await expect(service.getStatus("nonexistent")).rejects.toThrow(
        NotFoundException,
      );
    });

    it("should re-throw other errors", async () => {
      orchestratorClient.getWorkflowStatus.mockRejectedValueOnce(
        new Error("Connection refused"),
      );

      await expect(service.getStatus("test")).rejects.toThrow(
        "Connection refused",
      );
    });
  });

  describe("getHealth", () => {
    it("should return healthy status", async () => {
      orchestratorClient.getWorkflowHealth.mockResolvedValueOnce(
        MockResponses.workflowHealthyResponse,
      );

      const result = await service.getHealth("test-project");

      expect(result.status).toBe("healthy");
      expect(result.agents).toEqual({
        claude: true,
        cursor: true,
        gemini: true,
      });
    });

    it("should return degraded status", async () => {
      orchestratorClient.getWorkflowHealth.mockResolvedValueOnce(
        MockResponses.workflowDegradedResponse,
      );

      const result = await service.getHealth("test-project");

      expect(result.status).toBe("degraded");
      expect(result.agents.cursor).toBe(false);
    });

    it("should map snake_case to camelCase", async () => {
      orchestratorClient.getWorkflowHealth.mockResolvedValueOnce({
        status: "healthy",
        project: "test",
        current_phase: 2,
        phase_status: "in_progress",
        iteration_count: 5,
        last_updated: "2024-01-01T12:00:00Z",
        agents: {},
        langgraph_enabled: true,
        has_context: true,
        total_commits: 3,
      });

      const result = await service.getHealth("test");

      expect(result.currentPhase).toBe(2);
      expect(result.phaseStatus).toBe("in_progress");
      expect(result.iterationCount).toBe(5);
      expect(result.lastUpdated).toBe("2024-01-01T12:00:00Z");
      expect(result.langgraphEnabled).toBe(true);
      expect(result.hasContext).toBe(true);
      expect(result.totalCommits).toBe(3);
    });

    it("should use default values for missing fields", async () => {
      orchestratorClient.getWorkflowHealth.mockResolvedValueOnce({});

      const result = await service.getHealth("test");

      expect(result.status).toBe("unknown");
      expect(result.iterationCount).toBe(0);
      expect(result.agents).toEqual({});
      expect(result.langgraphEnabled).toBe(false);
      expect(result.hasContext).toBe(false);
      expect(result.totalCommits).toBe(0);
    });

    it("should throw NotFoundException when project not found", async () => {
      orchestratorClient.getWorkflowHealth.mockRejectedValueOnce(
        new Error("Project not found"),
      );

      await expect(service.getHealth("nonexistent")).rejects.toThrow(
        NotFoundException,
      );
    });
  });

  describe("getGraph", () => {
    it("should return workflow graph", async () => {
      orchestratorClient.getWorkflowGraph.mockResolvedValueOnce(
        MockResponses.workflowGraphResponse,
      );

      const result = await service.getGraph("test-project");

      expect(result).toHaveProperty("nodes");
      expect(result).toHaveProperty("edges");
    });

    it("should throw NotFoundException when project not found", async () => {
      orchestratorClient.getWorkflowGraph.mockRejectedValueOnce(
        new Error("HTTP 404"),
      );

      await expect(service.getGraph("nonexistent")).rejects.toThrow(
        NotFoundException,
      );
    });
  });

  describe("start", () => {
    it("should start workflow with default options", async () => {
      orchestratorClient.startWorkflow.mockResolvedValueOnce(
        MockResponses.startWorkflowSuccessResponse,
      );

      const result = await service.start("test-project", {
        startPhase: 1,
        endPhase: 5,
        skipValidation: false,
        autonomous: false,
      });

      expect(result.success).toBe(true);
      expect(result.mode).toBe("langgraph");
      expect(orchestratorClient.startWorkflow).toHaveBeenCalledWith(
        "test-project",
        {
          startPhase: 1,
          endPhase: 5,
          skipValidation: false,
          autonomous: false,
        },
      );
    });

    it("should start workflow with custom phase range", async () => {
      orchestratorClient.startWorkflow.mockResolvedValueOnce(
        MockResponses.startWorkflowSuccessResponse,
      );

      await service.start("test-project", {
        startPhase: 2,
        endPhase: 4,
        skipValidation: false,
        autonomous: false,
      });

      expect(orchestratorClient.startWorkflow).toHaveBeenCalledWith(
        "test-project",
        expect.objectContaining({
          startPhase: 2,
          endPhase: 4,
        }),
      );
    });

    it("should start workflow in autonomous mode", async () => {
      orchestratorClient.startWorkflow.mockResolvedValueOnce(
        MockResponses.startWorkflowSuccessResponse,
      );

      await service.start("test-project", {
        startPhase: 1,
        endPhase: 5,
        skipValidation: false,
        autonomous: true,
      });

      expect(orchestratorClient.startWorkflow).toHaveBeenCalledWith(
        "test-project",
        expect.objectContaining({ autonomous: true }),
      );
    });

    it("should return paused response when workflow pauses", async () => {
      orchestratorClient.startWorkflow.mockResolvedValueOnce(
        MockResponses.startWorkflowPausedResponse,
      );

      const result = await service.start("test-project", {
        startPhase: 1,
        endPhase: 5,
        skipValidation: false,
        autonomous: false,
      });

      expect(result.paused).toBe(true);
    });

    it("should throw NotFoundException when project not found", async () => {
      orchestratorClient.startWorkflow.mockRejectedValueOnce(
        new Error("Project not found"),
      );

      await expect(
        service.start("nonexistent", {
          startPhase: 1,
          endPhase: 5,
          skipValidation: false,
          autonomous: false,
        }),
      ).rejects.toThrow(NotFoundException);
    });

    it("should throw BadRequestException when prerequisites not met", async () => {
      orchestratorClient.startWorkflow.mockRejectedValueOnce(
        new Error("Prerequisites not met: PRODUCT.md is required"),
      );

      await expect(
        service.start("test", {
          startPhase: 1,
          endPhase: 5,
          skipValidation: false,
          autonomous: false,
        }),
      ).rejects.toThrow(BadRequestException);
    });

    it("should map response correctly", async () => {
      orchestratorClient.startWorkflow.mockResolvedValueOnce({
        success: true,
        mode: "langgraph",
        paused: false,
        message: "Started",
        results: { task: "T1" },
      });

      const result = await service.start("test", {
        startPhase: 1,
        endPhase: 5,
        skipValidation: false,
        autonomous: false,
      });

      expect(result).toEqual({
        success: true,
        mode: "langgraph",
        paused: false,
        message: "Started",
        error: undefined,
        results: { task: "T1" },
      });
    });
  });

  describe("resume", () => {
    it("should resume workflow", async () => {
      orchestratorClient.resumeWorkflow.mockResolvedValueOnce({
        success: true,
        mode: "langgraph",
      });

      const result = await service.resume("test-project", false);

      expect(result.success).toBe(true);
      expect(orchestratorClient.resumeWorkflow).toHaveBeenCalledWith(
        "test-project",
        false,
      );
    });

    it("should resume workflow in autonomous mode", async () => {
      orchestratorClient.resumeWorkflow.mockResolvedValueOnce({
        success: true,
      });

      await service.resume("test-project", true);

      expect(orchestratorClient.resumeWorkflow).toHaveBeenCalledWith(
        "test-project",
        true,
      );
    });

    it("should throw NotFoundException when project not found", async () => {
      orchestratorClient.resumeWorkflow.mockRejectedValueOnce(
        new Error("not found"),
      );

      await expect(service.resume("nonexistent", false)).rejects.toThrow(
        NotFoundException,
      );
    });
  });

  describe("pause", () => {
    it("should return pause message", async () => {
      const result = await service.pause("test-project");

      expect(result.message).toContain("Pause requested");
    });
  });

  describe("rollback", () => {
    it("should rollback to specified phase", async () => {
      orchestratorClient.rollbackWorkflow.mockResolvedValueOnce(
        MockResponses.rollbackSuccessResponse,
      );

      const result = await service.rollback("test-project", 2);

      expect(result.success).toBe(true);
      expect(orchestratorClient.rollbackWorkflow).toHaveBeenCalledWith(
        "test-project",
        2,
      );
    });

    it("should map response correctly", async () => {
      orchestratorClient.rollbackWorkflow.mockResolvedValueOnce({
        success: true,
        rolled_back_to: "checkpoint_phase_2",
        current_phase: 2,
        message: "Rolled back",
      });

      const result = await service.rollback("test", 2);

      expect(result).toEqual({
        success: true,
        rolledBackTo: "checkpoint_phase_2",
        currentPhase: 2,
        message: "Rolled back",
        error: undefined,
      });
    });

    it("should throw BadRequestException for invalid phase < 1", async () => {
      await expect(service.rollback("test", 0)).rejects.toThrow(
        BadRequestException,
      );
    });

    it("should throw BadRequestException for invalid phase > 5", async () => {
      await expect(service.rollback("test", 6)).rejects.toThrow(
        BadRequestException,
      );
    });

    it("should throw NotFoundException when project not found", async () => {
      orchestratorClient.rollbackWorkflow.mockRejectedValueOnce(
        new Error("not found"),
      );

      await expect(service.rollback("nonexistent", 2)).rejects.toThrow(
        NotFoundException,
      );
    });

    it("should throw BadRequestException on rollback failure", async () => {
      orchestratorClient.rollbackWorkflow.mockRejectedValueOnce(
        new Error("Cannot rollback to future phase"),
      );

      await expect(service.rollback("test", 2)).rejects.toThrow(
        BadRequestException,
      );
    });
  });

  describe("reset", () => {
    it("should reset workflow", async () => {
      orchestratorClient.resetWorkflow.mockResolvedValueOnce({
        message: "Workflow reset successfully",
      });

      const result = await service.reset("test-project");

      expect(result.message).toBe("Workflow reset successfully");
    });

    it("should use default message when not provided", async () => {
      orchestratorClient.resetWorkflow.mockResolvedValueOnce({});

      const result = await service.reset("test");

      expect(result.message).toBe("Workflow reset");
    });

    it("should throw NotFoundException when project not found", async () => {
      orchestratorClient.resetWorkflow.mockRejectedValueOnce(
        new Error("not found"),
      );

      await expect(service.reset("nonexistent")).rejects.toThrow(
        NotFoundException,
      );
    });
  });
});
