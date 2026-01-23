/**
 * Projects list page
 */

import { useState } from "react";
import { Link } from "@tanstack/react-router";
import { FolderOpen, Plus, RefreshCw } from "lucide-react";
import { useProjects, useInitProject } from "@/hooks";
import {
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Badge,
  Input,
  Label,
  Guidance,
} from "@/components/ui";
import { cn, formatDate, getStatusColor, getPhaseName } from "@/lib/utils";

export function ProjectsPage() {
  const { data: projects, isLoading, error, refetch } = useProjects();
  const initProject = useInitProject();
  const [newProjectName, setNewProjectName] = useState("");
  const [showNewProject, setShowNewProject] = useState(false);

  const handleCreateProject = async () => {
    if (!newProjectName.trim()) return;

    try {
      await initProject.mutateAsync(newProjectName);
      setNewProjectName("");
      setShowNewProject(false);
    } catch (e) {
      console.error("Failed to create project:", e);
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <RefreshCw className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-64 space-y-4">
        <p className="text-destructive">
          Failed to load projects: {error.message}
        </p>
        <Button onClick={() => refetch()}>Retry</Button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Projects</h1>
          <p className="text-muted-foreground">
            Manage your Conductor orchestration projects
          </p>
        </div>
        <div className="flex items-center space-x-2">
          <Button variant="outline" onClick={() => refetch()}>
            <RefreshCw className="h-4 w-4 mr-2" />
            Refresh
          </Button>
          <Button onClick={() => setShowNewProject(true)}>
            <Plus className="h-4 w-4 mr-2" />
            New Project
          </Button>
        </div>
      </div>

      {/* New project form */}
      {showNewProject && (
        <Card>
          <CardHeader>
            <CardTitle>Create New Project</CardTitle>
            <CardDescription>
              Initialize a new orchestration project
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex flex-col space-y-4">
              <div className="flex flex-col space-y-2">
                <div className="flex items-center gap-2">
                  <Label htmlFor="projectName">Project Name</Label>
                  <Guidance content="The name of your new orchestration project. Use only letters, numbers, underscores, and hyphens." />
                </div>
                <div className="flex items-center space-x-4">
                  <Input
                    id="projectName"
                    type="text"
                    placeholder="e.g. my-awesome-project"
                    value={newProjectName}
                    onChange={(e) => setNewProjectName(e.target.value)}
                    className="flex-1"
                    pattern="[a-zA-Z0-9_-]+"
                  />
                  <Button
                    onClick={handleCreateProject}
                    disabled={initProject.isPending}
                  >
                    {initProject.isPending ? "Creating..." : "Create"}
                  </Button>
                  <Button
                    variant="outline"
                    onClick={() => setShowNewProject(false)}
                  >
                    Cancel
                  </Button>
                </div>
              </div>
            </div>
            {initProject.isError && (
              <p className="mt-2 text-sm text-destructive">
                {initProject.error?.message || "Failed to create project"}
              </p>
            )}
          </CardContent>
        </Card>
      )}

      {/* Project list */}
      {projects && projects.length > 0 ? (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {projects.map((project) => (
            <Link
              key={project.name}
              to="/project/$name"
              params={{ name: project.name }}
              className="block"
            >
              <Card className="h-full hover:shadow-md transition-shadow cursor-pointer">
                <CardHeader className="pb-2">
                  <div className="flex items-center justify-between">
                    <CardTitle className="text-lg">{project.name}</CardTitle>
                    <Badge
                      className={cn(
                        getStatusColor(
                          project.workflow_status || "not_started",
                        ),
                      )}
                    >
                      {project.workflow_status || "Not Started"}
                    </Badge>
                  </div>
                  <CardDescription className="text-xs">
                    {project.path}
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="space-y-2">
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-muted-foreground">Phase</span>
                      <span className="font-medium">
                        {project.current_phase > 0
                          ? `${project.current_phase}/5 - ${getPhaseName(
                              project.current_phase,
                            )}`
                          : "Not started"}
                      </span>
                    </div>
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-muted-foreground">Docs</span>
                      <span>
                        {project.has_documents ? (
                          <Badge variant="success">Ready</Badge>
                        ) : (
                          <Badge variant="warning">Missing</Badge>
                        )}
                      </span>
                    </div>
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-muted-foreground">Context</span>
                      <span className="flex space-x-1">
                        {project.has_claude_md && (
                          <Badge variant="secondary">Claude</Badge>
                        )}
                        {project.has_gemini_md && (
                          <Badge variant="secondary">Gemini</Badge>
                        )}
                        {project.has_cursor_rules && (
                          <Badge variant="secondary">Cursor</Badge>
                        )}
                      </span>
                    </div>
                    {project.last_activity && (
                      <div className="text-xs text-muted-foreground pt-2">
                        Last activity: {formatDate(project.last_activity)}
                      </div>
                    )}
                  </div>
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      ) : (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-12">
            <FolderOpen className="h-12 w-12 text-muted-foreground mb-4" />
            <p className="text-lg font-medium">No projects yet</p>
            <p className="text-muted-foreground">
              Create your first project to get started
            </p>
            <Button className="mt-4" onClick={() => setShowNewProject(true)}>
              <Plus className="h-4 w-4 mr-2" />
              Create Project
            </Button>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
