/**
 * Projects list page
 */

import { useState, useMemo } from "react";
import { Link } from "@tanstack/react-router";
import {
  FolderOpen,
  Plus,
  RefreshCw,
  Trash2,
  Terminal,
  Clock,
  Folder,
} from "lucide-react";
import {
  useProjects,
  useInitProject,
  useDeleteProject,
  useWorkspaceFolders,
} from "@/hooks";
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
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui";
import { cn, formatDate, getStatusColor, getPhaseName } from "@/lib/utils";

export function ProjectsPage() {
  const { data: projects, isLoading, error, refetch } = useProjects();
  const { data: workspaceFolders } = useWorkspaceFolders();
  const initProject = useInitProject();
  const deleteProject = useDeleteProject();

  const [newProjectName, setNewProjectName] = useState("");
  const [selectedFolder, setSelectedFolder] = useState<string>("new");
  const [showNewProject, setShowNewProject] = useState(false);
  const [projectToDelete, setProjectToDelete] = useState<string | null>(null);
  const [deleteSource, setDeleteSource] = useState(false);

  // Filter folders that are NOT already projects
  const availableFolders = useMemo(() => {
    if (!workspaceFolders) return [];
    return workspaceFolders.filter((f) => !f.is_project);
  }, [workspaceFolders]);

  const handleCreateProject = async () => {
    const nameToUse =
      selectedFolder === "new" ? newProjectName : selectedFolder;

    if (!nameToUse.trim()) return;

    try {
      await initProject.mutateAsync(nameToUse);
      setNewProjectName("");
      setSelectedFolder("new");
      setShowNewProject(false);
    } catch (e) {
      console.error("Failed to create project:", e);
    }
  };

  const handleDeleteProject = async () => {
    if (!projectToDelete) return;
    try {
      await deleteProject.mutateAsync({
        name: projectToDelete,
        removeSource: deleteSource,
      });
      setProjectToDelete(null);
      setDeleteSource(false);
    } catch (e) {
      console.error("Failed to delete project:", e);
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-[50vh]">
        <div className="flex flex-col items-center gap-4">
          <RefreshCw className="h-10 w-10 animate-spin text-primary" />
          <p className="text-muted-foreground animate-pulse">
            Loading workspace...
          </p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-[50vh] space-y-6">
        <div className="bg-destructive/10 p-6 rounded-full">
          <FolderOpen className="h-12 w-12 text-destructive" />
        </div>
        <div className="text-center space-y-2">
          <h3 className="text-xl font-semibold">Failed to load projects</h3>
          <p className="text-muted-foreground max-w-md">{error.message}</p>
        </div>
        <Button onClick={() => refetch()} variant="outline">
          Try Again
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-8 animate-fade-in-up">
      <div className="flex items-center justify-between">
        <div className="space-y-1">
          <h1 className="text-4xl font-bold tracking-tight bg-gradient-to-r from-foreground to-foreground/60 bg-clip-text text-transparent">
            Projects
          </h1>
          <p className="text-lg text-muted-foreground">
            Manage your Conductor orchestration projects
          </p>
        </div>
        <div className="flex items-center space-x-3">
          <Button variant="outline" onClick={() => refetch()} className="group">
            <RefreshCw className="h-4 w-4 mr-2 group-hover:rotate-180 transition-transform" />
            Refresh
          </Button>
          <Button
            onClick={() => setShowNewProject(true)}
            className="shadow-lg shadow-primary/25 hover:shadow-primary/40 transition-shadow"
          >
            <Plus className="h-4 w-4 mr-2" />
            New Project
          </Button>
        </div>
      </div>

      {/* Project list */}
      {projects && projects.length > 0 ? (
        <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
          {projects.map((project, index) => (
            <div
              key={project.name}
              className="group relative"
              style={{ animationDelay: `${index * 50}ms` }}
            >
              <Link
                to="/project/$name"
                params={{ name: project.name }}
                className="block h-full"
              >
                <Card className="h-full hover:shadow-xl hover:ring-2 hover:ring-primary/20 transition-all duration-300 hover:-translate-y-1">
                  <CardHeader className="pb-3">
                    <div className="flex items-center justify-between mb-2">
                      <Badge
                        variant="outline"
                        className={cn(
                          "uppercase text-[10px] tracking-wider font-semibold",
                          getStatusColor(
                            project.workflow_status || "not_started",
                          ),
                        )}
                      >
                        {project.workflow_status?.replace(/_/g, " ") ||
                          "Not Started"}
                      </Badge>
                      <button
                        onClick={(e) => {
                          e.preventDefault();
                          e.stopPropagation();
                          setProjectToDelete(project.name);
                        }}
                        className="text-muted-foreground hover:text-destructive transition-colors p-1 rounded-md hover:bg-destructive/10"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
                    <CardTitle className="text-xl font-bold line-clamp-1 flex items-center gap-2">
                      <Folder className="h-5 w-5 text-primary/60" />
                      {project.name}
                    </CardTitle>
                    <CardDescription className="text-xs font-mono truncate pl-7">
                      {project.path}
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-4">
                      <div className="flex items-center justify-between text-sm py-2 border-b border-border/50">
                        <span className="text-muted-foreground flex items-center gap-2">
                          <Terminal className="h-3 w-3" /> Phase
                        </span>
                        <span className="font-medium bg-secondary px-2 py-0.5 rounded-full text-xs">
                          {project.current_phase > 0
                            ? `${project.current_phase}/5: ${getPhaseName(
                                project.current_phase,
                              )}`
                            : "Ready to start"}
                        </span>
                      </div>

                      <div className="flex items-center justify-between text-sm py-2 border-b border-border/50">
                        <span className="text-muted-foreground flex items-center gap-2">
                          <Clock className="h-3 w-3" /> Updated
                        </span>
                        <span className="text-xs">
                          {project.last_activity
                            ? formatDate(project.last_activity)
                            : "Never"}
                        </span>
                      </div>

                      <div className="flex items-center gap-2 pt-2">
                        {project.has_documents && (
                          <Badge
                            variant="secondary"
                            className="text-[10px] bg-blue-500/10 text-blue-600 dark:text-blue-400 border-transparent"
                          >
                            DOCS
                          </Badge>
                        )}
                        {project.has_claude_md && (
                          <Badge
                            variant="secondary"
                            className="text-[10px] bg-purple-500/10 text-purple-600 dark:text-purple-400 border-transparent"
                          >
                            AI
                          </Badge>
                        )}
                        {project.has_cursor_rules && (
                          <Badge
                            variant="secondary"
                            className="text-[10px] bg-slate-500/10 text-slate-600 dark:text-slate-400 border-transparent"
                          >
                            CURSOR
                          </Badge>
                        )}
                      </div>
                    </div>
                  </CardContent>
                </Card>
              </Link>
            </div>
          ))}
        </div>
      ) : (
        <Card className="border-dashed border-2 bg-muted/30">
          <CardContent className="flex flex-col items-center justify-center py-20 animate-fade-in-up">
            <div className="bg-background p-4 rounded-full shadow-sm mb-6 ring-1 ring-border">
              <FolderOpen className="h-12 w-12 text-muted-foreground" />
            </div>
            <h3 className="text-xl font-bold mb-2">No projects found</h3>
            <p className="text-muted-foreground text-center max-w-sm mb-8">
              Get started by creating a new orchestration project or importing
              an existing folder.
            </p>
            <Button
              onClick={() => setShowNewProject(true)}
              size="lg"
              className="shadow-lg"
            >
              <Plus className="h-5 w-5 mr-2" />
              Create First Project
            </Button>
          </CardContent>
        </Card>
      )}

      {/* New Project Dialog */}
      <Dialog open={showNewProject} onOpenChange={setShowNewProject}>
        <DialogContent className="sm:max-w-[500px]">
          <DialogHeader>
            <DialogTitle>Initialize Project</DialogTitle>
            <DialogDescription>
              Create a new project or initialize an existing workspace folder.
            </DialogDescription>
          </DialogHeader>

          <div className="grid gap-6 py-4">
            <div className="space-y-2">
              <Label>Source</Label>
              <Select value={selectedFolder} onValueChange={setSelectedFolder}>
                <SelectTrigger>
                  <SelectValue placeholder="Select source" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="new">
                    <span className="flex items-center">
                      <Plus className="h-4 w-4 mr-2 text-muted-foreground" />
                      Create New Folder
                    </span>
                  </SelectItem>
                  {availableFolders && availableFolders.length > 0 && (
                    <>
                      <div className="px-2 py-1.5 text-xs font-semibold text-muted-foreground">
                        Existing Folders
                      </div>
                      {availableFolders.map((folder) => (
                        <SelectItem key={folder.name} value={folder.name}>
                          <span className="flex items-center">
                            <Folder className="h-4 w-4 mr-2 text-blue-500" />
                            {folder.name}
                          </span>
                        </SelectItem>
                      ))}
                    </>
                  )}
                </SelectContent>
              </Select>
            </div>

            {selectedFolder === "new" && (
              <div className="space-y-2 animate-accordion-down">
                <div className="flex items-center justify-between">
                  <Label htmlFor="projectName">Project Name</Label>
                  <span className="text-xs text-muted-foreground">
                    Max 64 chars
                  </span>
                </div>
                <Input
                  id="projectName"
                  placeholder="my-new-project"
                  value={newProjectName}
                  onChange={(e) => setNewProjectName(e.target.value)}
                  pattern="[a-zA-Z0-9_-]+"
                  className="font-mono"
                />
                <Guidance content="Use only letters, numbers, underscores, and hyphens." />
              </div>
            )}
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setShowNewProject(false)}>
              Cancel
            </Button>
            <Button
              onClick={handleCreateProject}
              disabled={initProject.isPending}
            >
              {initProject.isPending && (
                <RefreshCw className="h-4 w-4 mr-2 animate-spin" />
              )}
              {selectedFolder === "new"
                ? "Create Project"
                : "Initialize Project"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation Alert */}
      <AlertDialog
        open={!!projectToDelete}
        onOpenChange={(open) => !open && setProjectToDelete(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle className="text-destructive">
              Delete Project?
            </AlertDialogTitle>
            <AlertDialogDescription>
              This will permanently delete the workflow state for{" "}
              <strong>{projectToDelete}</strong>. This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>

          <div className="flex items-center space-x-2 py-4">
            <input
              type="checkbox"
              id="deleteSource"
              checked={deleteSource}
              onChange={(e) => setDeleteSource(e.target.checked)}
              className="h-4 w-4 rounded border-gray-300 text-destructive focus:ring-destructive"
            />
            <Label
              htmlFor="deleteSource"
              className="text-destructive font-medium cursor-pointer"
            >
              Also delete source files (Dangerous!)
            </Label>
          </div>

          <AlertDialogFooter>
            <AlertDialogCancel
              onClick={() => {
                setProjectToDelete(null);
                setDeleteSource(false);
              }}
            >
              Cancel
            </AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDeleteProject}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {deleteProject.isPending ? "Deleting..." : "Delete Project"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
