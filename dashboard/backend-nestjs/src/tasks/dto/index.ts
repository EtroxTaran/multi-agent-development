import { ApiProperty, ApiPropertyOptional } from "@nestjs/swagger";
import { TaskStatus } from "../../common/enums";

export class TaskInfoDto {
  @ApiProperty({ description: "Task ID" })
  id: string;

  @ApiProperty({ description: "Task title" })
  title: string;

  @ApiPropertyOptional({ description: "Task description" })
  description?: string;

  @ApiProperty({
    enum: TaskStatus,
    description: "Task status",
    default: TaskStatus.PENDING,
  })
  status: TaskStatus = TaskStatus.PENDING;

  @ApiProperty({ description: "Task priority", default: 0 })
  priority: number = 0;

  @ApiProperty({ description: "Task dependencies", type: [String] })
  dependencies: string[] = [];

  @ApiProperty({ description: "Files to create", type: [String] })
  filesToCreate: string[] = [];

  @ApiProperty({ description: "Files to modify", type: [String] })
  filesToModify: string[] = [];

  @ApiProperty({ description: "Acceptance criteria", type: [String] })
  acceptanceCriteria: string[] = [];

  @ApiPropertyOptional({ description: "Complexity score" })
  complexityScore?: number;

  @ApiPropertyOptional({ description: "Created timestamp" })
  createdAt?: string;

  @ApiPropertyOptional({ description: "Started timestamp" })
  startedAt?: string;

  @ApiPropertyOptional({ description: "Completed timestamp" })
  completedAt?: string;

  @ApiPropertyOptional({ description: "Error message" })
  error?: string;
}

export class TaskListResponseDto {
  @ApiProperty({ description: "List of tasks", type: [TaskInfoDto] })
  tasks: TaskInfoDto[] = [];

  @ApiProperty({ description: "Total task count", default: 0 })
  total: number = 0;

  @ApiProperty({ description: "Completed task count", default: 0 })
  completed: number = 0;

  @ApiProperty({ description: "In-progress task count", default: 0 })
  inProgress: number = 0;

  @ApiProperty({ description: "Pending task count", default: 0 })
  pending: number = 0;

  @ApiProperty({ description: "Failed task count", default: 0 })
  failed: number = 0;
}
