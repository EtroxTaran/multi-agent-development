import {
  Injectable,
  Logger,
  OnModuleInit,
  NotFoundException,
} from "@nestjs/common";
import { ConfigService } from "@nestjs/config";
import * as fs from "fs/promises";
import * as path from "path";
import { spawn } from "child_process";
import { existsSync } from "fs";
import { EventEmitter } from "events";

@Injectable()
export class OrchestratorClientService
  extends EventEmitter
  implements OnModuleInit
{
  private readonly logger = new Logger(OrchestratorClientService.name);
  private projectsRoot: string;
  private pythonCommand = "python3";
  private runnerScript: string;

  constructor(private configService: ConfigService) {
    super();
    // Assuming backend runs in dashboard/backend-nestjs
    const rootPath =
      this.configService.get<string>("CONDUCTOR_ROOT") ||
      path.resolve(process.cwd(), "../../");
    this.projectsRoot = path.join(rootPath, "projects");
    this.runnerScript = path.resolve(process.cwd(), "scripts/runner.py");
    this.logger.log(`Projects root resolved to: ${this.projectsRoot}`);
  }

  async onModuleInit() {
    await this.checkHealth();
  }

  async checkHealth(): Promise<boolean> {
    try {
      await fs.access(this.projectsRoot);
      const result = await this.spawnPython(["--help"]);
      if (result.includes("Conductor Runner")) {
        this.logger.log("Native Orchestrator integration healthy");
        return true;
      }
      return false;
    } catch (error) {
      this.logger.error(`Orchestrator health check failed: ${error}`);
      return false;
    }
  }

  // ==================== Private Helpers ====================

  private getProjectDir(projectName: string): string {
    return path.join(this.projectsRoot, projectName);
  }

  private async readJsonFile<T>(filePath: string): Promise<T | null> {
    try {
      if (!existsSync(filePath)) return null;
      const content = await fs.readFile(filePath, "utf-8");
      return JSON.parse(content) as T;
    } catch (e) {
      this.logger.error(`Failed to read JSON file ${filePath}: ${e}`);
      return null;
    }
  }

  private spawnPython(args: string[], projectName?: string): Promise<string> {
    return new Promise((resolve, reject) => {
      const fullArgs = [this.runnerScript, ...args];
      this.logger.debug(
        `Spawning: ${this.pythonCommand} ${fullArgs.join(" ")}`,
      );

      const child = spawn(this.pythonCommand, fullArgs, {
        cwd: path.resolve(this.projectsRoot, ".."),
        shell: false,
      });

      let stdout = "";
      let stderr = "";

      child.stdout.on("data", (data) => {
        const str = data.toString();
        stdout += str;

        if (projectName) {
          const lines = str.split("\n");
          for (const line of lines) {
            if (line.trim().startsWith("{")) {
              try {
                const event = JSON.parse(line);
                this.emit("event", projectName, event);
              } catch (e) {
                // Not JSON, ignore
              }
            }
          }
        }
      });

      child.stderr.on("data", (data) => {
        stderr += data.toString();
        if (data.toString().trim()) {
          this.logger.debug(`[Python] ${data.toString().trim()}`);
        }
      });

      child.on("close", (code) => {
        if (code !== 0) {
          reject(
            new Error(`Python command failed with code ${code}: ${stderr}`),
          );
        } else {
          resolve(stdout);
        }
      });

      child.on("error", (err) => {
        reject(err);
      });
    });
  }

  // ==================== Projects ====================

  async listProjects(): Promise<any[]> {
    try {
      const dirs = await fs.readdir(this.projectsRoot, { withFileTypes: true });
      const projects = [];

      for (const dir of dirs) {
        if (dir.isDirectory()) {
          const projectPath = path.join(this.projectsRoot, dir.name);
          const config = await this.readJsonFile<any>(
            path.join(projectPath, ".project-config.json"),
          );

          const hasProductMd = existsSync(path.join(projectPath, "PRODUCT.md"));

          if (config || hasProductMd) {
            const state = await this.readJsonFile<any>(
              path.join(projectPath, ".workflow", "state.json"),
            );

            // Get creation time from PRODUCT.md or .project-config.json or dir stat
            // Basic stat
            let createdAt = new Date().toISOString();
            try {
              const stats = await fs.stat(projectPath);
              createdAt = stats.birthtime.toISOString();
            } catch {}

            const hasDocs =
              existsSync(path.join(projectPath, "docs")) ||
              existsSync(path.join(projectPath, "Docs"));
            const hasClaudeMd = existsSync(path.join(projectPath, "CLAUDE.md"));
            const hasGeminiMd = existsSync(path.join(projectPath, "GEMINI.md"));
            const hasCursorRules = existsSync(
              path.join(projectPath, ".cursor/rules"),
            );

            projects.push({
              name: dir.name,
              path: projectPath,
              current_phase: state?.current_phase || 0,
              created_at: createdAt,
              has_product_spec: hasProductMd,
              has_documents: hasDocs,
              has_claude_md: hasClaudeMd,
              has_gemini_md: hasGeminiMd,
              has_cursor_rules: hasCursorRules,
            });
          }
        }
      }
      return projects;
    } catch (e) {
      this.logger.error(`List projects failed: ${e}`);
      return [];
    }
  }

  async getProject(projectName: string): Promise<any> {
    const projectDir = this.getProjectDir(projectName);
    if (!existsSync(projectDir)) {
      throw new NotFoundException(`Project ${projectName} not found`);
    }

    const config = await this.readJsonFile<any>(
      path.join(projectDir, ".project-config.json"),
    );
    const state = await this.readJsonFile<any>(
      path.join(projectDir, ".workflow", "state.json"),
    );

    // Map state.phases (dict) to expected structure if needed
    // state.json usually has "phases": { "planning": { ... } }
    // API might expect something else or pass it through.
    // mapToProjectStatus uses: data.phases
    // So passing state.phases is correct.

    return {
      name: projectName,
      path: projectDir,
      config: config || {},
      state: state || {},
      files: {},
      phases: state?.phases || {},
    };
  }

  async initProject(projectName: string): Promise<any> {
    try {
      // Use direct orchestrator module for init
      const child = spawn(
        this.pythonCommand,
        ["-m", "orchestrator", "--init-project", projectName],
        {
          cwd: path.resolve(this.projectsRoot, ".."),
          shell: false,
        },
      );

      return new Promise((resolve, reject) => {
        child.on("close", (code) => {
          if (code === 0)
            resolve({
              success: true,
              project_dir: this.getProjectDir(projectName),
            });
          else reject(new Error(`Init failed with code ${code}`));
        });
      });
    } catch (e) {
      return { success: false, error: (e as Error).message };
    }
  }

  async deleteProject(projectName: string, removeSource = false): Promise<any> {
    const projectDir = this.getProjectDir(projectName);
    try {
      if (removeSource) {
        await fs.rm(projectDir, { recursive: true, force: true });
      } else {
        await fs.rm(path.join(projectDir, ".workflow"), {
          recursive: true,
          force: true,
        });
        await fs.rm(path.join(projectDir, ".project-config.json"), {
          force: true,
        });
      }
      return { success: true };
    } catch (e) {
      throw new Error(`Failed to delete project: ${(e as Error).message}`);
    }
  }

  // ==================== Workflow ====================

  async getWorkflowStatus(projectName: string): Promise<any> {
    const state = await this.readJsonFile<any>(
      path.join(this.getProjectDir(projectName), ".workflow", "state.json"),
    );

    // Map state.json to API response format
    const phaseStatus = state?.phases
      ? Object.fromEntries(
          Object.entries(state.phases).map(([k, v]: [string, any]) => [
            k,
            v.status,
          ]),
        )
      : {};

    return {
      mode: "langgraph",
      status: state?.current_phase ? "in_progress" : "not_started",
      project: projectName,
      current_phase: state?.current_phase,
      phase_status: phaseStatus, // WorkflowStatusResponseDto expects simple map
      pending_interrupt: null, // TODO: Read from runner status if possible
    };
  }

  async getWorkflowHealth(projectName: string): Promise<any> {
    const state = await this.readJsonFile<any>(
      path.join(this.getProjectDir(projectName), ".workflow", "state.json"),
    );

    const phaseStatus = state?.phases
      ? Object.fromEntries(
          Object.entries(state.phases).map(([k, v]: [string, any]) => [
            k,
            v.status,
          ]),
        )
      : {};

    return {
      status: "healthy",
      project: projectName,
      current_phase: state?.current_phase,
      phase_status: phaseStatus,
      iteration_count: state?.iteration_count,
      last_updated: state?.updated_at,
    };
  }

  async getWorkflowGraph(projectName: string): Promise<any> {
    try {
      const result = await this.spawnPython([
        "--project",
        projectName,
        "--graph",
      ]);
      // The result will be JSON from stdout
      // But spawnPython accumulates ALL stdout. runner.py might print other things?
      // runner.py only prints json dumps. ONE json dump per action usually.
      // But logging config causes stderr logs.
      // stdout should be clean.
      // However, if there are multiple lines (e.g. from imports printing stuff), it might break.
      // I'll try to find the last valid JSON line or just parse valid lines.
      // Graph is one big JSON object.
      return JSON.parse(result);
    } catch (e) {
      this.logger.error(`Get graph failed: ${e}`);
      return { nodes: [], edges: [] };
    }
  }

  async startWorkflow(
    projectName: string,
    options: {
      startPhase?: number;
      endPhase?: number;
      skipValidation?: boolean;
      autonomous?: boolean;
    } = {},
  ): Promise<any> {
    const args = ["--project", projectName, "--start"];
    if (options.startPhase) {
      args.push("--phase");
      args.push(options.startPhase.toString());
    }
    if (options.endPhase) {
      args.push("--end-phase");
      args.push(options.endPhase.toString());
    }
    if (options.skipValidation) args.push("--skip-validation");
    if (options.autonomous) args.push("--autonomous");

    this.spawnPython(args, projectName).catch((err) =>
      this.logger.error(`Workflow background error: ${err}`),
    );

    return { success: true, message: "Workflow started in background" };
  }

  async resumeWorkflow(projectName: string, autonomous = false): Promise<any> {
    const args = ["--project", projectName, "--resume"];
    if (autonomous) args.push("--autonomous");

    this.spawnPython(args, projectName).catch((err) =>
      this.logger.error(`Workflow resume error: ${err}`),
    );

    return { success: true, message: "Workflow resumed in background" };
  }

  async rollbackWorkflow(projectName: string, phase: number): Promise<any> {
    const args = ["--project", projectName, "--rollback", phase.toString()];
    const res = await this.spawnPython(args, projectName);
    try {
      const json = JSON.parse(res);
      if (json.type === "rollback") return json.data;
      return { success: true };
    } catch {
      return { success: true };
    }
  }

  async resetWorkflow(projectName: string): Promise<any> {
    const args = ["--project", projectName, "--reset"];
    await this.spawnPython(args, projectName);
    return { success: true };
  }

  // ==================== Tasks ====================

  async getTasks(projectName: string): Promise<any> {
    const state = await this.readJsonFile<any>(
      path.join(this.getProjectDir(projectName), ".workflow", "state.json"),
    );

    const tasks =
      state?.metadata?.task_breakdown?.tasks ||
      state?.task_breakdown?.tasks ||
      [];
    return {
      tasks,
      total: tasks.length,
      completed: tasks.filter((t: any) => t.status === "completed").length,
      in_progress: tasks.filter((t: any) => t.status === "in_progress").length,
      pending: tasks.filter((t: any) => t.status === "pending").length,
      failed: tasks.filter((t: any) => t.status === "failed").length,
    };
  }

  async getTask(projectName: string, taskId: string): Promise<any> {
    const resp = await this.getTasks(projectName);
    const task = resp.tasks.find((t: any) => t.id === taskId);
    if (!task) throw new NotFoundException(`Task ${taskId} not found`);
    return task;
  }

  async getTaskHistory(
    projectName: string,
    taskId: string,
    limit = 100,
  ): Promise<any> {
    return { entries: [], total: 0 };
  }

  // ==================== Budget ====================

  async getBudget(projectName: string): Promise<any> {
    const budget = await this.readJsonFile<any>(
      path.join(this.getProjectDir(projectName), ".workflow", "budget.json"),
    );
    return budget || {};
  }

  async getBudgetReport(projectName: string): Promise<any> {
    return { status: await this.getBudget(projectName), task_spending: [] };
  }

  // ==================== Agents & Audit ====================

  async getAgents(projectName: string): Promise<any> {
    return {};
  }

  async getAudit(projectName: string, options: any): Promise<any> {
    return { entries: [], total: 0 };
  }

  async getAuditStatistics(
    projectName: string,
    sinceHours?: number,
  ): Promise<any> {
    return {};
  }

  // ==================== Chat ====================

  async chat(
    message: string,
    projectName?: string,
    context?: any,
  ): Promise<any> {
    this.logger.warn("Chat not yet implemented in native mode");
    return { message: "Chat unavailable in migration mode", streaming: false };
  }

  async executeCommand(
    command: string,
    args: string[],
    projectName?: string,
  ): Promise<any> {
    this.logger.warn("Execute command not implemented");
    return { success: false, error: "Not implemented" };
  }
}
