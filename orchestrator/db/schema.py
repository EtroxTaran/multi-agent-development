"""SurrealDB schema definitions.

Defines tables, fields, indexes, and relationships for the orchestrator.
Schema is applied automatically on first connection to a database.

NOTE: This module now delegates to the migrations system for schema management.
The SCHEMA_DEFINITIONS constant is kept for reference but apply_schema() uses
the migration runner to apply versioned migrations.
"""

import logging
from typing import Optional

from ..security import validate_sql_field, validate_sql_table
from .connection import Connection, get_connection

logger = logging.getLogger(__name__)


# Schema version for migrations
# v2.0.0 - Per-project database isolation (removed project_name columns)
# v2.1.0 - Added phase_outputs and logs tables for DB-only storage
# v2.2.0 - Use FLEXIBLE TYPE object for nested objects (fixes SurrealDB v2.x issue)
# v2.3.0 - Added auto-improvement tables (agent_evaluations, prompt_versions, golden_examples, optimization_history)
# v2.4.0 - Added LangGraph persistence tables (graph_checkpoints, graph_writes)
SCHEMA_VERSION = "2.4.0"


SCHEMA_DEFINITIONS = """
-- ============================================
-- Meta-Architect Orchestrator Schema v2.0.0
-- ============================================
-- NOTE: This schema is designed for per-project database isolation.
-- Each project gets its own database, so project_name columns are removed.
-- All queries within a database are implicitly scoped to that project.

-- Schema version tracking
DEFINE TABLE IF NOT EXISTS schema_version SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS version ON TABLE schema_version TYPE string;
DEFINE FIELD IF NOT EXISTS applied_at ON TABLE schema_version TYPE datetime DEFAULT time::now();

-- ============================================
-- Workflow State (one per database/project)
-- ============================================

DEFINE TABLE IF NOT EXISTS workflow_state SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS project_dir ON TABLE workflow_state TYPE string;
DEFINE FIELD IF NOT EXISTS current_phase ON TABLE workflow_state TYPE int DEFAULT 1;
DEFINE FIELD IF NOT EXISTS phase_status ON TABLE workflow_state FLEXIBLE TYPE object DEFAULT {};
DEFINE FIELD IF NOT EXISTS iteration_count ON TABLE workflow_state TYPE int DEFAULT 0;
DEFINE FIELD IF NOT EXISTS plan ON TABLE workflow_state FLEXIBLE TYPE option<object>;
DEFINE FIELD IF NOT EXISTS validation_feedback ON TABLE workflow_state FLEXIBLE TYPE option<object>;
DEFINE FIELD IF NOT EXISTS verification_feedback ON TABLE workflow_state FLEXIBLE TYPE option<object>;
DEFINE FIELD IF NOT EXISTS implementation_result ON TABLE workflow_state FLEXIBLE TYPE option<object>;
DEFINE FIELD IF NOT EXISTS next_decision ON TABLE workflow_state TYPE option<string>;
DEFINE FIELD IF NOT EXISTS execution_mode ON TABLE workflow_state TYPE string DEFAULT "afk";
DEFINE FIELD IF NOT EXISTS discussion_complete ON TABLE workflow_state TYPE bool DEFAULT false;
DEFINE FIELD IF NOT EXISTS research_complete ON TABLE workflow_state TYPE bool DEFAULT false;
DEFINE FIELD IF NOT EXISTS research_findings ON TABLE workflow_state FLEXIBLE TYPE option<object>;
DEFINE FIELD IF NOT EXISTS token_usage ON TABLE workflow_state FLEXIBLE TYPE option<object>;
DEFINE FIELD IF NOT EXISTS created_at ON TABLE workflow_state TYPE datetime DEFAULT time::now();
DEFINE FIELD IF NOT EXISTS updated_at ON TABLE workflow_state TYPE datetime DEFAULT time::now();

-- ============================================
-- Tasks
-- ============================================

DEFINE TABLE IF NOT EXISTS tasks SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS task_id ON TABLE tasks TYPE string ASSERT $value != NONE;
DEFINE FIELD IF NOT EXISTS title ON TABLE tasks TYPE string;
DEFINE FIELD IF NOT EXISTS user_story ON TABLE tasks TYPE string;
DEFINE FIELD IF NOT EXISTS acceptance_criteria ON TABLE tasks TYPE array<string> DEFAULT [];
DEFINE FIELD IF NOT EXISTS dependencies ON TABLE tasks TYPE array<string> DEFAULT [];
DEFINE FIELD IF NOT EXISTS status ON TABLE tasks TYPE string DEFAULT "pending";
DEFINE FIELD IF NOT EXISTS priority ON TABLE tasks TYPE string DEFAULT "medium";
DEFINE FIELD IF NOT EXISTS milestone_id ON TABLE tasks TYPE option<string>;
DEFINE FIELD IF NOT EXISTS estimated_complexity ON TABLE tasks TYPE string DEFAULT "medium";
DEFINE FIELD IF NOT EXISTS files_to_create ON TABLE tasks TYPE array<string> DEFAULT [];
DEFINE FIELD IF NOT EXISTS files_to_modify ON TABLE tasks TYPE array<string> DEFAULT [];
DEFINE FIELD IF NOT EXISTS test_files ON TABLE tasks TYPE array<string> DEFAULT [];
DEFINE FIELD IF NOT EXISTS attempts ON TABLE tasks TYPE int DEFAULT 0;
DEFINE FIELD IF NOT EXISTS max_attempts ON TABLE tasks TYPE int DEFAULT 3;
DEFINE FIELD IF NOT EXISTS linear_issue_id ON TABLE tasks TYPE option<string>;
DEFINE FIELD IF NOT EXISTS implementation_notes ON TABLE tasks TYPE string DEFAULT "";
DEFINE FIELD IF NOT EXISTS error ON TABLE tasks TYPE option<string>;
DEFINE FIELD IF NOT EXISTS created_at ON TABLE tasks TYPE datetime DEFAULT time::now();
DEFINE FIELD IF NOT EXISTS updated_at ON TABLE tasks TYPE datetime DEFAULT time::now();

DEFINE INDEX IF NOT EXISTS idx_tasks_id ON TABLE tasks COLUMNS task_id UNIQUE;
DEFINE INDEX IF NOT EXISTS idx_tasks_status ON TABLE tasks COLUMNS status;
DEFINE INDEX IF NOT EXISTS idx_tasks_priority ON TABLE tasks COLUMNS priority;

-- ============================================
-- Milestones
-- ============================================

DEFINE TABLE IF NOT EXISTS milestones SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS milestone_id ON TABLE milestones TYPE string ASSERT $value != NONE;
DEFINE FIELD IF NOT EXISTS name ON TABLE milestones TYPE string;
DEFINE FIELD IF NOT EXISTS description ON TABLE milestones TYPE string;
DEFINE FIELD IF NOT EXISTS task_ids ON TABLE milestones TYPE array<string> DEFAULT [];
DEFINE FIELD IF NOT EXISTS status ON TABLE milestones TYPE string DEFAULT "pending";
DEFINE FIELD IF NOT EXISTS created_at ON TABLE milestones TYPE datetime DEFAULT time::now();

DEFINE INDEX IF NOT EXISTS idx_milestones_id ON TABLE milestones COLUMNS milestone_id UNIQUE;

-- ============================================
-- Audit Trail
-- ============================================

DEFINE TABLE IF NOT EXISTS audit_entries SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS entry_id ON TABLE audit_entries TYPE string ASSERT $value != NONE;
DEFINE FIELD IF NOT EXISTS agent ON TABLE audit_entries TYPE string ASSERT $value != NONE;
DEFINE FIELD IF NOT EXISTS task_id ON TABLE audit_entries TYPE string;
DEFINE FIELD IF NOT EXISTS session_id ON TABLE audit_entries TYPE option<string>;
DEFINE FIELD IF NOT EXISTS prompt_hash ON TABLE audit_entries TYPE string;
DEFINE FIELD IF NOT EXISTS prompt_length ON TABLE audit_entries TYPE int DEFAULT 0;
DEFINE FIELD IF NOT EXISTS command_args ON TABLE audit_entries TYPE array<string> DEFAULT [];
DEFINE FIELD IF NOT EXISTS exit_code ON TABLE audit_entries TYPE int DEFAULT 0;
DEFINE FIELD IF NOT EXISTS status ON TABLE audit_entries TYPE string DEFAULT "pending";
DEFINE FIELD IF NOT EXISTS duration_seconds ON TABLE audit_entries TYPE float DEFAULT 0.0;
DEFINE FIELD IF NOT EXISTS output_length ON TABLE audit_entries TYPE int DEFAULT 0;
DEFINE FIELD IF NOT EXISTS error_length ON TABLE audit_entries TYPE int DEFAULT 0;
DEFINE FIELD IF NOT EXISTS parsed_output_type ON TABLE audit_entries TYPE option<string>;
DEFINE FIELD IF NOT EXISTS cost_usd ON TABLE audit_entries TYPE option<float>;
DEFINE FIELD IF NOT EXISTS model ON TABLE audit_entries TYPE option<string>;
DEFINE FIELD IF NOT EXISTS metadata ON TABLE audit_entries FLEXIBLE TYPE object DEFAULT {};
DEFINE FIELD IF NOT EXISTS timestamp ON TABLE audit_entries TYPE datetime DEFAULT time::now();

DEFINE INDEX IF NOT EXISTS idx_audit_entry ON TABLE audit_entries COLUMNS entry_id UNIQUE;
DEFINE INDEX IF NOT EXISTS idx_audit_task ON TABLE audit_entries COLUMNS task_id;
DEFINE INDEX IF NOT EXISTS idx_audit_agent ON TABLE audit_entries COLUMNS agent;
DEFINE INDEX IF NOT EXISTS idx_audit_status ON TABLE audit_entries COLUMNS status;
DEFINE INDEX IF NOT EXISTS idx_audit_timestamp ON TABLE audit_entries COLUMNS timestamp;

-- ============================================
-- Error Patterns (for learning within project)
-- ============================================

DEFINE TABLE IF NOT EXISTS error_patterns SCHEMALESS;
DEFINE FIELD IF NOT EXISTS task_id ON TABLE error_patterns TYPE string;
DEFINE FIELD IF NOT EXISTS error_type ON TABLE error_patterns TYPE string;
DEFINE FIELD IF NOT EXISTS error_message ON TABLE error_patterns TYPE string;
DEFINE FIELD IF NOT EXISTS error_context ON TABLE error_patterns FLEXIBLE TYPE object DEFAULT {};
DEFINE FIELD IF NOT EXISTS solution ON TABLE error_patterns TYPE option<string>;
DEFINE FIELD IF NOT EXISTS embedding ON TABLE error_patterns TYPE option<array<float>>;
DEFINE FIELD IF NOT EXISTS created_at ON TABLE error_patterns TYPE datetime DEFAULT time::now();

DEFINE INDEX IF NOT EXISTS idx_error_type ON TABLE error_patterns COLUMNS error_type;
DEFINE INDEX IF NOT EXISTS idx_error_task ON TABLE error_patterns COLUMNS task_id;

-- Vector index for semantic search (when embeddings are added)
-- DEFINE INDEX IF NOT EXISTS idx_error_embedding ON TABLE error_patterns
--     COLUMNS embedding MTREE DIMENSION 1536 DIST COSINE;

-- ============================================
-- Checkpoints
-- ============================================

DEFINE TABLE IF NOT EXISTS checkpoints SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS checkpoint_id ON TABLE checkpoints TYPE string ASSERT $value != NONE;
DEFINE FIELD IF NOT EXISTS name ON TABLE checkpoints TYPE string;
DEFINE FIELD IF NOT EXISTS notes ON TABLE checkpoints TYPE string DEFAULT "";
DEFINE FIELD IF NOT EXISTS phase ON TABLE checkpoints TYPE int;
DEFINE FIELD IF NOT EXISTS task_progress ON TABLE checkpoints FLEXIBLE TYPE object DEFAULT {};
DEFINE FIELD IF NOT EXISTS state_snapshot ON TABLE checkpoints FLEXIBLE TYPE object DEFAULT {};
DEFINE FIELD IF NOT EXISTS files_snapshot ON TABLE checkpoints TYPE array<string> DEFAULT [];
DEFINE FIELD IF NOT EXISTS created_at ON TABLE checkpoints TYPE datetime DEFAULT time::now();

DEFINE INDEX IF NOT EXISTS idx_checkpoint_id ON TABLE checkpoints COLUMNS checkpoint_id UNIQUE;
DEFINE INDEX IF NOT EXISTS idx_checkpoint_time ON TABLE checkpoints COLUMNS created_at;

-- ============================================
-- Git Commits
-- ============================================

DEFINE TABLE IF NOT EXISTS git_commits SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS commit_hash ON TABLE git_commits TYPE string ASSERT $value != NONE;
DEFINE FIELD IF NOT EXISTS task_id ON TABLE git_commits TYPE option<string>;
DEFINE FIELD IF NOT EXISTS message ON TABLE git_commits TYPE string;
DEFINE FIELD IF NOT EXISTS files_changed ON TABLE git_commits TYPE array<string> DEFAULT [];
DEFINE FIELD IF NOT EXISTS created_at ON TABLE git_commits TYPE datetime DEFAULT time::now();

DEFINE INDEX IF NOT EXISTS idx_commits_hash ON TABLE git_commits COLUMNS commit_hash UNIQUE;
DEFINE INDEX IF NOT EXISTS idx_commits_task ON TABLE git_commits COLUMNS task_id;

-- ============================================
-- Session Management
-- ============================================

DEFINE TABLE IF NOT EXISTS sessions SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS session_id ON TABLE sessions TYPE string ASSERT $value != NONE;
DEFINE FIELD IF NOT EXISTS task_id ON TABLE sessions TYPE string;
DEFINE FIELD IF NOT EXISTS agent ON TABLE sessions TYPE string;
DEFINE FIELD IF NOT EXISTS status ON TABLE sessions TYPE string DEFAULT "active";
DEFINE FIELD IF NOT EXISTS invocation_count ON TABLE sessions TYPE int DEFAULT 0;
DEFINE FIELD IF NOT EXISTS total_cost_usd ON TABLE sessions TYPE float DEFAULT 0.0;
DEFINE FIELD IF NOT EXISTS created_at ON TABLE sessions TYPE datetime DEFAULT time::now();
DEFINE FIELD IF NOT EXISTS updated_at ON TABLE sessions TYPE datetime DEFAULT time::now();
DEFINE FIELD IF NOT EXISTS closed_at ON TABLE sessions TYPE option<datetime>;

DEFINE INDEX IF NOT EXISTS idx_sessions_id ON TABLE sessions COLUMNS session_id UNIQUE;
DEFINE INDEX IF NOT EXISTS idx_sessions_task ON TABLE sessions COLUMNS task_id;
DEFINE INDEX IF NOT EXISTS idx_sessions_active ON TABLE sessions COLUMNS status;

-- ============================================
-- Budget Tracking
-- ============================================

DEFINE TABLE IF NOT EXISTS budget_records SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS task_id ON TABLE budget_records TYPE option<string>;
DEFINE FIELD IF NOT EXISTS agent ON TABLE budget_records TYPE string;
DEFINE FIELD IF NOT EXISTS cost_usd ON TABLE budget_records TYPE float ASSERT $value >= 0;
DEFINE FIELD IF NOT EXISTS tokens_input ON TABLE budget_records TYPE option<int>;
DEFINE FIELD IF NOT EXISTS tokens_output ON TABLE budget_records TYPE option<int>;
DEFINE FIELD IF NOT EXISTS model ON TABLE budget_records TYPE option<string>;
DEFINE FIELD IF NOT EXISTS created_at ON TABLE budget_records TYPE datetime DEFAULT time::now();

DEFINE INDEX IF NOT EXISTS idx_budget_task ON TABLE budget_records COLUMNS task_id;
DEFINE INDEX IF NOT EXISTS idx_budget_time ON TABLE budget_records COLUMNS created_at;
DEFINE INDEX IF NOT EXISTS idx_budget_agent ON TABLE budget_records COLUMNS agent;

-- ============================================
-- Live Query Events (for monitoring)
-- ============================================

DEFINE TABLE IF NOT EXISTS workflow_events SCHEMALESS;
DEFINE FIELD IF NOT EXISTS event_type ON TABLE workflow_events TYPE string;
DEFINE FIELD IF NOT EXISTS event_data ON TABLE workflow_events FLEXIBLE TYPE object DEFAULT {};
DEFINE FIELD IF NOT EXISTS created_at ON TABLE workflow_events TYPE datetime DEFAULT time::now();

DEFINE INDEX IF NOT EXISTS idx_events_type ON TABLE workflow_events COLUMNS event_type;
DEFINE INDEX IF NOT EXISTS idx_events_time ON TABLE workflow_events COLUMNS created_at;

-- Auto-cleanup old events (keep last 7 days)
-- Events older than 7 days should be pruned by application

-- ============================================
-- Phase Outputs (plan.json, feedback, reviews)
-- ============================================
-- Stores structured output from each workflow phase:
-- Phase 1: plan (planning output)
-- Phase 2: cursor_feedback, gemini_feedback (validation)
-- Phase 3: task_result (per-task implementation output)
-- Phase 4: cursor_review, gemini_review (verification)
-- Phase 5: summary (completion output)

DEFINE TABLE IF NOT EXISTS phase_outputs SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS phase ON TABLE phase_outputs TYPE int ASSERT $value >= 1 AND $value <= 5;
DEFINE FIELD IF NOT EXISTS output_type ON TABLE phase_outputs TYPE string ASSERT $value != NONE;
DEFINE FIELD IF NOT EXISTS content ON TABLE phase_outputs FLEXIBLE TYPE object DEFAULT {};
DEFINE FIELD IF NOT EXISTS task_id ON TABLE phase_outputs TYPE option<string>;
DEFINE FIELD IF NOT EXISTS created_at ON TABLE phase_outputs TYPE datetime DEFAULT time::now();
DEFINE FIELD IF NOT EXISTS updated_at ON TABLE phase_outputs TYPE datetime DEFAULT time::now();

DEFINE INDEX IF NOT EXISTS idx_phase_output ON TABLE phase_outputs COLUMNS phase, output_type;
DEFINE INDEX IF NOT EXISTS idx_phase_output_task ON TABLE phase_outputs COLUMNS task_id;

-- ============================================
-- Logs (UAT documents, handoff briefs, etc)
-- ============================================
-- Stores various workflow artifacts that don't fit in phase_outputs:
-- - uat_document: User Acceptance Test documents per task
-- - handoff_brief: Session resume documents
-- - discussion: Discussion phase notes
-- - research: Research findings

DEFINE TABLE IF NOT EXISTS logs SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS log_type ON TABLE logs TYPE string ASSERT $value != NONE;
DEFINE FIELD IF NOT EXISTS task_id ON TABLE logs TYPE option<string>;
DEFINE FIELD IF NOT EXISTS content ON TABLE logs FLEXIBLE TYPE object DEFAULT {};
DEFINE FIELD IF NOT EXISTS metadata ON TABLE logs FLEXIBLE TYPE object DEFAULT {};
DEFINE FIELD IF NOT EXISTS created_at ON TABLE logs TYPE datetime DEFAULT time::now();

DEFINE INDEX IF NOT EXISTS idx_logs_type ON TABLE logs COLUMNS log_type;
DEFINE INDEX IF NOT EXISTS idx_logs_task ON TABLE logs COLUMNS task_id;
DEFINE INDEX IF NOT EXISTS idx_logs_time ON TABLE logs COLUMNS created_at;

-- ============================================
-- Agent Evaluations (auto-improvement system)
-- ============================================
-- Stores G-Eval results for every agent execution:
-- - Per-criterion scores (task_completion, output_quality, etc.)
-- - Overall weighted score
-- - Improvement suggestions
-- - Prompt hash for tracking performance by prompt

DEFINE TABLE IF NOT EXISTS agent_evaluations SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS evaluation_id ON TABLE agent_evaluations TYPE string ASSERT $value != NONE;
DEFINE FIELD IF NOT EXISTS agent ON TABLE agent_evaluations TYPE string ASSERT $value != NONE;
DEFINE FIELD IF NOT EXISTS node ON TABLE agent_evaluations TYPE string ASSERT $value != NONE;
DEFINE FIELD IF NOT EXISTS task_id ON TABLE agent_evaluations TYPE option<string>;
DEFINE FIELD IF NOT EXISTS session_id ON TABLE agent_evaluations TYPE option<string>;
DEFINE FIELD IF NOT EXISTS scores ON TABLE agent_evaluations FLEXIBLE TYPE object DEFAULT {};
DEFINE FIELD IF NOT EXISTS overall_score ON TABLE agent_evaluations TYPE float ASSERT $value >= 0.0 AND $value <= 10.0;
DEFINE FIELD IF NOT EXISTS feedback ON TABLE agent_evaluations TYPE string DEFAULT "";
DEFINE FIELD IF NOT EXISTS suggestions ON TABLE agent_evaluations TYPE array<string> DEFAULT [];
DEFINE FIELD IF NOT EXISTS prompt_hash ON TABLE agent_evaluations TYPE string ASSERT $value != NONE;
DEFINE FIELD IF NOT EXISTS prompt_version ON TABLE agent_evaluations TYPE option<string>;
DEFINE FIELD IF NOT EXISTS evaluator_model ON TABLE agent_evaluations TYPE string DEFAULT "haiku";
DEFINE FIELD IF NOT EXISTS metadata ON TABLE agent_evaluations FLEXIBLE TYPE object DEFAULT {};
DEFINE FIELD IF NOT EXISTS created_at ON TABLE agent_evaluations TYPE datetime DEFAULT time::now();

DEFINE INDEX IF NOT EXISTS idx_eval_id ON TABLE agent_evaluations COLUMNS evaluation_id UNIQUE;
DEFINE INDEX IF NOT EXISTS idx_eval_agent ON TABLE agent_evaluations COLUMNS agent;
DEFINE INDEX IF NOT EXISTS idx_eval_node ON TABLE agent_evaluations COLUMNS node;
DEFINE INDEX IF NOT EXISTS idx_eval_task ON TABLE agent_evaluations COLUMNS task_id;
DEFINE INDEX IF NOT EXISTS idx_eval_prompt ON TABLE agent_evaluations COLUMNS prompt_hash;
DEFINE INDEX IF NOT EXISTS idx_eval_score ON TABLE agent_evaluations COLUMNS overall_score;
DEFINE INDEX IF NOT EXISTS idx_eval_time ON TABLE agent_evaluations COLUMNS created_at;

-- ============================================
-- Prompt Versions (auto-improvement system)
-- ============================================
-- Stores versioned prompts with performance metrics:
-- - Version progression (parent_version for lineage)
-- - Status lifecycle (draft -> shadow -> canary -> production -> retired)
-- - Aggregated metrics from evaluations

DEFINE TABLE IF NOT EXISTS prompt_versions SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS version_id ON TABLE prompt_versions TYPE string ASSERT $value != NONE;
DEFINE FIELD IF NOT EXISTS agent ON TABLE prompt_versions TYPE string ASSERT $value != NONE;
DEFINE FIELD IF NOT EXISTS template_name ON TABLE prompt_versions TYPE string ASSERT $value != NONE;
DEFINE FIELD IF NOT EXISTS content ON TABLE prompt_versions TYPE string DEFAULT "";
DEFINE FIELD IF NOT EXISTS version ON TABLE prompt_versions TYPE int DEFAULT 1;
DEFINE FIELD IF NOT EXISTS metrics ON TABLE prompt_versions FLEXIBLE TYPE object DEFAULT {};
DEFINE FIELD IF NOT EXISTS parent_version ON TABLE prompt_versions TYPE option<string>;
DEFINE FIELD IF NOT EXISTS optimization_method ON TABLE prompt_versions TYPE string DEFAULT "manual";
DEFINE FIELD IF NOT EXISTS status ON TABLE prompt_versions TYPE string DEFAULT "draft";
DEFINE FIELD IF NOT EXISTS created_at ON TABLE prompt_versions TYPE datetime DEFAULT time::now();
DEFINE FIELD IF NOT EXISTS updated_at ON TABLE prompt_versions TYPE datetime DEFAULT time::now();

DEFINE INDEX IF NOT EXISTS idx_pv_id ON TABLE prompt_versions COLUMNS version_id UNIQUE;
DEFINE INDEX IF NOT EXISTS idx_pv_agent ON TABLE prompt_versions COLUMNS agent;
DEFINE INDEX IF NOT EXISTS idx_pv_template ON TABLE prompt_versions COLUMNS template_name;
DEFINE INDEX IF NOT EXISTS idx_pv_status ON TABLE prompt_versions COLUMNS status;
DEFINE INDEX IF NOT EXISTS idx_pv_version ON TABLE prompt_versions COLUMNS agent, template_name, version;

-- ============================================
-- Golden Examples (auto-improvement system)
-- ============================================
-- Stores high-quality output examples for few-shot learning:
-- - Captured from evaluations scoring >= 9.0
-- - Used for bootstrap optimization
-- - Grouped by agent and template

DEFINE TABLE IF NOT EXISTS golden_examples SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS example_id ON TABLE golden_examples TYPE string ASSERT $value != NONE;
DEFINE FIELD IF NOT EXISTS agent ON TABLE golden_examples TYPE string ASSERT $value != NONE;
DEFINE FIELD IF NOT EXISTS template_name ON TABLE golden_examples TYPE string ASSERT $value != NONE;
DEFINE FIELD IF NOT EXISTS input_prompt ON TABLE golden_examples TYPE string DEFAULT "";
DEFINE FIELD IF NOT EXISTS output ON TABLE golden_examples TYPE string DEFAULT "";
DEFINE FIELD IF NOT EXISTS score ON TABLE golden_examples TYPE float ASSERT $value >= 0.0 AND $value <= 10.0;
DEFINE FIELD IF NOT EXISTS evaluation_id ON TABLE golden_examples TYPE option<string>;
DEFINE FIELD IF NOT EXISTS metadata ON TABLE golden_examples FLEXIBLE TYPE object DEFAULT {};
DEFINE FIELD IF NOT EXISTS created_at ON TABLE golden_examples TYPE datetime DEFAULT time::now();

DEFINE INDEX IF NOT EXISTS idx_ge_id ON TABLE golden_examples COLUMNS example_id UNIQUE;
DEFINE INDEX IF NOT EXISTS idx_ge_agent ON TABLE golden_examples COLUMNS agent;
DEFINE INDEX IF NOT EXISTS idx_ge_template ON TABLE golden_examples COLUMNS template_name;
DEFINE INDEX IF NOT EXISTS idx_ge_score ON TABLE golden_examples COLUMNS score;

-- ============================================
-- Optimization History (auto-improvement system)
-- ============================================
-- Records optimization attempts and results:
-- - Tracks OPRO and bootstrap attempts
-- - Records validation results
-- - Links to prompt versions

DEFINE TABLE IF NOT EXISTS optimization_history SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS optimization_id ON TABLE optimization_history TYPE string ASSERT $value != NONE;
DEFINE FIELD IF NOT EXISTS agent ON TABLE optimization_history TYPE string ASSERT $value != NONE;
DEFINE FIELD IF NOT EXISTS template_name ON TABLE optimization_history TYPE string ASSERT $value != NONE;
DEFINE FIELD IF NOT EXISTS method ON TABLE optimization_history TYPE string ASSERT $value != NONE;
DEFINE FIELD IF NOT EXISTS source_version ON TABLE optimization_history TYPE option<string>;
DEFINE FIELD IF NOT EXISTS target_version ON TABLE optimization_history TYPE option<string>;
DEFINE FIELD IF NOT EXISTS success ON TABLE optimization_history TYPE bool DEFAULT false;
DEFINE FIELD IF NOT EXISTS source_score ON TABLE optimization_history TYPE option<float>;
DEFINE FIELD IF NOT EXISTS target_score ON TABLE optimization_history TYPE option<float>;
DEFINE FIELD IF NOT EXISTS improvement ON TABLE optimization_history TYPE option<float>;
DEFINE FIELD IF NOT EXISTS samples_used ON TABLE optimization_history TYPE int DEFAULT 0;
DEFINE FIELD IF NOT EXISTS validation_results ON TABLE optimization_history FLEXIBLE TYPE object DEFAULT {};
DEFINE FIELD IF NOT EXISTS error ON TABLE optimization_history TYPE option<string>;
DEFINE FIELD IF NOT EXISTS created_at ON TABLE optimization_history TYPE datetime DEFAULT time::now();

DEFINE INDEX IF NOT EXISTS idx_opt_id ON TABLE optimization_history COLUMNS optimization_id UNIQUE;
DEFINE INDEX IF NOT EXISTS idx_opt_agent ON TABLE optimization_history COLUMNS agent;
DEFINE INDEX IF NOT EXISTS idx_opt_template ON TABLE optimization_history COLUMNS template_name;
DEFINE INDEX IF NOT EXISTS idx_opt_method ON TABLE optimization_history COLUMNS method;
DEFINE INDEX IF NOT EXISTS idx_opt_success ON TABLE optimization_history COLUMNS success;
DEFINE INDEX IF NOT EXISTS idx_opt_time ON TABLE optimization_history COLUMNS created_at;

-- ============================================
-- LangGraph State Persistence
-- ============================================

DEFINE TABLE IF NOT EXISTS graph_checkpoints SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS thread_id ON TABLE graph_checkpoints TYPE string ASSERT $value != NONE;
DEFINE FIELD IF NOT EXISTS checkpoint_ns ON TABLE graph_checkpoints TYPE string DEFAULT "";
DEFINE FIELD IF NOT EXISTS checkpoint_id ON TABLE graph_checkpoints TYPE string ASSERT $value != NONE;
DEFINE FIELD IF NOT EXISTS parent_checkpoint_id ON TABLE graph_checkpoints TYPE option<string>;
DEFINE FIELD IF NOT EXISTS checkpoint ON TABLE graph_checkpoints TYPE string; -- Base64 encoded pickle
DEFINE FIELD IF NOT EXISTS metadata ON TABLE graph_checkpoints TYPE string; -- Base64 encoded pickle
DEFINE FIELD IF NOT EXISTS created_at ON TABLE graph_checkpoints TYPE datetime DEFAULT time::now();

DEFINE INDEX IF NOT EXISTS idx_graph_cp_thread ON TABLE graph_checkpoints COLUMNS thread_id;
DEFINE INDEX IF NOT EXISTS idx_graph_cp_ns ON TABLE graph_checkpoints COLUMNS thread_id, checkpoint_ns;
DEFINE INDEX IF NOT EXISTS idx_graph_cp_id ON TABLE graph_checkpoints COLUMNS thread_id, checkpoint_ns, checkpoint_id UNIQUE;


DEFINE TABLE IF NOT EXISTS graph_writes SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS thread_id ON TABLE graph_writes TYPE string ASSERT $value != NONE;
DEFINE FIELD IF NOT EXISTS checkpoint_ns ON TABLE graph_writes TYPE string DEFAULT "";
DEFINE FIELD IF NOT EXISTS checkpoint_id ON TABLE graph_writes TYPE string ASSERT $value != NONE;
DEFINE FIELD IF NOT EXISTS task_id ON TABLE graph_writes TYPE string ASSERT $value != NONE;
DEFINE FIELD IF NOT EXISTS idx ON TABLE graph_writes TYPE int ASSERT $value != NONE;
DEFINE FIELD IF NOT EXISTS channel ON TABLE graph_writes TYPE string ASSERT $value != NONE;
DEFINE FIELD IF NOT EXISTS type ON TABLE graph_writes TYPE string; -- "json" or "pickle"
DEFINE FIELD IF NOT EXISTS value ON TABLE graph_writes TYPE string; -- serialized value
DEFINE FIELD IF NOT EXISTS created_at ON TABLE graph_writes TYPE datetime DEFAULT time::now();

DEFINE INDEX IF NOT EXISTS idx_graph_writes_thread ON TABLE graph_writes COLUMNS thread_id;
DEFINE INDEX IF NOT EXISTS idx_graph_writes_ns ON TABLE graph_writes COLUMNS thread_id, checkpoint_ns;
DEFINE INDEX IF NOT EXISTS idx_graph_writes_cp ON TABLE graph_writes COLUMNS checkpoint_id;
DEFINE INDEX IF NOT EXISTS idx_graph_writes_task ON TABLE graph_writes COLUMNS task_id;

"""


async def _migrate_to_flexible_types(conn: Connection) -> None:
    """Migrate object fields to FLEXIBLE TYPE for nested object support.

    SurrealDB v2.x requires FLEXIBLE TYPE for nested objects in SCHEMAFULL tables.
    Regular TYPE object strips nested data.
    """
    # Fields that need FLEXIBLE TYPE for nested objects
    flexible_fields = {
        "workflow_state": [
            ("phase_status", "FLEXIBLE TYPE object DEFAULT {}"),
            ("plan", "FLEXIBLE TYPE option<object>"),
            ("validation_feedback", "FLEXIBLE TYPE option<object>"),
            ("verification_feedback", "FLEXIBLE TYPE option<object>"),
            ("implementation_result", "FLEXIBLE TYPE option<object>"),
            ("research_findings", "FLEXIBLE TYPE option<object>"),
            ("token_usage", "FLEXIBLE TYPE option<object>"),
        ],
        "audit_entries": [
            ("metadata", "FLEXIBLE TYPE object DEFAULT {}"),
        ],
        "error_patterns": [
            ("error_context", "FLEXIBLE TYPE object DEFAULT {}"),
        ],
        "checkpoints": [
            ("task_progress", "FLEXIBLE TYPE object DEFAULT {}"),
            ("state_snapshot", "FLEXIBLE TYPE object DEFAULT {}"),
        ],
        "workflow_events": [
            ("event_data", "FLEXIBLE TYPE object DEFAULT {}"),
        ],
        "phase_outputs": [
            ("content", "FLEXIBLE TYPE object DEFAULT {}"),
        ],
        "logs": [
            ("content", "FLEXIBLE TYPE object DEFAULT {}"),
            ("metadata", "FLEXIBLE TYPE object DEFAULT {}"),
        ],
        "agent_evaluations": [
            ("scores", "FLEXIBLE TYPE object DEFAULT {}"),
            ("metadata", "FLEXIBLE TYPE object DEFAULT {}"),
        ],
        "prompt_versions": [
            ("metrics", "FLEXIBLE TYPE object DEFAULT {}"),
        ],
        "golden_examples": [
            ("metadata", "FLEXIBLE TYPE object DEFAULT {}"),
        ],
        "optimization_history": [
            ("validation_results", "FLEXIBLE TYPE object DEFAULT {}"),
        ],
    }

    for table, fields in flexible_fields.items():
        for field_name, field_def in fields:
            try:
                # Validate table and field names to prevent SQL injection
                validated_table = validate_sql_table(table)
                validated_field = validate_sql_field(field_name)
                await conn.query(
                    f"REMOVE FIELD IF EXISTS {validated_field} ON TABLE {validated_table}"
                )
                await conn.query(
                    f"DEFINE FIELD {validated_field} ON TABLE {validated_table} {field_def}"
                )
            except Exception as e:
                logger.warning(f"Failed to migrate {table}.{field_name}: {e}")


async def apply_schema(conn: Connection) -> bool:
    """Apply schema to the database using the migration system.

    Args:
        conn: Database connection

    Returns:
        True if schema was applied successfully
    """
    try:
        # Import here to avoid circular imports
        from .migrations import MigrationRunner

        # Create a temporary project name from the connection
        # The connection is already scoped to a database
        project_name = getattr(conn, "_database", "default")

        # Use migration runner
        runner = MigrationRunner(project_name)

        # Apply pending migrations
        result = await runner.apply(dry_run=False)

        if result.success:
            applied_count = len(result.applied)
            if applied_count > 0:
                logger.info(f"Applied {applied_count} migration(s)")
            else:
                logger.debug("Schema is up to date")
            return True
        else:
            if result.failed:
                logger.error(
                    f"Migration failed: {result.failed.version}_{result.failed.name}: "
                    f"{result.failed.error}"
                )
            return False

    except ImportError:
        # Fallback to legacy schema application if migrations not available
        logger.warning("Migration system not available, using legacy schema")
        return await _apply_schema_legacy(conn)
    except Exception as e:
        logger.error(f"Failed to apply schema: {e}")
        return False


async def _apply_schema_legacy(conn: Connection) -> bool:
    """Legacy schema application (fallback).

    Args:
        conn: Database connection

    Returns:
        True if schema was applied successfully
    """
    try:
        # Check current schema version
        existing = await conn.query("SELECT * FROM schema_version ORDER BY applied_at DESC LIMIT 1")

        current_version = existing[0].get("version") if existing else None

        if current_version == SCHEMA_VERSION:
            logger.debug(f"Schema already at version {SCHEMA_VERSION}")
            return True

        # Apply base schema definitions (creates tables with IF NOT EXISTS)
        await conn.query(SCHEMA_DEFINITIONS)

        # Run migrations based on current version
        if current_version is None or current_version < "2.2.0":
            # Migration to v2.2.0: FLEXIBLE TYPE for nested objects
            logger.info("Migrating to FLEXIBLE TYPE fields for nested object support...")
            await _migrate_to_flexible_types(conn)

        # Record new schema version
        await conn.create(
            "schema_version",
            {
                "version": SCHEMA_VERSION,
            },
        )

        logger.info(f"Applied schema version {SCHEMA_VERSION}")
        return True

    except Exception as e:
        logger.error(f"Failed to apply schema: {e}")
        return False


async def ensure_schema(project_name: Optional[str] = None) -> bool:
    """Ensure schema is applied for a project database.

    Args:
        project_name: Project name

    Returns:
        True if schema is ready
    """
    async with get_connection(project_name) as conn:
        return await apply_schema(conn)


async def get_schema_version(project_name: Optional[str] = None) -> Optional[str]:
    """Get current schema version for a database.

    Args:
        project_name: Project name

    Returns:
        Schema version string or None
    """
    async with get_connection(project_name) as conn:
        # Note: SurrealDB v2 requires ORDER BY fields to be in SELECT
        result = await conn.query("SELECT * FROM schema_version ORDER BY applied_at DESC LIMIT 1")
        if result:
            return result[0].get("version")
        return None
