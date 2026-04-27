"""
DOME 2.0 - Contracts Module
===========================
Pydantic models defining strict I/O contracts between framework layers.
These contracts enforce type safety and validation across:
- Supervisor <-> Worker
- Worker <-> Tool
- Worker <-> Supervisor
- Supervisor <-> Channel Adapter

Version: 1.0.0
"""

from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, Dict, List, Literal, Any
from datetime import datetime, timezone
from enum import Enum
import uuid


# =============================================================================
# ENUMS
# =============================================================================

class EventType(str, Enum):
    """Normalized event types that trigger agent workflows."""
    LEAD_CREATED = "lead.created"
    MESSAGE_INBOUND = "message.inbound"
    MESSAGE_OUTBOUND = "message.outbound"
    APPOINTMENT_SCHEDULED = "appointment.scheduled"
    APPOINTMENT_CANCELLED = "appointment.cancelled"
    APPOINTMENT_REMINDER = "appointment.reminder"
    TASK_ASSIGNED = "task.assigned"
    TASK_COMPLETED = "task.completed"
    ESCALATION_TRIGGERED = "escalation.triggered"
    OPT_OUT_RECEIVED = "opt_out.received"
    SYSTEM_ERROR = "system.error"
    WEBHOOK_RECEIVED = "webhook.received"


class ChannelType(str, Enum):
    """Supported communication channels."""
    SMS = "sms"
    EMAIL = "email"
    VOICE = "voice"
    WEBCHAT = "webchat"
    INTERNAL = "internal"


class PolicyAction(str, Enum):
    """Policy gate decision actions."""
    APPROVE = "approve"
    REWRITE = "rewrite"
    ESCALATE = "escalate"
    BLOCK = "block"


class MessagePriority(str, Enum):
    """Message priority levels."""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class EscalationReason(str, Enum):
    """Reasons for escalating to human."""
    EMERGENCY_LANGUAGE = "emergency_language"
    ANGER_DETECTED = "anger_detected"
    LEGAL_MENTION = "legal_mention"
    REVIEW_THREAT = "review_threat"
    PHI_DETECTED = "phi_detected"
    DIAGNOSIS_ATTEMPT = "diagnosis_attempt"
    PRICING_EXCEEDED = "pricing_exceeded"
    LOOP_DETECTED = "loop_detected"
    POLICY_VIOLATION = "policy_violation"
    OPT_OUT = "opt_out"
    UNKNOWN = "unknown"


# =============================================================================
# VERSION TRACKING
# =============================================================================

class VersionInfo(BaseModel):
    """Version metadata for tracking framework components."""
    directive_version: str = Field(default="1.0.0", description="Version of active directives/SOPs")
    prompt_version: str = Field(default="1.0.0", description="Version of prompt templates")
    tool_versions: Dict[str, str] = Field(default_factory=dict, description="Version map of registered tools")
    policy_version: str = Field(default="1.0.0", description="Version of policy rules")
    config_version: str = Field(default="1.0.0", description="Version of tenant configuration")


# =============================================================================
# EVENT CONTRACT
# =============================================================================

class Event(BaseModel):
    """
    Normalized event that triggers agent workflows.
    All inbound triggers must be converted to this format.
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Unique event ID")
    tenant_id: str = Field(..., description="Tenant/organization identifier")
    type: EventType = Field(..., description="Event type classification")
    channel: ChannelType = Field(default=ChannelType.INTERNAL, description="Source channel")

    # Content
    content: str = Field(..., description="Event payload/message content")
    sender_id: Optional[str] = Field(default=None, description="External sender identifier (phone, email, etc.)")
    sender_name: Optional[str] = Field(default=None, description="Sender display name")

    # Context
    conversation_id: Optional[str] = Field(default=None, description="Conversation thread ID")
    parent_event_id: Optional[str] = Field(default=None, description="Parent event for threading")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional event metadata")

    # Timestamps
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Event creation time")
    received_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Event receipt time")

    model_config = ConfigDict(use_enum_values=True)


# =============================================================================
# STATE CONTRACT
# =============================================================================

class ConversationState(BaseModel):
    """
    Complete conversation state passed between supervisor and workers.
    Includes tenant context and conversation history.
    """
    # Identity
    tenant_id: str = Field(..., description="Tenant/organization identifier")
    conversation_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Conversation thread ID")

    # Participants
    customer_id: Optional[str] = Field(default=None, description="CRM customer ID if known")
    customer_name: Optional[str] = Field(default=None, description="Customer display name")
    customer_phone: Optional[str] = Field(default=None, description="Customer phone number")
    customer_email: Optional[str] = Field(default=None, description="Customer email")

    # Conversation tracking
    turn_count: int = Field(default=0, description="Number of turns in conversation")
    tool_call_count: int = Field(default=0, description="Total tool calls this conversation")
    last_worker: Optional[str] = Field(default=None, description="Last worker that handled the conversation")

    # State flags
    opted_out: bool = Field(default=False, description="Whether customer has opted out")
    escalated: bool = Field(default=False, description="Whether conversation has been escalated")
    escalation_reason: Optional[EscalationReason] = Field(default=None, description="Reason for escalation")

    # Memory
    extracted_entities: Dict[str, Any] = Field(default_factory=dict, description="Extracted entities from conversation")
    context_summary: Optional[str] = Field(default=None, description="Compressed conversation summary")

    # Versioning
    versions: VersionInfo = Field(default_factory=VersionInfo, description="Active component versions")

    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = ConfigDict(use_enum_values=True)


# =============================================================================
# AGENT OUTPUT CONTRACT
# =============================================================================

class AgentDecision(BaseModel):
    """
    Structured output from an agent worker node.
    Captures the agent's reasoning and proposed action.
    """
    worker_name: str = Field(..., description="Name of the worker that made this decision")

    # Reasoning
    intent_detected: str = Field(..., description="Detected user intent")
    reasoning: str = Field(..., description="Agent's reasoning for the action")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Confidence in the decision")

    # Proposed action
    action_type: Literal["respond", "tool_call", "escalate", "handoff", "finish"] = Field(
        ..., description="Type of action to take"
    )
    proposed_response: Optional[str] = Field(default=None, description="Proposed response text")
    tool_name: Optional[str] = Field(default=None, description="Tool to call if action_type is tool_call")
    tool_args: Dict[str, Any] = Field(default_factory=dict, description="Tool arguments")
    handoff_target: Optional[str] = Field(default=None, description="Target worker for handoff")

    # Flags
    requires_policy_check: bool = Field(default=True, description="Whether response needs policy gate review")
    contains_sensitive_info: bool = Field(default=False, description="Whether response contains sensitive data")

    # Metadata
    tokens_used: int = Field(default=0, description="Tokens consumed by this decision")
    latency_ms: int = Field(default=0, description="Latency in milliseconds")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# =============================================================================
# OUTBOUND MESSAGE CONTRACT
# =============================================================================

class OutboundMessage(BaseModel):
    """
    Standardized outbound message to external channels.
    All outgoing communications must use this format.
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Message ID")
    tenant_id: str = Field(..., description="Tenant identifier")
    conversation_id: str = Field(..., description="Conversation thread ID")

    # Destination
    channel: ChannelType = Field(..., description="Target channel")
    recipient_id: str = Field(..., description="Recipient identifier (phone, email, etc.)")
    recipient_name: Optional[str] = Field(default=None, description="Recipient display name")

    # Content
    content: str = Field(..., description="Message content")
    subject: Optional[str] = Field(default=None, description="Subject line (for email)")

    # Classification
    message_type: str = Field(default="response", description="Message type/category")
    priority: MessagePriority = Field(default=MessagePriority.NORMAL, description="Message priority")
    tags: List[str] = Field(default_factory=list, description="Classification tags")

    # Policy
    policy_approved: bool = Field(default=False, description="Whether policy gate approved this message")
    policy_version: str = Field(default="1.0.0", description="Policy version used for approval")
    rewritten: bool = Field(default=False, description="Whether content was rewritten by policy gate")
    original_content: Optional[str] = Field(default=None, description="Original content if rewritten")

    # Delivery
    scheduled_at: Optional[datetime] = Field(default=None, description="Scheduled delivery time")
    sent_at: Optional[datetime] = Field(default=None, description="Actual send time")
    delivered_at: Optional[datetime] = Field(default=None, description="Delivery confirmation time")
    delivery_status: Literal["pending", "sent", "delivered", "failed", "bounced"] = Field(
        default="pending", description="Delivery status"
    )

    # Metadata
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(use_enum_values=True)


# =============================================================================
# POLICY DECISION CONTRACT
# =============================================================================

class PolicyViolation(BaseModel):
    """Details of a policy violation detected by the policy gate."""
    rule_id: str = Field(..., description="Identifier of the violated rule")
    rule_name: str = Field(..., description="Human-readable rule name")
    severity: Literal["low", "medium", "high", "critical"] = Field(..., description="Violation severity")
    description: str = Field(..., description="Description of the violation")
    matched_text: Optional[str] = Field(default=None, description="Text that triggered the violation")


class PolicyDecision(BaseModel):
    """
    Output from the Policy Gate.
    Determines whether an outbound action should proceed.
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Decision ID")

    # Decision
    action: PolicyAction = Field(..., description="Policy decision action")
    approved: bool = Field(..., description="Whether the action is approved")

    # Analysis
    violations: List[PolicyViolation] = Field(default_factory=list, description="Detected violations")
    risk_score: float = Field(default=0.0, ge=0.0, le=1.0, description="Overall risk score")

    # Rewrite (if action is REWRITE)
    rewritten_content: Optional[str] = Field(default=None, description="Rewritten safe content")
    rewrite_reason: Optional[str] = Field(default=None, description="Reason for rewrite")

    # Escalation (if action is ESCALATE)
    escalation_reason: Optional[EscalationReason] = Field(default=None, description="Reason for escalation")
    escalation_notes: Optional[str] = Field(default=None, description="Additional escalation context")

    # Block (if action is BLOCK)
    block_reason: Optional[str] = Field(default=None, description="Reason for blocking")

    # Metadata
    policy_version: str = Field(default="1.0.0", description="Policy version used")
    rules_checked: List[str] = Field(default_factory=list, description="Rules that were evaluated")
    latency_ms: int = Field(default=0, description="Processing time in milliseconds")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = ConfigDict(use_enum_values=True)


# =============================================================================
# TOOL RESULT CONTRACT
# =============================================================================

class ToolResult(BaseModel):
    """
    Standardized result from tool execution.
    All tools must return results in this format.
    """
    tool_name: str = Field(..., description="Name of the executed tool")
    success: bool = Field(..., description="Whether execution succeeded")

    # Result data
    result: Any = Field(default=None, description="Tool result data")
    error_message: Optional[str] = Field(default=None, description="Error message if failed")
    error_code: Optional[str] = Field(default=None, description="Error code if failed")

    # Metadata
    execution_time_ms: int = Field(default=0, description="Execution time in milliseconds")
    retries: int = Field(default=0, description="Number of retry attempts")
    cached: bool = Field(default=False, description="Whether result was from cache")

    # Audit
    tenant_id: Optional[str] = Field(default=None, description="Tenant context")
    invoked_by: Optional[str] = Field(default=None, description="Agent/worker that invoked the tool")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# =============================================================================
# AUDIT LOG CONTRACT
# =============================================================================

class AuditLogEntry(BaseModel):
    """
    Immutable audit log entry for compliance and debugging.
    Records all significant actions in the system.
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Log entry ID")
    tenant_id: str = Field(..., description="Tenant identifier")
    conversation_id: Optional[str] = Field(default=None, description="Related conversation")

    # Action details
    action_type: str = Field(..., description="Type of action (message_sent, tool_called, policy_decision, etc.)")
    actor: str = Field(..., description="Who performed the action (worker name, system, etc.)")

    # Content
    summary: str = Field(..., description="Human-readable action summary")
    details: Dict[str, Any] = Field(default_factory=dict, description="Full action details")

    # Related entities
    event_id: Optional[str] = Field(default=None, description="Related event ID")
    message_id: Optional[str] = Field(default=None, description="Related message ID")
    policy_decision_id: Optional[str] = Field(default=None, description="Related policy decision ID")

    # Versioning
    versions: VersionInfo = Field(default_factory=VersionInfo, description="Component versions at time of action")

    # Timestamp
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = ConfigDict(use_enum_values=True)


# =============================================================================
# SUPERVISOR RUNTIME POLICY CONTRACT
# =============================================================================

class RetryPolicy(BaseModel):
    """Configuration for retry behavior."""
    max_retries: int = Field(default=3, ge=0, description="Maximum retry attempts")
    initial_delay_ms: int = Field(default=1000, ge=0, description="Initial delay before first retry")
    max_delay_ms: int = Field(default=30000, ge=0, description="Maximum delay between retries")
    exponential_base: float = Field(default=2.0, ge=1.0, description="Exponential backoff base")


class CircuitBreakerConfig(BaseModel):
    """Configuration for circuit breaker pattern."""
    failure_threshold: int = Field(default=5, ge=1, description="Failures before opening circuit")
    reset_timeout_seconds: int = Field(default=60, ge=1, description="Time before attempting reset")
    half_open_max_calls: int = Field(default=3, ge=1, description="Max calls in half-open state")


class SupervisorRuntimePolicy(BaseModel):
    """
    Runtime policy for supervisor behavior.
    Defines limits, failure handling, and safety constraints.
    """
    # Turn limits
    max_turns_per_conversation: int = Field(default=20, ge=1, description="Maximum turns before forcing end")
    max_tool_calls_per_turn: int = Field(default=5, ge=1, description="Maximum tool calls in a single turn")
    max_total_tool_calls: int = Field(default=50, ge=1, description="Maximum total tool calls per conversation")

    # Time limits
    max_conversation_duration_seconds: int = Field(default=1800, ge=60, description="Maximum conversation duration")
    max_turn_duration_seconds: int = Field(default=120, ge=10, description="Maximum time per turn")

    # Token limits
    max_tokens_per_turn: int = Field(default=4000, ge=100, description="Maximum tokens per turn")
    max_total_tokens: int = Field(default=100000, ge=1000, description="Maximum total tokens per conversation")

    # Stop conditions
    stop_on_opt_out: bool = Field(default=True, description="Immediately stop on opt-out")
    stop_on_escalation: bool = Field(default=True, description="Stop after escalating to human")
    stop_on_loop_detected: bool = Field(default=True, description="Stop if loop is detected")

    # Failure handling
    retry_policy: RetryPolicy = Field(default_factory=RetryPolicy, description="Retry configuration")
    circuit_breaker: CircuitBreakerConfig = Field(default_factory=CircuitBreakerConfig, description="Circuit breaker config")

    # Fallback strategy
    fallback_model: Optional[str] = Field(default=None, description="Fallback model if primary fails")
    use_smaller_model_for_routing: bool = Field(default=True, description="Use smaller model for routing decisions")

    # Caching
    enable_state_hash_caching: bool = Field(default=True, description="Cache responses for identical states")
    cache_ttl_seconds: int = Field(default=300, ge=0, description="Cache time-to-live")

    # Policy gate
    require_policy_gate: bool = Field(default=True, description="Require policy gate for all outbound")
    policy_gate_timeout_ms: int = Field(default=5000, ge=100, description="Policy gate timeout")

    model_config = ConfigDict(use_enum_values=True)


# =============================================================================
# OBSERVABILITY CONTRACT
# =============================================================================

class RunMetrics(BaseModel):
    """Metrics collected during a single agent run."""
    run_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Unique run identifier")
    tenant_id: str = Field(..., description="Tenant identifier")
    conversation_id: str = Field(..., description="Conversation identifier")

    # Route tracking
    route_plan: List[str] = Field(default_factory=list, description="Planned route through workers")
    actual_route: List[str] = Field(default_factory=list, description="Actual route taken")

    # Tool tracking
    tools_called: List[Dict[str, Any]] = Field(default_factory=list, description="Tools called with timing")
    tool_errors: List[Dict[str, Any]] = Field(default_factory=list, description="Tool errors encountered")

    # Token/cost tracking
    total_tokens: int = Field(default=0, description="Total tokens used")
    prompt_tokens: int = Field(default=0, description="Prompt tokens")
    completion_tokens: int = Field(default=0, description="Completion tokens")
    estimated_cost_usd: float = Field(default=0.0, description="Estimated cost in USD")

    # Policy tracking
    policy_decisions: List[Dict[str, Any]] = Field(default_factory=list, description="Policy decisions made")
    violations_detected: int = Field(default=0, description="Number of violations detected")

    # Timing
    total_latency_ms: int = Field(default=0, description="Total processing time")
    worker_latencies: Dict[str, int] = Field(default_factory=dict, description="Latency per worker")

    # Outcome
    final_outcome: Literal["completed", "escalated", "blocked", "timeout", "error"] = Field(
        default="completed", description="Final outcome of the run"
    )
    outbound_messages: int = Field(default=0, description="Number of outbound messages sent")

    # Versions
    versions: VersionInfo = Field(default_factory=VersionInfo, description="Component versions")

    # Timestamps
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = Field(default=None)

    model_config = ConfigDict(use_enum_values=True)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def create_event(
    tenant_id: str,
    event_type: EventType,
    content: str,
    channel: ChannelType = ChannelType.INTERNAL,
    sender_id: Optional[str] = None,
    conversation_id: Optional[str] = None,
    **kwargs
) -> Event:
    """Factory function to create a new Event."""
    return Event(
        tenant_id=tenant_id,
        type=event_type,
        content=content,
        channel=channel,
        sender_id=sender_id,
        conversation_id=conversation_id,
        **kwargs
    )


def create_outbound_message(
    tenant_id: str,
    conversation_id: str,
    channel: ChannelType,
    recipient_id: str,
    content: str,
    **kwargs
) -> OutboundMessage:
    """Factory function to create a new OutboundMessage."""
    return OutboundMessage(
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        channel=channel,
        recipient_id=recipient_id,
        content=content,
        **kwargs
    )


# =============================================================================
# DOME 4.0 — GRAPH STATE CONTRACTS
# =============================================================================

class GraphStateContract(BaseModel):
    """
    Contract for validating DOME 4.0 graph state transitions.
    Used to validate state before and after node execution.
    """
    messages_count: int = Field(ge=0, description="Number of messages in state")
    turn_count: int = Field(ge=0, description="Current turn number")
    max_turns: int = Field(ge=1, default=20, description="Max allowed turns")
    agent_id: str = Field(default="system", description="Active agent ID")
    environment: str = Field(default="home", description="Execution environment")
    escalated: bool = Field(default=False, description="Whether workflow has escalated")
    approval_needed: bool = Field(default=False, description="Whether HITL approval is needed")


class WorkerResult(BaseModel):
    """Standardized result from a DOME worker node."""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    worker_name: str = Field(description="Name of the worker that produced this result")
    success: bool = Field(default=True)
    output: Any = Field(default=None, description="The worker's output")
    error: Optional[str] = Field(default=None, description="Error message if failed")
    duration_ms: int = Field(default=0, description="Execution time in milliseconds")
    tools_used: List[str] = Field(default_factory=list, description="Tools invoked")
    metadata: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# =============================================================================
# DOME 4.0 — MCP TOOL SCHEMA
# =============================================================================

class MCPToolSchema(BaseModel):
    """
    Schema for registering a tool as MCP-compatible.
    Used in the dome_tools Supabase table.
    """
    tool_id: str = Field(description="Unique tool identifier")
    display_name: str = Field(description="Human-readable tool name")
    description: str = Field(default="", description="What the tool does")
    tool_type: Literal["python", "mcp", "playwright", "api"] = Field(default="python")
    input_schema: Dict[str, Any] = Field(
        default_factory=dict, 
        description="JSON Schema for tool inputs"
    )
    output_schema: Dict[str, Any] = Field(
        default_factory=dict, 
        description="JSON Schema for tool outputs"
    )
    source_path: Optional[str] = Field(
        default=None, 
        description="Relative path in DOME_CORE repo"
    )
    registered_by: Optional[str] = Field(default=None, description="Agent that registered it")
    version: str = Field(default="1.0.0")


class AgentCard(BaseModel):
    """
    Agent Card for A2A (Agent-to-Agent) protocol compatibility.
    Describes an agent's capabilities for discovery and negotiation.
    """
    agent_id: str
    display_name: str
    description: str = ""
    capabilities: List[str] = Field(default_factory=list)
    tools: List[str] = Field(default_factory=list)
    environment: str = Field(default="home")
    dome_version: str = Field(default="4.0")
    status: Literal["active", "dormant", "archived"] = "active"
    endpoint: Optional[str] = Field(default=None, description="Network endpoint if available")
    metadata: Dict[str, Any] = Field(default_factory=dict)

