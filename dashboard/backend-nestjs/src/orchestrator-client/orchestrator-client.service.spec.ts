import { Test, TestingModule } from "@nestjs/testing";
import { ConfigService } from "@nestjs/config";
import { OrchestratorClientService } from "./orchestrator-client.service";
import { MockResponses } from "../testing/mocks/orchestrator-client.mock";

// Mock global fetch
const mockFetch = jest.fn();
global.fetch = mockFetch;

describe("OrchestratorClientService", () => {
  let service: OrchestratorClientService;
  let configService: ConfigService;

  const mockConfigService = {
    get: jest.fn().mockReturnValue("http://localhost:8090"),
  };

  beforeEach(async () => {
    jest.clearAllMocks();
    mockFetch.mockReset();

    const module: TestingModule = await Test.createTestingModule({
      providers: [
        OrchestratorClientService,
        { provide: ConfigService, useValue: mockConfigService },
      ],
    }).compile();

    service = module.get<OrchestratorClientService>(OrchestratorClientService);
    configService = module.get<ConfigService>(ConfigService);
  });

  // Helper to create mock response
  const createMockResponse = (data: unknown, ok = true, status = 200) => ({
    ok,
    status,
    statusText: ok ? "OK" : "Error",
    json: jest.fn().mockResolvedValue(data),
  });

  describe("initialization", () => {
    it("should be defined", () => {
      expect(service).toBeDefined();
    });

    it("should use default URL when ORCHESTRATOR_API_URL is not set", () => {
      expect(configService.get).toHaveBeenCalledWith(
        "ORCHESTRATOR_API_URL",
        "http://localhost:8090",
      );
    });

    it("should call checkHealth on module init", async () => {
      mockFetch.mockResolvedValueOnce(
        createMockResponse(MockResponses.healthyResponse),
      );

      await service.onModuleInit();

      expect(mockFetch).toHaveBeenCalledWith(
        "http://localhost:8090/health",
        expect.objectContaining({ method: "GET" }),
      );
    });
  });

  describe("checkHealth", () => {
    it("should return true when API is healthy", async () => {
      mockFetch.mockResolvedValueOnce(
        createMockResponse(MockResponses.healthyResponse),
      );

      const result = await service.checkHealth();

      expect(result).toBe(true);
    });

    it("should return false when API is unhealthy", async () => {
      mockFetch.mockResolvedValueOnce(
        createMockResponse(MockResponses.unhealthyResponse),
      );

      const result = await service.checkHealth();

      expect(result).toBe(false);
    });

    it("should return false when API connection fails", async () => {
      mockFetch.mockRejectedValueOnce(new Error("Connection refused"));

      const result = await service.checkHealth();

      expect(result).toBe(false);
    });
  });

  describe("Projects", () => {
    describe("listProjects", () => {
      it("should return list of projects", async () => {
        mockFetch.mockResolvedValueOnce(
          createMockResponse(MockResponses.projectListResponse),
        );

        const result = await service.listProjects();

        expect(result).toEqual(MockResponses.projectListResponse);
        expect(mockFetch).toHaveBeenCalledWith(
          "http://localhost:8090/projects",
          expect.objectContaining({ method: "GET" }),
        );
      });

      it("should return empty array when no projects exist", async () => {
        mockFetch.mockResolvedValueOnce(createMockResponse([]));

        const result = await service.listProjects();

        expect(result).toEqual([]);
      });
    });

    describe("getProject", () => {
      it("should return project details", async () => {
        mockFetch.mockResolvedValueOnce(
          createMockResponse(MockResponses.projectStatusResponse),
        );

        const result = await service.getProject("test-project");

        expect(result).toEqual(MockResponses.projectStatusResponse);
        expect(mockFetch).toHaveBeenCalledWith(
          "http://localhost:8090/projects/test-project",
          expect.objectContaining({ method: "GET" }),
        );
      });

      it("should handle special characters in project name", async () => {
        mockFetch.mockResolvedValueOnce(
          createMockResponse(MockResponses.projectStatusResponse),
        );

        await service.getProject("my-project_v1");

        expect(mockFetch).toHaveBeenCalledWith(
          "http://localhost:8090/projects/my-project_v1",
          expect.any(Object),
        );
      });

      it("should throw error when project not found", async () => {
        mockFetch.mockResolvedValueOnce(
          createMockResponse(MockResponses.projectNotFoundError, false, 404),
        );

        await expect(service.getProject("nonexistent")).rejects.toThrow();
      });
    });

    describe("initProject", () => {
      it("should initialize project successfully", async () => {
        mockFetch.mockResolvedValueOnce(
          createMockResponse(MockResponses.initProjectSuccessResponse),
        );

        const result = await service.initProject("new-project");

        expect(result).toEqual(MockResponses.initProjectSuccessResponse);
        expect(mockFetch).toHaveBeenCalledWith(
          "http://localhost:8090/projects/new-project/init",
          expect.objectContaining({ method: "POST" }),
        );
      });

      it("should handle project already exists error", async () => {
        mockFetch.mockResolvedValueOnce(
          createMockResponse(
            MockResponses.initProjectErrorResponse,
            false,
            400,
          ),
        );

        await expect(service.initProject("existing-project")).rejects.toThrow();
      });
    });

    describe("deleteProject", () => {
      it("should delete project without removing source", async () => {
        mockFetch.mockResolvedValueOnce(
          createMockResponse(MockResponses.deleteProjectResponse),
        );

        const result = await service.deleteProject("test-project");

        expect(result).toEqual(MockResponses.deleteProjectResponse);
        expect(mockFetch).toHaveBeenCalledWith(
          "http://localhost:8090/projects/test-project",
          expect.objectContaining({ method: "DELETE" }),
        );
      });

      it("should delete project with source removal", async () => {
        mockFetch.mockResolvedValueOnce(
          createMockResponse(MockResponses.deleteProjectResponse),
        );

        await service.deleteProject("test-project", true);

        expect(mockFetch).toHaveBeenCalledWith(
          "http://localhost:8090/projects/test-project?remove_source=true",
          expect.objectContaining({ method: "DELETE" }),
        );
      });
    });
  });

  describe("Workflow", () => {
    describe("getWorkflowStatus", () => {
      it("should return workflow status - not started", async () => {
        mockFetch.mockResolvedValueOnce(
          createMockResponse(MockResponses.workflowNotStartedResponse),
        );

        const result = await service.getWorkflowStatus("test-project");

        expect(result).toEqual(MockResponses.workflowNotStartedResponse);
      });

      it("should return workflow status - in progress", async () => {
        mockFetch.mockResolvedValueOnce(
          createMockResponse(MockResponses.workflowInProgressResponse),
        );

        const result = await service.getWorkflowStatus("test-project");

        expect(result).toEqual(MockResponses.workflowInProgressResponse);
      });

      it("should return workflow status - paused with interrupt", async () => {
        mockFetch.mockResolvedValueOnce(
          createMockResponse(MockResponses.workflowPausedResponse),
        );

        const result = await service.getWorkflowStatus("test-project");

        expect(result).toHaveProperty("pending_interrupt");
      });

      it("should return workflow status - completed", async () => {
        mockFetch.mockResolvedValueOnce(
          createMockResponse(MockResponses.workflowCompletedResponse),
        );

        const result = await service.getWorkflowStatus("test-project");

        expect(result).toEqual(MockResponses.workflowCompletedResponse);
      });
    });

    describe("getWorkflowHealth", () => {
      it("should return healthy status", async () => {
        mockFetch.mockResolvedValueOnce(
          createMockResponse(MockResponses.workflowHealthyResponse),
        );

        const result = await service.getWorkflowHealth("test-project");

        expect(result).toHaveProperty("status", "healthy");
        expect(result).toHaveProperty("agents");
      });

      it("should return degraded status when agent unavailable", async () => {
        mockFetch.mockResolvedValueOnce(
          createMockResponse(MockResponses.workflowDegradedResponse),
        );

        const result = await service.getWorkflowHealth("test-project");

        expect(result).toHaveProperty("status", "degraded");
      });
    });

    describe("getWorkflowGraph", () => {
      it("should return workflow graph definition", async () => {
        mockFetch.mockResolvedValueOnce(
          createMockResponse(MockResponses.workflowGraphResponse),
        );

        const result = await service.getWorkflowGraph("test-project");

        expect(result).toHaveProperty("nodes");
        expect(result).toHaveProperty("edges");
      });
    });

    describe("startWorkflow", () => {
      it("should start workflow with default options", async () => {
        mockFetch.mockResolvedValueOnce(
          createMockResponse(MockResponses.startWorkflowSuccessResponse),
        );

        const result = await service.startWorkflow("test-project");

        expect(result).toEqual(MockResponses.startWorkflowSuccessResponse);
        expect(mockFetch).toHaveBeenCalledWith(
          "http://localhost:8090/projects/test-project/workflow/start",
          expect.objectContaining({
            method: "POST",
            body: JSON.stringify({
              start_phase: 1,
              end_phase: 5,
              skip_validation: false,
              autonomous: false,
            }),
          }),
        );
      });

      it("should start workflow with custom phase range", async () => {
        mockFetch.mockResolvedValueOnce(
          createMockResponse(MockResponses.startWorkflowSuccessResponse),
        );

        await service.startWorkflow("test-project", {
          startPhase: 2,
          endPhase: 4,
        });

        expect(mockFetch).toHaveBeenCalledWith(
          expect.any(String),
          expect.objectContaining({
            body: JSON.stringify({
              start_phase: 2,
              end_phase: 4,
              skip_validation: false,
              autonomous: false,
            }),
          }),
        );
      });

      it("should start workflow in autonomous mode", async () => {
        mockFetch.mockResolvedValueOnce(
          createMockResponse(MockResponses.startWorkflowSuccessResponse),
        );

        await service.startWorkflow("test-project", { autonomous: true });

        expect(mockFetch).toHaveBeenCalledWith(
          expect.any(String),
          expect.objectContaining({
            body: expect.stringContaining('"autonomous":true'),
          }),
        );
      });

      it("should start workflow with skip validation", async () => {
        mockFetch.mockResolvedValueOnce(
          createMockResponse(MockResponses.startWorkflowSuccessResponse),
        );

        await service.startWorkflow("test-project", { skipValidation: true });

        expect(mockFetch).toHaveBeenCalledWith(
          expect.any(String),
          expect.objectContaining({
            body: expect.stringContaining('"skip_validation":true'),
          }),
        );
      });

      it("should handle workflow start with pause", async () => {
        mockFetch.mockResolvedValueOnce(
          createMockResponse(MockResponses.startWorkflowPausedResponse),
        );

        const result = await service.startWorkflow("test-project");

        expect(result).toHaveProperty("paused", true);
      });
    });

    describe("resumeWorkflow", () => {
      it("should resume workflow", async () => {
        mockFetch.mockResolvedValueOnce(createMockResponse({ success: true }));

        const result = await service.resumeWorkflow("test-project");

        expect(mockFetch).toHaveBeenCalledWith(
          "http://localhost:8090/projects/test-project/workflow/resume?autonomous=false",
          expect.objectContaining({ method: "POST" }),
        );
      });

      it("should resume workflow in autonomous mode", async () => {
        mockFetch.mockResolvedValueOnce(createMockResponse({ success: true }));

        await service.resumeWorkflow("test-project", true);

        expect(mockFetch).toHaveBeenCalledWith(
          "http://localhost:8090/projects/test-project/workflow/resume?autonomous=true",
          expect.any(Object),
        );
      });
    });

    describe("rollbackWorkflow", () => {
      it("should rollback to specified phase", async () => {
        mockFetch.mockResolvedValueOnce(
          createMockResponse(MockResponses.rollbackSuccessResponse),
        );

        const result = await service.rollbackWorkflow("test-project", 2);

        expect(result).toEqual(MockResponses.rollbackSuccessResponse);
        expect(mockFetch).toHaveBeenCalledWith(
          "http://localhost:8090/projects/test-project/workflow/rollback/2",
          expect.objectContaining({ method: "POST" }),
        );
      });

      it("should handle invalid phase error", async () => {
        mockFetch.mockResolvedValueOnce(
          createMockResponse(MockResponses.invalidPhaseError, false, 400),
        );

        await expect(
          service.rollbackWorkflow("test-project", 6),
        ).rejects.toThrow();
      });
    });

    describe("resetWorkflow", () => {
      it("should reset workflow", async () => {
        mockFetch.mockResolvedValueOnce(createMockResponse({ success: true }));

        const result = await service.resetWorkflow("test-project");

        expect(mockFetch).toHaveBeenCalledWith(
          "http://localhost:8090/projects/test-project/workflow/reset",
          expect.objectContaining({ method: "POST" }),
        );
      });
    });
  });

  describe("Tasks", () => {
    describe("getTasks", () => {
      it("should return task list with counts", async () => {
        mockFetch.mockResolvedValueOnce(
          createMockResponse(MockResponses.taskListResponse),
        );

        const result = await service.getTasks("test-project");

        expect(result).toEqual(MockResponses.taskListResponse);
        expect(mockFetch).toHaveBeenCalledWith(
          "http://localhost:8090/projects/test-project/tasks",
          expect.objectContaining({ method: "GET" }),
        );
      });

      it("should return empty task list", async () => {
        mockFetch.mockResolvedValueOnce(
          createMockResponse({ tasks: [], total: 0 }),
        );

        const result = await service.getTasks("test-project");

        expect(result).toHaveProperty("tasks", []);
      });
    });

    describe("getTask", () => {
      it("should return task details", async () => {
        mockFetch.mockResolvedValueOnce(
          createMockResponse(MockResponses.taskDetailResponse),
        );

        const result = await service.getTask("test-project", "T1");

        expect(result).toEqual(MockResponses.taskDetailResponse);
        expect(mockFetch).toHaveBeenCalledWith(
          "http://localhost:8090/projects/test-project/tasks/T1",
          expect.any(Object),
        );
      });
    });

    describe("getTaskHistory", () => {
      it("should return task history with default limit", async () => {
        mockFetch.mockResolvedValueOnce(
          createMockResponse(MockResponses.taskHistoryResponse),
        );

        const result = await service.getTaskHistory("test-project", "T1");

        expect(result).toEqual(MockResponses.taskHistoryResponse);
        expect(mockFetch).toHaveBeenCalledWith(
          "http://localhost:8090/projects/test-project/tasks/T1/history?limit=100",
          expect.any(Object),
        );
      });

      it("should return task history with custom limit", async () => {
        mockFetch.mockResolvedValueOnce(
          createMockResponse(MockResponses.taskHistoryResponse),
        );

        await service.getTaskHistory("test-project", "T1", 50);

        expect(mockFetch).toHaveBeenCalledWith(
          "http://localhost:8090/projects/test-project/tasks/T1/history?limit=50",
          expect.any(Object),
        );
      });
    });
  });

  describe("Budget", () => {
    describe("getBudget", () => {
      it("should return budget status", async () => {
        mockFetch.mockResolvedValueOnce(
          createMockResponse(MockResponses.budgetStatusResponse),
        );

        const result = await service.getBudget("test-project");

        expect(result).toEqual(MockResponses.budgetStatusResponse);
        expect(mockFetch).toHaveBeenCalledWith(
          "http://localhost:8090/projects/test-project/budget",
          expect.any(Object),
        );
      });
    });

    describe("getBudgetReport", () => {
      it("should return budget report with task spending", async () => {
        mockFetch.mockResolvedValueOnce(
          createMockResponse(MockResponses.budgetReportResponse),
        );

        const result = await service.getBudgetReport("test-project");

        expect(result).toEqual(MockResponses.budgetReportResponse);
        expect(mockFetch).toHaveBeenCalledWith(
          "http://localhost:8090/projects/test-project/budget/report",
          expect.any(Object),
        );
      });
    });
  });

  describe("Agents & Audit", () => {
    describe("getAgents", () => {
      it("should return all agent statuses", async () => {
        mockFetch.mockResolvedValueOnce(
          createMockResponse(MockResponses.agentsResponse),
        );

        const result = await service.getAgents("test-project");

        expect(result).toEqual(MockResponses.agentsResponse);
        expect(mockFetch).toHaveBeenCalledWith(
          "http://localhost:8090/projects/test-project/agents",
          expect.any(Object),
        );
      });
    });

    describe("getAudit", () => {
      it("should return audit entries without filters", async () => {
        mockFetch.mockResolvedValueOnce(
          createMockResponse(MockResponses.auditEntriesResponse),
        );

        const result = await service.getAudit("test-project", {});

        expect(result).toEqual(MockResponses.auditEntriesResponse);
        expect(mockFetch).toHaveBeenCalledWith(
          "http://localhost:8090/projects/test-project/audit?",
          expect.any(Object),
        );
      });

      it("should return audit entries with agent filter", async () => {
        mockFetch.mockResolvedValueOnce(
          createMockResponse(MockResponses.auditEntriesResponse),
        );

        await service.getAudit("test-project", { agent: "claude" });

        expect(mockFetch).toHaveBeenCalledWith(
          "http://localhost:8090/projects/test-project/audit?agent=claude",
          expect.any(Object),
        );
      });

      it("should return audit entries with multiple filters", async () => {
        mockFetch.mockResolvedValueOnce(
          createMockResponse(MockResponses.auditEntriesResponse),
        );

        await service.getAudit("test-project", {
          agent: "claude",
          taskId: "T1",
          status: "success",
          sinceHours: 24,
          limit: 50,
        });

        expect(mockFetch).toHaveBeenCalledWith(
          expect.stringContaining("agent=claude"),
          expect.any(Object),
        );
        expect(mockFetch).toHaveBeenCalledWith(
          expect.stringContaining("task_id=T1"),
          expect.any(Object),
        );
        expect(mockFetch).toHaveBeenCalledWith(
          expect.stringContaining("status=success"),
          expect.any(Object),
        );
        expect(mockFetch).toHaveBeenCalledWith(
          expect.stringContaining("since_hours=24"),
          expect.any(Object),
        );
        expect(mockFetch).toHaveBeenCalledWith(
          expect.stringContaining("limit=50"),
          expect.any(Object),
        );
      });
    });

    describe("getAuditStatistics", () => {
      it("should return audit statistics without time filter", async () => {
        mockFetch.mockResolvedValueOnce(
          createMockResponse(MockResponses.auditStatisticsResponse),
        );

        const result = await service.getAuditStatistics("test-project");

        expect(result).toEqual(MockResponses.auditStatisticsResponse);
        expect(mockFetch).toHaveBeenCalledWith(
          "http://localhost:8090/projects/test-project/audit/statistics",
          expect.any(Object),
        );
      });

      it("should return audit statistics with time filter", async () => {
        mockFetch.mockResolvedValueOnce(
          createMockResponse(MockResponses.auditStatisticsResponse),
        );

        await service.getAuditStatistics("test-project", 24);

        expect(mockFetch).toHaveBeenCalledWith(
          "http://localhost:8090/projects/test-project/audit/statistics?since_hours=24",
          expect.any(Object),
        );
      });
    });
  });

  describe("Chat", () => {
    describe("chat", () => {
      it("should send chat message", async () => {
        mockFetch.mockResolvedValueOnce(
          createMockResponse(MockResponses.chatResponse),
        );

        const result = await service.chat("Hello");

        expect(result).toEqual(MockResponses.chatResponse);
        expect(mockFetch).toHaveBeenCalledWith(
          "http://localhost:8090/chat",
          expect.objectContaining({
            method: "POST",
            body: JSON.stringify({
              message: "Hello",
              project_name: undefined,
              context: undefined,
            }),
          }),
        );
      });

      it("should send chat message with project context", async () => {
        mockFetch.mockResolvedValueOnce(
          createMockResponse(MockResponses.chatResponse),
        );

        await service.chat("What is the status?", "test-project");

        expect(mockFetch).toHaveBeenCalledWith(
          "http://localhost:8090/chat",
          expect.objectContaining({
            body: JSON.stringify({
              message: "What is the status?",
              project_name: "test-project",
              context: undefined,
            }),
          }),
        );
      });

      it("should send chat message with additional context", async () => {
        mockFetch.mockResolvedValueOnce(
          createMockResponse(MockResponses.chatResponse),
        );

        await service.chat("Help me", "test-project", { phase: 2 });

        expect(mockFetch).toHaveBeenCalledWith(
          "http://localhost:8090/chat",
          expect.objectContaining({
            body: JSON.stringify({
              message: "Help me",
              project_name: "test-project",
              context: { phase: 2 },
            }),
          }),
        );
      });
    });

    describe("executeCommand", () => {
      it("should execute command", async () => {
        mockFetch.mockResolvedValueOnce(
          createMockResponse(MockResponses.commandSuccessResponse),
        );

        const result = await service.executeCommand("/status", []);

        expect(result).toEqual(MockResponses.commandSuccessResponse);
        expect(mockFetch).toHaveBeenCalledWith(
          "http://localhost:8090/chat/command",
          expect.objectContaining({
            method: "POST",
            body: JSON.stringify({
              command: "/status",
              args: [],
              project_name: undefined,
            }),
          }),
        );
      });

      it("should execute command with arguments", async () => {
        mockFetch.mockResolvedValueOnce(
          createMockResponse(MockResponses.commandSuccessResponse),
        );

        await service.executeCommand("/orchestrate", ["--project", "test"]);

        expect(mockFetch).toHaveBeenCalledWith(
          "http://localhost:8090/chat/command",
          expect.objectContaining({
            body: JSON.stringify({
              command: "/orchestrate",
              args: ["--project", "test"],
              project_name: undefined,
            }),
          }),
        );
      });

      it("should execute command with project context", async () => {
        mockFetch.mockResolvedValueOnce(
          createMockResponse(MockResponses.commandSuccessResponse),
        );

        await service.executeCommand("/start", [], "test-project");

        expect(mockFetch).toHaveBeenCalledWith(
          "http://localhost:8090/chat/command",
          expect.objectContaining({
            body: JSON.stringify({
              command: "/start",
              args: [],
              project_name: "test-project",
            }),
          }),
        );
      });

      it("should handle command error", async () => {
        mockFetch.mockResolvedValueOnce(
          createMockResponse(MockResponses.commandErrorResponse, false, 400),
        );

        await expect(service.executeCommand("/invalid", [])).rejects.toThrow();
      });
    });
  });

  describe("Error Handling", () => {
    it("should throw error on non-OK response", async () => {
      mockFetch.mockResolvedValueOnce(
        createMockResponse({ detail: "Not found" }, false, 404),
      );

      await expect(service.getProject("nonexistent")).rejects.toThrow(
        "Not found",
      );
    });

    it("should throw error with status text when no detail provided", async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 500,
        statusText: "Internal Server Error",
        json: jest.fn().mockRejectedValue(new Error("Invalid JSON")),
      });

      await expect(service.listProjects()).rejects.toThrow(
        "HTTP 500: Internal Server Error",
      );
    });

    it("should handle timeout", async () => {
      jest.useFakeTimers();

      const abortError = new Error("AbortError");
      abortError.name = "AbortError";

      mockFetch.mockImplementationOnce(
        () =>
          new Promise((_, reject) => {
            setTimeout(() => reject(abortError), 35000);
          }),
      );

      const promise = service.checkHealth();

      jest.advanceTimersByTime(31000);

      await expect(promise).rejects.toThrow();

      jest.useRealTimers();
    });
  });
});
