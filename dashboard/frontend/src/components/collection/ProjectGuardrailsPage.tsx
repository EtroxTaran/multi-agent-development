/**
 * Project Guardrails Page - Manage guardrails applied to a specific project
 */

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Shield,
  ShieldCheck,
  ShieldOff,
  RefreshCw,
  Upload,
  ToggleLeft,
  ToggleRight,
  CheckCircle2,
  FileCode,
  Lightbulb,
  AlertTriangle,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { AlertBanner } from "@/components/ui/AlertBanner";

interface ProjectGuardrail {
  item_id: string;
  item_type: string;
  enabled: boolean;
  delivery_method: string;
  version_applied: number;
  applied_at: string;
  file_path: string | null;
}

interface ProjectGuardrailsResponse {
  project_name: string;
  guardrails: ProjectGuardrail[];
  total: number;
  enabled_count: number;
  disabled_count: number;
}

interface ApplyRecommendedResponse {
  message: string;
  items_applied: number;
  files_created: string[];
  cursor_rules_created: string[];
  errors: string[];
}

const API_BASE = "/api/collection";

// API Functions
async function fetchProjectGuardrails(
  projectName: string,
): Promise<ProjectGuardrailsResponse> {
  const res = await fetch(`${API_BASE}/projects/${projectName}/guardrails`);
  if (!res.ok) throw new Error("Failed to fetch project guardrails");
  return res.json();
}

async function toggleGuardrail(
  projectName: string,
  itemId: string,
  enabled: boolean,
): Promise<{ message: string; item_id: string; enabled: boolean }> {
  const res = await fetch(
    `${API_BASE}/projects/${projectName}/guardrails/${itemId}/toggle`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled }),
    },
  );
  if (!res.ok) throw new Error("Failed to toggle guardrail");
  return res.json();
}

async function applyRecommended(
  projectName: string,
): Promise<ApplyRecommendedResponse> {
  const res = await fetch(
    `${API_BASE}/projects/${projectName}/apply-recommended`,
    {
      method: "POST",
    },
  );
  if (!res.ok) throw new Error("Failed to apply recommended guardrails");
  return res.json();
}

async function promoteGuardrail(
  projectName: string,
  itemId: string,
): Promise<{ message: string; item_id: string; source_project: string }> {
  const res = await fetch(
    `${API_BASE}/projects/${projectName}/guardrails/${itemId}/promote`,
    {
      method: "POST",
    },
  );
  if (!res.ok) throw new Error("Failed to promote guardrail");
  return res.json();
}

// Type styling
const typeStyles: Record<
  string,
  { bg: string; text: string; icon: React.ReactNode }
> = {
  rule: {
    bg: "bg-blue-500/10",
    text: "text-blue-600 dark:text-blue-400",
    icon: <FileCode className="h-3 w-3" />,
  },
  skill: {
    bg: "bg-green-500/10",
    text: "text-green-600 dark:text-green-400",
    icon: <Lightbulb className="h-3 w-3" />,
  },
  guardrail: {
    bg: "bg-amber-500/10",
    text: "text-amber-600 dark:text-amber-400",
    icon: <Shield className="h-3 w-3" />,
  },
};

interface ProjectGuardrailsPageProps {
  projectName: string;
}

export function ProjectGuardrailsPage({
  projectName,
}: ProjectGuardrailsPageProps) {
  const queryClient = useQueryClient();
  const [applyResult, setApplyResult] =
    useState<ApplyRecommendedResponse | null>(null);

  // Query for project guardrails
  const {
    data: guardrailsData,
    isLoading,
    error,
    refetch,
  } = useQuery({
    queryKey: ["projectGuardrails", projectName],
    queryFn: () => fetchProjectGuardrails(projectName),
    enabled: !!projectName,
  });

  // Toggle mutation
  const toggleMutation = useMutation({
    mutationFn: ({ itemId, enabled }: { itemId: string; enabled: boolean }) =>
      toggleGuardrail(projectName, itemId, enabled),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ["projectGuardrails", projectName],
      });
    },
  });

  // Apply recommended mutation
  const applyMutation = useMutation({
    mutationFn: () => applyRecommended(projectName),
    onSuccess: (data) => {
      setApplyResult(data);
      queryClient.invalidateQueries({
        queryKey: ["projectGuardrails", projectName],
      });
    },
  });

  // Promote mutation
  const promoteMutation = useMutation({
    mutationFn: (itemId: string) => promoteGuardrail(projectName, itemId),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ["projectGuardrails", projectName],
      });
    },
  });

  const getTypeStyle = (type: string) => {
    return typeStyles[type.toLowerCase()] || typeStyles.rule;
  };

  const formatDate = (dateStr: string) => {
    if (!dateStr) return "—";
    try {
      return new Date(dateStr).toLocaleDateString("en-US", {
        month: "short",
        day: "numeric",
        year: "numeric",
      });
    } catch {
      return dateStr;
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <RefreshCw className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (error) {
    return (
      <AlertBanner variant="destructive" title="Error Loading Guardrails">
        <span className="flex items-center gap-2">
          <AlertTriangle className="h-4 w-4" />
          {(error as Error).message}
        </span>
      </AlertBanner>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold tracking-tight">Guardrails</h2>
          <p className="text-muted-foreground">
            Manage rules, skills, and guardrails applied to this project
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => refetch()}>
            <RefreshCw className="h-4 w-4 mr-2" />
            Refresh
          </Button>
          <Button
            size="sm"
            onClick={() => applyMutation.mutate()}
            disabled={applyMutation.isPending}
          >
            {applyMutation.isPending ? (
              <RefreshCw className="h-4 w-4 mr-2 animate-spin" />
            ) : (
              <ShieldCheck className="h-4 w-4 mr-2" />
            )}
            Apply Recommended
          </Button>
        </div>
      </div>

      {/* Summary Cards */}
      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total Applied</CardTitle>
            <Shield className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {guardrailsData?.total ?? 0}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Enabled</CardTitle>
            <ShieldCheck className="h-4 w-4 text-green-500" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-green-600">
              {guardrailsData?.enabled_count ?? 0}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Disabled</CardTitle>
            <ShieldOff className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-muted-foreground">
              {guardrailsData?.disabled_count ?? 0}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Apply Result Banner */}
      {applyResult && (
        <AlertBanner variant="default" title="Guardrails Applied">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="h-4 w-4 text-green-500" />
            <span>{applyResult.message}</span>
          </div>
          {applyResult.errors.length > 0 && (
            <p className="text-xs text-destructive mt-1">
              Errors: {applyResult.errors.join(", ")}
            </p>
          )}
        </AlertBanner>
      )}

      {/* Guardrails List */}
      <Card>
        <CardHeader>
          <CardTitle>Applied Guardrails</CardTitle>
          <CardDescription>
            View and manage guardrails that have been applied to this project
          </CardDescription>
        </CardHeader>
        <CardContent>
          {!guardrailsData?.guardrails?.length ? (
            <div className="text-center py-8 text-muted-foreground">
              <Shield className="h-12 w-12 mx-auto mb-4 opacity-50" />
              <p className="font-medium">No guardrails applied</p>
              <p className="text-sm">
                Click "Apply Recommended" to automatically apply matching
                guardrails
              </p>
            </div>
          ) : (
            <div className="grid gap-3">
              {guardrailsData.guardrails.map((guardrail) => {
                const style = getTypeStyle(guardrail.item_type);
                return (
                  <div
                    key={guardrail.item_id}
                    className="flex items-center justify-between p-4 border rounded-lg bg-card hover:bg-muted/50 transition-colors"
                  >
                    <div className="flex items-center gap-4">
                      <TooltipProvider>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <Button
                              variant="ghost"
                              size="sm"
                              className="p-0 h-8 w-8"
                              onClick={() =>
                                toggleMutation.mutate({
                                  itemId: guardrail.item_id,
                                  enabled: !guardrail.enabled,
                                })
                              }
                              disabled={toggleMutation.isPending}
                            >
                              {guardrail.enabled ? (
                                <ToggleRight className="h-5 w-5 text-green-500" />
                              ) : (
                                <ToggleLeft className="h-5 w-5 text-muted-foreground" />
                              )}
                            </Button>
                          </TooltipTrigger>
                          <TooltipContent>
                            {guardrail.enabled ? "Disable" : "Enable"}
                          </TooltipContent>
                        </Tooltip>
                      </TooltipProvider>

                      <div>
                        <p className="font-mono text-sm font-medium">
                          {guardrail.item_id}
                        </p>
                        <div className="flex items-center gap-2 mt-1">
                          <Badge
                            variant="secondary"
                            className={`${style.bg} ${style.text} text-xs`}
                          >
                            {style.icon}
                            <span className="ml-1">{guardrail.item_type}</span>
                          </Badge>
                          <Badge variant="outline" className="text-xs">
                            {guardrail.delivery_method}
                          </Badge>
                          <span className="text-xs text-muted-foreground">
                            {formatDate(guardrail.applied_at)}
                          </span>
                        </div>
                      </div>
                    </div>

                    <TooltipProvider>
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() =>
                              promoteMutation.mutate(guardrail.item_id)
                            }
                            disabled={promoteMutation.isPending}
                          >
                            <Upload className="h-4 w-4" />
                          </Button>
                        </TooltipTrigger>
                        <TooltipContent>
                          Promote to Global Collection
                        </TooltipContent>
                      </Tooltip>
                    </TooltipProvider>
                  </div>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

export default ProjectGuardrailsPage;
