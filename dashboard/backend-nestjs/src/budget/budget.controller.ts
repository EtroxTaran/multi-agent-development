import { Controller, Get, Param } from "@nestjs/common";
import { ApiTags, ApiOperation, ApiResponse, ApiParam } from "@nestjs/swagger";
import { BudgetService } from "./budget.service";
import { BudgetStatusDto, BudgetReportResponseDto } from "./dto";

@Controller("api/projects/:projectName/budget")
@ApiTags("budget")
export class BudgetController {
  constructor(private readonly budgetService: BudgetService) {}

  @Get()
  @ApiOperation({ summary: "Get budget status for a project" })
  @ApiParam({ name: "projectName", description: "Project name" })
  @ApiResponse({
    status: 200,
    description: "Budget status",
    type: BudgetStatusDto,
  })
  @ApiResponse({ status: 404, description: "Project not found" })
  async getBudget(
    @Param("projectName") projectName: string,
  ): Promise<BudgetStatusDto> {
    return this.budgetService.getBudget(projectName);
  }

  @Get("report")
  @ApiOperation({ summary: "Get budget report" })
  @ApiParam({ name: "projectName", description: "Project name" })
  @ApiResponse({
    status: 200,
    description: "Budget report",
    type: BudgetReportResponseDto,
  })
  @ApiResponse({ status: 404, description: "Project not found" })
  async getReport(
    @Param("projectName") projectName: string,
  ): Promise<BudgetReportResponseDto> {
    return this.budgetService.getReport(projectName);
  }
}
