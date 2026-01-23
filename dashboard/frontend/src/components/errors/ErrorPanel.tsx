/**
 * Error panel component
 */

import { useQuery } from "@tanstack/react-query";
import { AlertCircle, Clock } from "lucide-react";
import { agentsApi } from "@/lib/api";
import {
  Badge,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  ScrollArea,
} from "@/components/ui";
import { formatDate, getAgentName } from "@/lib/utils";
import type { AuditEntry } from "@/types";

interface ErrorPanelProps {
  projectName: string;
}

function ErrorCard({ entry }: { entry: AuditEntry }) {
  return (
    <Card className="mb-3">
      <CardHeader className="py-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <AlertCircle className="h-4 w-4 text-red-500" />
            <CardTitle className="text-sm">{entry.task_id}</CardTitle>
          </div>
          <Badge variant="secondary">{getAgentName(entry.agent)}</Badge>
        </div>
        <CardDescription className="text-xs">
          {entry.timestamp && formatDate(entry.timestamp)}
        </CardDescription>
      </CardHeader>
      <CardContent className="py-2">
        <div className="space-y-2 text-sm">
          <div className="flex items-center space-x-2">
            <span className="text-muted-foreground">Status:</span>
            <Badge
              variant={entry.status === "timeout" ? "warning" : "destructive"}
            >
              {entry.status}
            </Badge>
          </div>
          {entry.exit_code !== undefined && entry.exit_code !== 0 && (
            <div className="flex items-center space-x-2">
              <span className="text-muted-foreground">Exit code:</span>
              <span className="font-mono">{entry.exit_code}</span>
            </div>
          )}
          {entry.error_length && entry.error_length > 0 && (
            <div className="flex items-center space-x-2">
              <span className="text-muted-foreground">Error length:</span>
              <span>{entry.error_length} chars</span>
            </div>
          )}
          {entry.model && (
            <div className="flex items-center space-x-2">
              <span className="text-muted-foreground">Model:</span>
              <span>{entry.model}</span>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

export function ErrorPanel({ projectName }: ErrorPanelProps) {
  const { data: failedData } = useQuery({
    queryKey: ["audit", "errors", projectName, "failed"],
    queryFn: () =>
      agentsApi.getAudit(projectName, { status: "failed", limit: 50 }),
    refetchInterval: 10000,
  });

  const { data: timeoutData } = useQuery({
    queryKey: ["audit", "errors", projectName, "timeout"],
    queryFn: () =>
      agentsApi.getAudit(projectName, { status: "timeout", limit: 50 }),
    refetchInterval: 10000,
  });

  const failedEntries = failedData?.entries || [];
  const timeoutEntries = timeoutData?.entries || [];

  // Combine and sort by timestamp
  const allErrors = [...failedEntries, ...timeoutEntries].sort((a, b) => {
    if (!a.timestamp || !b.timestamp) return 0;
    return new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime();
  });

  const failedCount = failedEntries.length;
  const timeoutCount = timeoutEntries.length;

  return (
    <div className="space-y-6">
      {/* Summary cards */}
      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Total Errors</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold text-red-600">
              {allErrors.length}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <div className="flex items-center space-x-2">
              <AlertCircle className="h-4 w-4 text-red-500" />
              <CardDescription>Failed</CardDescription>
            </div>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold">{failedCount}</div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <div className="flex items-center space-x-2">
              <Clock className="h-4 w-4 text-yellow-500" />
              <CardDescription>Timeouts</CardDescription>
            </div>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold">{timeoutCount}</div>
          </CardContent>
        </Card>
      </div>

      {/* Error list */}
      <Card>
        <CardHeader>
          <CardTitle>Error Log</CardTitle>
          <CardDescription>Recent errors and timeouts</CardDescription>
        </CardHeader>
        <CardContent>
          <ScrollArea className="h-[400px]">
            {allErrors.map((entry) => (
              <ErrorCard key={entry.id} entry={entry} />
            ))}
            {allErrors.length === 0 && (
              <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
                <AlertCircle className="h-12 w-12 mb-4" />
                <p>No errors recorded</p>
              </div>
            )}
          </ScrollArea>
        </CardContent>
      </Card>
    </div>
  );
}
