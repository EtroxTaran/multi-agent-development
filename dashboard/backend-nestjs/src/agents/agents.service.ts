import { Injectable, NotFoundException } from '@nestjs/common';
import { OrchestratorClientService } from '../orchestrator-client/orchestrator-client.service';
import { AgentType } from '../common/enums';
import {
  AgentStatusDto,
  AgentStatusResponseDto,
  AuditResponseDto,
  AuditStatisticsDto,
} from './dto';

@Injectable()
export class AgentsService {
  constructor(
    private readonly orchestratorClient: OrchestratorClientService,
  ) {}

  async getAgents(projectName: string): Promise<AgentStatusResponseDto> {
    try {
      const agents = (await this.orchestratorClient.getAgents(projectName)) as any[];
      return {
        agents: agents.map((a) => this.mapToAgentStatus(a)),
      };
    } catch (error: any) {
      if (error.message?.includes('404') || error.message?.includes('not found')) {
        throw new NotFoundException(`Project '${projectName}' not found`);
      }
      throw error;
    }
  }

  async getAudit(
    projectName: string,
    options: { limit?: number; agent?: string; taskId?: string; status?: string; sinceHours?: number }
  ): Promise<AuditResponseDto> {
    try {
      return (await this.orchestratorClient.getAudit(projectName, options)) as AuditResponseDto;
    } catch (error: any) {
      if (error.message?.includes('404') || error.message?.includes('not found')) {
        throw new NotFoundException(`Project '${projectName}' not found`);
      }
      throw error;
    }
  }

  async getStatistics(
    projectName: string,
    sinceHours?: number,
  ): Promise<AuditStatisticsDto> {
    try {
      return (await this.orchestratorClient.getAuditStatistics(projectName, sinceHours)) as AuditStatisticsDto;
    } catch (error: any) {
      if (error.message?.includes('404') || error.message?.includes('not found')) {
        throw new NotFoundException(`Project '${projectName}' not found`);
      }
      throw error;
    }
  }

  private mapToAgentStatus(data: any): AgentStatusDto {
    return {
      agent: (data.agent as AgentType) ?? AgentType.CLAUDE,
      available: data.available ?? true,
      lastInvocation: data.last_invocation,
      totalInvocations: data.total_invocations ?? 0,
      successRate: data.success_rate ?? 0,
      avgDurationSeconds: data.avg_duration_seconds ?? 0,
      totalCostUsd: data.total_cost_usd ?? 0,
    };
  }
}