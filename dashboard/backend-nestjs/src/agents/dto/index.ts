import { ApiProperty, ApiPropertyOptional } from '@nestjs/swagger';
import { AgentType } from '../../common/enums';

export class AgentStatusDto {
  @ApiProperty({ enum: AgentType, description: 'Agent type' })
  agent: AgentType;

  @ApiProperty({ description: 'Agent availability' })
  available: boolean;

  @ApiPropertyOptional({ description: 'Last invocation timestamp' })
  lastInvocation?: string;

  @ApiProperty({ description: 'Total invocations', default: 0 })
  totalInvocations: number = 0;

  @ApiProperty({ description: 'Success rate (0-1)', default: 0 })
  successRate: number = 0;

  @ApiProperty({ description: 'Average duration in seconds', default: 0 })
  avgDurationSeconds: number = 0;

  @ApiProperty({ description: 'Total cost in USD', default: 0 })
  totalCostUsd: number = 0;
}

export class AgentStatusResponseDto {
  @ApiProperty({ description: 'List of agent statuses', type: [AgentStatusDto] })
  agents: AgentStatusDto[] = [];
}

export class AuditEntryDto {
  @ApiProperty({ description: 'Entry ID' })
  id: string;

  @ApiProperty({ description: 'Agent name' })
  agent: string;

  @ApiProperty({ description: 'Task ID' })
  taskId: string;

  @ApiPropertyOptional({ description: 'Session ID' })
  sessionId?: string;

  @ApiPropertyOptional({ description: 'Prompt hash' })
  promptHash?: string;

  @ApiPropertyOptional({ description: 'Prompt length' })
  promptLength?: number;

  @ApiProperty({ description: 'Command arguments', type: [String] })
  commandArgs: string[] = [];

  @ApiPropertyOptional({ description: 'Exit code' })
  exitCode?: number;

  @ApiProperty({ description: 'Status', default: 'pending' })
  status: string = 'pending';

  @ApiPropertyOptional({ description: 'Duration in seconds' })
  durationSeconds?: number;

  @ApiPropertyOptional({ description: 'Output length' })
  outputLength?: number;

  @ApiPropertyOptional({ description: 'Error length' })
  errorLength?: number;

  @ApiPropertyOptional({ description: 'Parsed output type' })
  parsedOutputType?: string;

  @ApiPropertyOptional({ description: 'Cost in USD' })
  costUsd?: number;

  @ApiPropertyOptional({ description: 'Model used' })
  model?: string;

  @ApiProperty({ description: 'Metadata', additionalProperties: true })
  metadata: Record<string, unknown> = {};

  @ApiPropertyOptional({ description: 'Timestamp' })
  timestamp?: string;
}

export class AuditResponseDto {
  @ApiProperty({ description: 'List of audit entries', type: [AuditEntryDto] })
  entries: AuditEntryDto[];

  @ApiProperty({ description: 'Total count' })
  total: number;
}

export class AuditStatisticsDto {
  @ApiProperty({ description: 'Total entries', default: 0 })
  total: number = 0;

  @ApiProperty({ description: 'Success count', default: 0 })
  successCount: number = 0;

  @ApiProperty({ description: 'Failed count', default: 0 })
  failedCount: number = 0;

  @ApiProperty({ description: 'Timeout count', default: 0 })
  timeoutCount: number = 0;

  @ApiProperty({ description: 'Success rate', default: 0 })
  successRate: number = 0;

  @ApiProperty({ description: 'Total cost in USD', default: 0 })
  totalCostUsd: number = 0;

  @ApiProperty({ description: 'Total duration in seconds', default: 0 })
  totalDurationSeconds: number = 0;

  @ApiProperty({ description: 'Average duration in seconds', default: 0 })
  avgDurationSeconds: number = 0;

  @ApiProperty({ description: 'Count by agent', additionalProperties: { type: 'number' } })
  byAgent: Record<string, number> = {};

  @ApiProperty({ description: 'Count by status', additionalProperties: { type: 'number' } })
  byStatus: Record<string, number> = {};
}

export class SessionInfoDto {
  @ApiProperty({ description: 'Session ID' })
  sessionId: string;

  @ApiProperty({ description: 'Task ID' })
  taskId: string;

  @ApiProperty({ description: 'Agent name' })
  agent: string;

  @ApiProperty({ description: 'Creation timestamp' })
  createdAt: string;

  @ApiPropertyOptional({ description: 'Last active timestamp' })
  lastActive?: string;

  @ApiProperty({ description: 'Iteration count', default: 0 })
  iteration: number = 0;

  @ApiProperty({ description: 'Is active', default: true })
  active: boolean = true;
}

export class SessionListResponseDto {
  @ApiProperty({ description: 'List of sessions', type: [SessionInfoDto] })
  sessions: SessionInfoDto[];
}