import { Test, TestingModule } from "@nestjs/testing";
import { NotFoundException, BadRequestException } from "@nestjs/common";
import { ProjectsController } from "./projects.controller";
import { ProjectsService } from "./projects.service";
import {
  createProjectSummary,
  createProjectStatus,
} from "../testing/factories";

describe("ProjectsController", () => {
  let controller: ProjectsController;
  let projectsService: jest.Mocked<ProjectsService>;

  const mockProjectsService = {
    listProjects: jest.fn(),
    getProject: jest.fn(),
    initProject: jest.fn(),
    deleteProject: jest.fn(),
  };

  beforeEach(async () => {
    jest.clearAllMocks();

    const module: TestingModule = await Test.createTestingModule({
      controllers: [ProjectsController],
      providers: [{ provide: ProjectsService, useValue: mockProjectsService }],
    }).compile();

    controller = module.get<ProjectsController>(ProjectsController);
    projectsService = module.get(ProjectsService);
  });

  describe("initialization", () => {
    it("should be defined", () => {
      expect(controller).toBeDefined();
    });
  });

  describe("listProjects", () => {
    it("should return list of projects", async () => {
      const projects = [
        createProjectSummary({ name: "project-a" }),
        createProjectSummary({ name: "project-b" }),
      ];
      projectsService.listProjects.mockResolvedValueOnce(projects);

      const result = await controller.listProjects();

      expect(result).toEqual(projects);
      expect(projectsService.listProjects).toHaveBeenCalled();
    });

    it("should return empty array when no projects", async () => {
      projectsService.listProjects.mockResolvedValueOnce([]);

      const result = await controller.listProjects();

      expect(result).toEqual([]);
    });
  });

  describe("getProject", () => {
    it("should return project status", async () => {
      const status = createProjectStatus({ name: "test-project" });
      projectsService.getProject.mockResolvedValueOnce(status);

      const result = await controller.getProject("test-project");

      expect(result).toEqual(status);
      expect(projectsService.getProject).toHaveBeenCalledWith("test-project");
    });

    it("should throw NotFoundException when project not found", async () => {
      projectsService.getProject.mockRejectedValueOnce(
        new NotFoundException("Project 'nonexistent' not found"),
      );

      await expect(controller.getProject("nonexistent")).rejects.toThrow(
        NotFoundException,
      );
    });
  });

  describe("initProject", () => {
    it("should initialize project successfully", async () => {
      const response = {
        success: true,
        projectDir: "/projects/new-project",
        message: "Project initialized",
      };
      projectsService.initProject.mockResolvedValueOnce(response);

      const result = await controller.initProject("new-project");

      expect(result).toEqual(response);
      expect(projectsService.initProject).toHaveBeenCalledWith("new-project");
    });

    it("should throw BadRequestException on failure", async () => {
      projectsService.initProject.mockRejectedValueOnce(
        new BadRequestException("Project already exists"),
      );

      await expect(controller.initProject("existing")).rejects.toThrow(
        BadRequestException,
      );
    });
  });

  describe("deleteProject", () => {
    it("should delete project without source removal", async () => {
      const response = { message: "Project deleted" };
      projectsService.deleteProject.mockResolvedValueOnce(response);

      const result = await controller.deleteProject("test-project");

      expect(result).toEqual(response);
      expect(projectsService.deleteProject).toHaveBeenCalledWith(
        "test-project",
        false,
      );
    });

    it("should delete project with source removal", async () => {
      const response = { message: "Project and source deleted" };
      projectsService.deleteProject.mockResolvedValueOnce(response);

      const result = await controller.deleteProject("test-project", true);

      expect(result).toEqual(response);
      expect(projectsService.deleteProject).toHaveBeenCalledWith(
        "test-project",
        true,
      );
    });

    it("should throw NotFoundException when project not found", async () => {
      projectsService.deleteProject.mockRejectedValueOnce(
        new NotFoundException("Project 'nonexistent' not found"),
      );

      await expect(controller.deleteProject("nonexistent")).rejects.toThrow(
        NotFoundException,
      );
    });
  });
});
