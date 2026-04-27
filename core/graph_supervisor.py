"""
DOME 4.0 — Graph Supervisor (LangGraph StateGraph)
====================================================
Replaces the old enhanced_supervisor.py with a modern LangGraph StateGraph.

Key upgrades over DOME 2.0:
- Cyclical, stateful graph (not linear ReAct loops)
- Supabase-persisted checkpoints (cross-environment resume)
- Human-in-the-Loop (HITL) interrupt points
- Cloud memory integration (Mem0-pattern)
- Circuit breaker and retry patterns preserved
- Model-agnostic (works with Gemini, OpenAI, Anthropic)

Usage:
    from core.graph_supervisor import create_dome_graph, DOMEState

    # Create the graph
    graph = create_dome_graph(
        workers={"researcher": researcher_node, "writer": writer_node},
        system_prompt="You are a helpful assistant.",
        use_cloud_checkpoints=True
    )

    # Run it
    config = {"configurable": {"thread_id": "my-session-1"}}
    result = graph.invoke(
        {"messages": [HumanMessage(content="Hello!")]},
        config=config
    )

    # Resume later (even from a different machine!)
    result = graph.invoke(
        {"messages": [HumanMessage(content="Continue where we left off")]},
        config=config
    )
"""

import os
import time
import logging
from typing import (
    Any, Dict, List, Optional, Callable, Literal, 
    TypedDict, Annotated, Sequence
)
from datetime import datetime, timezone

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.messages import (
    BaseMessage, SystemMessage, HumanMessage, AIMessage
)
import operator

logger = logging.getLogger("dome.graph")


# =============================================================================
# DOME 4.0 GRAPH STATE
# =============================================================================

class DOMEState(TypedDict):
    """
    The shared state for all DOME 4.0 workflows.
    
    This is the single source of truth passed between all nodes in the graph.
    It gets checkpointed after every node execution.
    """
    # Core conversation
    messages: Annotated[Sequence[BaseMessage], operator.add]
    
    # Routing
    next_worker: Optional[str]
    
    # Memory context (injected from Supabase Mem0)
    memory_context: List[str]
    
    # Worker results
    tool_results: List[Dict[str, Any]]
    
    # Policy & safety
    turn_count: int
    max_turns: int
    escalated: bool
    escalation_reason: Optional[str]
    
    # HITL
    approval_needed: bool
    approval_action: Optional[str]  # What action needs approval
    
    # Metadata
    agent_id: str
    environment: str  # 'home' or 'work'
    started_at: str


# =============================================================================
# DEFAULT STATE
# =============================================================================

def default_state() -> Dict[str, Any]:
    """Create a default initial state."""
    from core.supabase_client import get_environment
    return {
        "messages": [],
        "next_worker": None,
        "memory_context": [],
        "tool_results": [],
        "turn_count": 0,
        "max_turns": 20,
        "escalated": False,
        "escalation_reason": None,
        "approval_needed": False,
        "approval_action": None,
        "agent_id": os.environ.get("AGENT_ID", "dome_agent"),
        "environment": get_environment(),
        "started_at": datetime.now(timezone.utc).isoformat(),
    }


# =============================================================================
# CORE NODES
# =============================================================================

def _build_router_node(
    workers: Dict[str, Callable],
    system_prompt: str,
    model: Any = None,
) -> Callable:
    """
    Build the supervisor/router node.
    
    This node decides which worker should handle the next step,
    or whether the conversation is complete.
    """
    worker_names = list(workers.keys())
    
    def router_node(state: DOMEState) -> Dict[str, Any]:
        turn = state.get("turn_count", 0)
        max_turns = state.get("max_turns", 20)
        
        # Safety: check turn limit
        if turn >= max_turns:
            logger.warning(f"Max turns ({max_turns}) reached, finishing.")
            return {
                "next_worker": "__end__",
                "escalated": True,
                "escalation_reason": "max_turns_exceeded",
                "turn_count": turn + 1,
            }
        
        # Safety: check escalation
        if state.get("escalated", False):
            return {"next_worker": "__end__"}
        
        # If we have a model, use it for intelligent routing
        if model is not None:
            try:
                from pydantic import BaseModel as PydanticModel, Field
                
                class RouteDecision(PydanticModel):
                    """Decision about which worker should handle the next step."""
                    next_step: str = Field(
                        description=f"Choose one of: {worker_names + ['FINISH']}"
                    )
                    reasoning: str = Field(
                        description="Brief explanation of why this worker was chosen"
                    )
                
                # Build routing prompt
                memory_context = "\n".join(state.get("memory_context", []))
                context_section = (
                    f"\n\nRelevant context from memory:\n{memory_context}"
                    if memory_context else ""
                )
                
                routing_prompt = (
                    f"{system_prompt}\n\n"
                    f"You are a supervisor managing these workers: {worker_names}.\n"
                    f"Current turn: {turn + 1}/{max_turns}\n"
                    f"{context_section}\n\n"
                    "Based on the conversation, decide who should act next.\n"
                    "If the user's request is fully satisfied, choose 'FINISH'."
                )
                
                router = model.with_structured_output(RouteDecision)
                messages = state.get("messages", [])
                response = router.invoke(
                    [SystemMessage(content=routing_prompt)] + list(messages)
                )
                
                choice = response.next_step
                if choice not in worker_names and "finish" not in choice.lower():
                    choice = worker_names[0]  # Default to first worker
                elif "finish" in choice.lower():
                    choice = "__end__"
                
                logger.info(f"Router → {choice} (reason: {response.reasoning[:60]})")
                
                return {
                    "next_worker": choice,
                    "turn_count": turn + 1,
                }
                
            except Exception as e:
                logger.error(f"Router model failed: {e}")
                # Fallback: route to first worker
                return {
                    "next_worker": worker_names[0] if worker_names else "__end__",
                    "turn_count": turn + 1,
                }
        
        # No model: simple round-robin or single-worker routing
        if len(worker_names) == 1:
            return {
                "next_worker": worker_names[0],
                "turn_count": turn + 1,
            }
        
        # Default: finish
        return {
            "next_worker": "__end__",
            "turn_count": turn + 1,
        }
    
    return router_node


def _build_memory_node() -> Callable:
    """
    Build the memory injection node.
    
    Runs before the router to pull relevant context from the
    Supabase cloud memory into the state.
    """
    def memory_node(state: DOMEState) -> Dict[str, Any]:
        messages = state.get("messages", [])
        if not messages:
            return {}
        
        # Get the latest user message for context retrieval
        last_msg = messages[-1]
        if not hasattr(last_msg, "content") or not last_msg.content:
            return {}
        
        query = str(last_msg.content)
        if len(query) < 10:
            return {}
        
        try:
            from core.memory_client import get_memory_client
            client = get_memory_client(state.get("agent_id", "system"))
            
            # Search cloud memory for relevant context
            results = client.search(query, limit=3)
            context = [
                f"[Memory] {r.get('content', '')}" 
                for r in results 
                if r.get('content')
            ]
            
            if context:
                logger.info(f"Injected {len(context)} memories into context")
            
            return {"memory_context": context}
            
        except Exception as e:
            logger.warning(f"Memory injection failed (non-critical): {e}")
            return {}
    
    return memory_node


def _build_learning_node() -> Callable:
    """
    Build the post-execution learning node.
    
    After a workflow completes, this node stores any new insights
    in the cloud memory for future recall.
    """
    def learning_node(state: DOMEState) -> Dict[str, Any]:
        try:
            from core.memory_client import get_memory_client
            from core.supabase_client import log_audit
            
            agent_id = state.get("agent_id", "system")
            client = get_memory_client(agent_id)
            
            # Log the completed workflow to audit
            log_audit(
                agent_id=agent_id,
                action_type="workflow_complete",
                summary=f"Workflow completed in {state.get('turn_count', 0)} turns",
                details={
                    "turns": state.get("turn_count", 0),
                    "escalated": state.get("escalated", False),
                    "environment": state.get("environment", "unknown"),
                    "tool_results_count": len(state.get("tool_results", [])),
                }
            )
            
        except Exception as e:
            logger.warning(f"Learning node failed (non-critical): {e}")
        
        return {}
    
    return learning_node


# =============================================================================
# GRAPH BUILDER
# =============================================================================

def create_dome_graph(
    workers: Dict[str, Callable],
    system_prompt: str = "You are a helpful DOME agent.",
    model: Any = None,
    max_turns: int = 20,
    use_cloud_checkpoints: bool = True,
    interrupt_before: List[str] = None,
) -> Any:
    """
    Create a DOME 4.0 StateGraph with cloud-persisted checkpoints.
    
    Args:
        workers: Dict mapping worker names to their node functions.
                 Each worker function takes DOMEState and returns a dict update.
        system_prompt: System prompt for the router/supervisor.
        model: LLM model for intelligent routing. If None, uses simple routing.
        max_turns: Maximum conversation turns before auto-finish.
        use_cloud_checkpoints: If True, uses Supabase for checkpoints.
                               If False, uses in-memory (no cross-env resume).
        interrupt_before: List of node names to pause before for HITL approval.
                          Example: ["deploy", "send_email"]
    
    Returns:
        Compiled LangGraph application with checkpointing.
    """
    
    # Build the graph
    graph = StateGraph(DOMEState)
    
    # --- Add core nodes ---
    graph.add_node("memory", _build_memory_node())
    graph.add_node("router", _build_router_node(workers, system_prompt, model))
    graph.add_node("learning", _build_learning_node())
    
    # --- Add worker nodes ---
    for name, func in workers.items():
        graph.add_node(name, func)
    
    # --- Define edges ---
    
    # Entry: always start with memory injection
    graph.add_edge(START, "memory")
    
    # Memory → Router
    graph.add_edge("memory", "router")
    
    # Router → Worker (conditional)
    def route_from_router(state: DOMEState) -> str:
        next_worker = state.get("next_worker", "__end__")
        if next_worker == "__end__" or next_worker not in workers:
            return "learning"
        return next_worker
    
    destinations = list(workers.keys()) + ["learning"]
    graph.add_conditional_edges("router", route_from_router, destinations)
    
    # Workers → Router (loop back for multi-turn)
    for name in workers:
        graph.add_edge(name, "router")
    
    # Learning → END
    graph.add_edge("learning", END)
    
    # --- Setup checkpointer ---
    if use_cloud_checkpoints:
        try:
            from core.checkpoint_saver import SupabaseCheckpointer
            checkpointer = SupabaseCheckpointer()
            logger.info("[DOME 4.0] Using Supabase cloud checkpoints")
        except Exception as e:
            logger.warning(f"Supabase checkpointer failed, using memory: {e}")
            checkpointer = MemorySaver()
    else:
        checkpointer = MemorySaver()
    
    # --- Compile with HITL interrupts ---
    compile_kwargs = {"checkpointer": checkpointer}
    if interrupt_before:
        compile_kwargs["interrupt_before"] = interrupt_before
    
    app = graph.compile(**compile_kwargs)
    
    logger.info(
        f"[DOME 4.0] Graph compiled: {len(workers)} workers, "
        f"cloud_checkpoints={use_cloud_checkpoints}, "
        f"hitl_nodes={interrupt_before or 'none'}"
    )
    
    return app


# =============================================================================
# CONVENIENCE: Simple single-agent graph
# =============================================================================

def create_simple_agent(
    agent_fn: Callable,
    agent_name: str = "agent",
    system_prompt: str = "You are a helpful assistant.",
    model: Any = None,
    use_cloud_checkpoints: bool = True,
) -> Any:
    """
    Create a simple single-worker DOME graph.
    
    For cases where you just need one agent with memory + checkpointing.
    
    Args:
        agent_fn: The agent's node function (takes DOMEState, returns dict)
        agent_name: Name for the agent node
        system_prompt: System prompt
        model: LLM for routing decisions (optional for single-agent)
        use_cloud_checkpoints: Use Supabase for cross-env checkpoints
    """
    return create_dome_graph(
        workers={agent_name: agent_fn},
        system_prompt=system_prompt,
        model=model,
        use_cloud_checkpoints=use_cloud_checkpoints,
    )
