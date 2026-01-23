import {
  Injectable,
  NotFoundException,
  BadRequestException,
} from "@nestjs/common";
import { OrchestratorClientService } from "../orchestrator-client/orchestrator-client.service";
import { WorkflowStatus } from "../common/enums";
import {
  WorkflowStatusResponseDto,
  WorkflowHealthResponseDto,
  WorkflowStartRequestDto,
  WorkflowStartResponseDto,
  WorkflowRollbackResponseDto,
} from "./dto";

@Injectable()
export class WorkflowService {
  constructor(private readonly orchestratorClient: OrchestratorClientService) {}

  async getStatus(projectName: string): Promise<WorkflowStatusResponseDto> {
    try {
      const status = (await this.orchestratorClient.getWorkflowStatus(
        projectName,
      )) as any;
      return this.mapToStatusResponse(status);
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

  async getHealth(projectName: string): Promise<WorkflowHealthResponseDto> {
    try {
      const health = (await this.orchestratorClient.getWorkflowHealth(
        projectName,
      )) as any;
      return this.mapToHealthResponse(health);
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

  async getGraph(projectName: string): Promise<unknown> {
    try {
      return await this.orchestratorClient.getWorkflowGraph(projectName);
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

  async start(
    projectName: string,
    request: WorkflowStartRequestDto,
  ): Promise<WorkflowStartResponseDto> {
    try {
      const result = (await this.orchestratorClient.startWorkflow(projectName, {
        startPhase: request.startPhase,
        endPhase: request.endPhase,
        skipValidation: request.skipValidation,
        autonomous: request.autonomous,
      })) as any;
      return this.mapToStartResponse(result);
    } catch (error: any) {
      if (
        error.message?.includes("404") ||
        error.message?.includes("not found")
      ) {
        throw new NotFoundException(`Project '${projectName}' not found`);
      }
      if (error.message?.includes("Prerequisites")) {
        throw new BadRequestException(error.message);
      }
      throw error;
    }
  }

  async resume(
    projectName: string,
    autonomous: boolean,
  ): Promise<WorkflowStartResponseDto> {
    try {
      const result = (await this.orchestratorClient.resumeWorkflow(
        projectName,
        autonomous,
      )) as any;
      return this.mapToStartResponse(result);
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

  async pause(projectName: string): Promise<{ message: string }> {
    // Note: Actual pause is handled via WebSocket broadcast
    // This just returns the intent to pause
    return {
      message: "Pause requested - workflow will pause at next checkpoint",
    };
  }

  async rollback(
    projectName: string,
    phase: number,
  ): Promise<WorkflowRollbackResponseDto> {
    if (phase < 1 || phase > 5) {
      throw new BadRequestException("Phase must be between 1 and 5");
    }

    try {
      const result = (await this.orchestratorClient.rollbackWorkflow(
        projectName,
        phase,
      )) as any;
      return {
        success: result.success,
        rolledBackTo: result.rolled_back_to,
        currentPhase: result.current_phase,
        message: result.message,
        error: result.error,
      };
    } catch (error: any) {
      if (
        error.message?.includes("404") ||
        error.message?.includes("not found")
      ) {
        throw new NotFoundException(`Project '${projectName}' not found`);
      }
      throw new BadRequestException(error.message || "Rollback failed");
    }
  }

  async reset(projectName: string): Promise<{ message: string }> {
    try {
      const result = (await this.orchestratorClient.resetWorkflow(
        projectName,
      )) as any;
      return { message: result.message || "Workflow reset" };
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

  private mapToStatusResponse(data: any): WorkflowStatusResponseDto {
    return {
      mode: data.mode ?? "langgraph",
      status: (data.status as WorkflowStatus) ?? WorkflowStatus.NOT_STARTED,
      project: data.project,
      currentPhase: data.current_phase,
      phaseStatus: data.phase_status ?? {},
      pendingInterrupt: data.pending_interrupt,
      message: data.message,
    };
  }

  private mapToHealthResponse(data: any): WorkflowHealthResponseDto {
    return {
      status: data.status ?? "unknown",
      project: data.project,
      currentPhase: data.current_phase,
      phaseStatus: data.phase_status,
      iterationCount: data.iteration_count ?? 0,
      lastUpdated: data.last_updated,
      agents: data.agents ?? {},
      langgraphEnabled: data.langgraph_enabled ?? false,
      hasContext: data.has_context ?? false,
      totalCommits: data.total_commits ?? 0,
    };
  }

  private mapToStartResponse(data: any): WorkflowStartResponseDto {
    return {
      success: data.success,
      mode: data.mode ?? "langgraph",
      paused: data.paused ?? false,
      message: data.message,
      error: data.error,
      results: data.results,
    };
  }
}
