"""Pydantic models for WebThreatReport (schema v2)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


ArtifactType = Literal["http_traffic", "webshell_or_code", "mixed", "unknown"]
FindingCategory = Literal[
    "sqli",
    "xss",
    "ssrf",
    "rce",
    "webshell",
    "traversal",
    "open_redirect",
    "other",
]
Severity = Literal["critical", "high", "medium", "low", "info"]
SignalType = Literal[
    "ast_sink",
    "param_context",
    "pattern",
    "yara_rule",
    "sandbox_trace",
]

LayerId = Literal["L1", "L2", "L3", "L4"]


class Signal(BaseModel):
    """Evidence signal feeding confidence and severity gates."""

    type: SignalType
    name: str
    weight: float = Field(ge=0.0, le=1.0)


class Evidence(BaseModel):
    """Location and snippet for a finding."""

    snippet: str = ""
    start: int = 0
    end: int = 0
    location: str = ""
    decoded: str = ""


class Finding(BaseModel):
    """Single security finding."""

    id: str
    category: FindingCategory
    severity: Severity
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: Evidence
    signals: list[Signal] = Field(default_factory=list)
    # Evidence chain: L1=YARA/entropy, L2=static sinks, L3=syntax sandbox.
    layer: LayerId | None = None
    risk_score: int | None = None
    owasp: str | None = None
    cwe: list[str] = Field(default_factory=list)


class HttpParseStatus(BaseModel):
    ok: bool = False
    errors: list[str] = Field(default_factory=list)


class CodeParseStatus(BaseModel):
    language: str = ""
    ast_ok: bool = False


class AnalysisLayersStatus(BaseModel):
    """Status for L1, L3, and L4; L2 is static scanners."""

    yara: str = "skipped"
    yara_rules_compiled: int = 0
    yara_detail: str = ""
    entropy: str = "skipped"
    sandbox: str = "skipped"
    sandbox_detail: str = ""
    e2b: str = "skipped"
    e2b_detail: str = ""
    e2b_trigger_reason: str = ""


class ParseStatus(BaseModel):
    http: HttpParseStatus = Field(default_factory=HttpParseStatus)
    code: CodeParseStatus = Field(default_factory=CodeParseStatus)
    truncated: bool = False
    layers: AnalysisLayersStatus | None = None


class LegacyReport(BaseModel):
    """Backward-compatible flat fields for callers expecting v1 shape."""

    attacks_detected: list[str] = Field(default_factory=list)
    severity: str = "info"
    attack_count: int = 0
    requires_immediate_action: bool = False


class SourceInfo(BaseModel):
    """Input source metadata for the tool result."""

    kind: str = "inline"
    path: str | None = None
    truncated: bool = False


class ToolError(BaseModel):
    """Structured tool-level error for invalid input or file-read failures."""

    code: str
    message: str


class DecodedArtifact(BaseModel):
    """A safely decoded payload layer extracted from hosted web code."""

    layer: int
    source_location: str
    chain: list[str] = Field(default_factory=list)
    content_sha256: str = ""
    preview: str = ""
    truncated: bool = False


class IOC(BaseModel):
    """Indicator extracted from original or decoded web artifacts."""

    type: str
    name: str | None = None
    value: str | None = None
    source: str = ""


class MitreTechnique(BaseModel):
    """MITRE ATT&CK mapping derived from confirmed tool evidence."""

    technique_id: str
    name: str
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: str = ""


class ForensicSnippet(BaseModel):
    """Redacted or bounded excerpt for analyst reports (deterministic)."""

    category: str = "other"
    preview: str = ""


class CapabilityMatrixRow(BaseModel):
    """Stable capability row with optional line-level evidence."""

    id: str
    label: str = ""
    detected: bool = False
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    snippets: list[str] = Field(default_factory=list)


class ForensicSupplement(BaseModel):
    """Extra material often obtained via manual SReadFile/grep; emitted by the tool."""

    file_header_preview: str = ""
    capability_matrix: list[CapabilityMatrixRow] = Field(default_factory=list)
    snippets: list[ForensicSnippet] = Field(default_factory=list)


class WebThreatReport(BaseModel):
    """Structured output for detect_web_attack (schema v2)."""

    schema_version: str = "2.0"
    artifact_type: ArtifactType = "unknown"
    parse_status: ParseStatus = Field(default_factory=ParseStatus)
    findings: list[Finding] = Field(default_factory=list)
    legacy: LegacyReport = Field(default_factory=LegacyReport)
    source: SourceInfo = Field(default_factory=SourceInfo)
    tool_error: ToolError | None = None
    decoded_artifacts: list[DecodedArtifact] = Field(default_factory=list)
    behaviors: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    iocs: list[IOC] = Field(default_factory=list)
    mitre_attack: list[MitreTechnique] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)
    tool_limitations: list[str] = Field(default_factory=list)
    forensic_supplement: ForensicSupplement = Field(default_factory=ForensicSupplement)

    def to_tool_dict(self) -> dict[str, Any]:
        """Return JSON-serializable dict including legacy top-level keys."""
        base = self.model_dump(mode="json")
        leg = base.pop("legacy", {})
        # Flatten legacy for backward compatibility at top level
        out: dict[str, Any] = {**base, **leg}
        return out
