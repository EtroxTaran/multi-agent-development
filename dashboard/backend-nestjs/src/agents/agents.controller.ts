import { Controller, Get, Param, Query } from "@nestjs/common";
import {
  ApiTags,
  ApiOperation,
  ApiResponse,
  ApiParam,
  ApiQuery,
} from "@nestjs/swagger";
import { AgentsService } from "./agents.service";
import {
  AgentStatusResponseDto,
  AuditResponseDto,
  AuditStatisticsDto,
} from "./dto";

@Controller("api/projects/:projectName")
@ApiTags("agents")
export class AgentsController {
  constructor(private readonly agentsService: AgentsService) {}

  @Get("agents")
  @ApiOperation({ summary: "Get agent statuses for a project" })
  @ApiParam({ name: "projectName", description: "Project name" })
  @ApiResponse({
    status: 200,
    description: "List of agent statuses",
    type: AgentStatusResponseDto,
  })
  @ApiResponse({ status: 404, description: "Project not found" })
  async getAgents(
    @Param("projectName") projectName: string,
  ): Promise<AgentStatusResponseDto> {
    return this.agentsService.getAgents(projectName);
  }

  @Get("audit")
  @ApiOperation({ summary: "Get audit entries" })
  @ApiParam({ name: "projectName", description: "Project name" })
  @ApiQuery({ name: "limit", required: false, type: Number })
  @ApiQuery({ name: "agent", required: false, type: String })
  @ApiQuery({ name: "task_id", required: false, type: String })
  @ApiQuery({ name: "status", required: false, type: String })
  @ApiQuery({ name: "since_hours", required: false, type: Number })
  @ApiResponse({
    status: 200,
    description: "Audit entries",
    type: AuditResponseDto,
  })
  async getAudit(
    @Param("projectName") projectName: string,
    @Query("limit") limit?: number,
    @Query("agent") agent?: string,
    @Query("task_id") taskId?: string,
    @Query("status") status?: string,
    @Query("since_hours") sinceHours?: number,
  ): Promise<AuditResponseDto> {
    return this.agentsService.getAudit(projectName, {
      limit,
      agent,
      taskId,
      status,
      sinceHours,
    });
  }

  @Get("audit/statistics")
  @ApiOperation({ summary: "Get audit statistics" })
  @ApiParam({ name: "projectName", description: "Project name" })
  @ApiQuery({ name: "since_hours", required: false, type: Number })
  @ApiResponse({
    status: 200,
    description: "Audit statistics",
    type: AuditStatisticsDto,
  })
  async getStatistics(
    @Param("projectName") projectName: string,
    @Query("since_hours") sinceHours?: number,
  ): Promise<AuditStatisticsDto> {
    return this.agentsService.getStatistics(projectName, sinceHours);
  }
}
