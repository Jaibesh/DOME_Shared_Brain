
import os
import json
import uuid
from typing import List, Dict, Optional, Literal
from datetime import datetime
from pydantic import BaseModel, Field

# DOME 2.2.2 Path Config
# Priority 1: D:\ Spine | Priority 2: G:\ Sync | Fallback: Local
DOME_ROOT = os.environ.get("DOME_CORE_ROOT", r"D:\DOME_CORE")

# Fallback hierarchy
if os.path.exists(DOME_ROOT):
    HUB_ROOT = os.path.join(DOME_ROOT, "knowledge")
elif os.path.exists(r"G:\DOME_CORE"):
    DOME_ROOT = r"G:\DOME_CORE"
    HUB_ROOT = os.path.join(DOME_ROOT, "knowledge")
else:
    # Local workspace fallback
    DOME_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    HUB_ROOT = os.path.join(DOME_ROOT, "knowledge_hub") 

class Insight(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    author_agent: str
    category: Literal["optimization", "compliance", "user_pattern", "error_fix", "strategy"]
    summary: str
    content: str
    tags: List[str] = []

class KnowledgeClient:
    def __init__(self, agent_name: str = "unknown_agent"):
        self.agent_name = agent_name
        self._ensure_paths()

    def _ensure_paths(self):
        os.makedirs(os.path.join(HUB_ROOT, "manifests"), exist_ok=True)
        os.makedirs(os.path.join(HUB_ROOT, "lessons"), exist_ok=True)
        os.makedirs(os.path.join(HUB_ROOT, "patterns"), exist_ok=True)

    def log_insight(self, category: str, summary: str, content: str, tags: List[str] = None) -> str:
        insight = Insight(
            author_agent=self.agent_name,
            category=category,
            summary=summary,
            content=content,
            tags=tags or []
        )
        log_path = os.path.join(HUB_ROOT, "lessons", f"{category}_log.jsonl")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(insight.model_dump_json() + "\n")
        return insight.id

    def search_insights(self, query: str, category: Optional[str] = None) -> List[Dict]:
        results = []
        target_files = []
        lessons_path = os.path.join(HUB_ROOT, "lessons")
        if not os.path.exists(lessons_path): return []
        
        if category:
            target_files = [f"{category}_log.jsonl"]
        else:
            target_files = [f for f in os.listdir(lessons_path) if f.endswith(".jsonl")]

        for filename in target_files:
            path = os.path.join(lessons_path, filename)
            if not os.path.exists(path): continue
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        data = json.loads(line)
                        blob = (data.get("summary", "") + data.get("content", "") + " ".join(data.get("tags", []))).lower()
                        if query.lower() in blob:
                            results.append(data)
                    except json.JSONDecodeError:
                        continue
        return results[-5:]

def get_knowledge_client(agent_name: str = "system") -> KnowledgeClient:
    return KnowledgeClient(agent_name)
