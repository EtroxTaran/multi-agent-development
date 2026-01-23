import {
  Controller,
  Get,
  Post,
  Param,
  Body,
  Query,
  ParseIntPipe,
} from "@nestjs/common";
import {
  ApiTags,
  ApiOperation,
  ApiResponse,
  ApiParam,
  ApiQuery,
} from "@nestjs/swagger";
import { WorkflowService } from "./workflow.service";
import {
  WorkflowStatusResponseDto,
  WorkflowHealthResponseDto,
  WorkflowStartRequestDto,
  WorkflowStartResponseDto,
  WorkflowRollbackResponseDto,
} from "./dto";

@Controller("api/projects/:projectName")
@ApiTags("workflow")
export class WorkflowController {
  constructor(private readonly workflowService: WorkflowService) {}

  @Get("status")
  @ApiOperation({ summary: "Get workflow status" })
  @ApiParam({ name: "projectName", description: "Project name" })
  @ApiResponse({
    status: 200,
    description: "Workflow status",
    type: WorkflowStatusResponseDto,
  })
  @ApiResponse({ status: 404, description: "Project not found" })
  async getStatus(
    @Param("projectName") projectName: string,
  ): Promise<WorkflowStatusResponseDto> {
    return this.workflowService.getStatus(projectName);
  }

  @Get("health")
  @ApiOperation({ summary: "Get workflow health" })
  @ApiParam({ name: "projectName", description: "Project name" })
  @ApiResponse({
    status: 200,
    description: "Workflow health",
    type: WorkflowHealthResponseDto,
  })
  @ApiResponse({ status: 404, description: "Project not found" })
  async getHealth(
    @Param("projectName") projectName: string,
  ): Promise<WorkflowHealthResponseDto> {
    return this.workflowService.getHealth(projectName);
  }

  @Get("workflow/graph")
  @ApiOperation({ summary: "Get workflow graph definition" })
  @ApiParam({ name: "projectName", description: "Project name" })
  @ApiResponse({ status: 200, description: "Graph definition" })
  async getGraph(@Param("projectName") projectName: string): Promise<unknown> {
    return this.workflowService.getGraph(projectName);
  }

  @Post("start")
  @ApiOperation({ summary: "Start workflow" })
  @ApiParam({ name: "projectName", description: "Project name" })
  @ApiResponse({
    status: 200,
    description: "Workflow started",
    type: WorkflowStartResponseDto,
  })
  @ApiResponse({ status: 400, description: "Prerequisites not met" })
  @ApiResponse({ status: 404, description: "Project not found" })
  async start(
    @Param("projectName") projectName: string,
    @Body() request: WorkflowStartRequestDto,
  ): Promise<WorkflowStartResponseDto> {
    return this.workflowService.start(projectName, request);
  }

  @Post("resume")
  @ApiOperation({ summary: "Resume paused workflow" })
  @ApiParam({ name: "projectName", description: "Project name" })
  @ApiQuery({
    name: "autonomous",
    required: false,
    description: "Run autonomously",
    type: Boolean,
  })
  @ApiResponse({
    status: 200,
    description: "Workflow resumed",
    type: WorkflowStartResponseDto,
  })
  @ApiResponse({ status: 404, description: "Project not found" })
  async resume(
    @Param("projectName") projectName: string,
    @Query("autonomous") autonomous?: boolean,
  ): Promise<WorkflowStartResponseDto> {
    return this.workflowService.resume(projectName, autonomous ?? false);
  }

  @Post("pause")
  @ApiOperation({ summary: "Request workflow pause" })
  @ApiParam({ name: "projectName", description: "Project name" })
  @ApiResponse({ status: 200, description: "Pause requested" })
  @ApiResponse({ status: 404, description: "Project not found" })
  async pause(
    @Param("projectName") projectName: string,
  ): Promise<{ message: string }> {
    return this.workflowService.pause(projectName);
  }

  @Post("rollback/:phase")
  @ApiOperation({ summary: "Rollback to a previous phase" })
  @ApiParam({ name: "projectName", description: "Project name" })
  @ApiParam({ name: "phase", description: "Phase to rollback to (1-5)" })
  @ApiResponse({
    status: 200,
    description: "Rollback completed",
    type: WorkflowRollbackResponseDto,
  })
  @ApiResponse({ status: 400, description: "Invalid phase or rollback failed" })
  @ApiResponse({ status: 404, description: "Project not found" })
  async rollback(
    @Param("projectName") projectName: string,
    @Param("phase", ParseIntPipe) phase: number,
  ): Promise<WorkflowRollbackResponseDto> {
    return this.workflowService.rollback(projectName, phase);
  }

  @Post("reset")
  @ApiOperation({ summary: "Reset workflow state" })
  @ApiParam({ name: "projectName", description: "Project name" })
  @ApiResponse({ status: 200, description: "Workflow reset" })
  @ApiResponse({ status: 404, description: "Project not found" })
  async reset(
    @Param("projectName") projectName: string,
  ): Promise<{ message: string }> {
    return this.workflowService.reset(projectName);
  }
}
