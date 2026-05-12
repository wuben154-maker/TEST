"""Shared models for task payloads, parameters, and optional SSE-shaped results.

Used by middleware helpers and file/context parsing. Routing lives in the
LangGraph agent (``MASTER_AGENT.md``), not a separate intent-classifier service.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from uuid import uuid4

from app.datetime_support import now_app
from app.middleware.file_parser import FileInfo


# ============================================
# Enums
# ============================================


class TaskCategory(str, Enum):
    """Task category enumeration."""
    SECURITY = "security"           # Security analysis task
    RESEARCH = "research"           # Deep research task
    UNKNOWN = "unknown"             # Unknown/unsupported
    PARAMETER_NEEDED = "parameter_needed"  # Requires user input parameters


class InputType(str, Enum):
    """Input type enumeration."""
    TEXT = "text"
    EMAIL = "email"
    LOG = "log"
    CODE = "code"
    BINARY = "binary"
    IMAGE = "image"
    DOCUMENT = "document"
    MIXED = "mixed"


class AnalysisScope(str, Enum):
    """Analysis scope boundary."""
    ALL_INPUT = "all_input"
    ATTACHMENT_ONLY = "attachment_only"
    TEXT_ONLY = "text_only"


class SecuritySubType(str, Enum):
    """Security sub-type enumeration."""
    EMAIL_ANALYSIS = "email_analysis"       # Email security analysis
    MALWARE_ANALYSIS = "malware_analysis"   # Malware analysis
    WEB_ATTACK = "web_attack"               # Web attack analysis
    SOC_ALERT = "soc_alert"                 # SOC alert analysis
    VULN_SCAN = "vuln_scan"                 # Vulnerability scan analysis
    IOC_LOOKUP = "ioc_lookup"               # IOC lookup
    GENERIC_SECURITY = "generic_security"   # Generic security


class ConfidenceLevel(str, Enum):
    """Confidence level classification for intent understanding."""
    HIGH = "high"      # >= 0.7: Direct execution
    MEDIUM = "medium"  # 0.4 - 0.7: Smart inference with LLM
    LOW = "low"        # < 0.4: Clarification needed with LLM reasoning


class IntentDecision(str, Enum):
    """High-level execution decision derived from reasoning."""

    CLARIFY = "clarify"
    DIRECT = "direct"
    EXECUTE = "execute"


# ============================================
# Data Classes
# ============================================

@dataclass
class UserInput:
    """User input structure."""
    text: str = ""
    files: list[FileInfo] = field(default_factory=list)
    analysis_scope: AnalysisScope = AnalysisScope.ALL_INPUT
    timestamp: datetime = field(default_factory=now_app)
    session_id: str = ""
    
    @property
    def has_files(self) -> bool:
        return len(self.files) > 0
    
    @property
    def file_count(self) -> int:
        return len(self.files)
    
    def get_combined_content(self) -> str:
        """Get combined content for analysis."""
        parts = []
        if self.text:
            parts.append(self.text)
        for f in self.files:
            if f.parsed_content:
                parts.append(f"[File: {f.filename}]\n{f.parsed_content}")
        return "\n\n---\n\n".join(parts)


@dataclass 
class ParameterRequest:
    """Parameter request (requires user input)."""
    id: str = field(default_factory=lambda: str(uuid4()))
    name: str = ""
    description: str = ""
    param_type: str = "text"  # text, password, url, json
    required: bool = True
    placeholder: str = ""
    validation_regex: str = ""
    encrypted: bool = True  # Whether to encrypt storage
    options: list[dict] = field(default_factory=list)  # [{"value": "A", "label": "Option A"}]
    allow_custom: bool = True  # Whether to allow custom input beyond options
    
    def to_dict(self) -> dict:
        # Frontend expects camelCase (same as HITL SSE); snake_case broke validationRegex wiring.
        out: dict = {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "paramType": self.param_type,
            "required": self.required,
            "placeholder": self.placeholder,
            "encrypted": self.encrypted,
            "options": self.options,
            "allowCustom": self.allow_custom,
        }
        if (self.validation_regex or "").strip():
            out["validationRegex"] = self.validation_regex.strip()
        return out


@dataclass
class TaskDescription:
    """Task description from understanding-oriented intent understanding.
    
    This represents a single task that needs to be executed,
    derived from understanding the user's intent (not classification).
    """
    description: str  # Natural language task description
    expertise_needed: str = "general"  # security/research/general
    task_type: str = ""  # Explicit task type: "security" | "research" | "context" (MUST be set)
    skill_hint: str = ""  # Suggested skill name (optional, from LLM)
    key_entities: list[str] = field(default_factory=list)  # Files, IPs, domains, etc.
    context_needed: list[str] = field(default_factory=list)  # Additional context required
    depends_on_task_ids: list[int] = field(default_factory=list)  # Task indices this task depends on (0-based)
    context: dict = field(default_factory=dict)  # Structured payload for subagent execution
    
    def to_dict(self) -> dict:
        return {
            "description": self.description,
            "expertise_needed": self.expertise_needed,
            "task_type": self.task_type,
            "skill_hint": self.skill_hint,
            "key_entities": self.key_entities,
            "context_needed": self.context_needed,
            "depends_on_task_ids": self.depends_on_task_ids,
            "context": self.context,
        }


@dataclass
class IntentResult:
    """Intent understanding result (understanding-oriented)."""
    # Basic information
    task_category: TaskCategory
    input_type: InputType
    confidence: float = 0.8
    confidence_level: ConfidenceLevel = field(init=False)  # Calculated from confidence
    
    # Understanding-oriented fields
    intent_description: str = ""  # Natural language description of user intent
    tasks: list[TaskDescription] = field(default_factory=list)  # Task descriptions
    analysis_scope: AnalysisScope = AnalysisScope.ALL_INPUT
    
    # Concise summary (returned to user)
    summary: str = ""
    
    # Detailed information
    key_entities: list[str] = field(default_factory=list)
    analysis_goals: list[str] = field(default_factory=list)
    suggested_approach: str = ""
    file_manifest: list[dict] = field(default_factory=list)
    history_context: list[dict] = field(default_factory=list)
    
    # Security task specific
    security_subtype: SecuritySubType | None = None
    threat_indicators: list[str] = field(default_factory=list)
    
    # Research task specific
    research_topic: str = ""
    research_scope: str = ""
    
    # Parameter requests
    parameter_requests: list[ParameterRequest] = field(default_factory=list)
    
    # Metadata
    reasoning: str = ""
    reasoning_summary: str = ""
    decision: IntentDecision | None = None
    timestamp: datetime = field(default_factory=now_app)

    # Out-of-scope handling
    suggested_alternatives: list[dict] = field(default_factory=list)  # 3-4 guided alternative solutions for out-of-scope requests
    
    # Boundary + capability + policy
    hard_constraints: dict = field(default_factory=dict)
    capability_request: dict = field(default_factory=dict)
    capability_negotiation: dict = field(default_factory=dict)
    policy_guard: dict = field(default_factory=dict)
    
    def __post_init__(self):
        """Calculate confidence level from confidence score."""
        if self.confidence >= 0.7:
            self.confidence_level = ConfidenceLevel.HIGH
        elif self.confidence >= 0.4:
            self.confidence_level = ConfidenceLevel.MEDIUM
        else:
            self.confidence_level = ConfidenceLevel.LOW
    
    def to_event_dict(self) -> dict:
        """Convert to SSE event format."""
        return {
            "inputType": self.input_type.value,
            "analysisScope": self.analysis_scope.value,
            "summary": self.summary,
            "intentDescription": self.intent_description,
            "tasks": [task.to_dict() for task in self.tasks],
            "keyEntities": self.key_entities,
            "fileManifest": self._sanitize_file_manifest_for_event(),
            "historyContext": self.history_context,
            "analysisGoals": self.analysis_goals,
            "suggestedApproach": self.suggested_approach,
            "confidence": self.confidence,
            "confidenceLevel": self.confidence_level.value,
            "taskCategory": self.task_category.value,
            "decision": self.decision.value if self.decision else None,
            "securitySubtype": self.security_subtype.value if self.security_subtype else None,
            "researchTopic": self.research_topic,
            "reasoningSummary": self.reasoning_summary,
            "parameterRequests": [p.to_dict() for p in self.parameter_requests],
            # Out-of-scope alternatives
            "suggestedAlternatives": self.suggested_alternatives,
            # Boundary + capability + policy
            "hardConstraints": self.hard_constraints,
            "capabilityRequest": self.capability_request,
            "capabilityNegotiation": self.capability_negotiation,
            "policyGuard": self.policy_guard,
        }

    def _sanitize_file_manifest_for_event(self) -> list[dict]:
        """Sanitize file manifest before sending to frontend events."""
        sanitized: list[dict] = []
        for file_item in self.file_manifest or []:
            if not isinstance(file_item, dict):
                continue
            artifact_id = (
                file_item.get("artifactId")
                or file_item.get("file_id")
                or file_item.get("sha256", "")[:16]
            )
            full_content = file_item.get("fullContent", "")
            if not isinstance(full_content, str):
                full_content = str(full_content or "")
            sanitized.append(
                {
                    "artifactId": artifact_id,
                    "file_id": file_item.get("file_id", artifact_id),
                    "filename": file_item.get("filename", ""),
                    "mime": file_item.get("mime", ""),
                    "size": file_item.get("size", 0),
                    "sha256": file_item.get("sha256", ""),
                    "inputType": file_item.get("inputType", ""),
                    "hasServerPath": bool(file_item.get("serverPath")),
                    "contentPreview": full_content[:240],
                }
            )
        return sanitized
    
    def get_user_message(self) -> str:
        """Get concise message returned to user."""
        if self.task_category == TaskCategory.SECURITY:
            return f"🔒 {self.summary}"
        if self.task_category == TaskCategory.RESEARCH:
            return f"🔍 {self.summary}"
        if self.task_category == TaskCategory.PARAMETER_NEEDED:
            return f"📝 {self.summary}"
        return self.summary
