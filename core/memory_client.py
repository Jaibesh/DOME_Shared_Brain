"""
DOME 4.0 - Memory Client (Mem0 Pattern)
========================================
Persistent, semantic memory layer for DOME agents.
Replaces the old JSONL-based knowledge_client.py with a cloud-native,
vector-search-enabled memory system backed by Supabase + pgvector.

Features:
- Semantic search via embeddings (pgvector cosine similarity)
- Intelligent relevance decay (stale memories are "forgotten")
- Access tracking (frequently accessed memories stay relevant)
- Cross-environment sync (home and work share the same brain)
- Backward compatibility with the old KnowledgeClient API

Usage:
    from core.memory_client import get_memory_client

    memory = get_memory_client("my_agent")
    
    # Store a memory
    memory.add("Supabase pgvector requires dimension 1536 for text-embedding-3-small",
               category="optimization", tags=["supabase", "embeddings"])
    
    # Search memories semantically
    results = memory.search("how to set up vector search")
    for r in results:
        print(f"{r['similarity']:.2f} | {r['content']}")
    
    # Log a structured insight
    memory.log_insight(
        category="error_fix",
        summary="Fixed circular import in supervisor",
        content="Moved the import inside the function to break the cycle."
    )
"""

import os
import json
import uuid
import logging
from typing import List, Dict, Optional, Any
from datetime import datetime, timezone
from pydantic import BaseModel, Field

logger = logging.getLogger("dome.memory")

# ---------------------------------------------------------------------------
# Embedding Provider
# ---------------------------------------------------------------------------
_embedding_fn = None

def _get_embedding(text: str) -> Optional[List[float]]:
    """
    Generate an embedding vector for the given text.
    
    Supports multiple providers with automatic fallback:
    1. OpenAI text-embedding-3-small (1536 dims) — preferred
    2. Google Gemini embedding
    3. None (falls back to keyword search)
    """
    global _embedding_fn
    
    if _embedding_fn is not None:
        return _embedding_fn(text)
    
    # Try OpenAI
    openai_key = os.environ.get("OPENAI_API_KEY")
    if openai_key:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=openai_key)
            
            def openai_embed(t: str) -> List[float]:
                resp = client.embeddings.create(
                    model="text-embedding-3-small",
                    input=t
                )
                return resp.data[0].embedding
            
            _embedding_fn = openai_embed
            logger.info("[DOME Memory] Using OpenAI text-embedding-3-small")
            return _embedding_fn(text)
        except Exception as e:
            logger.warning(f"[DOME Memory] OpenAI embedding failed: {e}")
    
    # Try Google Gemini
    google_key = os.environ.get("GOOGLE_API_KEY")
    if google_key:
        try:
            import google.generativeai as genai
            genai.configure(api_key=google_key)
            
            def gemini_embed(t: str) -> List[float]:
                result = genai.embed_content(
                    model="models/text-embedding-004",
                    content=t
                )
                emb = result["embedding"]
                # Pad/truncate to 1536 dims for pgvector compatibility
                if len(emb) < 1536:
                    emb = emb + [0.0] * (1536 - len(emb))
                return emb[:1536]
            
            _embedding_fn = gemini_embed
            logger.info("[DOME Memory] Using Google Gemini text-embedding-004")
            return _embedding_fn(text)
        except Exception as e:
            logger.warning(f"[DOME Memory] Gemini embedding failed: {e}")
    
    logger.warning("[DOME Memory] No embedding provider available. Using keyword search only.")
    return None


# ---------------------------------------------------------------------------
# Memory Client
# ---------------------------------------------------------------------------
class MemoryClient:
    """
    Mem0-pattern memory client backed by Supabase.
    
    Provides semantic memory storage, retrieval, and intelligent decay
    for DOME agents. Both home and work environments connect to the
    same Supabase instance, enabling seamless knowledge sharing.
    """
    
    def __init__(self, agent_id: str = "system"):
        self.agent_id = agent_id
        self._client = None
        self._local_mode = False
    
    @property
    def client(self):
        """Lazy-load the Supabase client."""
        if self._client is None and not self._local_mode:
            try:
                from core.supabase_client import get_supabase
                self._client = get_supabase()
            except (ImportError, ValueError) as e:
                logger.warning(f"[DOME Memory] Cloud unavailable, using local fallback: {e}")
                self._local_mode = True
        return self._client
    
    # ----- MEMORY OPERATIONS -----
    
    def add(
        self,
        content: str,
        category: str = "general",
        tags: List[str] = None,
        metadata: dict = None
    ) -> str:
        """
        Add a new memory. Returns the memory ID.
        
        Args:
            content: The memory content to store
            category: Category for organization (general, optimization, error_fix, etc.)
            tags: List of tags for filtering
            metadata: Additional structured metadata
        """
        memory_id = str(uuid.uuid4())
        embedding = _get_embedding(content)
        
        # Trigger lazy client loader (sets _local_mode if cloud unavailable)
        self.client
        
        if self._local_mode:
            return self._add_local(memory_id, content, category, tags, metadata)
        
        data = {
            "id": memory_id,
            "agent_id": self.agent_id,
            "content": content,
            "category": category,
            "tags": tags or [],
            "metadata": metadata or {},
            "relevance_score": 1.0,
            "access_count": 0,
        }
        
        if embedding:
            data["embedding"] = embedding
        
        self.client.table("dome_memories").insert(data).execute()
        logger.info(f"[DOME Memory] Stored: {content[:60]}... ({category})")
        return memory_id
    
    def search(
        self,
        query: str,
        limit: int = 5,
        category: str = None,
        agent_id: str = None
    ) -> List[Dict]:
        """
        Search memories semantically.
        
        Falls back to keyword search if embeddings are unavailable.
        Updates access tracking for returned results.
        
        Args:
            query: Natural language search query
            limit: Max results to return
            category: Filter by category
            agent_id: Filter by agent (None = search all agents)
        """
        # Trigger lazy client loader
        self.client
        
        if self._local_mode:
            return self._search_local(query, limit, category)
        
        embedding = _get_embedding(query)
        
        if embedding:
            # Semantic search via pgvector
            result = self.client.rpc("search_memories", {
                "query_embedding": embedding,
                "match_count": limit,
                "filter_agent": agent_id,
                "filter_category": category
            }).execute()
            
            memories = result.data or []
        else:
            # Fallback: keyword search
            q = self.client.table("dome_memories").select("*")
            if agent_id:
                q = q.eq("agent_id", agent_id)
            if category:
                q = q.eq("category", category)
            q = q.ilike("content", f"%{query}%")
            result = q.limit(limit).execute()
            memories = result.data or []
        
        # Touch accessed memories (update access_count & accessed_at)
        for mem in memories:
            try:
                self.client.rpc("touch_memory", {"memory_id": mem["id"]}).execute()
            except Exception:
                pass  # Non-critical
        
        return memories
    
    def forget(self, memory_id: str) -> None:
        """Soft-delete a memory by setting relevance to near-zero."""
        if self._local_mode:
            return
        self.client.table("dome_memories").update(
            {"relevance_score": 0.01}
        ).eq("id", memory_id).execute()
    
    def decay_stale(self, days: int = 90) -> int:
        """
        Run relevance decay on memories not accessed in `days` days.
        Returns the count of affected memories.
        """
        if self._local_mode:
            return 0
        result = self.client.rpc("decay_stale_memories", {"decay_days": days}).execute()
        count = result.data if result.data else 0
        logger.info(f"[DOME Memory] Decayed {count} stale memories (>{days} days)")
        return count
    
    # ----- INSIGHT OPERATIONS (backward-compatible with old KnowledgeClient) -----
    
    def log_insight(
        self,
        category: str,
        summary: str,
        content: str,
        tags: List[str] = None
    ) -> str:
        """
        Log a structured insight. Backward-compatible with the old KnowledgeClient API.
        
        Args:
            category: one of optimization, compliance, user_pattern, error_fix, 
                      strategy, architecture, tool_creation
            summary: Brief description
            content: Full insight content
            tags: List of tags
        """
        insight_id = str(uuid.uuid4())
        embedding = _get_embedding(f"{summary} {content}")
        
        # Trigger lazy client loader
        self.client
        
        if self._local_mode:
            return self._log_insight_local(insight_id, category, summary, content, tags)
        
        data = {
            "id": insight_id,
            "author_agent": self.agent_id,
            "category": category,
            "summary": summary,
            "content": content,
            "tags": tags or [],
        }
        
        if embedding:
            data["embedding"] = embedding
        
        self.client.table("dome_insights").insert(data).execute()
        logger.info(f"[DOME Memory] Insight logged: {summary[:60]}...")
        return insight_id
    
    def search_insights(
        self,
        query: str,
        category: str = None,
        limit: int = 5
    ) -> List[Dict]:
        """
        Search insights semantically. Backward-compatible API.
        """
        # Trigger lazy client loader
        self.client
        
        if self._local_mode:
            return self._search_insights_local(query, category)
        
        embedding = _get_embedding(query)
        
        if embedding:
            result = self.client.rpc("search_insights", {
                "query_embedding": embedding,
                "match_count": limit,
                "filter_category": category
            }).execute()
            return result.data or []
        else:
            q = self.client.table("dome_insights").select("*")
            if category:
                q = q.eq("category", category)
            q = q.ilike("content", f"%{query}%").is_("superseded_by", "null")
            result = q.limit(limit).execute()
            return result.data or []
    
    # ----- LOCAL FALLBACK (graceful degradation) -----
    
    def _get_local_path(self) -> str:
        dome_root = os.environ.get("DOME_CORE_ROOT", r"D:\DOME_CORE")
        path = os.path.join(dome_root, "knowledge", "lessons")
        os.makedirs(path, exist_ok=True)
        return path
    
    def _add_local(self, memory_id, content, category, tags, metadata):
        path = os.path.join(self._get_local_path(), "memories.jsonl")
        entry = {
            "id": memory_id,
            "agent_id": self.agent_id,
            "content": content,
            "category": category,
            "tags": tags or [],
            "metadata": metadata or {},
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
        return memory_id
    
    def _search_local(self, query, limit, category):
        path = os.path.join(self._get_local_path(), "memories.jsonl")
        if not os.path.exists(path):
            return []
        results = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    data = json.loads(line)
                    if category and data.get("category") != category:
                        continue
                    blob = (data.get("content", "") + " ".join(data.get("tags", []))).lower()
                    if query.lower() in blob:
                        results.append(data)
                except json.JSONDecodeError:
                    continue
        return results[-limit:]
    
    def _log_insight_local(self, insight_id, category, summary, content, tags):
        path = os.path.join(self._get_local_path(), f"{category}_log.jsonl")
        entry = {
            "id": insight_id,
            "author_agent": self.agent_id,
            "category": category,
            "summary": summary,
            "content": content,
            "tags": tags or [],
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
        return insight_id
    
    def _search_insights_local(self, query, category):
        """Backward-compatible local search (matches old KnowledgeClient)."""
        path = self._get_local_path()
        results = []
        target_files = []
        
        if category:
            target_files = [f"{category}_log.jsonl"]
        else:
            target_files = [f for f in os.listdir(path) if f.endswith(".jsonl")]
        
        for filename in target_files:
            filepath = os.path.join(path, filename)
            if not os.path.exists(filepath):
                continue
            with open(filepath, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        data = json.loads(line)
                        blob = (
                            data.get("summary", "") + 
                            data.get("content", "") + 
                            " ".join(data.get("tags", []))
                        ).lower()
                        if query.lower() in blob:
                            results.append(data)
                    except json.JSONDecodeError:
                        continue
        return results[-5:]


# ---------------------------------------------------------------------------
# Factory Function (backward-compatible)
# ---------------------------------------------------------------------------
def get_memory_client(agent_id: str = "system") -> MemoryClient:
    """Get a MemoryClient instance for the given agent."""
    return MemoryClient(agent_id)


# Backward compatibility alias
def get_knowledge_client(agent_name: str = "system") -> MemoryClient:
    """
    Backward-compatible alias for get_memory_client.
    The old KnowledgeClient API (log_insight, search_insights) is fully supported.
    """
    return MemoryClient(agent_name)
