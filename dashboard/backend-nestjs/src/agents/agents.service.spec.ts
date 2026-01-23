import { Test, TestingModule } from "@nestjs/testing";
import { NotFoundException } from "@nestjs/common";
import { AgentsService } from "./agents.service";
import { OrchestratorClientService } from "../orchestrator-client/orchestrator-client.service";
import { AgentType } from "../common/enums";
import {
  createMockOrchestratorClient,
  MockResponses,
} from "../testing/mocks/orchestrator-client.mock";

describe("AgentsService", () => {
  let service: AgentsService;
  let orchestratorClient: jest.Mocked<OrchestratorClientService>;

  beforeEach(async () => {
    const mockClient = createMockOrchestratorClient();

    const module: TestingModule = await Test.createTestingModule({
      providers: [
        AgentsService,
        { provide: OrchestratorClientService, useValue: mockClient },
      ],
    }).compile();

    service = module.get<AgentsService>(AgentsService);
    orchestratorClient = module.get(OrchestratorClientService);
  });

  afterEach(() => {
    jest.clearAllMocks();
  });

  describe("getAgents", () => {
    it("should return all agent statuses", async () => {
      orchestratorClient.getAgents.mockResolvedValueOnce([
        { agent: "claude", available: true, total_invocations: 10 },
        { agent: "cursor", available: true, total_invocations: 5 },
        { agent: "gemini", available: false, total_invocations: 3 },
      ]);

      const result = await service.getAgents("test-project");

      expect(result.agents).toHaveLength(3);
      expect(result.agents[0].agent).toBe(AgentType.CLAUDE);
      expect(result.agents[2].available).toBe(false);
    });

    it("should map snake_case to camelCase", async () => {
      orchestratorClient.getAgents.mockResolvedValueOnce([
        {
          agent: "claude",
          available: true,
          last_invocation: "2024-01-01T00:00:00Z",
          total_invocations: 25,
          success_rate: 0.92,
          avg_duration_seconds: 45.5,
          total_cost_usd: 1.25,
        },
      ]);

      const result = await service.getAgents("test");

      expect(result.agents[0]).toEqual({
        agent: AgentType.CLAUDE,
        available: true,
        lastInvocation: "2024-01-01T00:00:00Z",
        totalInvocations: 25,
        successRate: 0.92,
        avgDurationSeconds: 45.5,
        totalCostUsd: 1.25,
      });
    });

    it("should throw NotFoundException when project not found", async () => {
      orchestratorClient.getAgents.mockRejectedValueOnce(
        new Error("not found"),
      );

      await expect(service.getAgents("nonexistent")).rejects.toThrow(
        NotFoundException,
      );
    });
  });

  describe("getAudit", () => {
    it("should return audit entries", async () => {
      orchestratorClient.getAudit.mockResolvedValueOnce(
        MockResponses.auditEntriesResponse,
      );

      const result = await service.getAudit("test", {});

      expect(result.entries).toHaveLength(1);
      expect(result.total).toBe(1);
    });

    it("should pass filter options", async () => {
      orchestratorClient.getAudit.mockResolvedValueOnce({
        entries: [],
        total: 0,
      });

      await service.getAudit("test", {
        agent: "claude",
        taskId: "T1",
        status: "success",
        sinceHours: 24,
        limit: 50,
      });

      expect(orchestratorClient.getAudit).toHaveBeenCalledWith("test", {
        agent: "claude",
        taskId: "T1",
        status: "success",
        sinceHours: 24,
        limit: 50,
      });
    });

    it("should throw NotFoundException when project not found", async () => {
      orchestratorClient.getAudit.mockRejectedValueOnce(new Error("not found"));

      await expect(service.getAudit("nonexistent", {})).rejects.toThrow(
        NotFoundException,
      );
    });
  });

  describe("getStatistics", () => {
    it("should return audit statistics", async () => {
      orchestratorClient.getAuditStatistics.mockResolvedValueOnce(
        MockResponses.auditStatisticsResponse,
      );

      const result = await service.getStatistics("test");

      expect(result.total).toBe(50);
      expect(result.successRate).toBe(0.9);
    });

    it("should pass time filter", async () => {
      orchestratorClient.getAuditStatistics.mockResolvedValueOnce(
        MockResponses.auditStatisticsResponse,
      );

      await service.getStatistics("test", 24);

      expect(orchestratorClient.getAuditStatistics).toHaveBeenCalledWith(
        "test",
        24,
      );
    });

    it("should throw NotFoundException when project not found", async () => {
      orchestratorClient.getAuditStatistics.mockRejectedValueOnce(
        new Error("not found"),
      );

      await expect(service.getStatistics("nonexistent")).rejects.toThrow(
        NotFoundException,
      );
    });
  });
});
