"""Unit tests for :mod:`tools.document_extract` (C5, FR-03 / C6, FR-06).

Coverage targets (per task AC table):
- FR-03 AC-1/2  : OOXML / OLE2 VBA module + XL4 macro extraction via olevba mock
- FR-03 AC-3    : XL4 formula forwarded to xl4_macro Indicator
- FR-03 AC-6/7  : PDF object tree + trigger parsing via peepdf mock
- FR-03 AC-8    : PDF JavaScript passed as embedded_js in trigger Indicator (no AST)
- FR-03 AC-9    : RTF → olevba path (no vmonkey)
- FR-03 AC-12   : Encrypted Office password hit → decrypt → olevba
- FR-03 AC-13   : Each password attempt generates a password_attempt audit entry
- FR-03 AC-14   : Encrypted Office password exhausted → status=degraded
- FR-03 AC-15   : Three buckets (document_analysis / macro_analysis / embedded_payloads)
                  receive correct indicator_type values from the v1.1 enums
- Non-document  : document_format=PE → ValueError raised immediately
- Parser failure: worker non-zero exit → document_parser_failed Indicator + status=degraded
- Total failure : all workers fail → status=failed
- FR-06 C6     : document IOC merge into ``strings_iocs``; return ``strings_iocs`` key;
                 static + simulated dedup with ``source=["static","simulated"]``
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from evidence_chain.store import EvidenceChainStore
from sandbox.client import SandboxSession, sandbox_workspace
from sandbox.registry import _SESSION_REGISTRY
from schema.evidence_chain import Bucket
from schema.indicator import Severity
from tools.document_extract import (
    DocExtractTool,
    _load_password_list,
    _log_password_attempt,
)

# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------

_ANALYSIS_ID = "test-analysis-c5-01"
_SAMPLE_PATH = f"/workspace/{_ANALYSIS_ID}/sample.bin"

# ---------------------------------------------------------------------------
# Fixtures — fake sandbox client
# ---------------------------------------------------------------------------

_OLEVBA_EMPTY: dict = {"vba_modules": [], "xl4_macros": [], "triggers": []}
_PEEPDF_EMPTY: dict = {
    "object_tree": [],
    "triggers": [],
    "embedded_files": [],
    "action_chains": [],
    "xfa_form": {"present": False, "script_count": 0},
}
_VMONKEY_EMPTY: dict = {
    "simulation_events": [],
    "simulation_gaps": [],
    "simulation_status": "completed",
}


def _make_session(analysis_id: str = _ANALYSIS_ID) -> SandboxSession:
    session = SandboxSession(
        analysis_id=analysis_id,
        sandbox_id=f"fake-{analysis_id}",
        backend="subprocess",
        workdir=sandbox_workspace(analysis_id),
        created_at=0.0,
    )
    _SESSION_REGISTRY[analysis_id] = session
    return session


def _make_exec_result(stdout: dict | str, exit_code: int = 0) -> Any:
    """Return a fake ExecResult for a worker."""
    from sandbox.client import ExecResult

    out = json.dumps(stdout) if isinstance(stdout, dict) else stdout
    return ExecResult(
        stdout=out, stderr="", exit_code=exit_code, duration_ms=10.0, timed_out=False
    )


class _FakeSandboxClient:
    """Records uploads; exec returns per-worker fixtures set by tests."""

    def __init__(self, exec_responses: dict[str, Any]) -> None:
        self.uploads: list[tuple[str, bytes]] = []
        self._exec_responses = exec_responses

    async def create(self, analysis_id: str) -> SandboxSession:  # pragma: no cover
        return _make_session(analysis_id)

    async def upload(self, session: SandboxSession, path: str, data: bytes) -> None:
        self.uploads.append((path, data))

    async def exec(
        self,
        session: SandboxSession,
        cmd: list[str],
        *,
        timeout: float,
        user: str = "user",
        cwd: str | None = None,
    ) -> Any:
        # Match worker filename from argv[1]
        worker_filename = cmd[1] if len(cmd) > 1 else ""
        if worker_filename in self._exec_responses:
            response = self._exec_responses[worker_filename]
            if callable(response):
                return response()
            return response
        return _make_exec_result(_OLEVBA_EMPTY)

    async def download(self, *args: Any, **kwargs: Any) -> bytes:  # pragma: no cover
        raise NotImplementedError

    async def kill(self, *args: Any, **kwargs: Any) -> None:  # pragma: no cover
        pass


def _make_tool(
    exec_responses: dict[str, Any] | None = None,
    analysis_id: str = _ANALYSIS_ID,
    embedded_payload_handler: Any | None = None,
) -> tuple[DocExtractTool, _FakeSandboxClient, EvidenceChainStore, SandboxSession]:
    _make_session(analysis_id)
    store = EvidenceChainStore(analysis_id)
    client = _FakeSandboxClient(exec_responses or {})
    tool = DocExtractTool(
        sandbox_client=client,
        store=store,
        embedded_payload_handler=embedded_payload_handler,
    )
    session = _SESSION_REGISTRY[analysis_id]
    return tool, client, store, session


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _bucket_types(store: EvidenceChainStore, bucket: Bucket) -> list[str]:
    return [ind.indicator_type for ind in store.query(bucket=bucket)]


# ---------------------------------------------------------------------------
# Invalid / non-document format
# ---------------------------------------------------------------------------


class TestInvalidFormat:
    """DocExtractTool must return structured failure on non-document formats."""

    @pytest.mark.asyncio
    async def test_pe_format_returns_schema_error(self) -> None:
        tool, *_ = _make_tool()
        result = await tool._arun(
            sample_path=_SAMPLE_PATH,
            analysis_id=_ANALYSIS_ID,
            document_format="PE32",
            document_tier="P0",
            options={},
        )
        assert result["ok"] is False
        assert result["status"] == "failed"
        assert result["error_code"] == "TOOL_SCHEMA_INVALID"
        assert result["reason"] == "invalid_document_format"

    @pytest.mark.asyncio
    async def test_unknown_format_returns_schema_error(self) -> None:
        tool, *_ = _make_tool()
        result = await tool._arun(
            sample_path=_SAMPLE_PATH,
            analysis_id=_ANALYSIS_ID,
            document_format="not_a_format",
            document_tier="P0",
            options={},
        )
        assert result["ok"] is False
        assert result["status"] == "failed"
        assert result["error_code"] == "TOOL_SCHEMA_INVALID"
        assert result["reason"] == "invalid_document_format"

    def test_sync_run_raises_not_implemented(self) -> None:
        tool, *_ = _make_tool()
        with pytest.raises(NotImplementedError):
            tool._run()


# ---------------------------------------------------------------------------
# FR-03 AC-1/2 — OOXML / OLE2 VBA extraction (olevba worker)
# ---------------------------------------------------------------------------


class TestOlevbaExtraction:
    """OOXML / OLE2 formats → olevba + vmonkey (FR-03 AC-1/2/3)."""

    _OLEVBA_RESULT: dict = {
        "vba_modules": [
            {
                "name": "Module1",
                "source_hash": "sha256:abcdef12",
                "source_preview": "Sub AutoOpen()\nEnd Sub",
                "deobfuscated_preview": 'Sub AutoOpen()\nShell "powershell -nop"\nEnd Sub',
                "deobfuscated_changed": True,
                "code_page": "utf-8",
            }
        ],
        "xl4_macros": [{"cell": "HIDDEN!A1", "formula": '=EXEC("cmd")'}],
        "macro_actions": [
            {
                "action": "powershell_cradle",
                "args_literal": ["powershell -nop"],
                "source": "olevba_static",
                "module": "Module1",
            }
        ],
        "static_iocs": [
            {
                "type": "url",
                "value": "http://evil.example/payload",
                "source": "olevba_deobfuscated",
                "module": "Module1",
            }
        ],
        "triggers": [{"type": "AutoOpen", "location": "VBA.ThisDocument"}],
    }

    @pytest.mark.parametrize(
        "document_format",
        [
            "ooxml_docx_macro",
            "ooxml_xlsx_macro",
            "ooxml_pptx_macro",
            "ole2_doc",
            "ole2_xls",
            "ole2_ppt",
        ],
    )
    @pytest.mark.asyncio
    async def test_vba_module_written_to_macro_analysis(
        self, document_format: str
    ) -> None:
        tool, client, store, _ = _make_tool(
            exec_responses={
                "run_olevba.py": _make_exec_result(self._OLEVBA_RESULT),
                "run_vmonkey.py": _make_exec_result(_VMONKEY_EMPTY),
            }
        )
        result = await tool._arun(
            sample_path=_SAMPLE_PATH,
            analysis_id=_ANALYSIS_ID,
            document_format=document_format,
            document_tier="P0",
            options={},
        )
        macro_types = _bucket_types(store, Bucket.macro_analysis)
        assert "vba_module" in macro_types, f"vba_module missing for {document_format}"
        vba_inds = store.query(bucket=Bucket.macro_analysis, source_fr="FR-03")
        vba_mod = next(i for i in vba_inds if i.indicator_type == "vba_module")
        assert vba_mod.data["name"] == "Module1"
        assert vba_mod.data["source_hash"].startswith("sha256:")
        assert "powershell" in vba_mod.data["deobfuscated_preview"]
        assert vba_mod.data["deobfuscated_changed"] is True
        assert result["status"] in ("ok", "degraded")

    @pytest.mark.asyncio
    async def test_xl4_macro_written_to_macro_analysis(self) -> None:
        """AC-3: XL4 macro cell + formula forwarded as xl4_macro Indicator."""
        tool, client, store, _ = _make_tool(
            exec_responses={
                "run_olevba.py": _make_exec_result(self._OLEVBA_RESULT),
                "run_vmonkey.py": _make_exec_result(_VMONKEY_EMPTY),
            }
        )
        await tool._arun(
            sample_path=_SAMPLE_PATH,
            analysis_id=_ANALYSIS_ID,
            document_format="ooxml_xlsx_macro",
            document_tier="P0",
            options={},
        )
        xl4_inds = [
            i
            for i in store.query(bucket=Bucket.macro_analysis)
            if i.indicator_type == "xl4_macro"
        ]
        assert len(xl4_inds) == 1
        assert xl4_inds[0].data["cell"] == "HIDDEN!A1"
        assert "EXEC" in xl4_inds[0].data["formula"]

    @pytest.mark.asyncio
    async def test_trigger_written_to_document_analysis(self) -> None:
        tool, client, store, _ = _make_tool(
            exec_responses={
                "run_olevba.py": _make_exec_result(self._OLEVBA_RESULT),
                "run_vmonkey.py": _make_exec_result(_VMONKEY_EMPTY),
            }
        )
        await tool._arun(
            sample_path=_SAMPLE_PATH,
            analysis_id=_ANALYSIS_ID,
            document_format="ooxml_docx_macro",
            document_tier="P0",
            options={},
        )
        trigger_inds = [
            i
            for i in store.query(bucket=Bucket.document_analysis)
            if i.indicator_type == "trigger"
        ]
        assert len(trigger_inds) == 1
        assert trigger_inds[0].data["type"] == "AutoOpen"
        assert trigger_inds[0].data["tag"] == "auto_trigger"

    @pytest.mark.asyncio
    async def test_static_olevba_actions_written(self) -> None:
        """Static olevba findings should become scored macro_action_call facts."""
        tool, client, store, _ = _make_tool(
            exec_responses={
                "run_olevba.py": _make_exec_result(self._OLEVBA_RESULT),
                "run_vmonkey.py": _make_exec_result(_VMONKEY_EMPTY),
            }
        )
        result = await tool._arun(
            sample_path=_SAMPLE_PATH,
            analysis_id=_ANALYSIS_ID,
            document_format="ooxml_docx_macro",
            document_tier="P0",
            options={},
        )
        action_inds = [
            i
            for i in store.query(bucket=Bucket.macro_analysis)
            if i.indicator_type == "macro_action_call"
        ]
        assert any(i.data["source"] == "olevba_static" for i in action_inds)
        assert any(i.data["tag"] == "lolbin" for i in action_inds)
        assert result["macro_analysis"]["static_actions"][0]["module"] == "Module1"

    @pytest.mark.asyncio
    async def test_static_olevba_iocs_feed_strings_iocs(self) -> None:
        """Deobfuscated static URLs should flow into FR-06 IOC extraction."""
        tool, client, store, _ = _make_tool(
            exec_responses={
                "run_olevba.py": _make_exec_result(self._OLEVBA_RESULT),
                "run_vmonkey.py": _make_exec_result(_VMONKEY_EMPTY),
            }
        )
        result = await tool._arun(
            sample_path=_SAMPLE_PATH,
            analysis_id=_ANALYSIS_ID,
            document_format="ooxml_docx_macro",
            document_tier="P0",
            options={},
        )
        assert result["macro_analysis"]["static_iocs"][0]["value"].startswith("http")
        ioc_values = [
            i.data["value"]
            for i in store.query(bucket=Bucket.strings_iocs)
            if i.indicator_type in {"url", "remote_template_url"}
        ]
        assert "http://evil.example/payload" in ioc_values

    @pytest.mark.asyncio
    async def test_docm_macro_enabled_missing_vba_project_degrades_with_structure_fact(
        self,
    ) -> None:
        """Malformed DOCM should produce OOXML structure facts, not empty failure."""
        ooxml_result = {
            "document_metadata": {
                "container": "ooxml",
                "macro_enabled_declared": True,
                "has_vba_project": False,
                "content_type_count": 2,
                "part_count": 4,
            },
            "ooxml_parts": [
                {"name": "[Content_Types].xml", "tag": "content_types"},
                {"name": "word/document.xml", "tag": "word_part"},
            ],
            "remote_templates": [],
            "embedded_objects": [],
            "warnings": [
                "macro-enabled OOXML declares VBA content type but vbaProject.bin is missing"
            ],
        }
        tool, _client, store, _ = _make_tool(
            exec_responses={
                "run_olevba.py": _make_exec_result(_OLEVBA_EMPTY),
                "run_vmonkey.py": _make_exec_result(
                    {
                        "simulation_events": [],
                        "simulation_gaps": [],
                        "simulation_status": "unavailable",
                    }
                ),
                "run_ooxml_structure.py": _make_exec_result(ooxml_result),
            }
        )

        result = await tool._arun(
            sample_path=_SAMPLE_PATH,
            analysis_id=_ANALYSIS_ID,
            document_format="ooxml_docx_macro",
            document_tier="P0",
            options={},
        )

        assert result["status"] == "degraded"
        assert result["document_analysis"]["metadata"]["macro_enabled_declared"] is True
        assert result["document_analysis"]["metadata"]["has_vba_project"] is False
        doc_types = _bucket_types(store, Bucket.document_analysis)
        assert "document_metadata" in doc_types
        assert "ooxml_part" in doc_types
        assert "document_parser_failed" in doc_types
        failures = result["error_summary"]["parser_failures"]
        assert any("vbaProject.bin is missing" in f["error"] for f in failures)

    @pytest.mark.asyncio
    async def test_vmonkey_simulation_events_written(self) -> None:
        vmonkey_result = {
            "simulation_events": [
                {
                    "action": "WScript.Shell.Run",
                    "args_literal": ["powershell -NoP"],
                    "source_line": 17,
                }
            ],
            "simulation_gaps": [],
            "simulation_status": "completed",
        }
        tool, client, store, _ = _make_tool(
            exec_responses={
                "run_olevba.py": _make_exec_result(self._OLEVBA_RESULT),
                "run_vmonkey.py": _make_exec_result(vmonkey_result),
            }
        )
        await tool._arun(
            sample_path=_SAMPLE_PATH,
            analysis_id=_ANALYSIS_ID,
            document_format="ooxml_xlsx_macro",
            document_tier="P0",
            options={},
        )
        action_inds = [
            i
            for i in store.query(bucket=Bucket.macro_analysis)
            if i.indicator_type == "macro_action_call"
        ]
        runtime = next(
            i for i in action_inds if i.data["action"] == "WScript.Shell.Run"
        )
        assert "powershell" in runtime.data["args_literal"][0]
        assert runtime.data["tag"] == "lolbin"

    @pytest.mark.asyncio
    async def test_vmonkey_gaps_written(self) -> None:
        """FR-03 AC-5: simulation gaps written as vba_simulation_gap Indicators."""
        vmonkey_result = {
            "simulation_events": [],
            "simulation_gaps": [
                {
                    "statement_type": "Application.OnTime",
                    "source_line": 42,
                    "skip_reason": "out_of_tier_b",
                }
            ],
            "simulation_status": "completed",
        }
        tool, client, store, _ = _make_tool(
            exec_responses={
                "run_olevba.py": _make_exec_result(_OLEVBA_EMPTY),
                "run_vmonkey.py": _make_exec_result(vmonkey_result),
            }
        )
        await tool._arun(
            sample_path=_SAMPLE_PATH,
            analysis_id=_ANALYSIS_ID,
            document_format="ole2_xls",
            document_tier="P0",
            options={},
        )
        gap_inds = [
            i
            for i in store.query(bucket=Bucket.macro_analysis)
            if i.indicator_type == "vba_simulation_gap"
        ]
        assert len(gap_inds) == 1
        assert gap_inds[0].data["statement_type"] == "Application.OnTime"

    @pytest.mark.asyncio
    async def test_rtf_uses_olevba_not_vmonkey(self) -> None:
        """AC-9: RTF format calls olevba only (no vmonkey)."""
        tool, client, store, _ = _make_tool(
            exec_responses={
                "run_olevba.py": _make_exec_result(self._OLEVBA_RESULT),
            }
        )
        await tool._arun(
            sample_path=_SAMPLE_PATH,
            analysis_id=_ANALYSIS_ID,
            document_format="rtf",
            document_tier="P1",
            options={},
        )
        # Worker file names uploaded — vmonkey must NOT appear
        uploaded_filenames = [Path(p).name for p, _ in client.uploads]
        assert "run_olevba.py" in uploaded_filenames
        assert "run_vmonkey.py" not in uploaded_filenames

    @pytest.mark.asyncio
    async def test_status_ok_when_all_workers_succeed(self) -> None:
        tool, client, store, _ = _make_tool(
            exec_responses={
                "run_olevba.py": _make_exec_result(_OLEVBA_EMPTY),
                "run_vmonkey.py": _make_exec_result(_VMONKEY_EMPTY),
            }
        )
        result = await tool._arun(
            sample_path=_SAMPLE_PATH,
            analysis_id=_ANALYSIS_ID,
            document_format="ooxml_docx_macro",
            document_tier="P0",
            options={},
        )
        assert result["status"] == "ok"


# ---------------------------------------------------------------------------
# FR-03 AC-6/7/8 — PDF via peepdf
# ---------------------------------------------------------------------------


class TestPeepdfExtraction:
    """PDF format → peepdf worker (FR-03 AC-6/7/8)."""

    _PEEPDF_RESULT: dict = {
        "object_tree": [
            {"obj_id": 1, "obj_type": "dictionary", "contains_js": True},
            {"obj_id": 2, "obj_type": "stream", "contains_js": False},
        ],
        "triggers": [
            {
                "type": "OpenAction",
                "action_type": "JavaScript",
                "js_preview": "app.alert('pwn');",
            }
        ],
        "embedded_files": [
            {"name": "payload.exe", "sha256": "deadbeef" * 8, "size_bytes": 4096}
        ],
        "action_chains": [{"chain": ["OpenAction", "JavaScript"]}],
        "xfa_form": {"present": False, "script_count": 0},
        "keyword_summary": {
            "keywords": {
                "/OpenAction": 1,
                "/JS": 1,
                "/JBIG2Decode": 1,
                "/SubmitForm": 1,
            },
            "risk_counts": {"high": 3, "medium": 1, "low": 0},
            "structure": {"pdf_version": "1.7", "object_count": 2},
            "has_jbig2decode": True,
            "has_submit_form": True,
            "has_object_stream": False,
            "has_open_action": True,
            "has_launch": False,
            "has_js": True,
            "has_embedded_file": True,
        },
        "js_analysis": {
            "blocks": [
                {
                    "type": "inline",
                    "preview": "eval(unescape('%u9090%u9090%u9090%u9090'))",
                    "length": 43,
                }
            ],
            "markers": {"eval_call": 1, "unescape_chain": 1, "heap_spray": 1},
            "has_shellcode_markers": True,
            "has_obfuscation_markers": True,
        },
        "uris": [],
    }

    @pytest.mark.asyncio
    async def test_pdf_object_tree_indicator_written(self) -> None:
        tool, client, store, _ = _make_tool(
            exec_responses={"run_peepdf.py": _make_exec_result(self._PEEPDF_RESULT)}
        )
        await tool._arun(
            sample_path=_SAMPLE_PATH,
            analysis_id=_ANALYSIS_ID,
            document_format="pdf",
            document_tier="P0",
            options={},
        )
        doc_types = _bucket_types(store, Bucket.document_analysis)
        assert "pdf_object_tree" in doc_types
        assert "pdf_keyword_summary" in doc_types
        assert "pdf_js_analysis" in doc_types

    @pytest.mark.asyncio
    async def test_pdf_keyword_and_js_analysis_indicators_written(self) -> None:
        tool, client, store, _ = _make_tool(
            exec_responses={"run_peepdf.py": _make_exec_result(self._PEEPDF_RESULT)}
        )
        await tool._arun(
            sample_path=_SAMPLE_PATH,
            analysis_id=_ANALYSIS_ID,
            document_format="pdf",
            document_tier="P0",
            options={},
        )

        keyword_ind = next(
            i
            for i in store.query(bucket=Bucket.document_analysis)
            if i.indicator_type == "pdf_keyword_summary"
        )
        assert keyword_ind.data["has_jbig2decode"] is True
        assert keyword_ind.data["has_submit_form"] is True

        js_ind = next(
            i
            for i in store.query(bucket=Bucket.document_analysis)
            if i.indicator_type == "pdf_js_analysis"
        )
        assert js_ind.severity == Severity.CRITICAL
        assert js_ind.data["has_shellcode_markers"] is True

    @pytest.mark.asyncio
    async def test_pdf_trigger_written_with_js_preview(self) -> None:
        """AC-8: JS source passed as embedded_js, no AST analysis."""
        tool, client, store, _ = _make_tool(
            exec_responses={"run_peepdf.py": _make_exec_result(self._PEEPDF_RESULT)}
        )
        await tool._arun(
            sample_path=_SAMPLE_PATH,
            analysis_id=_ANALYSIS_ID,
            document_format="pdf",
            document_tier="P0",
            options={},
        )
        trigger_inds = [
            i
            for i in store.query(bucket=Bucket.document_analysis)
            if i.indicator_type == "trigger"
        ]
        assert len(trigger_inds) == 1
        assert trigger_inds[0].data["type"] == "OpenAction"
        assert "embedded_js" in trigger_inds[0].data
        assert "app.alert" in trigger_inds[0].data["embedded_js"]

    @pytest.mark.asyncio
    async def test_pdf_embedded_file_in_embedded_payloads(self) -> None:
        tool, client, store, _ = _make_tool(
            exec_responses={"run_peepdf.py": _make_exec_result(self._PEEPDF_RESULT)}
        )
        result = await tool._arun(
            sample_path=_SAMPLE_PATH,
            analysis_id=_ANALYSIS_ID,
            document_format="pdf",
            document_tier="P0",
            options={},
        )
        payload_types = _bucket_types(store, Bucket.embedded_payloads)
        assert "pdf_embedded_file" in payload_types
        payload_ind = next(
            i
            for i in store.query(bucket=Bucket.embedded_payloads)
            if i.indicator_type == "pdf_embedded_file"
        )
        assert payload_ind.data["suggested_format"] == "pe"
        assert (
            payload_ind.data["child_analysis_id"] == payload_ind.data["child_sample_id"]
        )
        assert payload_ind.data["materialized"] is False
        assert payload_ind.data["recursive_ready"] is False
        assert (
            payload_ind.data["materialization_status"] == "best_effort_unmaterialized"
        )
        assert len(result["embedded_payloads"]) == 1
        assert result["embedded_payloads"][0]["sha256"] == "deadbeef" * 8
        assert result["embedded_payloads"][0]["suggested_format"] == "pe"
        assert (
            result["embedded_payloads"][0]["child_analysis_id"]
            == result["embedded_payloads"][0]["child_sample_id"]
        )
        assert result["embedded_payloads"][0]["materialized"] is False

    @pytest.mark.asyncio
    async def test_pdf_worker_payload_format_hint_is_preserved(self) -> None:
        pe_magic_result = {
            **self._PEEPDF_RESULT,
            "embedded_files": [
                {
                    "name": "document.dat",
                    "sha256": "feedface" * 8,
                    "size_bytes": 2048,
                    "suggested_format": "pe",
                }
            ],
        }
        tool, client, store, _ = _make_tool(
            exec_responses={"run_peepdf.py": _make_exec_result(pe_magic_result)}
        )
        result = await tool._arun(
            sample_path=_SAMPLE_PATH,
            analysis_id=_ANALYSIS_ID,
            document_format="pdf",
            document_tier="P0",
            options={},
        )
        payload_ind = next(
            i
            for i in store.query(bucket=Bucket.embedded_payloads)
            if i.indicator_type == "pdf_embedded_file"
        )
        assert payload_ind.data["name"] == "document.dat"
        assert payload_ind.data["suggested_format"] == "pe"
        assert result["embedded_payloads"][0]["suggested_format"] == "pe"

    @pytest.mark.asyncio
    async def test_pdf_worker_extracted_path_is_preserved(self) -> None:
        extracted_to = f"/workspace/{_ANALYSIS_ID}/children/pdf_embedded_001.bin"
        peepdf_result = {
            **self._PEEPDF_RESULT,
            "embedded_files": [
                {
                    "name": "payload.exe",
                    "sha256": "baddcafe" * 8,
                    "size_bytes": 512,
                    "suggested_format": "pe",
                    "extracted_to": extracted_to,
                    "materialized": True,
                }
            ],
        }
        tool, _client, store, _ = _make_tool(
            exec_responses={"run_peepdf.py": _make_exec_result(peepdf_result)}
        )
        result = await tool._arun(
            sample_path=_SAMPLE_PATH,
            analysis_id=_ANALYSIS_ID,
            document_format="pdf",
            document_tier="P0",
            options={},
        )
        payload_ind = next(
            i
            for i in store.query(bucket=Bucket.embedded_payloads)
            if i.indicator_type == "pdf_embedded_file"
        )
        assert payload_ind.data["extracted_to"] == extracted_to
        assert payload_ind.data["materialized"] is True
        assert payload_ind.data["recursive_ready"] is True
        assert result["embedded_payloads"][0]["extracted_to"] == extracted_to
        assert result["embedded_payloads"][0]["materialized"] is True

    @pytest.mark.asyncio
    async def test_pdf_materialized_payload_invokes_embedded_handler(self) -> None:
        extracted_to = f"/workspace/{_ANALYSIS_ID}/children/pdf_embedded_001.bin"
        calls: list[tuple[str, list[dict[str, Any]]]] = []

        async def _handler(
            analysis_id: str, payloads: list[dict[str, Any]]
        ) -> list[dict[str, Any]]:
            calls.append((analysis_id, payloads))
            return [
                {
                    **payload,
                    "child_recursion_status": "completed",
                    "child_verdict": "MALICIOUS",
                }
                for payload in payloads
            ]

        peepdf_result = {
            **self._PEEPDF_RESULT,
            "embedded_files": [
                {
                    "name": "payload.exe",
                    "sha256": "f00df00d" * 8,
                    "size_bytes": 512,
                    "suggested_format": "pe",
                    "extracted_to": extracted_to,
                    "materialized": True,
                }
            ],
        }
        tool, _client, _store, _ = _make_tool(
            exec_responses={"run_peepdf.py": _make_exec_result(peepdf_result)},
            embedded_payload_handler=_handler,
        )

        result = await tool._arun(
            sample_path=_SAMPLE_PATH,
            analysis_id=_ANALYSIS_ID,
            document_format="pdf",
            document_tier="P0",
            options={},
        )

        assert len(calls) == 1
        assert calls[0][0] == _ANALYSIS_ID
        assert calls[0][1][0]["recursive_ready"] is True
        assert result["embedded_payloads"][0]["child_recursion_status"] == "completed"
        assert result["embedded_payloads"][0]["child_verdict"] == "MALICIOUS"

    @pytest.mark.asyncio
    async def test_pdf_action_chain_indicator_written(self) -> None:
        tool, client, store, _ = _make_tool(
            exec_responses={"run_peepdf.py": _make_exec_result(self._PEEPDF_RESULT)}
        )
        await tool._arun(
            sample_path=_SAMPLE_PATH,
            analysis_id=_ANALYSIS_ID,
            document_format="pdf",
            document_tier="P0",
            options={},
        )
        chain_ind = next(
            i
            for i in store.query(bucket=Bucket.document_analysis)
            if i.indicator_type == "pdf_action_chain"
        )
        assert chain_ind.data["tag"] == "js_trigger"
        assert chain_ind.data["chain"] == ["OpenAction", "JavaScript"]

    @pytest.mark.asyncio
    async def test_xfa_form_indicator_when_present(self) -> None:
        xfa_result = {
            **self._PEEPDF_RESULT,
            "xfa_form": {"present": True, "script_count": 3},
        }
        tool, client, store, _ = _make_tool(
            exec_responses={"run_peepdf.py": _make_exec_result(xfa_result)}
        )
        await tool._arun(
            sample_path=_SAMPLE_PATH,
            analysis_id=_ANALYSIS_ID,
            document_format="pdf",
            document_tier="P0",
            options={},
        )
        doc_types = _bucket_types(store, Bucket.document_analysis)
        assert "xfa_form" in doc_types


# ---------------------------------------------------------------------------
# OneNote (P2 degraded path)
# ---------------------------------------------------------------------------


class TestOneNoteExtraction:
    """OneNote format → run_onenote worker."""

    @pytest.mark.asyncio
    async def test_onenote_file_data_store_in_embedded_payloads(self) -> None:
        extracted_to = f"/workspace/{_ANALYSIS_ID}/children/onenote_fds_001.bin"
        onenote_result = {
            "file_data_stores": [
                {
                    "guid": "89CA5A93-DCAB-4FC9-82C5-EB85F4FCE2AE",
                    "extension": ".exe",
                    "size_bytes": 8192,
                    "sha256": "cafebabe" * 8,
                    "extracted_to": extracted_to,
                    "materialized": True,
                }
            ],
            "fallback_strings_ioc": [],
        }
        tool, client, store, _ = _make_tool(
            exec_responses={"run_onenote.py": _make_exec_result(onenote_result)}
        )
        result = await tool._arun(
            sample_path=_SAMPLE_PATH,
            analysis_id=_ANALYSIS_ID,
            document_format="onenote",
            document_tier="P2",
            options={},
        )
        payload_types = _bucket_types(store, Bucket.embedded_payloads)
        assert "onenote_file_data_store" in payload_types
        assert len(result["embedded_payloads"]) == 1
        assert result["embedded_payloads"][0]["extension"] == ".exe"
        assert result["embedded_payloads"][0]["suggested_format"] == "pe"
        assert (
            result["embedded_payloads"][0]["child_analysis_id"]
            == result["embedded_payloads"][0]["child_sample_id"]
        )
        assert result["embedded_payloads"][0]["extracted_to"] == extracted_to
        assert result["embedded_payloads"][0]["materialized"] is True
        assert result["embedded_payloads"][0]["recursive_ready"] is True

    @pytest.mark.asyncio
    async def test_onenote_fallback_without_bytes_has_no_fake_path(self) -> None:
        onenote_result = {
            "degraded": "parser_unavailable",
            "file_data_stores": [
                {
                    "guid": "89CA5A93-DCAB-4FC9-82C5-EB85F4FCE2AE",
                    "offset": 1024,
                    "materialized": False,
                    "suggested_format": "unknown",
                }
            ],
            "fallback_strings_ioc": [],
        }
        tool, _client, store, _ = _make_tool(
            exec_responses={"run_onenote.py": _make_exec_result(onenote_result)}
        )
        result = await tool._arun(
            sample_path=_SAMPLE_PATH,
            analysis_id=_ANALYSIS_ID,
            document_format="onenote",
            document_tier="P2",
            options={},
        )
        payload_ind = next(
            i
            for i in store.query(bucket=Bucket.embedded_payloads)
            if i.indicator_type == "onenote_file_data_store"
        )
        assert payload_ind.data["materialized"] is False
        assert payload_ind.data["recursive_ready"] is False
        assert "extracted_to" not in payload_ind.data
        assert "extracted_to" not in result["embedded_payloads"][0]


# ---------------------------------------------------------------------------
# HTA → vmonkey only
# ---------------------------------------------------------------------------


class TestHTAExtraction:
    """HTA format → run_vmonkey (VBScript mode)."""

    @pytest.mark.asyncio
    async def test_hta_uses_vmonkey_only(self) -> None:
        vmonkey_result = {
            "simulation_events": [
                {
                    "action": "shell_run",
                    "args_literal": ["wscript evil.js"],
                    "source_line": 1,
                }
            ],
            "simulation_gaps": [],
            "simulation_status": "completed",
        }
        tool, client, store, _ = _make_tool(
            exec_responses={"run_vmonkey.py": _make_exec_result(vmonkey_result)}
        )
        await tool._arun(
            sample_path=_SAMPLE_PATH,
            analysis_id=_ANALYSIS_ID,
            document_format="hta",
            document_tier="P1",
            options={},
        )
        uploaded = [Path(p).name for p, _ in client.uploads]
        assert "run_vmonkey.py" in uploaded
        assert "run_olevba.py" not in uploaded

        action_inds = [
            i
            for i in store.query(bucket=Bucket.macro_analysis)
            if i.indicator_type == "macro_action_call"
        ]
        assert len(action_inds) == 1
        assert action_inds[0].data["action"] == "shell_run"


# ---------------------------------------------------------------------------
# FR-03 AC-12/13/14 — Encrypted Office
# ---------------------------------------------------------------------------


class TestEncryptedOffice:
    """Encrypted Office format → msoffcrypto + olevba on success."""

    _CRYPTO_SUCCESS: dict = {
        "decrypted": True,
        "attempted": 1,
        "succeeded_password_hash": "sha256:5e884898",
        "metadata": {
            "cipher_algorithm": "AES",
            "key_bits": 128,
            "hash_algorithm": "SHA-1",
        },
    }
    _CRYPTO_FAIL: dict = {
        "decrypted": False,
        "attempted": 20,
        "succeeded_password_hash": None,
        "metadata": {},
    }

    @pytest.mark.asyncio
    async def test_password_hit_runs_olevba_after(self) -> None:
        """AC-12: successful decryption triggers olevba pass."""
        olevba_result = {
            "vba_modules": [
                {
                    "name": "Sheet1",
                    "source_hash": "sha256:aa",
                    "source_preview": "x",
                    "code_page": "utf-8",
                }
            ],
            "xl4_macros": [],
            "triggers": [],
        }
        tool, client, store, _ = _make_tool(
            exec_responses={
                "run_msoffcrypto.py": _make_exec_result(self._CRYPTO_SUCCESS),
                "run_olevba.py": _make_exec_result(olevba_result),
            }
        )
        result = await tool._arun(
            sample_path=_SAMPLE_PATH,
            analysis_id=_ANALYSIS_ID,
            document_format="encrypted_office",
            document_tier="P2",
            options={},
        )
        assert result["error_summary"]["password_attempts"]["succeeded"] is True
        macro_types = _bucket_types(store, Bucket.macro_analysis)
        assert "vba_module" in macro_types

    @pytest.mark.asyncio
    async def test_password_attempts_logged(self) -> None:
        """AC-13: every password in the list gets a log entry."""
        logged_calls: list[dict] = []

        def _fake_log_tool_call(**kwargs: Any) -> None:
            if kwargs.get("tool_name") == "document_extract_password_attempt":
                logged_calls.append(kwargs)

        tool, client, store, _ = _make_tool(
            exec_responses={
                "run_msoffcrypto.py": _make_exec_result(self._CRYPTO_FAIL),
            }
        )

        passwords = ["infected", "virus", "malware"]
        # Patch directly into the function's own __globals__ dict so the fix is
        # immune to sys.modules purges performed by test_cli.py's fast-startup
        # test (which evicts binary_analysis.tools.* and causes a second import
        # that creates a different module object from the one already bound here).
        with patch.dict(
            _log_password_attempt.__globals__,
            {
                "_load_password_list": lambda *_: passwords,
                "log_tool_call": _fake_log_tool_call,
            },
        ):
            await tool._arun(
                sample_path=_SAMPLE_PATH,
                analysis_id=_ANALYSIS_ID,
                document_format="encrypted_office",
                document_tier="P2",
                options={},
            )

        assert len(logged_calls) == len(passwords), (
            f"Expected {len(passwords)} password attempt log entries, "
            f"got {len(logged_calls)}"
        )
        for entry in logged_calls:
            assert "hash_prefix" in entry["args"]
            assert entry["args"]["hash_prefix"].startswith("sha256:")
            assert "truncated" in entry["args"]

    @pytest.mark.asyncio
    async def test_password_exhausted_status_degraded(self) -> None:
        """AC-14: dictionary exhausted → status=degraded + encrypted_office_no_password."""
        tool, client, store, _ = _make_tool(
            exec_responses={
                "run_msoffcrypto.py": _make_exec_result(self._CRYPTO_FAIL),
            }
        )
        with patch(
            "tools.document_extract._load_password_list",
            return_value=["infected", "virus"],
        ):
            result = await tool._arun(
                sample_path=_SAMPLE_PATH,
                analysis_id=_ANALYSIS_ID,
                document_format="encrypted_office",
                document_tier="P2",
                options={},
            )
        assert result["status"] == "degraded"
        assert result["error_summary"]["password_attempts"]["succeeded"] is False
        # document_parser_failed Indicator must be written
        doc_types = _bucket_types(store, Bucket.document_analysis)
        assert "document_parser_failed" in doc_types

    @pytest.mark.asyncio
    async def test_password_exhausted_attempts_olevba_fallback(self) -> None:
        """Password exhaustion should still try protected OLE macro extraction."""
        olevba_result = {
            "vba_modules": [
                {
                    "name": "ThisDocument",
                    "source_hash": "sha256:bb",
                    "source_preview": "Sub Document_Open()\nEnd Sub",
                    "deobfuscated_preview": (
                        "Sub Document_Open()\n"
                        "Shell \"powershell -w 1 DownloadFile\"\n"
                        "End Sub"
                    ),
                    "deobfuscated_changed": True,
                    "code_page": "utf-8",
                }
            ],
            "xl4_macros": [],
            "macro_actions": [
                {
                    "action": "powershell_cradle",
                    "args_literal": ["powershell -w 1 DownloadFile"],
                    "source": "olevba_static",
                    "module": "ThisDocument",
                }
            ],
            "static_iocs": [
                {
                    "type": "url",
                    "value": "http://185.189.58.222/x.exe",
                    "source": "olevba_deobfuscated",
                    "module": "ThisDocument",
                }
            ],
            "triggers": [{"type": "Document_Open", "location": "VBA.ThisDocument"}],
        }
        tool, client, store, _ = _make_tool(
            exec_responses={
                "run_msoffcrypto.py": _make_exec_result(self._CRYPTO_FAIL),
                "run_olevba.py": _make_exec_result(olevba_result),
            }
        )
        result = await tool._arun(
            sample_path=_SAMPLE_PATH,
            analysis_id=_ANALYSIS_ID,
            document_format="encrypted_office",
            document_tier="P2",
            options={},
        )

        uploaded_filenames = {Path(path).name for path, _data in client.uploads}
        assert "run_msoffcrypto.py" in uploaded_filenames
        assert "run_olevba.py" in uploaded_filenames
        assert result["status"] == "degraded"
        assert result["error_summary"]["password_attempts"]["succeeded"] is False
        assert result["macro_analysis"]["vba_modules"]
        macro_types = _bucket_types(store, Bucket.macro_analysis)
        assert "vba_module" in macro_types
        assert result["strings_iocs"]

    @pytest.mark.asyncio
    async def test_password_exhausted_fallback_emits_completion_metrics(self) -> None:
        """Completion telemetry should expose fallback macro extraction counts."""
        olevba_result = {
            "vba_modules": [
                {
                    "name": "ThisDocument",
                    "source_hash": "sha256:bb",
                    "source_preview": "Sub Document_Open()\nEnd Sub",
                    "deobfuscated_preview": "Shell \"powershell DownloadFile\"",
                    "deobfuscated_changed": True,
                    "code_page": "utf-8",
                }
            ],
            "xl4_macros": [],
            "macro_actions": [
                {
                    "action": "powershell_cradle",
                    "args_literal": ["powershell DownloadFile"],
                    "source": "olevba_static",
                    "module": "ThisDocument",
                }
            ],
            "static_iocs": [
                {
                    "type": "url",
                    "value": "http://185.189.58.222/x.exe",
                    "source": "olevba_deobfuscated",
                    "module": "ThisDocument",
                }
            ],
            "triggers": [{"type": "Document_Open", "location": "VBA.ThisDocument"}],
        }
        crypto_fail = {**self._CRYPTO_FAIL, "attempted": 2}
        tool, _client, _store, _ = _make_tool(
            exec_responses={
                "run_msoffcrypto.py": _make_exec_result(crypto_fail),
                "run_olevba.py": _make_exec_result(olevba_result),
            }
        )

        with (
            patch("tools.document_extract._load_password_list", return_value=["infected", "virus"]),
            patch("tools.document_extract.logger.info", create=True) as log_info,
        ):
            await tool._arun(
                sample_path=_SAMPLE_PATH,
                analysis_id=_ANALYSIS_ID,
                document_format="encrypted_office",
                document_tier="P2",
                options={},
            )

        log_info.assert_called_once()
        event_name = log_info.call_args.args[0]
        fields = log_info.call_args.kwargs
        assert event_name == "document_extract_complete"
        assert fields["analysis_id"] == _ANALYSIS_ID
        assert fields["status"] == "degraded"
        assert fields["document_format"] == "encrypted_office"
        assert fields["password_attempted"] == 2
        assert fields["password_succeeded"] is False
        assert fields["vba_module_count"] == 1
        assert fields["macro_action_count"] == 1
        assert fields["static_ioc_count"] == 1
        assert fields["trigger_count"] == 1

    @pytest.mark.asyncio
    async def test_metadata_indicator_written_on_decrypt(self) -> None:
        """document_metadata Indicator carries cipher info after successful decrypt."""
        tool, client, store, _ = _make_tool(
            exec_responses={
                "run_msoffcrypto.py": _make_exec_result(self._CRYPTO_SUCCESS),
                "run_olevba.py": _make_exec_result(_OLEVBA_EMPTY),
            }
        )
        await tool._arun(
            sample_path=_SAMPLE_PATH,
            analysis_id=_ANALYSIS_ID,
            document_format="encrypted_office",
            document_tier="P2",
            options={},
        )
        meta_inds = [
            i
            for i in store.query(bucket=Bucket.document_analysis)
            if i.indicator_type == "document_metadata"
        ]
        assert len(meta_inds) >= 1
        assert meta_inds[0].data["encrypted"] is True
        assert meta_inds[0].data["cipher_algorithm"] == "AES"


# ---------------------------------------------------------------------------
# FR-03 AC-15 — Indicator types within v1.1 enums (all three buckets)
# ---------------------------------------------------------------------------


class TestIndicatorTypeEnumCompliance:
    """All indicator_types written must be in the v1.1 schema frozensets (AC-15)."""

    @pytest.mark.asyncio
    async def test_all_indicator_types_valid_for_ooxml(self) -> None:
        from schema.indicator_types_v1_1 import (
            DOC_ANALYSIS_TYPES,
            EMBEDDED_PAYLOADS_TYPES,
            MACRO_ANALYSIS_TYPES,
        )

        olevba_result = {
            "vba_modules": [
                {
                    "name": "M1",
                    "source_hash": "sha256:aa",
                    "source_preview": "",
                    "code_page": "utf-8",
                }
            ],
            "xl4_macros": [{"cell": "A1", "formula": "=EXEC(x)"}],
            "triggers": [{"type": "AutoOpen", "location": "VBA"}],
        }
        vmonkey_result = {
            "simulation_events": [
                {"action": "shell_run", "args_literal": [], "source_line": 1}
            ],
            "simulation_gaps": [
                {
                    "statement_type": "AppOnTime",
                    "source_line": 5,
                    "skip_reason": "out_of_tier_b",
                }
            ],
            "simulation_status": "completed",
        }
        tool, client, store, _ = _make_tool(
            exec_responses={
                "run_olevba.py": _make_exec_result(olevba_result),
                "run_vmonkey.py": _make_exec_result(vmonkey_result),
            }
        )
        await tool._arun(
            sample_path=_SAMPLE_PATH,
            analysis_id=_ANALYSIS_ID,
            document_format="ooxml_xlsx_macro",
            document_tier="P0",
            options={},
        )
        for ind in store.query(bucket=Bucket.document_analysis):
            if ind.source_fr == "FR-03":
                assert ind.indicator_type in DOC_ANALYSIS_TYPES, (
                    f"indicator_type {ind.indicator_type!r} not in DOC_ANALYSIS_TYPES"
                )
        for ind in store.query(bucket=Bucket.macro_analysis):
            if ind.source_fr == "FR-03":
                assert ind.indicator_type in MACRO_ANALYSIS_TYPES, (
                    f"indicator_type {ind.indicator_type!r} not in MACRO_ANALYSIS_TYPES"
                )
        for ind in store.query(bucket=Bucket.embedded_payloads):
            if ind.source_fr == "FR-03":
                assert ind.indicator_type in EMBEDDED_PAYLOADS_TYPES, (
                    f"indicator_type {ind.indicator_type!r} not in EMBEDDED_PAYLOADS_TYPES"
                )

    @pytest.mark.asyncio
    async def test_all_indicator_types_valid_for_pdf(self) -> None:
        from schema.indicator_types_v1_1 import (
            DOC_ANALYSIS_TYPES,
            EMBEDDED_PAYLOADS_TYPES,
        )

        peepdf_result = {
            "object_tree": [{"obj_id": 1, "obj_type": "dict", "contains_js": True}],
            "triggers": [
                {
                    "type": "OpenAction",
                    "action_type": "JavaScript",
                    "js_preview": "alert(1)",
                }
            ],
            "embedded_files": [
                {"name": "evil.exe", "sha256": "aa" * 32, "size_bytes": 100}
            ],
            "action_chains": [{"chain": ["OpenAction"]}],
            "xfa_form": {"present": True, "script_count": 1},
        }
        tool, client, store, _ = _make_tool(
            exec_responses={"run_peepdf.py": _make_exec_result(peepdf_result)}
        )
        await tool._arun(
            sample_path=_SAMPLE_PATH,
            analysis_id=_ANALYSIS_ID,
            document_format="pdf",
            document_tier="P0",
            options={},
        )
        for ind in store.query(bucket=Bucket.document_analysis):
            if ind.source_fr == "FR-03":
                assert ind.indicator_type in DOC_ANALYSIS_TYPES
        for ind in store.query(bucket=Bucket.embedded_payloads):
            if ind.source_fr == "FR-03":
                assert ind.indicator_type in EMBEDDED_PAYLOADS_TYPES


# ---------------------------------------------------------------------------
# Parser failure / degraded paths
# ---------------------------------------------------------------------------


class TestWorkerFailure:
    """Worker non-zero exit / bad JSON → document_parser_failed + status=degraded."""

    @pytest.mark.asyncio
    async def test_olevba_failure_writes_parser_failed_indicator(self) -> None:
        error_result = {
            "error": "VBA_Parser init failed: file is corrupt",
            "vba_modules": [],
            "xl4_macros": [],
            "triggers": [],
        }
        tool, client, store, _ = _make_tool(
            exec_responses={
                "run_olevba.py": _make_exec_result(error_result, exit_code=1),
                "run_vmonkey.py": _make_exec_result(_VMONKEY_EMPTY),
            }
        )
        result = await tool._arun(
            sample_path=_SAMPLE_PATH,
            analysis_id=_ANALYSIS_ID,
            document_format="ooxml_docx_macro",
            document_tier="P0",
            options={},
        )
        assert result["status"] == "degraded"
        doc_types = _bucket_types(store, Bucket.document_analysis)
        assert "document_parser_failed" in doc_types
        assert len(result["error_summary"]["parser_failures"]) >= 1

    @pytest.mark.asyncio
    async def test_all_workers_fail_status_is_failed(self) -> None:
        error_result = {
            "error": "crash",
            "vba_modules": [],
            "xl4_macros": [],
            "triggers": [],
        }
        vmonkey_error = {
            "simulation_events": None,
            "simulation_gaps": [],
            "simulation_status": "parse_error",
            "error": "crash",
        }
        tool, client, store, _ = _make_tool(
            exec_responses={
                "run_olevba.py": _make_exec_result(error_result, exit_code=1),
                "run_vmonkey.py": _make_exec_result(vmonkey_error, exit_code=1),
            }
        )
        result = await tool._arun(
            sample_path=_SAMPLE_PATH,
            analysis_id=_ANALYSIS_ID,
            document_format="ole2_doc",
            document_tier="P0",
            options={},
        )
        assert result["status"] == "failed"

    @pytest.mark.asyncio
    async def test_pdf_worker_error_degrades_status(self) -> None:
        error_result = {**_PEEPDF_EMPTY, "error": "peepdf crashed"}
        tool, client, store, _ = _make_tool(
            exec_responses={
                "run_peepdf.py": _make_exec_result(error_result, exit_code=1)
            }
        )
        result = await tool._arun(
            sample_path=_SAMPLE_PATH,
            analysis_id=_ANALYSIS_ID,
            document_format="pdf",
            document_tier="P0",
            options={},
        )
        # Object tree is empty so the worker output doesn't count as success
        assert result["status"] in ("degraded", "failed")


# ---------------------------------------------------------------------------
# Return value structure
# ---------------------------------------------------------------------------


class TestReturnStructure:
    """Tool return value always has the expected top-level keys."""

    @pytest.mark.asyncio
    async def test_return_value_keys(self) -> None:
        tool, client, store, _ = _make_tool(
            exec_responses={
                "run_olevba.py": _make_exec_result(_OLEVBA_EMPTY),
                "run_vmonkey.py": _make_exec_result(_VMONKEY_EMPTY),
            }
        )
        result = await tool._arun(
            sample_path=_SAMPLE_PATH,
            analysis_id=_ANALYSIS_ID,
            document_format="ooxml_docx_macro",
            document_tier="P0",
            options={},
        )
        required = {
            "status",
            "document_analysis",
            "macro_analysis",
            "embedded_payloads",
            "delivery_chain_doc",
            "strings_iocs",
            "error_summary",
        }
        assert required.issubset(result.keys())

    @pytest.mark.asyncio
    async def test_macro_analysis_keys(self) -> None:
        tool, client, store, _ = _make_tool(
            exec_responses={
                "run_olevba.py": _make_exec_result(_OLEVBA_EMPTY),
                "run_vmonkey.py": _make_exec_result(_VMONKEY_EMPTY),
            }
        )
        result = await tool._arun(
            sample_path=_SAMPLE_PATH,
            analysis_id=_ANALYSIS_ID,
            document_format="ooxml_xlsx_macro",
            document_tier="P0",
            options={},
        )
        ma = result["macro_analysis"]
        assert "vba_modules" in ma
        assert "xl4_macros" in ma
        assert "static_actions" in ma
        assert "static_iocs" in ma
        assert "simulation_events" in ma
        assert "simulation_gaps" in ma
        assert "simulation_status" in ma


# ---------------------------------------------------------------------------
# FR-06 C6 — document IOC merge into strings_iocs
# ---------------------------------------------------------------------------


class TestDocumentStringIocsFr06:
    """FR-06 AC-2/5/6 — DocExtract merges document strings into ``strings_iocs``."""

    @pytest.mark.asyncio
    async def test_powershell_cradle_merges_static_and_simulated_sources(self) -> None:
        shared = "powershell.exe -nop -w hidden -enc AAA"
        olevba = {
            "vba_modules": [
                {
                    "name": "M1",
                    "source_hash": "sha256:dummy",
                    "source": shared,
                    "source_preview": shared[:128],
                    "code_page": "utf-8",
                }
            ],
            "xl4_macros": [],
            "triggers": [],
        }
        vmonkey = {
            "simulation_events": [
                {
                    "action": "Shell.Run",
                    "args_literal": [shared],
                    "source_line": 1,
                }
            ],
            "simulation_gaps": [],
            "simulation_status": "completed",
        }
        tool, _client, store, _session = _make_tool(
            exec_responses={
                "run_olevba.py": _make_exec_result(olevba),
                "run_vmonkey.py": _make_exec_result(vmonkey),
            }
        )
        result = await tool._arun(
            sample_path=_SAMPLE_PATH,
            analysis_id=_ANALYSIS_ID,
            document_format="ooxml_docx_macro",
            document_tier="P0",
            options={},
        )
        ps_inds = [
            i
            for i in store.query(bucket=Bucket.strings_iocs)
            if i.indicator_type == "powershell_cradle"
        ]
        assert len(ps_inds) == 1
        assert ps_inds[0].data["source"] == ["simulated", "static"]
        assert ps_inds[0].confidence.value == "HIGH"
        assert any(
            x["indicator_type"] == "powershell_cradle"
            and x["data"]["source"] == ["simulated", "static"]
            for x in result["strings_iocs"]
        )

    @pytest.mark.asyncio
    async def test_remote_template_url_is_high_confidence(self) -> None:
        tmpl_url = "https://evil.example/payload.dotm"
        olevba = {
            "vba_modules": [
                {
                    "name": "M1",
                    "source_hash": "sha256:dummy",
                    "source": f'Const u = "{tmpl_url}"',
                    "source_preview": tmpl_url,
                    "code_page": "utf-8",
                }
            ],
            "xl4_macros": [],
            "triggers": [],
        }
        tool, _client, store, _session = _make_tool(
            exec_responses={
                "run_olevba.py": _make_exec_result(olevba),
                "run_vmonkey.py": _make_exec_result(_VMONKEY_EMPTY),
            }
        )
        await tool._arun(
            sample_path=_SAMPLE_PATH,
            analysis_id=_ANALYSIS_ID,
            document_format="ooxml_docx_macro",
            document_tier="P0",
            options={},
        )
        rt = [
            i
            for i in store.query(bucket=Bucket.strings_iocs)
            if i.indicator_type == "remote_template_url"
        ]
        assert len(rt) == 1
        assert tmpl_url in rt[0].data["value"]
        assert rt[0].confidence.value == "HIGH"


# ---------------------------------------------------------------------------
# _load_password_list helper
# ---------------------------------------------------------------------------


class TestLoadPasswordList:
    """_load_password_list falls back to bundled YAML when system path absent."""

    def test_returns_list_from_bundled_yaml(self, tmp_path: Path) -> None:
        yaml_content = "version: '1.0'\npasswords:\n  - infected\n  - virus\n"
        pw_file = tmp_path / "passwords.yaml"
        pw_file.write_text(yaml_content)
        result = _load_password_list(str(pw_file))
        assert "infected" in result
        assert "virus" in result

    def test_returns_empty_on_missing_file(self) -> None:
        result = _load_password_list("/nonexistent/path/to/passwords.yaml")
        # Falls through to bundled YAML; bundled YAML should exist
        assert isinstance(result, list)

    def test_path_override_takes_precedence(self, tmp_path: Path) -> None:
        yaml_content = "version: '1.0'\npasswords:\n  - custom_password\n"
        pw_file = tmp_path / "custom.yaml"
        pw_file.write_text(yaml_content)
        result = _load_password_list(str(pw_file))
        assert "custom_password" in result


# ---------------------------------------------------------------------------
# _log_password_attempt audit coverage
# ---------------------------------------------------------------------------


class TestLogPasswordAttempt:
    """_log_password_attempt must never store plaintext (FR-03 AC-13)."""

    def test_no_plaintext_in_log_args(self) -> None:
        logged: list[dict] = []

        def _capture(**kwargs: Any) -> None:
            logged.append(kwargs)

        with patch.dict(_log_password_attempt.__globals__, {"log_tool_call": _capture}):
            _log_password_attempt("infected")

        assert len(logged) == 1
        args = logged[0]["args"]
        assert "infected" not in str(args), (
            "Plaintext password must not appear in audit args"
        )
        assert args["hash_prefix"].startswith("sha256:")
        assert "[len=" in args["truncated"]

    def test_truncated_field_hides_full_password(self) -> None:
        logged: list[dict] = []

        def _capture(**kwargs: Any) -> None:
            logged.append(kwargs)

        password = "VelvetSweatshop"
        with patch.dict(_log_password_attempt.__globals__, {"log_tool_call": _capture}):
            _log_password_attempt(password)

        truncated = logged[0]["args"]["truncated"]
        assert password not in truncated
        assert truncated.startswith("Ve")
        assert f"[len={len(password)}]" in truncated
