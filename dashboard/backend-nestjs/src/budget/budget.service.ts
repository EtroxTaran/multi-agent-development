import { Injectable, NotFoundException } from '@nestjs/common';
import { OrchestratorClientService } from '../orchestrator-client/orchestrator-client.service';
import { BudgetStatusDto, BudgetReportResponseDto } from './dto';

@Injectable()
export class BudgetService {
  constructor(
    private readonly orchestratorClient: OrchestratorClientService,
  ) {}

  async getBudget(projectName: string): Promise<BudgetStatusDto> {
    try {
      const budget = (await this.orchestratorClient.getBudget(projectName)) as any;
      return this.mapToBudgetStatus(budget);
    } catch (error: any) {
      if (error.message?.includes('404') || error.message?.includes('not found')) {
        throw new NotFoundException(`Project '${projectName}' not found`);
      }
      throw error;
    }
  }

  async getReport(projectName: string): Promise<BudgetReportResponseDto> {
    try {
      return (await this.orchestratorClient.getBudgetReport(projectName)) as BudgetReportResponseDto;
    } catch (error: any) {
      if (error.message?.includes('404') || error.message?.includes('not found')) {
        throw new NotFoundException(`Project '${projectName}' not found`);
      }
      throw error;
    }
  }

  private mapToBudgetStatus(data: any): BudgetStatusDto {
    return {
      totalSpentUsd: data.total_spent_usd ?? 0,
      projectBudgetUsd: data.project_budget_usd,
      projectRemainingUsd: data.project_remaining_usd,
      projectUsedPercent: data.project_used_percent,
      taskCount: data.task_count ?? 0,
      recordCount: data.record_count ?? 0,
      taskSpent: data.task_spent ?? {},
      updatedAt: data.updated_at,
      enabled: data.enabled ?? true,
    };
  }
}