"""Migration 0001: Initial Schema.

Creates the base schema for the orchestrator database including:
- Schema version tracking
- Workflow state
- Tasks and milestones
- Audit trail
- Error patterns
- Checkpoints
- Git commits
- Sessions
- Budget tracking
- Workflow events
"""

from ....security import validate_sql_table
from ..base import BaseMigration, MigrationContext


class MigrationInitialSchema(BaseMigration):
    """Initial database schema for the orchestrator."""

    version = "0001"
    name = "initial_schema"
    dependencies = []  # No dependencies - this is the first migration

    async def up(self, ctx: MigrationContext) -> None:
        """Apply the initial schema."""
        await ctx.execute(
            """
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
DEFINE FIELD IF NOT EXISTS phase_status ON TABLE workflow_state TYPE object DEFAULT {};
DEFINE FIELD IF NOT EXISTS iteration_count ON TABLE workflow_state TYPE int DEFAULT 0;
DEFINE FIELD IF NOT EXISTS plan ON TABLE workflow_state TYPE option<object>;
DEFINE FIELD IF NOT EXISTS validation_feedback ON TABLE workflow_state TYPE option<object>;
DEFINE FIELD IF NOT EXISTS verification_feedback ON TABLE workflow_state TYPE option<object>;
DEFINE FIELD IF NOT EXISTS implementation_result ON TABLE workflow_state TYPE option<object>;
DEFINE FIELD IF NOT EXISTS next_decision ON TABLE workflow_state TYPE option<string>;
DEFINE FIELD IF NOT EXISTS execution_mode ON TABLE workflow_state TYPE string DEFAULT "afk";
DEFINE FIELD IF NOT EXISTS discussion_complete ON TABLE workflow_state TYPE bool DEFAULT false;
DEFINE FIELD IF NOT EXISTS research_complete ON TABLE workflow_state TYPE bool DEFAULT false;
DEFINE FIELD IF NOT EXISTS research_findings ON TABLE workflow_state TYPE option<object>;
DEFINE FIELD IF NOT EXISTS token_usage ON TABLE workflow_state TYPE option<object>;
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
DEFINE FIELD IF NOT EXISTS metadata ON TABLE audit_entries TYPE object DEFAULT {};
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
DEFINE FIELD IF NOT EXISTS error_context ON TABLE error_patterns TYPE object DEFAULT {};
DEFINE FIELD IF NOT EXISTS solution ON TABLE error_patterns TYPE option<string>;
DEFINE FIELD IF NOT EXISTS embedding ON TABLE error_patterns TYPE option<array<float>>;
DEFINE FIELD IF NOT EXISTS created_at ON TABLE error_patterns TYPE datetime DEFAULT time::now();

DEFINE INDEX IF NOT EXISTS idx_error_type ON TABLE error_patterns COLUMNS error_type;
DEFINE INDEX IF NOT EXISTS idx_error_task ON TABLE error_patterns COLUMNS task_id;

-- ============================================
-- Checkpoints
-- ============================================

DEFINE TABLE IF NOT EXISTS checkpoints SCHEMAFULL;
DEFINE FIELD IF NOT EXISTS checkpoint_id ON TABLE checkpoints TYPE string ASSERT $value != NONE;
DEFINE FIELD IF NOT EXISTS name ON TABLE checkpoints TYPE string;
DEFINE FIELD IF NOT EXISTS notes ON TABLE checkpoints TYPE string DEFAULT "";
DEFINE FIELD IF NOT EXISTS phase ON TABLE checkpoints TYPE int;
DEFINE FIELD IF NOT EXISTS task_progress ON TABLE checkpoints TYPE object DEFAULT {};
DEFINE FIELD IF NOT EXISTS state_snapshot ON TABLE checkpoints TYPE object DEFAULT {};
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
DEFINE FIELD IF NOT EXISTS event_data ON TABLE workflow_events TYPE object DEFAULT {};
DEFINE FIELD IF NOT EXISTS created_at ON TABLE workflow_events TYPE datetime DEFAULT time::now();

DEFINE INDEX IF NOT EXISTS idx_events_type ON TABLE workflow_events COLUMNS event_type;
DEFINE INDEX IF NOT EXISTS idx_events_time ON TABLE workflow_events COLUMNS created_at;
        """
        )

    async def down(self, ctx: MigrationContext) -> None:
        """Rollback by removing all tables.

        WARNING: This will delete all data!
        """
        tables = [
            "workflow_events",
            "budget_records",
            "sessions",
            "git_commits",
            "checkpoints",
            "error_patterns",
            "audit_entries",
            "milestones",
            "tasks",
            "workflow_state",
            "schema_version",
        ]

        for table in tables:
            validated_table = validate_sql_table(table)
            await ctx.execute(f"REMOVE TABLE IF EXISTS {validated_table}")
