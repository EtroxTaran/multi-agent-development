"""Migration 0004: Auto-Improvement Tables.

Adds tables for the auto-improvement system:
- agent_evaluations: G-Eval results for agent executions
- prompt_versions: Versioned prompts with performance metrics
- golden_examples: High-quality output examples for few-shot learning
- optimization_history: Records of optimization attempts
"""

from ..base import BaseMigration, MigrationContext


class MigrationAutoImprovement(BaseMigration):
    """Add auto-improvement tables for agent evaluation and prompt optimization."""

    version = "0004"
    name = "auto_improvement"
    dependencies = ["0003"]

    async def up(self, ctx: MigrationContext) -> None:
        """Apply the migration."""
        await ctx.execute("""
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
        """)

    async def down(self, ctx: MigrationContext) -> None:
        """Rollback by removing tables."""
        tables = [
            "optimization_history",
            "golden_examples",
            "prompt_versions",
            "agent_evaluations",
        ]

        for table in tables:
            await ctx.execute(f"REMOVE TABLE IF EXISTS {table}")
