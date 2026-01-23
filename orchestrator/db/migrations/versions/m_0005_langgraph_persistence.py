"""Migration 0005: LangGraph Persistence.

Adds tables for LangGraph checkpoint persistence in SurrealDB.
Replaces AsyncSqliteSaver.
"""

from ..base import BaseMigration, MigrationContext


class MigrationLangGraphPersistence(BaseMigration):
    """Add LangGraph persistence tables."""

    version = "0005"
    name = "langgraph_persistence"
    dependencies = ["0004"]

    SCHEMA = """
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

    async def up(self, ctx: MigrationContext) -> None:
        """Apply the migration."""
        await ctx.execute(self.SCHEMA)

    async def down(self, ctx: MigrationContext) -> None:
        """Rollback."""
        await ctx.execute("REMOVE TABLE graph_checkpoints")
        await ctx.execute("REMOVE TABLE graph_writes")
