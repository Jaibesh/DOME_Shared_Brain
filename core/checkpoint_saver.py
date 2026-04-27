"""
DOME 4.0 — Supabase Checkpoint Saver
======================================
LangGraph-compatible checkpoint saver that persists workflow state
to the dome_checkpoints table in Supabase.

Enables:
- Cross-environment resume (start at home, resume at work)
- Time-travel debugging (replay from any checkpoint)
- Human-in-the-loop (pause, approve, resume)

Usage:
    from core.checkpoint_saver import SupabaseCheckpointer
    from langgraph.graph import StateGraph

    checkpointer = SupabaseCheckpointer()
    app = graph.compile(checkpointer=checkpointer)
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional, Iterator, Sequence, Tuple

from langgraph.checkpoint.base import (
    BaseCheckpointSaver,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
)
from langchain_core.runnables import RunnableConfig

logger = logging.getLogger("dome.checkpoint")


class SupabaseCheckpointer(BaseCheckpointSaver):
    """
    Persists LangGraph checkpoints to Supabase PostgreSQL.
    
    This enables workflows to be paused on one machine and
    resumed on another, as long as both connect to the same
    Supabase project.
    """
    
    def __init__(self):
        super().__init__()
        self._client = None
    
    @property
    def client(self):
        if self._client is None:
            from core.supabase_client import get_supabase
            self._client = get_supabase()
        return self._client
    
    def put(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: Optional[dict] = None,
    ) -> RunnableConfig:
        """Save a checkpoint to Supabase."""
        thread_id = config["configurable"]["thread_id"]
        checkpoint_id = checkpoint["id"]
        parent_id = config["configurable"].get("checkpoint_id")
        
        # Serialize checkpoint data
        data = {
            "thread_id": thread_id,
            "checkpoint_id": checkpoint_id,
            "parent_checkpoint_id": parent_id,
            "checkpoint": self._serialize(checkpoint),
            "metadata": self._serialize(metadata) if metadata else {},
        }
        
        self.client.table("dome_checkpoints").upsert(data).execute()
        
        logger.debug(f"Checkpoint saved: thread={thread_id}, id={checkpoint_id[:8]}...")
        
        return {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_id": checkpoint_id,
            }
        }
    
    def put_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[Tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        """Store intermediate writes (pending sends). Simplified implementation."""
        # For our use case, we store writes as part of the checkpoint metadata
        thread_id = config["configurable"]["thread_id"]
        checkpoint_id = config["configurable"].get("checkpoint_id", "")
        
        if not checkpoint_id:
            return
            
        try:
            result = self.client.table("dome_checkpoints").select("metadata").eq(
                "thread_id", thread_id
            ).eq("checkpoint_id", checkpoint_id).execute()
            
            if result.data:
                existing_meta = result.data[0].get("metadata", {})
                if not isinstance(existing_meta, dict):
                    existing_meta = {}
                existing_meta["pending_writes"] = [
                    {"channel": w[0], "value": str(w[1])[:500]} for w in writes
                ]
                existing_meta["task_id"] = task_id
                
                self.client.table("dome_checkpoints").update(
                    {"metadata": existing_meta}
                ).eq("thread_id", thread_id).eq("checkpoint_id", checkpoint_id).execute()
        except Exception as e:
            logger.warning(f"Failed to store writes: {e}")
    
    def get_tuple(self, config: RunnableConfig) -> Optional[CheckpointTuple]:
        """Get a specific checkpoint."""
        thread_id = config["configurable"]["thread_id"]
        checkpoint_id = config["configurable"].get("checkpoint_id")
        
        query = self.client.table("dome_checkpoints").select("*").eq(
            "thread_id", thread_id
        )
        
        if checkpoint_id:
            query = query.eq("checkpoint_id", checkpoint_id)
        else:
            query = query.order("created_at", desc=True).limit(1)
        
        result = query.execute()
        
        if not result.data:
            return None
        
        row = result.data[0]
        checkpoint = self._deserialize(row["checkpoint"])
        metadata = self._deserialize(row.get("metadata", {}))
        parent_id = row.get("parent_checkpoint_id")
        
        parent_config = None
        if parent_id:
            parent_config = {
                "configurable": {
                    "thread_id": thread_id,
                    "checkpoint_id": parent_id,
                }
            }
        
        return CheckpointTuple(
            config={
                "configurable": {
                    "thread_id": thread_id,
                    "checkpoint_id": row["checkpoint_id"],
                }
            },
            checkpoint=checkpoint,
            metadata=metadata,
            parent_config=parent_config,
        )
    
    def list(
        self,
        config: Optional[RunnableConfig],
        *,
        filter: Optional[dict[str, Any]] = None,
        before: Optional[RunnableConfig] = None,
        limit: Optional[int] = None,
    ) -> Iterator[CheckpointTuple]:
        """List checkpoints for a thread."""
        if not config:
            return
        
        thread_id = config["configurable"]["thread_id"]
        query = self.client.table("dome_checkpoints").select("*").eq(
            "thread_id", thread_id
        ).order("created_at", desc=True)
        
        if limit:
            query = query.limit(limit)
        
        result = query.execute()
        
        for row in (result.data or []):
            checkpoint = self._deserialize(row["checkpoint"])
            metadata = self._deserialize(row.get("metadata", {}))
            parent_id = row.get("parent_checkpoint_id")
            
            parent_config = None
            if parent_id:
                parent_config = {
                    "configurable": {
                        "thread_id": thread_id,
                        "checkpoint_id": parent_id,
                    }
                }
            
            yield CheckpointTuple(
                config={
                    "configurable": {
                        "thread_id": thread_id,
                        "checkpoint_id": row["checkpoint_id"],
                    }
                },
                checkpoint=checkpoint,
                metadata=metadata,
                parent_config=parent_config,
            )
    
    # --- Serialization helpers ---
    
    def _serialize(self, obj: Any) -> Any:
        """Serialize checkpoint data for JSON storage."""
        if isinstance(obj, dict):
            return {k: self._serialize(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self._serialize(v) for v in obj]
        if isinstance(obj, (datetime,)):
            return obj.isoformat()
        if hasattr(obj, 'model_dump'):
            return obj.model_dump(mode="json")
        if hasattr(obj, '__dict__'):
            return str(obj)
        return obj
    
    def _deserialize(self, data: Any) -> Any:
        """Deserialize checkpoint data from JSON storage."""
        if isinstance(data, str):
            try:
                return json.loads(data)
            except (json.JSONDecodeError, TypeError):
                return data
        return data
