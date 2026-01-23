import { Test, TestingModule } from "@nestjs/testing";
import { NotFoundException } from "@nestjs/common";
import { BudgetService } from "./budget.service";
import { OrchestratorClientService } from "../orchestrator-client/orchestrator-client.service";
import {
  createMockOrchestratorClient,
  MockResponses,
} from "../testing/mocks/orchestrator-client.mock";

describe("BudgetService", () => {
  let service: BudgetService;
  let orchestratorClient: jest.Mocked<OrchestratorClientService>;

  beforeEach(async () => {
    const mockClient = createMockOrchestratorClient();

    const module: TestingModule = await Test.createTestingModule({
      providers: [
        BudgetService,
        { provide: OrchestratorClientService, useValue: mockClient },
      ],
    }).compile();

    service = module.get<BudgetService>(BudgetService);
    orchestratorClient = module.get(OrchestratorClientService);
  });

  afterEach(() => {
    jest.clearAllMocks();
  });

  describe("getBudget", () => {
    it("should return budget status", async () => {
      orchestratorClient.getBudget.mockResolvedValueOnce(
        MockResponses.budgetStatusResponse,
      );

      const result = await service.getBudget("test-project");

      expect(result.totalSpentUsd).toBe(1.25);
      expect(result.projectBudgetUsd).toBe(10.0);
      expect(result.enabled).toBe(true);
    });

    it("should map snake_case to camelCase", async () => {
      orchestratorClient.getBudget.mockResolvedValueOnce({
        total_spent_usd: 5.0,
        project_budget_usd: 20.0,
        project_remaining_usd: 15.0,
        project_used_percent: 25.0,
        task_count: 5,
        record_count: 50,
        task_spent: { T1: 2.5, T2: 2.5 },
        updated_at: "2024-01-01T00:00:00Z",
        enabled: true,
      });

      const result = await service.getBudget("test");

      expect(result).toEqual({
        totalSpentUsd: 5.0,
        projectBudgetUsd: 20.0,
        projectRemainingUsd: 15.0,
        projectUsedPercent: 25.0,
        taskCount: 5,
        recordCount: 50,
        taskSpent: { T1: 2.5, T2: 2.5 },
        updatedAt: "2024-01-01T00:00:00Z",
        enabled: true,
      });
    });

    it("should use default values for missing fields", async () => {
      orchestratorClient.getBudget.mockResolvedValueOnce({});

      const result = await service.getBudget("test");

      expect(result.totalSpentUsd).toBe(0);
      expect(result.taskCount).toBe(0);
      expect(result.recordCount).toBe(0);
      expect(result.taskSpent).toEqual({});
      expect(result.enabled).toBe(true);
    });

    it("should throw NotFoundException when project not found", async () => {
      orchestratorClient.getBudget.mockRejectedValueOnce(
        new Error("not found"),
      );

      await expect(service.getBudget("nonexistent")).rejects.toThrow(
        NotFoundException,
      );
    });
  });

  describe("getReport", () => {
    it("should return budget report", async () => {
      orchestratorClient.getBudgetReport.mockResolvedValueOnce(
        MockResponses.budgetReportResponse,
      );

      const result = await service.getReport("test");

      expect(result.status).toBeDefined();
      expect(result.taskSpending).toHaveLength(2);
    });

    it("should throw NotFoundException when project not found", async () => {
      orchestratorClient.getBudgetReport.mockRejectedValueOnce(
        new Error("not found"),
      );

      await expect(service.getReport("nonexistent")).rejects.toThrow(
        NotFoundException,
      );
    });
  });
});
