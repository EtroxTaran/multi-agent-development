import { ApiProperty, ApiPropertyOptional } from "@nestjs/swagger";
import {
  IsString,
  IsBoolean,
  IsOptional,
  IsInt,
  Matches,
  MinLength,
  MaxLength,
} from "class-validator";

export class ProjectSummaryDto {
  @ApiProperty({ description: "Project name" })
  name: string;

  @ApiProperty({ description: "Project path" })
  path: string;

  @ApiPropertyOptional({ description: "Creation timestamp" })
  createdAt?: string;

  @ApiProperty({ description: "Current workflow phase", default: 0 })
  currentPhase: number = 0;

  @ApiProperty({ description: "Has Documents folder", default: false })
  hasDocuments: boolean = false;

  @ApiProperty({ description: "Has PRODUCT.md file", default: false })
  hasProductSpec: boolean = false;

  @ApiProperty({ description: "Has CLAUDE.md file", default: false })
  hasClaudeMd: boolean = false;

  @ApiProperty({ description: "Has GEMINI.md file", default: false })
  hasGeminiMd: boolean = false;

  @ApiProperty({ description: "Has .cursor/rules file", default: false })
  hasCursorRules: boolean = false;
}

export class ProjectStatusDto {
  @ApiProperty({ description: "Project name" })
  name: string;

  @ApiProperty({ description: "Project path" })
  path: string;

  @ApiPropertyOptional({ description: "Project configuration" })
  config?: Record<string, unknown>;

  @ApiPropertyOptional({ description: "Workflow state" })
  state?: Record<string, unknown>;

  @ApiProperty({
    description: "File existence map",
    additionalProperties: { type: "boolean" },
  })
  files: Record<string, boolean> = {};

  @ApiProperty({ description: "Phase information", additionalProperties: true })
  phases: Record<string, Record<string, unknown>> = {};
}

export class InitProjectDto {
  @ApiProperty({ description: "Project name", minLength: 1, maxLength: 64 })
  @IsString()
  @MinLength(1)
  @MaxLength(64)
  @Matches(/^[a-zA-Z0-9_-]+$/, {
    message:
      "Project name can only contain alphanumeric characters, underscores, and hyphens",
  })
  name: string;
}

export class InitProjectResponseDto {
  @ApiProperty({ description: "Success status" })
  success: boolean;

  @ApiPropertyOptional({ description: "Project directory path" })
  projectDir?: string;

  @ApiPropertyOptional({ description: "Success message" })
  message?: string;

  @ApiPropertyOptional({ description: "Error message" })
  error?: string;
}

export class FolderInfoDto {
  @ApiProperty({ description: "Folder name" })
  name: string;

  @ApiProperty({ description: "Folder path" })
  path: string;

  @ApiProperty({ description: "Is initialized project", default: false })
  isProject: boolean = false;

  @ApiProperty({ description: "Has workflow state", default: false })
  hasWorkflow: boolean = false;

  @ApiProperty({ description: "Has PRODUCT.md", default: false })
  hasProductMd: boolean = false;
}

export class DeleteProjectResponseDto {
  @ApiProperty({ description: "Success message" })
  message: string;
}
