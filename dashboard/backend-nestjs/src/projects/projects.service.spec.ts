import { Test, TestingModule } from "@nestjs/testing";
import { NotFoundException, BadRequestException } from "@nestjs/common";
import { ProjectsService } from "./projects.service";
import { OrchestratorClientService } from "../orchestrator-client/orchestrator-client.service";
import {
  createMockOrchestratorClient,
  MockResponses,
} from "../testing/mocks/orchestrator-client.mock";
import {
  createProjectSummary,
  createProjectSummaryList,
  createProjectStatus,
} from "../testing/factories";

describe("ProjectsService", () => {
  let service: ProjectsService;
  let orchestratorClient: jest.Mocked<OrchestratorClientService>;

  beforeEach(async () => {
    const mockClient = createMockOrchestratorClient();

    const module: TestingModule = await Test.createTestingModule({
      providers: [
        ProjectsService,
        { provide: OrchestratorClientService, useValue: mockClient },
      ],
    }).compile();

    service = module.get<ProjectsService>(ProjectsService);
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

  describe("listProjects", () => {
    it("should return list of projects", async () => {
      orchestratorClient.listProjects.mockResolvedValueOnce(
        MockResponses.projectListResponse,
      );

      const result = await service.listProjects();

      expect(result).toHaveLength(2);
      expect(result[0].name).toBe("test-project");
      expect(result[1].name).toBe("another-project");
    });

    it("should return empty array when no projects exist", async () => {
      orchestratorClient.listProjects.mockResolvedValueOnce([]);

      const result = await service.listProjects();

      expect(result).toEqual([]);
    });

    it("should map snake_case to camelCase", async () => {
      orchestratorClient.listProjects.mockResolvedValueOnce([
        {
          name: "test",
          path: "/projects/test",
          created_at: "2024-01-01T00:00:00Z",
          current_phase: 2,
          has_documents: true,
          has_product_spec: true,
          has_claude_md: true,
          has_gemini_md: false,
          has_cursor_rules: false,
        },
      ]);

      const result = await service.listProjects();

      expect(result[0]).toEqual({
        name: "test",
        path: "/projects/test",
        createdAt: "2024-01-01T00:00:00Z",
        currentPhase: 2,
        hasDocuments: true,
        hasProductSpec: true,
        hasClaudeMd: true,
        hasGeminiMd: false,
        hasCursorRules: false,
      });
    });

    it("should use default values for missing fields", async () => {
      orchestratorClient.listProjects.mockResolvedValueOnce([
        { name: "test", path: "/projects/test" },
      ]);

      const result = await service.listProjects();

      expect(result[0].currentPhase).toBe(0);
      expect(result[0].hasDocuments).toBe(false);
      expect(result[0].hasProductSpec).toBe(false);
      expect(result[0].hasClaudeMd).toBe(false);
      expect(result[0].hasGeminiMd).toBe(false);
      expect(result[0].hasCursorRules).toBe(false);
    });
  });

  describe("getProject", () => {
    it("should return project status", async () => {
      orchestratorClient.getProject.mockResolvedValueOnce(
        MockResponses.projectStatusResponse,
      );

      const result = await service.getProject("test-project");

      expect(result.name).toBe("test-project");
      expect(result.config).toBeDefined();
      expect(result.state).toBeDefined();
    });

    it("should map response correctly", async () => {
      orchestratorClient.getProject.mockResolvedValueOnce({
        name: "test",
        path: "/projects/test",
        config: { version: "1.0" },
        state: { phase: 2 },
        files: { "PRODUCT.md": true },
        phases: { "1": { status: "completed" } },
      });

      const result = await service.getProject("test");

      expect(result).toEqual({
        name: "test",
        path: "/projects/test",
        config: { version: "1.0" },
        state: { phase: 2 },
        files: { "PRODUCT.md": true },
        phases: { "1": { status: "completed" } },
      });
    });

    it("should throw NotFoundException when project not found (404 message)", async () => {
      orchestratorClient.getProject.mockRejectedValueOnce(
        new Error("HTTP 404: Not Found"),
      );

      await expect(service.getProject("nonexistent")).rejects.toThrow(
        NotFoundException,
      );
    });

    it("should throw NotFoundException when project not found (not found message)", async () => {
      orchestratorClient.getProject.mockRejectedValueOnce(
        new Error("Project not found"),
      );

      await expect(service.getProject("nonexistent")).rejects.toThrow(
        NotFoundException,
      );
    });

    it("should re-throw other errors", async () => {
      const error = new Error("Connection refused");
      orchestratorClient.getProject.mockRejectedValueOnce(error);

      await expect(service.getProject("test")).rejects.toThrow(
        "Connection refused",
      );
    });

    it("should use default values for missing files and phases", async () => {
      orchestratorClient.getProject.mockResolvedValueOnce({
        name: "test",
        path: "/projects/test",
      });

      const result = await service.getProject("test");

      expect(result.files).toEqual({});
      expect(result.phases).toEqual({});
    });
  });

  describe("initProject", () => {
    it("should initialize project successfully", async () => {
      orchestratorClient.initProject.mockResolvedValueOnce(
        MockResponses.initProjectSuccessResponse,
      );

      const result = await service.initProject("new-project");

      expect(result.success).toBe(true);
      expect(result.projectDir).toBeDefined();
      expect(result.message).toBeDefined();
    });

    it("should map response fields correctly", async () => {
      orchestratorClient.initProject.mockResolvedValueOnce({
        success: true,
        project_dir: "/projects/my-project",
        message: "Project created",
      });

      const result = await service.initProject("my-project");

      expect(result).toEqual({
        success: true,
        projectDir: "/projects/my-project",
        message: "Project created",
        error: undefined,
      });
    });

    it("should throw BadRequestException on initialization failure", async () => {
      orchestratorClient.initProject.mockRejectedValueOnce(
        new Error("Project already exists"),
      );

      await expect(service.initProject("existing")).rejects.toThrow(
        BadRequestException,
      );
    });

    it("should use default message when error has no message", async () => {
      orchestratorClient.initProject.mockRejectedValueOnce(new Error());

      try {
        await service.initProject("test");
        fail("Should have thrown");
      } catch (error) {
        expect(error).toBeInstanceOf(BadRequestException);
        expect((error as BadRequestException).message).toBe(
          "Failed to initialize project",
        );
      }
    });

    it("should include error from response when present", async () => {
      orchestratorClient.initProject.mockResolvedValueOnce({
        success: false,
        error: "Invalid project name",
      });

      const result = await service.initProject("bad-name");

      expect(result.success).toBe(false);
      expect(result.error).toBe("Invalid project name");
    });
  });

  describe("deleteProject", () => {
    it("should delete project without removing source", async () => {
      orchestratorClient.deleteProject.mockResolvedValueOnce(
        MockResponses.deleteProjectResponse,
      );

      const result = await service.deleteProject("test-project", false);

      expect(result.message).toBeDefined();
      expect(orchestratorClient.deleteProject).toHaveBeenCalledWith(
        "test-project",
        false,
      );
    });

    it("should delete project with source removal", async () => {
      orchestratorClient.deleteProject.mockResolvedValueOnce(
        MockResponses.deleteProjectResponse,
      );

      await service.deleteProject("test-project", true);

      expect(orchestratorClient.deleteProject).toHaveBeenCalledWith(
        "test-project",
        true,
      );
    });

    it("should throw NotFoundException when project not found", async () => {
      orchestratorClient.deleteProject.mockRejectedValueOnce(
        new Error("HTTP 404: Not Found"),
      );

      await expect(service.deleteProject("nonexistent", false)).rejects.toThrow(
        NotFoundException,
      );
    });

    it("should re-throw other errors", async () => {
      orchestratorClient.deleteProject.mockRejectedValueOnce(
        new Error("Permission denied"),
      );

      await expect(service.deleteProject("test", false)).rejects.toThrow(
        "Permission denied",
      );
    });
  });
});
