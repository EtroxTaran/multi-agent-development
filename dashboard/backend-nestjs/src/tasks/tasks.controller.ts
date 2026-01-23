import { Controller, Get, Param, Query } from "@nestjs/common";
import {
  ApiTags,
  ApiOperation,
  ApiResponse,
  ApiParam,
  ApiQuery,
} from "@nestjs/swagger";
import { TasksService } from "./tasks.service";
import { TaskInfoDto, TaskListResponseDto } from "./dto";
import { AuditResponseDto } from "../agents/dto";

@Controller("api/projects/:projectName/tasks")
@ApiTags("tasks")
export class TasksController {
  constructor(private readonly tasksService: TasksService) {}

  @Get()
  @ApiOperation({ summary: "Get tasks for a project" })
  @ApiParam({ name: "projectName", description: "Project name" })
  @ApiResponse({
    status: 200,
    description: "List of tasks",
    type: TaskListResponseDto,
  })
  @ApiResponse({ status: 404, description: "Project not found" })
  async getTasks(
    @Param("projectName") projectName: string,
  ): Promise<TaskListResponseDto> {
    return this.tasksService.getTasks(projectName);
  }

  @Get(":taskId")
  @ApiOperation({ summary: "Get task details" })
  @ApiParam({ name: "projectName", description: "Project name" })
  @ApiParam({ name: "taskId", description: "Task ID" })
  @ApiResponse({
    status: 200,
    description: "Task details",
    type: TaskInfoDto,
  })
  @ApiResponse({ status: 404, description: "Task not found" })
  async getTask(
    @Param("projectName") projectName: string,
    @Param("taskId") taskId: string,
  ): Promise<TaskInfoDto> {
    return this.tasksService.getTask(projectName, taskId);
  }

  @Get(":taskId/history")
  @ApiOperation({ summary: "Get task audit history" })
  @ApiParam({ name: "projectName", description: "Project name" })
  @ApiParam({ name: "taskId", description: "Task ID" })
  @ApiQuery({ name: "limit", required: false, type: Number })
  @ApiResponse({
    status: 200,
    description: "Audit history",
    type: AuditResponseDto,
  })
  @ApiResponse({ status: 404, description: "Task not found" })
  async getTaskHistory(
    @Param("projectName") projectName: string,
    @Param("taskId") taskId: string,
    @Query("limit") limit?: number,
  ): Promise<AuditResponseDto> {
    return this.tasksService.getHistory(projectName, taskId, limit);
  }
}
