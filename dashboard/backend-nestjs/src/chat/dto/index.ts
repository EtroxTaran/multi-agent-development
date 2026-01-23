import { ApiProperty, ApiPropertyOptional } from '@nestjs/swagger';
import { IsString, IsOptional } from 'class-validator';

export class ChatMessageDto {
  @ApiProperty({ description: 'Message role: user, assistant, system' })
  role: string;

  @ApiProperty({ description: 'Message content' })
  content: string;

  @ApiPropertyOptional({ description: 'Message timestamp' })
  timestamp?: string;
}

export class ChatRequestDto {
  @ApiProperty({ description: 'User message' })
  @IsString()
  message: string;

  @ApiPropertyOptional({ description: 'Project name for context' })
  @IsString()
  @IsOptional()
  projectName?: string;

  @ApiPropertyOptional({ description: 'Additional context' })
  @IsOptional()
  context?: Record<string, unknown>;
}

export class ChatResponseDto {
  @ApiProperty({ description: 'Assistant response message' })
  message: string;

  @ApiProperty({ description: 'Is streaming response', default: false })
  streaming: boolean = false;
}

export class CommandRequestDto {
  @ApiProperty({ description: 'Command to execute' })
  @IsString()
  command: string;

  @ApiProperty({ description: 'Command arguments', type: [String], default: [] })
  args: string[] = [];

  @ApiPropertyOptional({ description: 'Project name' })
  @IsString()
  @IsOptional()
  projectName?: string;
}

export class CommandResponseDto {
  @ApiProperty({ description: 'Success status' })
  success: boolean;

  @ApiPropertyOptional({ description: 'Command output' })
  output?: string;

  @ApiPropertyOptional({ description: 'Error message' })
  error?: string;
}
