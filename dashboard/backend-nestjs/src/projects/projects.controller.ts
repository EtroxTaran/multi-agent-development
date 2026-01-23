import {
  Controller,
  Get,
  Post,
  Delete,
  Param,
  Query,
  Body,
} from "@nestjs/common";
import {
  ApiTags,
  ApiOperation,
  ApiResponse,
  ApiParam,
  ApiQuery,
} from "@nestjs/swagger";
import { ProjectsService } from "./projects.service";
import {
  ProjectSummaryDto,
  ProjectStatusDto,
  InitProjectDto,
  InitProjectResponseDto,
  DeleteProjectResponseDto,
} from "./dto";

@Controller("api/projects")
@ApiTags("projects")
export class ProjectsController {
  constructor(private readonly projectsService: ProjectsService) {}

  @Get()
  @ApiOperation({ summary: "List all projects" })
  @ApiResponse({
    status: 200,
    description: "List of projects",
    type: [ProjectSummaryDto],
  })
  async listProjects(): Promise<ProjectSummaryDto[]> {
    return this.projectsService.listProjects();
  }

  @Get(":projectName")
  @ApiOperation({ summary: "Get project status" })
  @ApiParam({ name: "projectName", description: "Project name" })
  @ApiResponse({
    status: 200,
    description: "Project status",
    type: ProjectStatusDto,
  })
  @ApiResponse({ status: 404, description: "Project not found" })
  async getProject(
    @Param("projectName") projectName: string,
  ): Promise<ProjectStatusDto> {
    return this.projectsService.getProject(projectName);
  }

  @Post(":projectName/init")
  @ApiOperation({ summary: "Initialize a new project" })
  @ApiParam({ name: "projectName", description: "Project name" })
  @ApiResponse({
    status: 201,
    description: "Project initialized",
    type: InitProjectResponseDto,
  })
  @ApiResponse({ status: 400, description: "Initialization failed" })
  async initProject(
    @Param("projectName") projectName: string,
  ): Promise<InitProjectResponseDto> {
    return this.projectsService.initProject(projectName);
  }

  @Delete(":projectName")
  @ApiOperation({ summary: "Delete a project" })
  @ApiParam({ name: "projectName", description: "Project name" })
  @ApiQuery({
    name: "removeSource",
    required: false,
    description: "Also remove source files",
    type: Boolean,
  })
  @ApiResponse({
    status: 200,
    description: "Project deleted",
    type: DeleteProjectResponseDto,
  })
  @ApiResponse({ status: 404, description: "Project not found" })
  async deleteProject(
    @Param("projectName") projectName: string,
    @Query("removeSource") removeSource?: boolean,
  ): Promise<DeleteProjectResponseDto> {
    return this.projectsService.deleteProject(
      projectName,
      removeSource ?? false,
    );
  }
}
