"""In-request mutable snapshot of the last main-graph LLM usage (provider-reported)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ContextMeter:
    """Updated on each main ``llm_invoke_end`` (see ``LlmInvokeLifecycleCallbackHandler``).

    Subagent invocations strip the lifecycle handler — this meter reflects the
    main DeepAgents graph only.
    """

    last_main_input_tokens: int = 0
    last_main_output_tokens: int = 0
    last_main_model_id: str | None = None
    last_main_ended_at_ms: int = 0

    def record_main_invoke_end(
        self,
        *,
        input_tokens: int,
        output_tokens: int,
        model_id: str | None,
        ended_at_ms: int,
    ) -> None:
        self.last_main_input_tokens = max(0, int(input_tokens))
        self.last_main_output_tokens = max(0, int(output_tokens))
        self.last_main_model_id = model_id
        self.last_main_ended_at_ms = int(ended_at_ms)
