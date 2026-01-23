import { ApiProperty, ApiPropertyOptional } from "@nestjs/swagger";
import { IsInt, IsBoolean, IsOptional, Min, Max } from "class-validator";
import { WorkflowStatus } from "../../common/enums";

export class WorkflowStatusResponseDto {
  @ApiProperty({ description: "Workflow mode", default: "langgraph" })
  mode: string = "langgraph";

  @ApiProperty({ enum: WorkflowStatus, description: "Current workflow status" })
  status: WorkflowStatus;

  @ApiPropertyOptional({ description: "Project name" })
  project?: string;

  @ApiPropertyOptional({ description: "Current phase number" })
  currentPhase?: number;

  @ApiProperty({
    description: "Status of each phase",
    additionalProperties: { type: "string" },
  })
  phaseStatus: Record<string, string> = {};

  @ApiPropertyOptional({ description: "Pending interrupt details" })
  pendingInterrupt?: Record<string, unknown>;

  @ApiPropertyOptional({ description: "Status message" })
  message?: string;
}

export class WorkflowHealthResponseDto {
  @ApiProperty({ description: "Health status: healthy, degraded, unhealthy" })
  status: string;

  @ApiPropertyOptional({ description: "Project name" })
  project?: string;

  @ApiPropertyOptional({ description: "Current phase number" })
  currentPhase?: number;

  @ApiPropertyOptional({ description: "Phase status" })
  phaseStatus?: string;

  @ApiProperty({ description: "Iteration count", default: 0 })
  iterationCount: number = 0;

  @ApiPropertyOptional({ description: "Last updated timestamp" })
  lastUpdated?: string;

  @ApiProperty({
    description: "Agent availability",
    additionalProperties: { type: "boolean" },
  })
  agents: Record<string, boolean> = {};

  @ApiProperty({ description: "LangGraph enabled", default: false })
  langgraphEnabled: boolean = false;

  @ApiProperty({ description: "Has context files", default: false })
  hasContext: boolean = false;

  @ApiProperty({ description: "Total commits", default: 0 })
  totalCommits: number = 0;
}

export class WorkflowStartRequestDto {
  @ApiProperty({
    description: "Starting phase",
    default: 1,
    minimum: 1,
    maximum: 5,
  })
  @IsInt()
  @Min(1)
  @Max(5)
  @IsOptional()
  startPhase: number = 1;

  @ApiProperty({
    description: "Ending phase",
    default: 5,
    minimum: 1,
    maximum: 5,
  })
  @IsInt()
  @Min(1)
  @Max(5)
  @IsOptional()
  endPhase: number = 5;

  @ApiProperty({ description: "Skip validation phase", default: false })
  @IsBoolean()
  @IsOptional()
  skipValidation: boolean = false;

  @ApiProperty({
    description: "Run autonomously without human input",
    default: false,
  })
  @IsBoolean()
  @IsOptional()
  autonomous: boolean = false;
}

export class WorkflowStartResponseDto {
  @ApiProperty({ description: "Success status" })
  success: boolean;

  @ApiProperty({ description: "Workflow mode", default: "langgraph" })
  mode: string = "langgraph";

  @ApiProperty({ description: "Workflow paused", default: false })
  paused: boolean = false;

  @ApiPropertyOptional({ description: "Status message" })
  message?: string;

  @ApiPropertyOptional({ description: "Error message" })
  error?: string;

  @ApiPropertyOptional({ description: "Workflow results" })
  results?: Record<string, unknown>;
}

export class WorkflowRollbackResponseDto {
  @ApiProperty({ description: "Success status" })
  success: boolean;

  @ApiPropertyOptional({ description: "Checkpoint rolled back to" })
  rolledBackTo?: string;

  @ApiPropertyOptional({ description: "Current phase after rollback" })
  currentPhase?: number;

  @ApiPropertyOptional({ description: "Status message" })
  message?: string;

  @ApiPropertyOptional({ description: "Error message" })
  error?: string;
}
