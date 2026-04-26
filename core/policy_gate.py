"""
DOME 2.0 - Policy Gate Module
==============================
Enforces compliance rules on all outbound actions.
The Policy Gate runs on EVERY outbound message before it's sent.

Key responsibilities:
- Detect policy violations (diagnosis, PHI, guarantees, etc.)
- Approve, rewrite, escalate, or block messages
- Maintain audit trail of decisions

Version: 1.0.0
"""

import re
import time
from typing import List, Optional, Dict, Any, Callable, Set
from datetime import datetime, timezone
from pydantic import BaseModel, Field

from execution.contracts import (
    PolicyDecision,
    PolicyViolation,
    PolicyAction,
    EscalationReason,
    OutboundMessage,
    ConversationState,
    AuditLogEntry,
)


# =============================================================================
# POLICY RULES
# =============================================================================

class PolicyRule(BaseModel):
    """Definition of a policy rule."""
    id: str
    name: str
    description: str
    severity: str  # low, medium, high, critical
    patterns: List[str] = Field(default_factory=list)  # Regex patterns
    keywords: List[str] = Field(default_factory=list)  # Keyword matches
    action: PolicyAction = PolicyAction.BLOCK  # Default action on violation
    escalation_reason: Optional[EscalationReason] = None
    enabled: bool = True


# =============================================================================
# DEFAULT POLICY RULES (Chiropractor-focused)
# =============================================================================

DEFAULT_RULES: List[PolicyRule] = [
    # === CRITICAL: Medical/Legal Compliance ===
    PolicyRule(
        id="no_diagnosis",
        name="No Diagnosis Language",
        description="Prevents any diagnostic or medical advice language",
        severity="critical",
        patterns=[
            r"\b(diagnos(e|is|ing|ed)|condition|disease|disorder|syndrome)\b",
            r"\byou (have|suffer from|are experiencing)\b.*\b(pain|injury|problem)\b",
            r"\b(appears to be|looks like|seems like|could be)\b.*\b(medical|condition|injury)\b",
        ],
        keywords=[
            "diagnosis", "diagnose", "diagnosed", "prognosis",
            "you have", "you're suffering from", "your condition is",
            "based on your symptoms", "medical opinion", "medical advice"
        ],
        action=PolicyAction.REWRITE,
        escalation_reason=EscalationReason.DIAGNOSIS_ATTEMPT,
    ),
    PolicyRule(
        id="no_treatment_claims",
        name="No Treatment Claims",
        description="Prevents treatment promises or outcome guarantees",
        severity="critical",
        patterns=[
            r"\bwill (cure|fix|heal|eliminate|resolve)\b",
            r"\bguarantee(d|s)?\b.*\b(results?|outcome|relief|improvement)\b",
            r"\b(100%|definitely|certainly|absolutely)\b.*\b(work|help|cure|better|improve)\b",
            r"\bwill definitely\b",
            r"\bdefinitely (help|work|feel)\b",
        ],
        keywords=[
            "will cure", "will fix", "guaranteed results", "guaranteed relief",
            "promise you", "we guarantee", "100% effective", "definitely help",
            "will eliminate", "will heal", "definitely feel better", "will definitely"
        ],
        action=PolicyAction.REWRITE,
    ),
    PolicyRule(
        id="no_phi_collection",
        name="No PHI Collection",
        description="Prevents collection or storage of Protected Health Information",
        severity="critical",
        patterns=[
            r"\b(social security|ssn|ss#)\b",
            r"\b(insurance|policy)\s*(number|id|#)\b",
            r"\bdate of birth\b",
            r"\b(medical|health)\s*record\b",
        ],
        keywords=[
            "social security", "insurance number", "policy number",
            "medical record", "health record", "diagnosis history",
            "treatment history", "what medications"
        ],
        action=PolicyAction.ESCALATE,
        escalation_reason=EscalationReason.PHI_DETECTED,
    ),

    # === HIGH: Safety Escalation ===
    PolicyRule(
        id="emergency_language",
        name="Emergency Language Detection",
        description="Escalates messages containing emergency/crisis language",
        severity="high",
        patterns=[
            r"\b(emergency|911|ambulance|hospital)\b",
            r"\b(severe|excruciating|unbearable)\s+pain\b",
            r"\b(can't|cannot)\s+(move|walk|breathe|feel)\b",
            r"\b(suicide|suicidal|kill myself|end my life)\b",
        ],
        keywords=[
            "emergency", "call 911", "go to hospital", "severe pain",
            "can't move", "can't breathe", "numbness", "paralysis",
            "chest pain", "heart attack", "stroke"
        ],
        action=PolicyAction.ESCALATE,
        escalation_reason=EscalationReason.EMERGENCY_LANGUAGE,
    ),
    PolicyRule(
        id="anger_detection",
        name="Anger/Threat Detection",
        description="Escalates angry or threatening messages",
        severity="high",
        patterns=[
            r"\b(lawyer|attorney|sue|lawsuit|legal action)\b",
            r"\b(report|complaint|better business|bbb)\b",
            r"\b(review|yelp|google review)\b.*\b(bad|negative|terrible|worst)\b",
            r"\b(furious|outraged|disgusted)\b",
        ],
        keywords=[
            "speak to manager", "supervisor", "owner",
            "lawyer", "attorney", "sue", "legal action",
            "BBB", "Better Business Bureau", "file a complaint",
            "leaving a review", "terrible service", "worst experience"
        ],
        action=PolicyAction.ESCALATE,
        escalation_reason=EscalationReason.ANGER_DETECTED,
    ),
    PolicyRule(
        id="review_threat",
        name="Review Threat Detection",
        description="Escalates review threats for human handling",
        severity="high",
        patterns=[
            r"\b(leave|post|write)\b.*\b(review|rating)\b",
            r"\b(tell|warn)\b.*\b(everyone|friends|family)\b",
            r"\b(social media|facebook|twitter|instagram)\b",
        ],
        keywords=[
            "leave a review", "post a review", "one star",
            "warn everyone", "tell my friends", "social media"
        ],
        action=PolicyAction.ESCALATE,
        escalation_reason=EscalationReason.REVIEW_THREAT,
    ),

    # === MEDIUM: Compliance ===
    PolicyRule(
        id="opt_out_handling",
        name="Opt-Out Detection",
        description="Detects opt-out requests that must be honored",
        severity="medium",
        patterns=[
            r"\b(stop|unsubscribe|opt.?out|remove)\b.*\b(text|message|contact)\b",
            r"\bdo not (text|message|call|contact)\b",
            r"\bleave me alone\b",
        ],
        keywords=[
            "stop", "unsubscribe", "opt out", "opt-out",
            "remove me", "stop texting", "stop messaging",
            "don't contact", "do not contact", "leave me alone"
        ],
        action=PolicyAction.ESCALATE,
        escalation_reason=EscalationReason.OPT_OUT,
    ),
    PolicyRule(
        id="pricing_accuracy",
        name="Pricing Accuracy",
        description="Flags specific pricing claims for verification",
        severity="medium",
        patterns=[
            r"\$\d+",  # Any dollar amount
            r"\b\d+\s*(dollars|usd)\b",
            r"\b(free|no cost|complimentary)\b.*\b(consultation|exam|visit)\b",
        ],
        keywords=[
            "special offer", "discount", "promotion", "limited time",
            "free consultation", "no charge"
        ],
        action=PolicyAction.APPROVE,  # Flag but allow (for audit)
    ),

    # === LOW: Quality ===
    PolicyRule(
        id="no_competitor_mention",
        name="No Competitor Mentions",
        description="Flags mentions of competitor practices",
        severity="low",
        patterns=[
            r"\bother (chiropractor|clinic|practice|doctor)\b",
            r"\bcompetitor\b",
        ],
        keywords=[
            "other chiropractor", "another clinic", "competitor"
        ],
        action=PolicyAction.APPROVE,
    ),
]


# =============================================================================
# REWRITE TEMPLATES
# =============================================================================

REWRITE_TEMPLATES: Dict[str, str] = {
    "no_diagnosis": (
        "I understand you're experiencing discomfort. Our chiropractor would be happy to "
        "assess your situation during a consultation and discuss options that may help. "
        "Would you like to schedule an appointment?"
    ),
    "no_treatment_claims": (
        "Many of our patients have reported positive experiences with chiropractic care. "
        "Results vary by individual, and our chiropractor will work with you to develop "
        "a personalized approach. Would you like to learn more?"
    ),
    "emergency_language": None,  # Always escalate, no rewrite
    "anger_detection": None,  # Always escalate, no rewrite
    "review_threat": None,  # Always escalate, no rewrite
    "opt_out_handling": (
        "I understand. You've been removed from our contact list. "
        "If you ever need our services in the future, please don't hesitate to reach out. "
        "Have a great day!"
    ),
}


# =============================================================================
# POLICY GATE CLASS
# =============================================================================

class PolicyGate:
    """
    Enforces policies on outbound messages.
    Must be called before any message is sent externally.
    """

    def __init__(
        self,
        rules: Optional[List[PolicyRule]] = None,
        rewrite_templates: Optional[Dict[str, str]] = None,
        custom_validators: Optional[List[Callable]] = None,
        version: str = "1.0.0"
    ):
        self.rules = rules or DEFAULT_RULES
        self.rewrite_templates = rewrite_templates or REWRITE_TEMPLATES
        self.custom_validators = custom_validators or []
        self.version = version

        # Compile regex patterns for efficiency
        self._compiled_patterns: Dict[str, List[re.Pattern]] = {}
        for rule in self.rules:
            if rule.enabled and rule.patterns:
                self._compiled_patterns[rule.id] = [
                    re.compile(p, re.IGNORECASE) for p in rule.patterns
                ]

    def check(
        self,
        message: OutboundMessage,
        state: Optional[ConversationState] = None
    ) -> PolicyDecision:
        """
        Check a message against all policy rules.

        Args:
            message: The outbound message to check
            state: Optional conversation state for context

        Returns:
            PolicyDecision with approval status and any required actions
        """
        start_time = time.time()
        violations: List[PolicyViolation] = []
        rules_checked: List[str] = []

        content = message.content.lower()

        # Check each rule
        for rule in self.rules:
            if not rule.enabled:
                continue

            rules_checked.append(rule.id)
            violation = self._check_rule(rule, content, message.content)

            if violation:
                violations.append(violation)

        # Run custom validators
        for validator in self.custom_validators:
            try:
                custom_violations = validator(message, state)
                if custom_violations:
                    violations.extend(custom_violations)
            except Exception:
                pass  # Don't let custom validators break the gate

        # Determine final action
        decision = self._determine_action(violations, message)

        # Add metadata
        decision.policy_version = self.version
        decision.rules_checked = rules_checked
        decision.latency_ms = int((time.time() - start_time) * 1000)

        return decision

    def _check_rule(
        self,
        rule: PolicyRule,
        content_lower: str,
        content_original: str
    ) -> Optional[PolicyViolation]:
        """Check a single rule against content."""
        matched_text = None

        # Check keyword matches
        for keyword in rule.keywords:
            if keyword.lower() in content_lower:
                matched_text = keyword
                break

        # Check regex patterns
        if not matched_text and rule.id in self._compiled_patterns:
            for pattern in self._compiled_patterns[rule.id]:
                match = pattern.search(content_original)
                if match:
                    matched_text = match.group()
                    break

        if matched_text:
            return PolicyViolation(
                rule_id=rule.id,
                rule_name=rule.name,
                severity=rule.severity,
                description=rule.description,
                matched_text=matched_text
            )

        return None

    def _determine_action(
        self,
        violations: List[PolicyViolation],
        _message: OutboundMessage  # Reserved for future dynamic rewrites
    ) -> PolicyDecision:
        """Determine the final action based on violations."""
        if not violations:
            return PolicyDecision(
                action=PolicyAction.APPROVE,
                approved=True,
                violations=[],
                risk_score=0.0
            )

        # Calculate risk score
        severity_weights = {"low": 0.1, "medium": 0.3, "high": 0.6, "critical": 1.0}
        risk_score = min(
            1.0,
            sum(severity_weights.get(v.severity, 0.5) for v in violations)
        )

        # Find the highest severity violation
        severity_order = ["low", "medium", "high", "critical"]
        max_severity = max(violations, key=lambda v: severity_order.index(v.severity))
        max_severity_rule = next(
            (r for r in self.rules if r.id == max_severity.rule_id),
            None
        )

        if not max_severity_rule:
            return PolicyDecision(
                action=PolicyAction.BLOCK,
                approved=False,
                violations=violations,
                risk_score=risk_score,
                block_reason="Unknown rule violation"
            )

        # Determine action based on rule configuration
        action = max_severity_rule.action

        if action == PolicyAction.ESCALATE:
            return PolicyDecision(
                action=PolicyAction.ESCALATE,
                approved=False,
                violations=violations,
                risk_score=risk_score,
                escalation_reason=max_severity_rule.escalation_reason,
                escalation_notes=f"Triggered by: {max_severity.matched_text}"
            )

        if action == PolicyAction.REWRITE:
            rewritten = self._try_rewrite(max_severity_rule.id)
            if rewritten:
                return PolicyDecision(
                    action=PolicyAction.REWRITE,
                    approved=True,
                    violations=violations,
                    risk_score=risk_score,
                    rewritten_content=rewritten,
                    rewrite_reason=f"Violation of: {max_severity_rule.name}"
                )
            else:
                # Can't rewrite, escalate instead
                return PolicyDecision(
                    action=PolicyAction.ESCALATE,
                    approved=False,
                    violations=violations,
                    risk_score=risk_score,
                    escalation_reason=EscalationReason.POLICY_VIOLATION,
                    escalation_notes=f"Cannot rewrite: {max_severity_rule.name}"
                )

        if action == PolicyAction.BLOCK:
            return PolicyDecision(
                action=PolicyAction.BLOCK,
                approved=False,
                violations=violations,
                risk_score=risk_score,
                block_reason=f"Blocked by rule: {max_severity_rule.name}"
            )

        # Default: approve with warnings
        return PolicyDecision(
            action=PolicyAction.APPROVE,
            approved=True,
            violations=violations,
            risk_score=risk_score
        )

    def _try_rewrite(self, rule_id: str) -> Optional[str]:
        """Attempt to rewrite content using templates."""
        template = self.rewrite_templates.get(rule_id)
        if template:
            return template
        return None

    def add_rule(self, rule: PolicyRule) -> None:
        """Add a new policy rule."""
        self.rules.append(rule)
        if rule.enabled and rule.patterns:
            self._compiled_patterns[rule.id] = [
                re.compile(p, re.IGNORECASE) for p in rule.patterns
            ]

    def disable_rule(self, rule_id: str) -> None:
        """Disable a policy rule."""
        for rule in self.rules:
            if rule.id == rule_id:
                rule.enabled = False
                break

    def enable_rule(self, rule_id: str) -> None:
        """Enable a policy rule."""
        for rule in self.rules:
            if rule.id == rule_id:
                rule.enabled = True
                break


# =============================================================================
# CONSENT ENFORCER
# =============================================================================

class ConsentEnforcer:
    """
    Manages opt-out/consent state and enforces messaging permissions.
    """

    def __init__(self):
        self._opted_out: Set[str] = set()  # Set of opted-out identifiers
        self._consent_log: List[Dict[str, Any]] = []

    def _norm_channel(self, channel) -> str:
        """Normalize channel to string. Accepts ChannelType enum or string."""
        if hasattr(channel, "value"):
            return str(channel.value).lower()
        return str(channel).lower()

    def record_opt_out(
        self,
        tenant_id: str,
        identifier: str,
        channel: str,
        reason: Optional[str] = None
    ) -> AuditLogEntry:
        """Record an opt-out request."""
        ch = self._norm_channel(channel)
        key = f"{tenant_id}:{ch}:{identifier}"
        self._opted_out.add(key)

        log_entry = {
            "tenant_id": tenant_id,
            "identifier": identifier,
            "channel": ch,
            "action": "opt_out",
            "reason": reason,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        self._consent_log.append(log_entry)

        return AuditLogEntry(
            tenant_id=tenant_id,
            action_type="consent_opt_out",
            actor="system",
            summary=f"Opt-out recorded for {identifier} on {ch}",
            details=log_entry
        )

    def check_consent(
        self,
        tenant_id: str,
        identifier: str,
        channel: str
    ) -> bool:
        """Check if we have consent to message this identifier."""
        ch = self._norm_channel(channel)
        key = f"{tenant_id}:{ch}:{identifier}"
        return key not in self._opted_out

    def is_opted_out(
        self,
        tenant_id: str,
        identifier: str,
        channel: str
    ) -> bool:
        """Check if identifier has opted out."""
        ch = self._norm_channel(channel)
        key = f"{tenant_id}:{ch}:{identifier}"
        return key in self._opted_out


# =============================================================================
# POLICY GATE SINGLETON
# =============================================================================

_policy_gate_instance: Optional[PolicyGate] = None
_consent_enforcer_instance: Optional[ConsentEnforcer] = None


def get_policy_gate() -> PolicyGate:
    """Get the singleton PolicyGate instance."""
    global _policy_gate_instance
    if _policy_gate_instance is None:
        _policy_gate_instance = PolicyGate()
    return _policy_gate_instance


def get_consent_enforcer() -> ConsentEnforcer:
    """Get the singleton ConsentEnforcer instance."""
    global _consent_enforcer_instance
    if _consent_enforcer_instance is None:
        _consent_enforcer_instance = ConsentEnforcer()
    return _consent_enforcer_instance


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def check_message(
    content: str,
    tenant_id: str,
    recipient_id: str,
    channel: str = "sms"
) -> PolicyDecision:
    """
    Convenience function to check a message string.

    Args:
        content: Message content to check
        tenant_id: Tenant identifier
        recipient_id: Recipient identifier
        channel: Communication channel

    Returns:
        PolicyDecision
    """
    from execution.contracts import ChannelType

    message = OutboundMessage(
        tenant_id=tenant_id,
        conversation_id="check",
        channel=ChannelType(channel),
        recipient_id=recipient_id,
        content=content
    )

    gate = get_policy_gate()
    return gate.check(message)


def enforce_policy(
    message: OutboundMessage,
    state: Optional[ConversationState] = None
) -> tuple[bool, OutboundMessage, PolicyDecision]:
    """
    Enforce policy on a message and return the result.

    Args:
        message: The outbound message
        state: Optional conversation state

    Returns:
        Tuple of (can_send, final_message, decision)
    """
    gate = get_policy_gate()
    consent = get_consent_enforcer()

    # First check consent
    if consent.is_opted_out(message.tenant_id, message.recipient_id, message.channel):
        return (
            False,
            message,
            PolicyDecision(
                action=PolicyAction.BLOCK,
                approved=False,
                block_reason="Recipient has opted out"
            )
        )

    # Check policy
    decision = gate.check(message, state)

    if decision.action == PolicyAction.APPROVE:
        message.policy_approved = True
        return (True, message, decision)

    if decision.action == PolicyAction.REWRITE and decision.rewritten_content:
        message.original_content = message.content
        message.content = decision.rewritten_content
        message.rewritten = True
        message.policy_approved = True
        return (True, message, decision)

    # ESCALATE or BLOCK
    return (False, message, decision)
