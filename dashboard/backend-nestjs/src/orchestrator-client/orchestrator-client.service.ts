import { Injectable, Logger, OnModuleInit } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';

interface RequestOptions {
  method?: string;
  body?: unknown;
  timeout?: number;
}

@Injectable()
export class OrchestratorClientService implements OnModuleInit {
  private readonly logger = new Logger(OrchestratorClientService.name);
  private baseUrl: string;

  constructor(private configService: ConfigService) {
    this.baseUrl = this.configService.get<string>(
      'ORCHESTRATOR_API_URL',
      'http://localhost:8090',
    );
  }

  async onModuleInit() {
    await this.checkHealth();
  }

  private async request<T>(
    path: string,
    options: RequestOptions = {},
  ): Promise<T> {
    const { method = 'GET', body, timeout = 30000 } = options;
    const url = `${this.baseUrl}${path}`;

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeout);

    try {
      const fetchOptions: RequestInit = {
        method,
        headers: {
          'Content-Type': 'application/json',
        },
        signal: controller.signal,
      };

      if (body) {
        fetchOptions.body = JSON.stringify(body);
      }

      const response = await fetch(url, fetchOptions);

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(
          errorData.detail || `HTTP ${response.status}: ${response.statusText}`,
        );
      }

      return (await response.json()) as T;
    } finally {
      clearTimeout(timeoutId);
    }
  }

  async checkHealth(): Promise<boolean> {
    try {
      const result = await this.request<{ status: string }>('/health');
      const healthy = result.status === 'healthy';
      if (healthy) {
        this.logger.log('Orchestrator API connection established');
      } else {
        this.logger.warn('Orchestrator API unhealthy');
      }
      return healthy;
    } catch (error) {
      this.logger.error(`Failed to connect to Orchestrator API: ${error}`);
      return false;
    }
  }

  // ==================== Projects ====================

  async listProjects(): Promise<unknown[]> {
    return this.request<unknown[]>('/projects');
  }

  async getProject(projectName: string): Promise<unknown> {
    return this.request<unknown>(`/projects/${encodeURIComponent(projectName)}`);
  }

  async initProject(projectName: string): Promise<unknown> {
    return this.request<unknown>(
      `/projects/${encodeURIComponent(projectName)}/init`,
      { method: 'POST' },
    );
  }

  async deleteProject(
    projectName: string,
    removeSource = false,
  ): Promise<unknown> {
    const query = removeSource ? '?remove_source=true' : '';
    return this.request<unknown>(
      `/projects/${encodeURIComponent(projectName)}${query}`,
      { method: 'DELETE' },
    );
  }

  // ==================== Workflow ====================

  async getWorkflowStatus(projectName: string): Promise<unknown> {
    return this.request<unknown>(
      `/projects/${encodeURIComponent(projectName)}/workflow/status`,
    );
  }

  async getWorkflowHealth(projectName: string): Promise<unknown> {
    return this.request<unknown>(
      `/projects/${encodeURIComponent(projectName)}/workflow/health`,
    );
  }

  async getWorkflowGraph(projectName: string): Promise<unknown> {
    return this.request<unknown>(
      `/projects/${encodeURIComponent(projectName)}/workflow/graph`,
    );
  }

  async startWorkflow(
    projectName: string,
    options: {
      startPhase?: number;
      endPhase?: number;
      skipValidation?: boolean;
      autonomous?: boolean;
    } = {},
  ): Promise<unknown> {
    return this.request<unknown>(
      `/projects/${encodeURIComponent(projectName)}/workflow/start`,
      {
        method: 'POST',
        body: {
          start_phase: options.startPhase ?? 1,
          end_phase: options.endPhase ?? 5,
          skip_validation: options.skipValidation ?? false,
          autonomous: options.autonomous ?? false,
        },
        timeout: 60000, // Longer timeout for workflow start
      },
    );
  }

  async resumeWorkflow(
    projectName: string,
    autonomous = false,
  ): Promise<unknown> {
    return this.request<unknown>(
      `/projects/${encodeURIComponent(projectName)}/workflow/resume?autonomous=${autonomous}`,
      { method: 'POST', timeout: 60000 },
    );
  }

  async rollbackWorkflow(projectName: string, phase: number): Promise<unknown> {
    return this.request<unknown>(
      `/projects/${encodeURIComponent(projectName)}/workflow/rollback/${phase}`,
      { method: 'POST' },
    );
  }

  async resetWorkflow(projectName: string): Promise<unknown> {
    return this.request<unknown>(
      `/projects/${encodeURIComponent(projectName)}/workflow/reset`,
      { method: 'POST' },
    );
  }

  // ==================== Tasks ====================

  async getTasks(projectName: string): Promise<unknown> {
    return this.request<unknown>(
      `/projects/${encodeURIComponent(projectName)}/tasks`,
    );
  }

  async getTask(projectName: string, taskId: string): Promise<unknown> {
    return this.request<unknown>(
      `/projects/${encodeURIComponent(projectName)}/tasks/${encodeURIComponent(taskId)}`,
    );
  }

  async getTaskHistory(
    projectName: string,
    taskId: string,
    limit = 100,
  ): Promise<unknown> {
    return this.request<unknown>(
      `/projects/${encodeURIComponent(projectName)}/tasks/${encodeURIComponent(taskId)}/history?limit=${limit}`,
    );
  }

  // ==================== Budget ====================

  async getBudget(projectName: string): Promise<unknown> {
    return this.request<unknown>(
      `/projects/${encodeURIComponent(projectName)}/budget`,
    );
  }

  async getBudgetReport(projectName: string): Promise<unknown> {
    return this.request<unknown>(
      `/projects/${encodeURIComponent(projectName)}/budget/report`,
    );
  }

  // ==================== Agents & Audit ====================

  async getAgents(projectName: string): Promise<unknown> {
    return this.request<unknown>(
      `/projects/${encodeURIComponent(projectName)}/agents`,
    );
  }

  async getAudit(
    projectName: string,
    options: {
      agent?: string;
      taskId?: string;
      status?: string;
      sinceHours?: number;
      limit?: number;
    } = {},
  ): Promise<unknown> {
    const params = new URLSearchParams();
    if (options.agent) params.set('agent', options.agent);
    if (options.taskId) params.set('task_id', options.taskId);
    if (options.status) params.set('status', options.status);
    if (options.sinceHours) params.set('since_hours', options.sinceHours.toString());
    if (options.limit) params.set('limit', options.limit.toString());

    return this.request<unknown>(
      `/projects/${encodeURIComponent(projectName)}/audit?${params.toString()}`,
    );
  }

  async getAuditStatistics(
    projectName: string,
    sinceHours?: number,
  ): Promise<unknown> {
    const query = sinceHours ? `?since_hours=${sinceHours}` : '';
    return this.request<unknown>(
      `/projects/${encodeURIComponent(projectName)}/audit/statistics${query}`,
    );
  }

  // ==================== Chat ====================

  async chat(
    message: string,
    projectName?: string,
    context?: Record<string, unknown>,
  ): Promise<unknown> {
    return this.request<unknown>('/chat', {
      method: 'POST',
      body: { message, project_name: projectName, context },
    });
  }

  async executeCommand(
    command: string,
    args: string[] = [],
    projectName?: string,
  ): Promise<unknown> {
    return this.request<unknown>('/chat/command', {
      method: 'POST',
      body: { command, args, project_name: projectName },
    });
  }
}