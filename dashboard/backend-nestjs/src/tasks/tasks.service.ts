import { Injectable, NotFoundException } from '@nestjs/common';
import { OrchestratorClientService } from '../orchestrator-client/orchestrator-client.service';
import { TaskStatus } from '../common/enums';
import { TaskInfoDto, TaskListResponseDto } from './dto';
import { AuditResponseDto } from '../agents/dto';

@Injectable()
export class TasksService {
  constructor(
    private readonly orchestratorClient: OrchestratorClientService,
  ) {}

  async getTasks(projectName: string): Promise<TaskListResponseDto> {
    try {
      const data = (await this.orchestratorClient.getTasks(projectName)) as any;
      return this.mapToTaskListResponse(data);
    } catch (error: any) {
      if (error.message?.includes('404') || error.message?.includes('not found')) {
        throw new NotFoundException(`Project '${projectName}' not found`);
      }
      throw error;
    }
  }

  async getTask(projectName: string, taskId: string): Promise<TaskInfoDto> {
    try {
      const data = (await this.orchestratorClient.getTask(projectName, taskId)) as any;
      return this.mapToTaskInfo(data);
    } catch (error: any) {
      if (error.message?.includes('404') || error.message?.includes('not found')) {
        throw new NotFoundException(`Task '${taskId}' not found`);
      }
      throw error;
    }
  }

  async getHistory(projectName: string, taskId: string, limit = 100): Promise<AuditResponseDto> {
    try {
      return (await this.orchestratorClient.getTaskHistory(projectName, taskId, limit)) as AuditResponseDto;
    } catch (error: any) {
      if (error.message?.includes('404') || error.message?.includes('not found')) {
        throw new NotFoundException(`Task '${taskId}' not found`);
      }
      throw error;
    }
  }

  private mapToTaskListResponse(data: any): TaskListResponseDto {
    const tasks = (data.tasks ?? []).map((t: any) => this.mapToTaskInfo(t));
    return {
      tasks,
      total: data.total ?? tasks.length,
      completed: data.completed ?? tasks.filter((t: TaskInfoDto) => t.status === TaskStatus.COMPLETED).length,
      inProgress: data.in_progress ?? tasks.filter((t: TaskInfoDto) => t.status === TaskStatus.IN_PROGRESS).length,
      pending: data.pending ?? tasks.filter((t: TaskInfoDto) => t.status === TaskStatus.PENDING).length,
      failed: data.failed ?? tasks.filter((t: TaskInfoDto) => t.status === TaskStatus.FAILED).length,
    };
  }

  private mapToTaskInfo(data: any): TaskInfoDto {
    return {
      id: data.id,
      title: data.title,
      description: data.description,
      status: (data.status as TaskStatus) ?? TaskStatus.PENDING,
      priority: data.priority ?? 0,
      dependencies: data.dependencies ?? [],
      filesToCreate: data.files_to_create ?? [],
      filesToModify: data.files_to_modify ?? [],
      acceptanceCriteria: data.acceptance_criteria ?? [],
      complexityScore: data.complexity_score,
      createdAt: data.created_at,
      startedAt: data.started_at,
      completedAt: data.completed_at,
      error: data.error,
    };
  }
}