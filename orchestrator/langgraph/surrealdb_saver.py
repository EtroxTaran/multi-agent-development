"""SurrealDB Checkpoint Saver for LangGraph.

Provides persistence for LangGraph state using SurrealDB.
"""

import base64
import json
import logging
from collections.abc import AsyncIterator, Sequence
from typing import Any, Optional

from langgraph.checkpoint.base import (
    BaseCheckpointSaver,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
    SerializerProtocol,
)

from orchestrator.db.connection import get_connection

logger = logging.getLogger(__name__)


class SurrealDBSaver(BaseCheckpointSaver):
    """A checkpoint saver that stores state in SurrealDB."""

    def __init__(
        self,
        project_name: str,
        serde: Optional[SerializerProtocol] = None,
    ):
        """Initialize the saver.

        Args:
            project_name: Project name (database scope)
            serde: Optional serializer (defaults to pickle)
        """
        super().__init__(serde=serde)
        self.project_name = project_name

    async def aget_tuple(self, config: dict) -> Optional[CheckpointTuple]:
        """Get a checkpoint tuple from the database."""
        thread_id = config["configurable"]["thread_id"]
        checkpoint_id = config["configurable"].get("checkpoint_id")
        checkpoint_ns = config["configurable"].get("checkpoint_ns", "")

        async with get_connection(self.project_name) as conn:
            if checkpoint_id:
                # Get specific checkpoint
                query = """
                SELECT * FROM graph_checkpoints
                WHERE thread_id = $thread_id
                AND checkpoint_ns = $checkpoint_ns
                AND checkpoint_id = $checkpoint_id
                LIMIT 1
                """
                params = {
                    "thread_id": thread_id,
                    "checkpoint_ns": checkpoint_ns,
                    "checkpoint_id": checkpoint_id,
                }
            else:
                # Get latest checkpoint
                query = """
                SELECT * FROM graph_checkpoints
                WHERE thread_id = $thread_id
                AND checkpoint_ns = $checkpoint_ns
                ORDER BY created_at DESC
                LIMIT 1
                """
                params = {"thread_id": thread_id, "checkpoint_ns": checkpoint_ns}

            result = await conn.query(query, params)
            if not result:
                return None

            row = result[0]

            # Deserialize checkpoint and metadata
            # Note: We stored {"type": type, "data": base64(bytes)} so we reconstruct the tuple
            checkpoint_stored = json.loads(row["checkpoint"])
            metadata_stored = json.loads(row["metadata"])
            checkpoint = self.serde.loads_typed(
                (checkpoint_stored["type"], base64.b64decode(checkpoint_stored["data"]))
            )
            metadata = self.serde.loads_typed(
                (metadata_stored["type"], base64.b64decode(metadata_stored["data"]))
            )
            parent_id = row.get("parent_checkpoint_id")

            # Load pending writes
            writes_query = """
            SELECT * FROM graph_writes
            WHERE thread_id = $thread_id
            AND checkpoint_ns = $checkpoint_ns
            AND checkpoint_id = $checkpoint_id
            ORDER BY created_at ASC, idx ASC
            """
            writes_result = await conn.query(
                writes_query,
                {
                    "thread_id": thread_id,
                    "checkpoint_ns": checkpoint_ns,
                    "checkpoint_id": row["checkpoint_id"],
                },
            )

            pending_writes = []
            for w in writes_result:
                value_stored = json.loads(w["value"])
                deserialized = self.serde.loads_typed(
                    (value_stored["type"], base64.b64decode(value_stored["data"]))
                )
                pending_writes.append((w["task_id"], w["channel"], deserialized))

            return CheckpointTuple(
                config=config,
                checkpoint=checkpoint,
                metadata=metadata,
                parent_config={
                    "configurable": {
                        "thread_id": thread_id,
                        "checkpoint_id": parent_id,
                        "checkpoint_ns": checkpoint_ns,
                    }
                }
                if parent_id
                else None,
                pending_writes=pending_writes,
            )

    async def alist(
        self,
        config: dict,
        *,
        filter: Optional[dict] = None,
        before: Optional[dict] = None,
        limit: Optional[int] = None,
    ) -> AsyncIterator[CheckpointTuple]:
        """List checkpoints."""
        thread_id = config["configurable"]["thread_id"]
        checkpoint_ns = config["configurable"].get("checkpoint_ns", "")

        limit = limit or 10

        query = """
        SELECT * FROM graph_checkpoints
        WHERE thread_id = $thread_id
        AND checkpoint_ns = $checkpoint_ns
        """
        params = {"thread_id": thread_id, "checkpoint_ns": checkpoint_ns, "limit": limit}

        query += " ORDER BY created_at DESC LIMIT $limit"

        async with get_connection(self.project_name) as conn:
            results = await conn.query(query, params)

            for row in results:
                checkpoint_stored = json.loads(row["checkpoint"])
                metadata_stored = json.loads(row["metadata"])
                checkpoint = self.serde.loads_typed(
                    (checkpoint_stored["type"], base64.b64decode(checkpoint_stored["data"]))
                )
                metadata = self.serde.loads_typed(
                    (metadata_stored["type"], base64.b64decode(metadata_stored["data"]))
                )
                parent_id = row.get("parent_checkpoint_id")

                yield CheckpointTuple(
                    config={
                        "configurable": {
                            "thread_id": thread_id,
                            "checkpoint_id": row["checkpoint_id"],
                            "checkpoint_ns": checkpoint_ns,
                        }
                    },
                    checkpoint=checkpoint,
                    metadata=metadata,
                    parent_config={
                        "configurable": {
                            "thread_id": thread_id,
                            "checkpoint_id": parent_id,
                            "checkpoint_ns": checkpoint_ns,
                        }
                    }
                    if parent_id
                    else None,
                )

    async def aput(
        self,
        config: dict,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: dict[str, Any],
    ) -> dict:
        """Save a checkpoint."""
        thread_id = config["configurable"]["thread_id"]
        checkpoint_ns = config["configurable"].get("checkpoint_ns", "")
        checkpoint_id = checkpoint["id"]
        parent_id = config["configurable"].get("checkpoint_id")

        logger.info(f"Saving checkpoint: thread={thread_id}, cp_id={checkpoint_id[:20]}...")

        # Serialize
        try:
            logger.debug(f"Serializing checkpoint {checkpoint_id[:20]}...")
            # Use dumps_typed which returns (type, bytes) - store both as JSON
            cp_type, cp_bytes = self.serde.dumps_typed(checkpoint)
            meta_type, meta_bytes = self.serde.dumps_typed(metadata)
            # Store as JSON with type and base64-encoded data
            checkpoint_blob = json.dumps(
                {"type": cp_type, "data": base64.b64encode(cp_bytes).decode("utf-8")}
            )
            metadata_blob = json.dumps(
                {"type": meta_type, "data": base64.b64encode(meta_bytes).decode("utf-8")}
            )
            logger.debug(
                f"Serialization complete: checkpoint={len(checkpoint_blob)} bytes, metadata={len(metadata_blob)} bytes"
            )
        except Exception as e:
            logger.error(f"Serialization failed for {checkpoint_id[:20]}: {e}")
            raise

        try:
            logger.debug(f"Acquiring connection for {self.project_name}...")
            async with get_connection(self.project_name) as conn:
                logger.debug("Connection acquired, creating record...")
                # Don't set created_at - let SurrealDB's DEFAULT time::now() handle it
                result = await conn.create(
                    "graph_checkpoints",
                    {
                        "thread_id": thread_id,
                        "checkpoint_ns": checkpoint_ns,
                        "checkpoint_id": checkpoint_id,
                        "parent_checkpoint_id": parent_id,
                        "checkpoint": checkpoint_blob,
                        "metadata": metadata_blob,
                    },
                )
                logger.info(
                    f"Checkpoint saved successfully: {checkpoint_id[:20]}... result_id={result.get('id') if isinstance(result, dict) else result}"
                )
        except Exception as e:
            logger.error(
                f"Failed to save checkpoint {checkpoint_id[:20]}: {type(e).__name__}: {e}",
                exc_info=True,
            )
            raise

        return {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_ns": checkpoint_ns,
                "checkpoint_id": checkpoint_id,
            }
        }

    async def aput_writes(
        self,
        config: dict,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
    ) -> None:
        """Save intermediate writes."""
        thread_id = config["configurable"]["thread_id"]
        checkpoint_ns = config["configurable"].get("checkpoint_ns", "")
        checkpoint_id = config["configurable"]["checkpoint_id"]

        async with get_connection(self.project_name) as conn:
            for idx, (channel, value) in enumerate(writes):
                # Serialize value using dumps_typed (returns tuple of type, bytes)
                val_type, val_bytes = self.serde.dumps_typed(value)
                value_blob = json.dumps(
                    {"type": val_type, "data": base64.b64encode(val_bytes).decode("utf-8")}
                )

                await conn.create(
                    "graph_writes",
                    {
                        "thread_id": thread_id,
                        "checkpoint_ns": checkpoint_ns,
                        "checkpoint_id": checkpoint_id,
                        "task_id": task_id,
                        "idx": idx,
                        "channel": channel,
                        "type": "pickle",
                        "value": value_blob,
                        "created_at": "time::now()",
                    },
                )
