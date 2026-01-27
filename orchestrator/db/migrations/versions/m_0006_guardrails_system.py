"""Migration 0006: Guardrails System.

Adds tables for the Guardrails System:
- collection_items: Central metadata for rules, skills, templates
- collection_tags: Tags for filtering collection items
- project_guardrails: Track which items are applied per project
"""

from ..base import BaseMigration, MigrationContext


class MigrationGuardrailsSystem(BaseMigration):
    """Add guardrails system tables."""

    version = "0006"
    name = "guardrails_system"
    dependencies = ["0005"]

    SCHEMA = """
    -- ============================================
    -- Collection Items (Rules, Skills, Templates)
    -- ============================================
    -- Central repository of reusable guardrails.
    -- Content stored in filesystem, metadata in DB.

    DEFINE TABLE IF NOT EXISTS collection_items SCHEMAFULL;
    DEFINE FIELD IF NOT EXISTS item_id ON TABLE collection_items TYPE string ASSERT $value != NONE;
    DEFINE FIELD IF NOT EXISTS name ON TABLE collection_items TYPE string ASSERT $value != NONE;
    DEFINE FIELD IF NOT EXISTS item_type ON TABLE collection_items TYPE string ASSERT $value != NONE;  -- rule, skill, template
    DEFINE FIELD IF NOT EXISTS category ON TABLE collection_items TYPE string DEFAULT "";
    DEFINE FIELD IF NOT EXISTS file_path ON TABLE collection_items TYPE string ASSERT $value != NONE;
    DEFINE FIELD IF NOT EXISTS content_hash ON TABLE collection_items TYPE string DEFAULT "";
    DEFINE FIELD IF NOT EXISTS summary ON TABLE collection_items TYPE string DEFAULT "";
    DEFINE FIELD IF NOT EXISTS version ON TABLE collection_items TYPE int DEFAULT 1;
    DEFINE FIELD IF NOT EXISTS priority ON TABLE collection_items TYPE string DEFAULT "medium";
    DEFINE FIELD IF NOT EXISTS is_active ON TABLE collection_items TYPE bool DEFAULT true;
    DEFINE FIELD IF NOT EXISTS created_at ON TABLE collection_items TYPE datetime DEFAULT time::now();
    DEFINE FIELD IF NOT EXISTS updated_at ON TABLE collection_items TYPE datetime DEFAULT time::now();

    DEFINE INDEX IF NOT EXISTS idx_collection_items_id ON TABLE collection_items COLUMNS item_id UNIQUE;
    DEFINE INDEX IF NOT EXISTS idx_collection_items_type ON TABLE collection_items COLUMNS item_type;
    DEFINE INDEX IF NOT EXISTS idx_collection_items_active ON TABLE collection_items COLUMNS is_active;

    -- ============================================
    -- Collection Tags (many-to-many)
    -- ============================================

    DEFINE TABLE IF NOT EXISTS collection_tags SCHEMAFULL;
    DEFINE FIELD IF NOT EXISTS item_id ON TABLE collection_tags TYPE string ASSERT $value != NONE;
    DEFINE FIELD IF NOT EXISTS tag_type ON TABLE collection_tags TYPE string ASSERT $value != NONE;  -- technology, feature, priority
    DEFINE FIELD IF NOT EXISTS tag_value ON TABLE collection_tags TYPE string ASSERT $value != NONE;
    DEFINE FIELD IF NOT EXISTS created_at ON TABLE collection_tags TYPE datetime DEFAULT time::now();

    DEFINE INDEX IF NOT EXISTS idx_collection_tags_item ON TABLE collection_tags COLUMNS item_id;
    DEFINE INDEX IF NOT EXISTS idx_collection_tags_lookup ON TABLE collection_tags COLUMNS tag_type, tag_value;

    -- ============================================
    -- Project Guardrails (applied per project)
    -- ============================================
    -- Tracks which collection items are applied to each project.
    -- Enables per-project enable/disable of specific guardrails.

    DEFINE TABLE IF NOT EXISTS project_guardrails SCHEMAFULL;
    DEFINE FIELD IF NOT EXISTS project_id ON TABLE project_guardrails TYPE string ASSERT $value != NONE;
    DEFINE FIELD IF NOT EXISTS item_id ON TABLE project_guardrails TYPE string ASSERT $value != NONE;
    DEFINE FIELD IF NOT EXISTS item_type ON TABLE project_guardrails TYPE string ASSERT $value != NONE;
    DEFINE FIELD IF NOT EXISTS applied_at ON TABLE project_guardrails TYPE datetime DEFAULT time::now();
    DEFINE FIELD IF NOT EXISTS enabled ON TABLE project_guardrails TYPE bool DEFAULT true;
    DEFINE FIELD IF NOT EXISTS delivery_method ON TABLE project_guardrails TYPE string DEFAULT "file";  -- file, prompt, both
    DEFINE FIELD IF NOT EXISTS version_applied ON TABLE project_guardrails TYPE int DEFAULT 1;
    DEFINE FIELD IF NOT EXISTS file_path ON TABLE project_guardrails TYPE option<string>;  -- Path in project where copied

    DEFINE INDEX IF NOT EXISTS idx_project_guardrails_project ON TABLE project_guardrails COLUMNS project_id;
    DEFINE INDEX IF NOT EXISTS idx_project_guardrails_item ON TABLE project_guardrails COLUMNS project_id, item_id UNIQUE;
    DEFINE INDEX IF NOT EXISTS idx_project_guardrails_enabled ON TABLE project_guardrails COLUMNS project_id, enabled;

    -- ============================================
    -- Gap Analysis Cache
    -- ============================================

    DEFINE TABLE IF NOT EXISTS gap_analysis_results SCHEMAFULL;
    DEFINE FIELD IF NOT EXISTS project_id ON TABLE gap_analysis_results TYPE string ASSERT $value != NONE;
    DEFINE FIELD IF NOT EXISTS technologies ON TABLE gap_analysis_results TYPE array<string> DEFAULT [];
    DEFINE FIELD IF NOT EXISTS features ON TABLE gap_analysis_results TYPE array<string> DEFAULT [];
    DEFINE FIELD IF NOT EXISTS matched_items ON TABLE gap_analysis_results TYPE array<string> DEFAULT [];  -- item_ids
    DEFINE FIELD IF NOT EXISTS gaps ON TABLE gap_analysis_results FLEXIBLE TYPE array DEFAULT [];
    DEFINE FIELD IF NOT EXISTS analyzed_at ON TABLE gap_analysis_results TYPE datetime DEFAULT time::now();

    DEFINE INDEX IF NOT EXISTS idx_gap_analysis_project ON TABLE gap_analysis_results COLUMNS project_id UNIQUE;
    """

    async def up(self, ctx: MigrationContext) -> None:
        """Apply the migration."""
        await ctx.execute(self.SCHEMA)

    async def down(self, ctx: MigrationContext) -> None:
        """Rollback by removing guardrails system tables."""
        await ctx.execute("REMOVE TABLE IF EXISTS gap_analysis_results")
        await ctx.execute("REMOVE TABLE IF EXISTS project_guardrails")
        await ctx.execute("REMOVE TABLE IF EXISTS collection_tags")
        await ctx.execute("REMOVE TABLE IF EXISTS collection_items")
