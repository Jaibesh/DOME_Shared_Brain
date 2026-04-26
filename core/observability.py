"""
DOME 2.0 - Observability Module
================================
Provides structured logging, metrics collection, and debugging capabilities.

Logs structured data for every run:
- Route plans and actual routes taken
- Tools called with timing
- Token usage and cost
- Policy decisions with reasons
- Final outbound content and delivery status

Version: 1.0.0
"""

import os
import json
import time
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any, Callable
from contextlib import contextmanager
from functools import wraps

from pydantic import BaseModel, Field

from execution.contracts import (
    RunMetrics,
    VersionInfo,
    PolicyDecision,
    OutboundMessage,
)

# Setup Logging
try:
    from execution import utils
    base_logger = utils.setup_logging("observability", "brain/logs/observability.log")
except ImportError:
    logging.basicConfig(level=logging.INFO)
    base_logger = logging.getLogger("observability")


# =============================================================================
# CONFIGURATION - DOME 2.2.2
# =============================================================================

# Import path utilities
try:
    from core.utils import get_dome_path
except ImportError:
    def get_dome_path():
        return None

# Use centralized paths if available, fallback to local
_dome_root = get_dome_path()
if _dome_root:
    LOGS_PATH = os.path.join(_dome_root, "logs")
    METRICS_PATH = os.path.join(_dome_root, "logs")  # Metrics also in logs for unified NOC
else:
    LOGS_PATH = "brain/logs"
    METRICS_PATH = "brain/metrics"

# Cost estimates per 1K tokens (adjust as needed)
MODEL_COSTS = {
    "gemini-2.0-flash": {"prompt": 0.00015, "completion": 0.0006},
    "gemini-1.5-pro": {"prompt": 0.00125, "completion": 0.005},
    "gpt-4": {"prompt": 0.03, "completion": 0.06},
    "gpt-3.5-turbo": {"prompt": 0.0005, "completion": 0.0015},
    "claude-3-opus": {"prompt": 0.015, "completion": 0.075},
    "claude-3-sonnet": {"prompt": 0.003, "completion": 0.015},
    "default": {"prompt": 0.001, "completion": 0.002}
}


# =============================================================================
# STRUCTURED LOG ENTRY
# =============================================================================

class LogEntry(BaseModel):
    """A single structured log entry - DOME 2.2.2 Enhanced."""
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    level: str = "INFO"
    event_type: str
    tenant_id: Optional[str] = None
    conversation_id: Optional[str] = None
    run_id: Optional[str] = None
    worker: Optional[str] = None
    message: str
    data: Dict[str, Any] = Field(default_factory=dict)
    duration_ms: Optional[int] = None
    error: Optional[str] = None
    # DOME 2.2.2: Multi-tenant tracking
    agent_id: Optional[str] = None
    workspace_id: Optional[str] = None


# =============================================================================
# STRUCTURED LOGGER
# =============================================================================

class StructuredLogger:
    """
    Structured logger for observability.
    Logs to both console and JSON lines file.
    """

    def __init__(
        self,
        name: str,
        tenant_id: Optional[str] = None,
        logs_path: str = LOGS_PATH,
        agent_id: Optional[str] = None,
        workspace_id: Optional[str] = None
    ):
        self.name = name
        self.tenant_id = tenant_id
        self.logs_path = logs_path
        self._current_run_id: Optional[str] = None
        self._current_conversation_id: Optional[str] = None
        # DOME 2.2.2: Agent tracking
        self.agent_id = agent_id or os.environ.get("AGENT_ID")
        self.workspace_id = workspace_id or os.environ.get("WORKSPACE_ID")

        # Ensure log directory exists
        os.makedirs(logs_path, exist_ok=True)

        # File path for structured logs
        date_str = datetime.utcnow().strftime("%Y-%m-%d")
        self.log_file = os.path.join(logs_path, f"{name}_{date_str}.jsonl")

    def set_context(
        self,
        run_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        tenant_id: Optional[str] = None
    ):
        """Set context for subsequent log entries."""
        if run_id:
            self._current_run_id = run_id
        if conversation_id:
            self._current_conversation_id = conversation_id
        if tenant_id:
            self.tenant_id = tenant_id

    def clear_context(self):
        """Clear logging context."""
        self._current_run_id = None
        self._current_conversation_id = None

    def _write_entry(self, entry: LogEntry):
        """Write entry to log file and console."""
        # Add agent context
        entry.agent_id = self.agent_id
        entry.workspace_id = self.workspace_id
        
        # Console output
        log_msg = f"[{entry.event_type}] {entry.message}"
        if entry.duration_ms:
            log_msg += f" ({entry.duration_ms}ms)"
        if entry.error:
            log_msg += f" ERROR: {entry.error}"

        if entry.level == "ERROR":
            base_logger.error(log_msg)
        elif entry.level == "WARNING":
            base_logger.warning(log_msg)
        elif entry.level == "DEBUG":
            base_logger.debug(log_msg)
        else:
            base_logger.info(log_msg)

        # JSON file output
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(entry.model_dump_json() + "\n")
        except Exception as e:
            base_logger.error(f"Failed to write log entry: {e}")

    def log(
        self,
        event_type: str,
        message: str,
        level: str = "INFO",
        data: Optional[Dict[str, Any]] = None,
        duration_ms: Optional[int] = None,
        error: Optional[str] = None,
        worker: Optional[str] = None
    ):
        """Log a structured event."""
        entry = LogEntry(
            level=level,
            event_type=event_type,
            tenant_id=self.tenant_id,
            conversation_id=self._current_conversation_id,
            run_id=self._current_run_id,
            worker=worker,
            message=message,
            data=data or {},
            duration_ms=duration_ms,
            error=error
        )
        self._write_entry(entry)

    # Convenience methods
    def info(self, event_type: str, message: str, **kwargs):
        self.log(event_type, message, level="INFO", **kwargs)

    def warning(self, event_type: str, message: str, **kwargs):
        self.log(event_type, message, level="WARNING", **kwargs)

    def error(self, event_type: str, message: str, **kwargs):
        self.log(event_type, message, level="ERROR", **kwargs)

    def debug(self, event_type: str, message: str, **kwargs):
        self.log(event_type, message, level="DEBUG", **kwargs)

    # Domain-specific logging methods
    def log_route_decision(
        self,
        from_node: str,
        to_node: str,
        reason: Optional[str] = None
    ):
        """Log a routing decision."""
        self.info(
            "route_decision",
            f"Routing from {from_node} to {to_node}",
            data={"from": from_node, "to": to_node, "reason": reason}
        )

    def log_tool_call(
        self,
        tool_name: str,
        args: Dict[str, Any],
        result: Any,
        duration_ms: int,
        success: bool
    ):
        """Log a tool invocation."""
        level = "INFO" if success else "ERROR"
        self.log(
            "tool_call",
            f"Called {tool_name}",
            level=level,
            data={
                "tool": tool_name,
                "args": args,
                "result_preview": str(result)[:200] if result else None,
                "success": success
            },
            duration_ms=duration_ms,
            error=str(result) if not success else None
        )

    def log_token_usage(
        self,
        model: str,
        prompt_tokens: int,
        completion_tokens: int
    ):
        """Log token usage and estimated cost."""
        costs = MODEL_COSTS.get(model, MODEL_COSTS["default"])
        cost = (prompt_tokens / 1000 * costs["prompt"]) + \
               (completion_tokens / 1000 * costs["completion"])

        self.info(
            "token_usage",
            f"Model {model}: {prompt_tokens}+{completion_tokens} tokens, ~${cost:.4f}",
            data={
                "model": model,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
                "estimated_cost_usd": cost
            }
        )

    def log_policy_decision(self, decision: PolicyDecision):
        """Log a policy gate decision."""
        level = "INFO" if decision.approved else "WARNING"
        self.log(
            "policy_decision",
            f"Policy: {decision.action} (approved={decision.approved})",
            level=level,
            data={
                "action": decision.action,
                "approved": decision.approved,
                "violations": [v.model_dump() for v in decision.violations],
                "risk_score": decision.risk_score,
                "escalation_reason": decision.escalation_reason
            }
        )

    def log_outbound_message(
        self,
        message: OutboundMessage,
        delivered: bool
    ):
        """Log an outbound message."""
        self.info(
            "outbound_message",
            f"Outbound to {message.channel}: {message.delivery_status}",
            data={
                "message_id": message.id,
                "channel": message.channel,
                "recipient": message.recipient_id,
                "content_preview": message.content[:100] if message.content else None,
                "rewritten": message.rewritten,
                "policy_approved": message.policy_approved,
                "delivered": delivered
            }
        )


# =============================================================================
# RUN TRACKER
# =============================================================================

class RunTracker:
    """
    Tracks metrics for a single agent run.
    """

    def __init__(
        self,
        tenant_id: str,
        conversation_id: str,
        versions: Optional[VersionInfo] = None
    ):
        self.metrics = RunMetrics(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            versions=versions or VersionInfo()
        )
        self.logger = StructuredLogger("run_tracker", tenant_id=tenant_id)
        self.logger.set_context(
            run_id=self.metrics.run_id,
            conversation_id=conversation_id
        )
        self._start_time = time.time()

    @property
    def run_id(self) -> str:
        return self.metrics.run_id

    def add_route(self, worker: str):
        """Record a routing step."""
        self.metrics.actual_route.append(worker)
        self.logger.log_route_decision(
            from_node=self.metrics.actual_route[-2] if len(self.metrics.actual_route) > 1 else "start",
            to_node=worker
        )

    def record_tool_call(
        self,
        tool_name: str,
        args: Dict[str, Any],
        result: Any,
        duration_ms: int,
        success: bool
    ):
        """Record a tool invocation."""
        self.metrics.tools_called.append({
            "name": tool_name,
            "args": args,
            "duration_ms": duration_ms,
            "success": success,
            "timestamp": datetime.utcnow().isoformat()
        })

        if not success:
            self.metrics.tool_errors.append({
                "name": tool_name,
                "error": str(result),
                "timestamp": datetime.utcnow().isoformat()
            })

        self.logger.log_tool_call(tool_name, args, result, duration_ms, success)

    def record_tokens(
        self,
        model: str,
        prompt_tokens: int,
        completion_tokens: int
    ):
        """Record token usage."""
        self.metrics.prompt_tokens += prompt_tokens
        self.metrics.completion_tokens += completion_tokens
        self.metrics.total_tokens += prompt_tokens + completion_tokens

        costs = MODEL_COSTS.get(model, MODEL_COSTS["default"])
        cost = (prompt_tokens / 1000 * costs["prompt"]) + \
               (completion_tokens / 1000 * costs["completion"])
        self.metrics.estimated_cost_usd += cost

        self.logger.log_token_usage(model, prompt_tokens, completion_tokens)

    def record_policy_decision(self, decision: PolicyDecision):
        """Record a policy gate decision."""
        self.metrics.policy_decisions.append(decision.model_dump(mode="json"))
        self.metrics.violations_detected += len(decision.violations)
        self.logger.log_policy_decision(decision)

    def record_outbound(self, message: OutboundMessage, delivered: bool):
        """Record an outbound message."""
        if delivered:
            self.metrics.outbound_messages += 1
        self.logger.log_outbound_message(message, delivered)

    def record_worker_latency(self, worker: str, latency_ms: int):
        """Record latency for a worker."""
        self.metrics.worker_latencies[worker] = latency_ms

    def complete(self, outcome: str = "completed") -> RunMetrics:
        """Complete the run and return final metrics."""
        self.metrics.completed_at = datetime.utcnow()
        self.metrics.final_outcome = outcome
        self.metrics.total_latency_ms = int((time.time() - self._start_time) * 1000)

        self.logger.info(
            "run_completed",
            f"Run completed: {outcome}",
            data={
                "run_id": self.metrics.run_id,
                "outcome": outcome,
                "total_latency_ms": self.metrics.total_latency_ms,
                "total_tokens": self.metrics.total_tokens,
                "estimated_cost_usd": self.metrics.estimated_cost_usd,
                "outbound_messages": self.metrics.outbound_messages,
                "violations_detected": self.metrics.violations_detected
            }
        )

        # Save metrics to file
        self._save_metrics()

        return self.metrics

    def _save_metrics(self):
        """Save run metrics to file."""
        try:
            os.makedirs(METRICS_PATH, exist_ok=True)
            date_str = datetime.utcnow().strftime("%Y-%m-%d")
            metrics_file = os.path.join(METRICS_PATH, f"runs_{date_str}.jsonl")
            with open(metrics_file, "a", encoding="utf-8") as f:
                f.write(self.metrics.model_dump_json() + "\n")
        except Exception as e:
            self.logger.error("metrics_save_failed", f"Failed to save metrics: {e}")


# =============================================================================
# DECORATORS
# =============================================================================

def timed(logger: StructuredLogger, event_type: str):
    """Decorator to time and log function execution."""
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            start = time.time()
            try:
                result = func(*args, **kwargs)
                duration_ms = int((time.time() - start) * 1000)
                logger.info(
                    event_type,
                    f"{func.__name__} completed",
                    duration_ms=duration_ms
                )
                return result
            except Exception as e:
                duration_ms = int((time.time() - start) * 1000)
                logger.error(
                    event_type,
                    f"{func.__name__} failed",
                    duration_ms=duration_ms,
                    error=str(e)
                )
                raise
        return wrapper
    return decorator


@contextmanager
def track_operation(
    logger: StructuredLogger,
    event_type: str,
    message: str,
    data: Optional[Dict[str, Any]] = None
):
    """Context manager for tracking operation timing."""
    start = time.time()
    try:
        yield
        duration_ms = int((time.time() - start) * 1000)
        logger.info(event_type, f"{message} completed", data=data, duration_ms=duration_ms)
    except Exception as e:
        duration_ms = int((time.time() - start) * 1000)
        logger.error(event_type, f"{message} failed", data=data, duration_ms=duration_ms, error=str(e))
        raise


# =============================================================================
# METRICS AGGREGATION
# =============================================================================

class MetricsAggregator:
    """
    Aggregates metrics across runs for reporting.
    """

    def __init__(self, metrics_path: str = METRICS_PATH):
        self.metrics_path = metrics_path

    def load_runs(
        self,
        tenant_id: Optional[str] = None,
        date: Optional[str] = None,
        limit: int = 100
    ) -> List[RunMetrics]:
        """Load run metrics from files."""
        runs = []
        date_str = date or datetime.utcnow().strftime("%Y-%m-%d")
        metrics_file = os.path.join(self.metrics_path, f"runs_{date_str}.jsonl")

        if not os.path.exists(metrics_file):
            return runs

        try:
            with open(metrics_file, "r", encoding="utf-8") as f:
                for line in f:
                    if len(runs) >= limit:
                        break
                    try:
                        run = RunMetrics.model_validate_json(line.strip())
                        if tenant_id is None or run.tenant_id == tenant_id:
                            runs.append(run)
                    except Exception:
                        continue
        except Exception as e:
            base_logger.error(f"Failed to load metrics: {e}")

        return runs

    def get_summary(
        self,
        runs: List[RunMetrics]
    ) -> Dict[str, Any]:
        """Get aggregate summary of runs."""
        if not runs:
            return {"total_runs": 0}

        total_tokens = sum(r.total_tokens for r in runs)
        total_cost = sum(r.estimated_cost_usd for r in runs)
        total_latency = sum(r.total_latency_ms for r in runs)
        total_violations = sum(r.violations_detected for r in runs)
        total_outbound = sum(r.outbound_messages for r in runs)

        outcomes = {}
        for r in runs:
            outcomes[r.final_outcome] = outcomes.get(r.final_outcome, 0) + 1

        return {
            "total_runs": len(runs),
            "total_tokens": total_tokens,
            "total_cost_usd": total_cost,
            "avg_tokens_per_run": total_tokens / len(runs),
            "avg_cost_per_run": total_cost / len(runs),
            "avg_latency_ms": total_latency / len(runs),
            "total_violations": total_violations,
            "total_outbound_messages": total_outbound,
            "outcomes": outcomes
        }


# =============================================================================
# FACTORY FUNCTIONS
# =============================================================================

def create_logger(
    name: str,
    tenant_id: Optional[str] = None
) -> StructuredLogger:
    """Create a structured logger."""
    return StructuredLogger(name, tenant_id=tenant_id)


def create_run_tracker(
    tenant_id: str,
    conversation_id: str,
    versions: Optional[VersionInfo] = None
) -> RunTracker:
    """Create a run tracker."""
    return RunTracker(tenant_id, conversation_id, versions)
