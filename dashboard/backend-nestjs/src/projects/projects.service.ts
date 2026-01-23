import {
  Injectable,
  NotFoundException,
  BadRequestException,
} from "@nestjs/common";
import { OrchestratorClientService } from "../orchestrator-client/orchestrator-client.service";
import {
  ProjectSummaryDto,
  ProjectStatusDto,
  InitProjectResponseDto,
  DeleteProjectResponseDto,
} from "./dto";

@Injectable()
export class ProjectsService {
  constructor(private readonly orchestratorClient: OrchestratorClientService) {}

  async listProjects(): Promise<ProjectSummaryDto[]> {
    const projects = (await this.orchestratorClient.listProjects()) as any[];
    return projects.map((p) => this.mapToProjectSummary(p));
  }

  async getProject(projectName: string): Promise<ProjectStatusDto> {
    try {
      const project = (await this.orchestratorClient.getProject(
        projectName,
      )) as any;
      return this.mapToProjectStatus(project);
    } catch (error: any) {
      if (
        error.message?.includes("404") ||
        error.message?.includes("not found")
      ) {
        throw new NotFoundException(`Project '${projectName}' not found`);
      }
      throw error;
    }
  }

  async initProject(projectName: string): Promise<InitProjectResponseDto> {
    try {
      const result = (await this.orchestratorClient.initProject(
        projectName,
      )) as any;
      return {
        success: result.success,
        projectDir: result.project_dir,
        message: result.message,
        error: result.error,
      };
    } catch (error: any) {
      throw new BadRequestException(
        error.message || "Failed to initialize project",
      );
    }
  }

  async deleteProject(
    projectName: string,
    removeSource: boolean,
  ): Promise<DeleteProjectResponseDto> {
    try {
      const result = (await this.orchestratorClient.deleteProject(
        projectName,
        removeSource,
      )) as any;
      return { message: result.message };
    } catch (error: any) {
      if (
        error.message?.includes("404") ||
        error.message?.includes("not found")
      ) {
        throw new NotFoundException(`Project '${projectName}' not found`);
      }
      throw error;
    }
  }

  private mapToProjectSummary(data: any): ProjectSummaryDto {
    return {
      name: data.name,
      path: data.path,
      createdAt: data.created_at,
      currentPhase: data.current_phase ?? 0,
      hasDocuments: data.has_documents ?? false,
      hasProductSpec: data.has_product_spec ?? false,
      hasClaudeMd: data.has_claude_md ?? false,
      hasGeminiMd: data.has_gemini_md ?? false,
      hasCursorRules: data.has_cursor_rules ?? false,
    };
  }

  private mapToProjectStatus(data: any): ProjectStatusDto {
    return {
      name: data.name,
      path: data.path,
      config: data.config,
      state: data.state,
      files: data.files ?? {},
      phases: data.phases ?? {},
    };
  }
}
