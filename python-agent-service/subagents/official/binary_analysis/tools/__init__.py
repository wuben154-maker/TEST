"""Binary-analysis Tools (ADR-13, 5 self-authored + 3 primitive).

C6 ships the first self-authored tool — :class:`FileIdentifyTool` — and its
pure helper :func:`identify_file`.  C5 adds :class:`DocExtractTool` for the
document analysis pipeline (FR-03).  Later batches add the remaining tools
(ScoringTool, DecisionGateTool, ReportGenTool) and the three primitive
tools (Bash / PythonExec / FileRead).
"""

from tools.document_extract import (
    DocExtractInput,
    DocExtractOptions,
    DocExtractTool,
)
from tools.file_identify import (
    FileIdentifyInput,
    FileIdentifyResult,
    FileIdentifyTool,
    identify_file,
)

__all__ = [
    "DocExtractInput",
    "DocExtractOptions",
    "DocExtractTool",
    "FileIdentifyInput",
    "FileIdentifyResult",
    "FileIdentifyTool",
    "identify_file",
]
