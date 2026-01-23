import { ApiProperty, ApiPropertyOptional } from "@nestjs/swagger";

export class BudgetStatusDto {
  @ApiProperty({ description: "Total spent in USD", default: 0 })
  totalSpentUsd: number = 0;

  @ApiPropertyOptional({ description: "Project budget in USD" })
  projectBudgetUsd?: number;

  @ApiPropertyOptional({ description: "Project remaining budget in USD" })
  projectRemainingUsd?: number;

  @ApiPropertyOptional({ description: "Project budget used percentage" })
  projectUsedPercent?: number;

  @ApiProperty({ description: "Number of tasks", default: 0 })
  taskCount: number = 0;

  @ApiProperty({ description: "Number of records", default: 0 })
  recordCount: number = 0;

  @ApiProperty({
    description: "Spending by task",
    additionalProperties: { type: "number" },
  })
  taskSpent: Record<string, number> = {};

  @ApiPropertyOptional({ description: "Last updated timestamp" })
  updatedAt?: string;

  @ApiProperty({ description: "Budget tracking enabled", default: true })
  enabled: boolean = true;
}

export class TaskSpendingDto {
  @ApiProperty({ description: "Task ID" })
  taskId: string;

  @ApiProperty({ description: "Amount spent in USD", default: 0 })
  spentUsd: number = 0;

  @ApiPropertyOptional({ description: "Task budget in USD" })
  budgetUsd?: number;

  @ApiPropertyOptional({ description: "Remaining budget in USD" })
  remainingUsd?: number;

  @ApiPropertyOptional({ description: "Used percentage" })
  usedPercent?: number;
}

export class BudgetReportResponseDto {
  @ApiProperty({ description: "Budget status", type: BudgetStatusDto })
  status: BudgetStatusDto;

  @ApiProperty({
    description: "Task spending details",
    type: [TaskSpendingDto],
  })
  taskSpending: TaskSpendingDto[] = [];
}
