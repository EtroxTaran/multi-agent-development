/**
 * Agent activity feed component
 */

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Eye } from "lucide-react";
import { agentsApi } from "@/lib/api";
import {
  Badge,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  ScrollArea,
  Separator,
  Guidance,
} from "@/components/ui";
import {
  formatDate,
  formatDuration,
  formatCost,
  getAgentName,
} from "@/lib/utils";
import type { AgentStatus, AuditEntry } from "@/types";

interface AgentFeedProps {
  projectName: string;
}

function AgentCard({ agent }: { agent: AgentStatus }) {
  return (
    <Card>
      <CardHeader className="py-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-lg">{getAgentName(agent.agent)}</CardTitle>
          <Badge variant={agent.available ? "success" : "destructive"}>
            {agent.available ? "Available" : "Unavailable"}
          </Badge>
        </div>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-2 gap-4 text-sm">
          <div>
            <span className="text-muted-foreground">Invocations</span>
            <p className="font-medium">{agent.total_invocations}</p>
          </div>
          <div>
            <div className="flex items-center gap-1">
              <span className="text-muted-foreground">Success Rate</span>
              <Guidance
                content="Percentage of successful tool calls by this agent."
                className="h-3 w-3"
              />
            </div>
            <p className="font-medium">
              {(agent.success_rate * 100).toFixed(1)}%
            </p>
          </div>
          <div>
            <span className="text-muted-foreground">Avg Duration</span>
            <p className="font-medium">
              {formatDuration(agent.avg_duration_seconds)}
            </p>
          </div>
          <div>
            <div className="flex items-center gap-1">
              <span className="text-muted-foreground">Total Cost</span>
              <Guidance
                content="Total API cost incurred by this agent across all tasks."
                className="h-3 w-3"
              />
            </div>
            <p className="font-medium">{formatCost(agent.total_cost_usd)}</p>
          </div>
        </div>
        {agent.last_invocation && (
          <p className="mt-2 text-xs text-muted-foreground">
            Last: {formatDate(agent.last_invocation)}
          </p>
        )}
      </CardContent>
    </Card>
  );
}

function AuditEntryRow({
  entry,
  onSelect,
}: {
  entry: AuditEntry;
  onSelect: (entry: AuditEntry) => void;
}) {
  return (
    <div
      className="flex items-center justify-between py-2 border-b hover:bg-muted/50 transition-colors px-2 rounded-sm cursor-pointer"
      onClick={() => onSelect(entry)}
    >
      <div className="flex items-center space-x-3">
        <Badge variant="secondary" className="text-xs">
          {getAgentName(entry.agent)}
        </Badge>
        <span className="text-sm font-medium">{entry.task_id}</span>
        <Badge
          variant={
            entry.status === "success"
              ? "success"
              : entry.status === "failed"
                ? "destructive"
                : "secondary"
          }
          className="text-xs"
        >
          {entry.status}
        </Badge>
      </div>
      <div className="flex items-center space-x-4 text-xs text-muted-foreground">
        {entry.duration_seconds !== undefined && (
          <span>{formatDuration(entry.duration_seconds)}</span>
        )}
        {entry.cost_usd !== undefined && (
          <span>{formatCost(entry.cost_usd)}</span>
        )}
        {entry.timestamp && <span>{formatDate(entry.timestamp)}</span>}
        <Button variant="ghost" size="icon" className="h-6 w-6">
          <Eye className="h-3 w-3" />
        </Button>
      </div>
    </div>
  );
}

export function AgentFeed({ projectName }: AgentFeedProps) {
  const [selectedEntry, setSelectedEntry] = useState<AuditEntry | null>(null);

  const { data: agentStatus } = useQuery({
    queryKey: ["agents", projectName],
    queryFn: () => agentsApi.getStatus(projectName),
  });

  const { data: auditData } = useQuery({
    queryKey: ["audit", projectName],
    queryFn: () => agentsApi.getAudit(projectName, { limit: 50 }),
    refetchInterval: 5000,
  });

  const agents = agentStatus?.agents || [];
  const entries = auditData?.entries || [];

  return (
    <div className="space-y-6">
      {/* Agent status cards */}
      <div className="grid gap-4 md:grid-cols-3">
        {agents.map((agent) => (
          <AgentCard key={agent.agent} agent={agent} />
        ))}
      </div>

      <Separator />

      {/* Recent activity */}
      <Card>
        <CardHeader>
          <CardTitle>Recent Activity</CardTitle>
          <CardDescription>
            Latest agent invocations (Click for details)
          </CardDescription>
        </CardHeader>
        <CardContent>
          <ScrollArea className="h-[300px]">
            {entries.map((entry) => (
              <AuditEntryRow
                key={entry.id}
                entry={entry}
                onSelect={setSelectedEntry}
              />
            ))}
            {entries.length === 0 && (
              <p className="text-sm text-muted-foreground">No activity yet</p>
            )}
          </ScrollArea>
        </CardContent>
      </Card>

      <Dialog
        open={selectedEntry !== null}
        onOpenChange={(open) => {
          if (!open) setSelectedEntry(null);
        }}
      >
        <DialogContent className="max-w-3xl max-h-[80vh] flex flex-col">
          <DialogHeader>
            <DialogTitle>Audit Entry Details</DialogTitle>
            <DialogDescription>
              Task: {selectedEntry?.task_id} | Agent:{" "}
              {selectedEntry?.agent ? getAgentName(selectedEntry.agent) : ""}
            </DialogDescription>
          </DialogHeader>

          <div className="flex-1 overflow-auto py-4">
            {selectedEntry && (
              <div className="space-y-4">
                <div className="grid grid-cols-2 gap-4 text-sm">
                  <div>
                    <span className="font-semibold block">Status</span>
                    <Badge
                      variant={
                        selectedEntry.status === "success"
                          ? "success"
                          : "destructive"
                      }
                    >
                      {selectedEntry.status}
                    </Badge>
                  </div>
                  <div>
                    <span className="font-semibold block">Duration</span>
                    {formatDuration(selectedEntry.duration_seconds || 0)}
                  </div>
                  <div>
                    <span className="font-semibold block">Cost</span>
                    {formatCost(selectedEntry.cost_usd || 0)}
                  </div>
                  <div>
                    <span className="font-semibold block">Timestamp</span>
                    {selectedEntry.timestamp
                      ? formatDate(selectedEntry.timestamp)
                      : "-"}
                  </div>
                </div>

                {selectedEntry.command_args &&
                  selectedEntry.command_args.length > 0 && (
                    <div>
                      <span className="font-semibold block mb-1">Command</span>
                      <pre className="bg-muted p-2 rounded text-xs overflow-x-auto whitespace-pre-wrap">
                        {selectedEntry.command_args.join(" ")}
                      </pre>
                    </div>
                  )}

                {selectedEntry.metadata &&
                  Object.keys(selectedEntry.metadata).length > 0 && (
                    <div>
                      <span className="font-semibold block mb-1">Metadata</span>
                      <pre className="bg-muted p-2 rounded text-xs overflow-x-auto">
                        {JSON.stringify(selectedEntry.metadata, null, 2)}
                      </pre>
                    </div>
                  )}
              </div>
            )}
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
