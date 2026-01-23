import { Test, TestingModule } from "@nestjs/testing";
import { AgentsController } from "./agents.controller";
import { AgentsService } from "./agents.service";
import { AgentType } from "../common/enums";
import { createAuditStatistics, createAgentStatus } from "../testing/factories";

describe("AgentsController", () => {
  let controller: AgentsController;
  let agentsService: jest.Mocked<AgentsService>;

  const mockAgentsService = {
    getAgents: jest.fn(),
    getAudit: jest.fn(),
    getStatistics: jest.fn(),
  };

  beforeEach(async () => {
    jest.clearAllMocks();

    const module: TestingModule = await Test.createTestingModule({
      controllers: [AgentsController],
      providers: [{ provide: AgentsService, useValue: mockAgentsService }],
    }).compile();

    controller = module.get<AgentsController>(AgentsController);
    agentsService = module.get(AgentsService);
  });

  describe("getAgents", () => {
    it("should return agent statuses", async () => {
      const agents = {
        agents: [createAgentStatus(AgentType.CLAUDE)],
      };
      agentsService.getAgents.mockResolvedValueOnce(agents);

      const result = await controller.getAgents("test");

      expect(result).toEqual(agents);
      expect(agentsService.getAgents).toHaveBeenCalledWith("test");
    });
  });

  describe("getAudit", () => {
    it("should return audit entries with filters", async () => {
      const audit = { entries: [], total: 0 };
      agentsService.getAudit.mockResolvedValueOnce(audit);

      const result = await controller.getAudit(
        "test",
        50,
        "claude",
        "T1",
        "success",
        24,
      );

      expect(result).toEqual(audit);
      expect(agentsService.getAudit).toHaveBeenCalledWith("test", {
        limit: 50,
        agent: "claude",
        taskId: "T1",
        status: "success",
        sinceHours: 24,
      });
    });
  });

  describe("getStatistics", () => {
    it("should return audit statistics", async () => {
      const stats = createAuditStatistics({ total: 100, successRate: 0.9 });
      agentsService.getStatistics.mockResolvedValueOnce(stats);

      const result = await controller.getStatistics("test", 24);

      expect(result).toEqual(stats);
      expect(agentsService.getStatistics).toHaveBeenCalledWith("test", 24);
    });
  });
});
