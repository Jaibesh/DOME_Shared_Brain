"""
DOME 2.0 - Enhanced Supervisor with Runtime Policy
===================================================
Extends the base supervisor with:
- Runtime policy enforcement (max turns, tool calls, etc.)
- Retry policy with exponential backoff
- Circuit breaker pattern
- Fallback model strategy
- Policy gate integration
- State hash caching

Version: 1.0.0
"""

import time
import hashlib
import logging
from typing import List, Optional, Dict, Any, TypedDict, Annotated, Callable
from datetime import datetime, timedelta
from collections import defaultdict
import operator

from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage, AIMessage
from langgraph.graph import StateGraph, END
from pydantic import BaseModel

try:
    from langchain_google_genai import ChatGoogleGenerativeAI
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

from execution.contracts import (
    SupervisorRuntimePolicy,
    RetryPolicy,
    CircuitBreakerConfig,
    ConversationState,
    OutboundMessage,
    PolicyDecision,
    PolicyAction,
    EscalationReason,
    RunMetrics,
    VersionInfo,
    ChannelType,
)
from execution.policy_gate import get_policy_gate, get_consent_enforcer, enforce_policy
from execution.tenant_memory import get_tenant_memory
from execution.utils import minify_prompt

# Setup Logging
try:
    from execution import utils
    logger = utils.setup_logging("enhanced_supervisor", "brain/logs/supervisor.log")
except ImportError:
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("enhanced_supervisor")


# =============================================================================
# CIRCUIT BREAKER
# =============================================================================

class CircuitState:
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """
    Circuit breaker pattern for handling repeated failures.
    """

    def __init__(self, config: CircuitBreakerConfig):
        self.config = config
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: Optional[datetime] = None
        self._half_open_calls = 0

    @property
    def state(self) -> str:
        """Get current circuit state, checking for timeout reset."""
        if self._state == CircuitState.OPEN:
            if self._last_failure_time:
                elapsed = (datetime.utcnow() - self._last_failure_time).total_seconds()
                if elapsed >= self.config.reset_timeout_seconds:
                    self._state = CircuitState.HALF_OPEN
                    self._half_open_calls = 0
        return self._state

    def can_execute(self) -> bool:
        """Check if execution is allowed."""
        state = self.state  # Triggers timeout check
        if state == CircuitState.CLOSED:
            return True
        if state == CircuitState.HALF_OPEN:
            return self._half_open_calls < self.config.half_open_max_calls
        return False  # OPEN

    def record_success(self):
        """Record a successful execution."""
        if self._state == CircuitState.HALF_OPEN:
            self._half_open_calls += 1
            if self._half_open_calls >= self.config.half_open_max_calls:
                # Enough successes, close the circuit
                self._state = CircuitState.CLOSED
                self._failure_count = 0
        else:
            self._failure_count = 0

    def record_failure(self):
        """Record a failed execution."""
        self._failure_count += 1
        self._last_failure_time = datetime.utcnow()

        if self._state == CircuitState.HALF_OPEN:
            # Failed during half-open, reopen circuit
            self._state = CircuitState.OPEN
        elif self._failure_count >= self.config.failure_threshold:
            # Threshold exceeded, open circuit
            self._state = CircuitState.OPEN

    def reset(self):
        """Reset the circuit breaker."""
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time = None
        self._half_open_calls = 0


# =============================================================================
# RETRY EXECUTOR
# =============================================================================

class RetryExecutor:
    """
    Executes operations with retry logic and exponential backoff.
    """

    def __init__(self, policy: RetryPolicy):
        self.policy = policy

    def execute(
        self,
        operation: Callable,
        *args,
        **kwargs
    ) -> tuple[Any, int]:
        """
        Execute operation with retries.

        Args:
            operation: Function to execute
            *args, **kwargs: Arguments for the operation

        Returns:
            Tuple of (result, attempts_made)

        Raises:
            Last exception if all retries fail
        """
        last_exception = None
        delay = self.policy.initial_delay_ms / 1000.0  # Convert to seconds

        for attempt in range(self.policy.max_retries + 1):
            try:
                result = operation(*args, **kwargs)
                return result, attempt + 1
            except Exception as e:
                last_exception = e
                logger.warning(f"Attempt {attempt + 1} failed: {e}")

                if attempt < self.policy.max_retries:
                    time.sleep(delay)
                    # Exponential backoff
                    delay = min(
                        delay * self.policy.exponential_base,
                        self.policy.max_delay_ms / 1000.0
                    )

        raise last_exception


# =============================================================================
# STATE CACHE
# =============================================================================

class StateCache:
    """
    Caches responses based on state hashes.
    """

    def __init__(self, ttl_seconds: int = 300):
        self.ttl_seconds = ttl_seconds
        self._cache: Dict[str, Dict[str, Any]] = {}

    def _compute_hash(self, state: Dict[str, Any]) -> str:
        """Compute a hash for the state."""
        # Create a deterministic representation
        content = []
        for msg in state.get("messages", []):
            if hasattr(msg, "content"):
                content.append(str(msg.content))
        state_str = "|".join(content)
        return hashlib.md5(state_str.encode()).hexdigest()

    def get(self, state: Dict[str, Any]) -> Optional[Any]:
        """Get cached response for state."""
        state_hash = self._compute_hash(state)
        if state_hash in self._cache:
            entry = self._cache[state_hash]
            if datetime.utcnow() < entry["expires_at"]:
                logger.debug(f"Cache hit for state hash {state_hash[:8]}")
                return entry["value"]
            else:
                del self._cache[state_hash]
        return None

    def set(self, state: Dict[str, Any], value: Any):
        """Cache response for state."""
        state_hash = self._compute_hash(state)
        self._cache[state_hash] = {
            "value": value,
            "expires_at": datetime.utcnow() + timedelta(seconds=self.ttl_seconds)
        }

    def clear(self):
        """Clear the cache."""
        self._cache.clear()


# =============================================================================
# ENHANCED AGENT STATE
# =============================================================================

class EnhancedAgentState(TypedDict):
    """Enhanced state with policy tracking."""
    messages: Annotated[List[BaseMessage], operator.add]
    next_agent: Optional[str]
    
    # Policy tracking
    turn_count: int
    tool_call_count: int
    total_tokens: int
    start_time: float

    # Flags
    opted_out: bool
    escalated: bool
    escalation_reason: Optional[str]

    # Tenant context
    tenant_id: str
    conversation_id: str

    # Outbound message pending policy check (Option A from DOME checklist)
    pending_outbound: Optional[OutboundMessage]
    last_policy_decision: Optional[Dict[str, Any]]


# =============================================================================
# ENHANCED SUPERVISOR
# =============================================================================

class EnhancedSupervisor:
    """
    Enhanced supervisor with runtime policy enforcement.
    """

    def __init__(
        self,
        system_prompt: str,
        workers: List[str],
        tenant_id: str,
        runtime_policy: Optional[SupervisorRuntimePolicy] = None,
        model_name: str = "models/gemini-1.5-pro",
        router_model_name: str = "models/gemini-2.0-flash",
        fallback_model_name: Optional[str] = None,
        versions: Optional[VersionInfo] = None
    ):
        # OPTIMIZATION: Minify system prompt to save tokens
        self.system_prompt = minify_prompt(system_prompt)
        
        self.workers = workers
        self.tenant_id = tenant_id
        self.runtime_policy = runtime_policy or SupervisorRuntimePolicy()
        self.model_name = model_name
        self.router_model_name = router_model_name
        self.fallback_model_name = fallback_model_name
        self.versions = versions or VersionInfo()

        # Initialize models
        if GEMINI_AVAILABLE:
            try:
                # Main model for complex tasks (if needed) or fallback
                self.model = ChatGoogleGenerativeAI(
                    model=model_name,
                )
                # Fast, cheap model for routing & summarization
                self.router_model = ChatGoogleGenerativeAI(
                    model=router_model_name,
                )
                if fallback_model_name:
                    self.fallback_model = ChatGoogleGenerativeAI(
                        model=fallback_model_name,
                    )
                else:
                    self.fallback_model = None
            except Exception as e:
                logger.error(f"Failed to initialize Gemini models: {e}")
                self.model = None
                self.router_model = None
                self.fallback_model = None
        else:
            self.model = None
            self.router_model = None
            self.fallback_model = None
            logger.warning("Gemini not available")

        # Initialize components
        self.circuit_breaker = CircuitBreaker(self.runtime_policy.circuit_breaker)
        self.retry_executor = RetryExecutor(self.runtime_policy.retry_policy)
        self.state_cache = StateCache(self.runtime_policy.cache_ttl_seconds)

        # Metrics tracking
        self._current_metrics: Optional[RunMetrics] = None

    def _summarize_messages(self, current_summary: Optional[str], messages: List[Dict[str, Any]]) -> str:
        """Callback for memory compaction."""
        if not self.router_model:
            return current_summary or ""

        # Format messages for prompt
        msg_text = "\n".join([f"{m.get('role', 'unknown')}: {m.get('content', '')}" for m in messages])
        
        prompt = (
            "Summarize the following conversation history into a concise paragraph. "
            "Preserve key facts, user intent, and pending tasks. "
            "If a previous summary exists, merge it.\n\n"
            f"Previous Summary: {current_summary or 'None'}\n\n"
            f"New Messages:\n{msg_text}"
        )
        
        try:
            response = self.router_model.invoke(prompt)
            return str(response.content)
        except Exception as e:
            logger.error(f"Summarization failed: {e}")
            # Return old summary on failure to be safe
            return current_summary or "Summary generation failed."

    def create_workflow(self):
        """Build the routing graph with policy enforcement."""

        policy = self.runtime_policy

        def supervisor_node(state: EnhancedAgentState):
            """Main supervisor routing node with policy checks."""

            # === Check turn limits ===
            if state.get("turn_count", 0) >= policy.max_turns_per_conversation:
                logger.warning(f"Max turns ({policy.max_turns_per_conversation}) reached")
                return {"next_agent": "FINISH", "escalated": True, "escalation_reason": "max_turns_exceeded"}

            # === Memory Compaction (Rolling Context) ===
            # Attempt to compact memory if threshold reached
            if self.router_model:
                try:
                    memory = get_tenant_memory(self.tenant_id)
                    conv_id = state.get("conversation_id")
                    if conv_id:
                        memory.compact_conversation(
                            conversation_id=conv_id,
                            summarizer=self._summarize_messages,
                            threshold=15, # trigger after 15 messages
                            keep_last=5   # keep last 5
                        )
                except Exception as e:
                    logger.warning(f"Auto-compaction failed (non-critical): {e}")

            # === Check opt-out ===
            if state.get("opted_out", False) and policy.stop_on_opt_out:
                logger.info("Stopping due to opt-out")
                return {"next_agent": "FINISH"}

            # === Check escalation ===
            if state.get("escalated", False) and policy.stop_on_escalation:
                logger.info("Stopping due to escalation")
                return {"next_agent": "FINISH"}

            # === Check time limits ===
            start_time = state.get("start_time", time.time())
            elapsed = time.time() - start_time
            if elapsed > policy.max_conversation_duration_seconds:
                logger.warning("Max conversation duration exceeded")
                return {"next_agent": "FINISH", "escalated": True, "escalation_reason": "timeout"}

            # === Check circuit breaker ===
            if not self.circuit_breaker.can_execute():
                logger.warning("Circuit breaker open, escalating")
                return {"next_agent": "FINISH", "escalated": True, "escalation_reason": "circuit_open"}

            # === Check cache ===
            if policy.enable_state_hash_caching:
                cached = self.state_cache.get(state)
                if cached:
                    return cached

            # === Context Injection (Proactive Memory) ===
            context_injection = ""
            if messages and isinstance(messages[-1], HumanMessage):
                try:
                    query_text = str(messages[-1].content)
                    if len(query_text) > 10:  # Only search for meaningful queries
                        memory = get_tenant_memory(self.tenant_id)
                        # We use the router model (if available) to generate a better search query? 
                        # For speed, just use the raw text for now.
                        results = memory.search_cold_memory(query_text, n_results=3)
                        if results:
                            context_items = [f"- {r['content']}" for r in results]
                            context_injection = "\n\nRelevant Context from Memory:\n" + "\n".join(context_items)
                            logger.info(f"Injected {len(results)} context items from memory")
                except Exception as e:
                    logger.warning(f"Context injection failed: {e}")

            # === Route to worker ===
            messages = state["messages"]
            options = self.workers + ["FINISH"]

            prompt = (
                f"{self.system_prompt}\n"
                f"{context_injection}\n"
                f"You are a Supervisor managing these workers: {self.workers}.\n"
                "Given the conversation, who should act next?\n"
                "If the user's request is fully satisfied, respond with FINISH.\n"
                "Otherwise, choose the best worker.\n"
                f"Current turn: {state.get('turn_count', 0) + 1}/{policy.max_turns_per_conversation}"
            )

            class Route(BaseModel):
                next_step: str

            try:
                # Use router_model (Flash) for decision making if available and policy allows
                active_model = self.router_model if (self.router_model and policy.use_smaller_model_for_routing) else self.model
                
                router = active_model.with_structured_output(Route)
                response, attempts = self.retry_executor.execute(
                    router.invoke,
                    [SystemMessage(content=prompt)] + messages
                )

                # Record success
                self.circuit_breaker.record_success()

                choice = response.next_step
                if choice not in options:
                    if "finish" in choice.lower():
                        choice = "FINISH"
                    else:
                        choice = self.workers[0]

                result = {
                    "next_agent": choice,
                    "turn_count": state.get("turn_count", 0) + 1
                }

                # Cache result (include context in state hash?)
                # To be correct, the context injection changes the input. 
                # Ideally, state caching should account for injected context.
                # But since context depends on the message (which is part of the state), 
                # the hash of the messages should implicitly cover it if we assume context is deterministic for a given query.
                if policy.enable_state_hash_caching:
                    self.state_cache.set(state, result)

                return result

            except Exception as e:
                # Record failure
                self.circuit_breaker.record_failure()
                logger.error(f"Supervisor routing failed: {e}")

                # Try fallback model
                if self.fallback_model:
                    try:
                        fallback_router = self.fallback_model.with_structured_output(Route)
                        # Re-inject context for fallback? Yes.
                        fallback_prompt = prompt 
                        response = fallback_router.invoke([SystemMessage(content=fallback_prompt)] + messages)
                        return {"next_agent": response.next_step, "turn_count": state.get("turn_count", 0) + 1}
                    except Exception as fallback_error:
                        logger.error(f"Fallback model also failed: {fallback_error}")

                # Escalate on failure
                return {"next_agent": "FINISH", "escalated": True, "escalation_reason": "routing_failure"}

        def send_outbound_node(state: EnhancedAgentState):
            """
            Centralized outbound node that enforces policy gate on ALL messages.
            This node runs BEFORE any message is sent externally.
            Implements Option A from DOME v2 checklist.
            """
            messages = state.get("messages", [])
            if not messages:
                return state

            last_message = messages[-1]
            if not hasattr(last_message, "content") or not last_message.content:
                return state

            # Check if this is an AI message (potential outbound)
            if not isinstance(last_message, AIMessage):
                return state

            # Create outbound message for policy check
            outbound = OutboundMessage(
                tenant_id=state.get("tenant_id", "unknown"),
                conversation_id=state.get("conversation_id", "unknown"),
                channel=ChannelType.INTERNAL,
                recipient_id="customer",
                content=last_message.content
            )

            # Enforce policy gate
            can_send, final_message, decision = enforce_policy(outbound)

            # Log the policy decision for audit trail
            self.record_policy_decision(decision)

            # Store decision in state for observability
            decision_dict = decision.model_dump(mode="json")

            if decision.action == PolicyAction.ESCALATE:
                logger.info(f"Message escalated: {decision.escalation_reason}")
                return {
                    "escalated": True,
                    "escalation_reason": str(decision.escalation_reason) if decision.escalation_reason else "policy_escalation",
                    "last_policy_decision": decision_dict
                }

            if decision.action == PolicyAction.BLOCK:
                logger.warning(f"Message blocked: {decision.block_reason}")
                # Remove the blocked message and escalate
                return {
                    "messages": messages[:-1],  # Remove blocked message
                    "escalated": True,
                    "escalation_reason": f"message_blocked: {decision.block_reason}",
                    "last_policy_decision": decision_dict
                }

            if decision.action == PolicyAction.REWRITE and decision.rewritten_content:
                logger.info(f"Message rewritten: {decision.rewrite_reason}")
                # Replace message content with rewritten version
                new_message = AIMessage(content=decision.rewritten_content)
                return {
                    "messages": messages[:-1] + [new_message],
                    "last_policy_decision": decision_dict
                }

            # APPROVE - message can be sent as-is
            return {
                "last_policy_decision": decision_dict
            }

        def send_route(state: EnhancedAgentState):
            """Route from send_outbound to END or back to supervisor."""
            if state.get("escalated", False):
                return END
            if state.get("next_agent") == "FINISH":
                return END
            # Can continue the conversation
            return "supervisor"

        # Build workflow
        workflow = StateGraph(EnhancedAgentState)
        workflow.add_node("supervisor", supervisor_node)

        # Always add send_outbound node - policy gate enforced here
        workflow.add_node("send_outbound", send_outbound_node)

        # Add placeholder worker nodes (workers will be added externally)
        for worker in self.workers:
            pass  # Workers added externally via add_worker_node

        workflow.set_entry_point("supervisor")

        # Supervisor routes to workers or directly to send_outbound (for FINISH)
        def route(state):
            next_agent = state.get("next_agent")
            if next_agent == "FINISH":
                return "send_outbound"  # Route through policy gate before ending
            if next_agent in self.workers:
                return next_agent
            # Unknown worker - route to send_outbound
            return "send_outbound"

        workflow.add_conditional_edges("supervisor", route)

        # send_outbound routes to END or back to supervisor
        workflow.add_conditional_edges("send_outbound", send_route)

        return workflow

    def start_run(self, conversation_id: str) -> RunMetrics:
        """Start a new run and initialize metrics."""
        self._current_metrics = RunMetrics(
            tenant_id=self.tenant_id,
            conversation_id=conversation_id,
            versions=self.versions
        )
        return self._current_metrics

    def end_run(self, outcome: str = "completed") -> RunMetrics:
        """End the current run and finalize metrics."""
        if self._current_metrics:
            self._current_metrics.completed_at = datetime.utcnow()
            self._current_metrics.final_outcome = outcome
            self._current_metrics.total_latency_ms = int(
                (self._current_metrics.completed_at - self._current_metrics.started_at).total_seconds() * 1000
            )

            # Log to tenant memory
            memory = get_tenant_memory(self.tenant_id)
            memory.log_outbound_action(
                action_type="run_completed",
                conversation_id=self._current_metrics.conversation_id,
                summary=f"Run completed with outcome: {outcome}",
                details=self._current_metrics.model_dump(mode="json"),
                versions=self.versions
            )

        return self._current_metrics

    def record_tool_call(self, tool_name: str, latency_ms: int, success: bool):
        """Record a tool call in metrics."""
        if self._current_metrics:
            self._current_metrics.tools_called.append({
                "name": tool_name,
                "latency_ms": latency_ms,
                "success": success,
                "timestamp": datetime.utcnow().isoformat()
            })
            if not success:
                self._current_metrics.tool_errors.append({
                    "name": tool_name,
                    "timestamp": datetime.utcnow().isoformat()
                })

    def record_policy_decision(self, decision: PolicyDecision):
        """Record a policy decision in metrics."""
        if self._current_metrics:
            self._current_metrics.policy_decisions.append(decision.model_dump(mode="json"))
            self._current_metrics.violations_detected += len(decision.violations)

        # Also log to tenant memory for audit trail
        try:
            memory = get_tenant_memory(self.tenant_id)
            memory.log_outbound_action(
                action_type="policy_decision",
                conversation_id=self._current_metrics.conversation_id if self._current_metrics else "unknown",
                summary=f"Policy decision: {decision.action.value}",
                details={
                    "action": decision.action.value,
                    "approved": decision.approved,
                    "violations": [v.model_dump(mode="json") for v in decision.violations] if decision.violations else [],
                    "risk_score": decision.risk_score,
                    "block_reason": decision.block_reason,
                    "rewrite_reason": decision.rewrite_reason,
                    "escalation_reason": str(decision.escalation_reason) if decision.escalation_reason else None,
                },
                versions=self.versions
            )
        except Exception as e:
            logger.warning(f"Failed to log policy decision to tenant memory: {e}")

    def add_worker_to_workflow(self, workflow: StateGraph, worker_name: str, worker_node: Callable):
        """
        Add a worker node to the workflow with proper routing to send_outbound.

        Args:
            workflow: The StateGraph being built
            worker_name: Name of the worker
            worker_node: The worker node function
        """
        workflow.add_node(worker_name, worker_node)
        # Route worker output through policy gate (send_outbound)
        workflow.add_edge(worker_name, "send_outbound")


# =============================================================================
# FACTORY FUNCTION
# =============================================================================

def create_enhanced_supervisor(
    system_prompt: str,
    workers: List[str],
    tenant_id: str,
    runtime_policy: Optional[SupervisorRuntimePolicy] = None,
    router_model_name: str = "models/gemini-2.0-flash",
    **kwargs
) -> EnhancedSupervisor:
    """
    Factory function to create an enhanced supervisor.

    Args:
        system_prompt: System prompt for the supervisor
        workers: List of worker names
        tenant_id: Tenant identifier
        runtime_policy: Optional runtime policy (uses defaults if not provided)
        router_model_name: Model to use for routing (defaults to fast flash model)
        **kwargs: Additional arguments passed to EnhancedSupervisor

    Returns:
        Configured EnhancedSupervisor instance
    """
    return EnhancedSupervisor(
        system_prompt=system_prompt,
        workers=workers,
        tenant_id=tenant_id,
        runtime_policy=runtime_policy,
        router_model_name=router_model_name,
        **kwargs
    )
