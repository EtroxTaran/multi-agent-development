"""Migration 0002: Phase Outputs and Logs Tables.

Adds tables for storing phase outputs and logs for DB-only storage:
- phase_outputs: Stores plan, feedback, reviews, task results
- logs: Stores UAT documents, handoff briefs, discussion notes
"""

from ..base import BaseMigration, MigrationContext


class MigrationPhaseOutputsLogs(BaseMigration):
    """Add phase_outputs and logs tables for DB-only storage."""

    version = "0002"
    name = "phase_outputs_logs"
    dependencies = ["0001"]

    async def up(self, ctx: MigrationContext) -> None:
        """Apply the migration."""
        await ctx.execute("""
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
DEFINE FIELD IF NOT EXISTS content ON TABLE phase_outputs TYPE object DEFAULT {};
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
DEFINE FIELD IF NOT EXISTS content ON TABLE logs TYPE object DEFAULT {};
DEFINE FIELD IF NOT EXISTS metadata ON TABLE logs TYPE object DEFAULT {};
DEFINE FIELD IF NOT EXISTS created_at ON TABLE logs TYPE datetime DEFAULT time::now();

DEFINE INDEX IF NOT EXISTS idx_logs_type ON TABLE logs COLUMNS log_type;
DEFINE INDEX IF NOT EXISTS idx_logs_task ON TABLE logs COLUMNS task_id;
DEFINE INDEX IF NOT EXISTS idx_logs_time ON TABLE logs COLUMNS created_at;
        """)

    async def down(self, ctx: MigrationContext) -> None:
        """Rollback by removing tables."""
        await ctx.execute("REMOVE TABLE IF EXISTS logs")
        await ctx.execute("REMOVE TABLE IF EXISTS phase_outputs")
