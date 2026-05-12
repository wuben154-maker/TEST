"""Deep Research agent prompt templates.

Source of truth: ``prompt_md/*.md`` (Markdown sections only; no XML-style wrappers).
Python string formatting placeholders (e.g. ``{messages}``, ``{date}``) are preserved in those files.
"""

from __future__ import annotations

from .prompt_loader import load_deep_research_prompt

clarify_with_user_instructions = load_deep_research_prompt("clarify_with_user_instructions")
transform_messages_into_research_topic_prompt = load_deep_research_prompt(
    "transform_messages_into_research_topic_prompt"
)
lead_researcher_prompt = load_deep_research_prompt("lead_researcher_prompt")
research_system_prompt = load_deep_research_prompt("research_system_prompt")
compress_research_system_prompt = load_deep_research_prompt("compress_research_system_prompt")
compress_research_simple_human_message = load_deep_research_prompt(
    "compress_research_simple_human_message"
)
final_report_generation_prompt = load_deep_research_prompt("final_report_generation_prompt")
summarize_webpage_prompt = load_deep_research_prompt("summarize_webpage_prompt")
