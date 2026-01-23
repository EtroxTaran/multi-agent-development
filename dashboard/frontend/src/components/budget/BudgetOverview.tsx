/**
 * Budget overview component
 */

import { useQuery } from "@tanstack/react-query";
import { budgetApi } from "@/lib/api";
import {
  Badge,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Progress,
  ScrollArea,
} from "@/components/ui";
import { formatCost, formatPercent } from "@/lib/utils";
import type { TaskSpending } from "@/types";

interface BudgetOverviewProps {
  projectName: string;
}

function SpendingRow({ spending }: { spending: TaskSpending }) {
  return (
    <div className="flex items-center justify-between py-2 border-b">
      <div className="flex items-center space-x-3">
        <span className="font-medium">{spending.task_id}</span>
      </div>
      <div className="flex items-center space-x-4">
        <span className="text-sm">{formatCost(spending.spent_usd)}</span>
        {spending.budget_usd !== undefined && (
          <>
            <span className="text-muted-foreground">/</span>
            <span className="text-sm text-muted-foreground">
              {formatCost(spending.budget_usd)}
            </span>
          </>
        )}
        {spending.used_percent !== undefined && (
          <Badge
            variant={
              spending.used_percent >= 90
                ? "destructive"
                : spending.used_percent >= 70
                  ? "warning"
                  : "secondary"
            }
          >
            {formatPercent(spending.used_percent)}
          </Badge>
        )}
      </div>
    </div>
  );
}

export function BudgetOverview({ projectName }: BudgetOverviewProps) {
  const { data: report, isLoading } = useQuery({
    queryKey: ["budget", "report", projectName],
    queryFn: () => budgetApi.getReport(projectName),
    refetchInterval: 10000,
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-48">
        <span className="text-muted-foreground">Loading budget...</span>
      </div>
    );
  }

  const status = report?.status;
  const taskSpending = report?.task_spending || [];

  const usedPercent = status?.project_used_percent || 0;

  return (
    <div className="space-y-6">
      {/* Overview cards */}
      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Total Spent</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold">
              {formatCost(status?.total_spent_usd || 0)}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Budget Remaining</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold">
              {status?.project_remaining_usd !== undefined
                ? formatCost(status.project_remaining_usd)
                : "Unlimited"}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Budget Used</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold">
              {formatPercent(usedPercent)}
            </div>
            {status?.project_budget_usd !== undefined && (
              <Progress value={usedPercent} className="mt-2" />
            )}
          </CardContent>
        </Card>
      </div>

      {/* Project budget */}
      {status?.project_budget_usd !== undefined && (
        <Card>
          <CardHeader>
            <CardTitle>Project Budget</CardTitle>
            <CardDescription>
              {formatCost(status.total_spent_usd)} of{" "}
              {formatCost(status.project_budget_usd)} used
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Progress
              value={usedPercent}
              className={
                usedPercent >= 90
                  ? "[&>div]:bg-red-500"
                  : usedPercent >= 70
                    ? "[&>div]:bg-yellow-500"
                    : ""
              }
            />
          </CardContent>
        </Card>
      )}

      {/* Task spending */}
      <Card>
        <CardHeader>
          <CardTitle>Spending by Task</CardTitle>
          <CardDescription>Cost breakdown per task</CardDescription>
        </CardHeader>
        <CardContent>
          <ScrollArea className="h-[300px]">
            {taskSpending.map((spending) => (
              <SpendingRow key={spending.task_id} spending={spending} />
            ))}
            {taskSpending.length === 0 && (
              <p className="text-sm text-muted-foreground">
                No spending recorded
              </p>
            )}
          </ScrollArea>
        </CardContent>
      </Card>
    </div>
  );
}
