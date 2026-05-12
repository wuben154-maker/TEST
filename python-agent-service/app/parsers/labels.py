"""
Label Loader - Parses LABELS.md configuration file for multi-language UI labels.

This module provides functions to load and access labels from the shared LABELS.md file.
"""

import re
from pathlib import Path
from typing import Dict, List, Optional
from functools import lru_cache

# Supported languages
SupportedLanguage = str  # 'en', 'zh', 'ja', 'ko'
DEFAULT_LANGUAGE = 'zh'

# Path to the labels file
LABELS_FILE = Path(__file__).parent.parent.parent / 'config' / 'LABELS.md'


@lru_cache(maxsize=1)
def _load_labels_file() -> str:
    """Load the LABELS.md file content."""
    if not LABELS_FILE.exists():
        raise FileNotFoundError(f"Labels file not found: {LABELS_FILE}")
    return LABELS_FILE.read_text(encoding='utf-8')


def _parse_section(content: str, section_name: str) -> Dict[str, Dict[str, str]]:
    """Parse a section from the markdown file.
    
    Returns a dict like:
    {
        'extract_iocs': {'en': 'Extracting IOCs', 'zh': '提取安全指标', ...},
        ...
    }
    """
    result = {}
    
    # Find the section
    section_pattern = rf'^# {re.escape(section_name)}\s*$'
    section_match = re.search(section_pattern, content, re.MULTILINE)
    if not section_match:
        return result
    
    # Get content until next main section or end
    start = section_match.end()
    next_section = re.search(r'^# (?!#)', content[start:], re.MULTILINE)
    end = start + next_section.start() if next_section else len(content)
    section_content = content[start:end]
    
    # Parse each item (## item_name followed by - lang: value lines)
    item_pattern = r'^## (\w+)\s*$'
    items = list(re.finditer(item_pattern, section_content, re.MULTILINE))
    
    for i, item_match in enumerate(items):
        item_name = item_match.group(1)
        item_start = item_match.end()
        item_end = items[i + 1].start() if i + 1 < len(items) else len(section_content)
        item_content = section_content[item_start:item_end]
        
        # Parse language lines
        lang_pattern = r'^- (\w+):\s*(.+)$'
        labels = {}
        for lang_match in re.finditer(lang_pattern, item_content, re.MULTILINE):
            lang = lang_match.group(1)
            value = lang_match.group(2).strip().strip('"\'')
            labels[lang] = value
        
        if labels:
            result[item_name] = labels
    
    return result


@lru_cache(maxsize=1)
def get_tool_step_labels() -> Dict[str, Dict[str, str]]:
    """Get all tool step labels."""
    content = _load_labels_file()
    return _parse_section(content, 'Tool Step Labels')


@lru_cache(maxsize=1)
def get_analysis_phases() -> Dict[str, Dict[str, str]]:
    """Get all analysis phase labels."""
    content = _load_labels_file()
    return _parse_section(content, 'Analysis Phases')


@lru_cache(maxsize=1)
def get_ui_text() -> Dict[str, Dict[str, str]]:
    """Get all UI text labels."""
    content = _load_labels_file()
    return _parse_section(content, 'UI Text')


@lru_cache(maxsize=1)
def get_intent_understanding_labels() -> Dict[str, Dict[str, str]]:
    """Get all intent understanding labels."""
    content = _load_labels_file()
    return _parse_section(content, 'Intent Understanding')


@lru_cache(maxsize=1)
def get_stream_adapter_labels() -> Dict[str, Dict[str, str]]:
    """Get all stream adapter labels (SSE event labels)."""
    content = _load_labels_file()
    return _parse_section(content, 'Stream Adapter')


def get_stream_adapter_label(key: str, lang: SupportedLanguage = DEFAULT_LANGUAGE) -> str:
    """Get a stream adapter label for a specific language.

    Args:
        key: The label key (e.g., 'stream_analysis_start')
        lang: The language code (default: 'zh')

    Returns:
        The localized label, or the key if not found
    """
    labels = get_stream_adapter_labels()
    item = labels.get(key, {})
    return item.get(lang, item.get('en', key))


def get_task_submitted_placeholders() -> List[str]:
    """Get all task-submitted placeholder strings for content matching.

    Used to detect when LLM output indicates task was submitted without
    producing tool results. Returns lowercase values for case-insensitive match.
    """
    labels = get_stream_adapter_labels()
    ph = labels.get('task_submitted_placeholder', {})
    return [v.lower().strip() for v in ph.values() if v]


@lru_cache(maxsize=1)
def get_vendor_auth_type_labels() -> Dict[str, Dict[str, str]]:
    """Get display labels for vendor integration auth type codes."""
    content = _load_labels_file()
    return _parse_section(content, 'Vendor Auth Types')


@lru_cache(maxsize=1)
def get_file_parsing_labels() -> Dict[str, Dict[str, str]]:
    """Get all file parsing labels."""
    content = _load_labels_file()
    return _parse_section(content, 'File Parsing')


def get_vendor_auth_type_label(
    code: str, lang: SupportedLanguage = DEFAULT_LANGUAGE
) -> str:
    """Resolve a vendor auth type code to a localized display name.

    Args:
        code: Stored value such as ``basic`` or ``api_key`` (matches DB / JSON).
        lang: BCP-47 style language code (default: ``zh``).

    Returns:
        Localized label, or ``code`` if unknown.
    """
    labels = get_vendor_auth_type_labels()
    entry = labels.get(code, {})
    return entry.get(lang, entry.get('en', code))


def get_vendor_auth_types_dict(lang: SupportedLanguage = DEFAULT_LANGUAGE) -> Dict[str, str]:
    """Map every defined auth type code to its display string for one locale."""
    labels = get_vendor_auth_type_labels()
    return {
        code: langs.get(lang, langs.get('en', code))
        for code, langs in labels.items()
    }


def get_file_parsing_label(key: str, lang: SupportedLanguage = DEFAULT_LANGUAGE) -> str:
    """Get a file parsing label for a specific language.
    
    Args:
        key: The label key (e.g., 'file_binary')
        lang: The language code (default: 'zh')
    
    Returns:
        The localized label, or the key if not found
    """
    labels = get_file_parsing_labels()
    file_labels = labels.get(key, {})
    return file_labels.get(lang, file_labels.get('en', key))


def get_tool_label(tool_name: str, lang: SupportedLanguage = DEFAULT_LANGUAGE) -> str:
    """Get a tool step label for a specific language.
    
    Args:
        tool_name: The name of the tool (e.g., 'extract_iocs')
        lang: The language code (default: 'zh')
    
    Returns:
        The localized label, or the tool name if not found
    """
    labels = get_tool_step_labels()
    tool_labels = labels.get(tool_name, {})
    return tool_labels.get(lang, tool_labels.get('en', tool_name))


def get_phase_label(phase_num: int, lang: SupportedLanguage = DEFAULT_LANGUAGE) -> str:
    """Get an analysis phase label for a specific language.
    
    Args:
        phase_num: The phase number (1-10)
        lang: The language code (default: 'zh')
    
    Returns:
        The localized phase label
    """
    phases = get_analysis_phases()
    phase_key = f'phase_{phase_num}'
    phase_labels = phases.get(phase_key, {})
    
    # Fallback to last phase if out of range
    if not phase_labels and phases:
        last_phase = max(phases.keys(), key=lambda k: int(k.split('_')[1]) if k.startswith('phase_') else 0)
        phase_labels = phases.get(last_phase, {})
    
    return phase_labels.get(lang, phase_labels.get('en', f'Phase {phase_num}'))


def get_ui_label(key: str, lang: SupportedLanguage = DEFAULT_LANGUAGE) -> str:
    """Get a UI text label for a specific language.
    
    Args:
        key: The label key (e.g., 'analyzing')
        lang: The language code (default: 'zh')
    
    Returns:
        The localized label, or the key if not found
    """
    labels = get_ui_text()
    text_labels = labels.get(key, {})
    return text_labels.get(lang, text_labels.get('en', key))


def get_intent_label(key: str, lang: SupportedLanguage = DEFAULT_LANGUAGE) -> str:
    """Get an intent understanding label for a specific language.
    
    Args:
        key: The label key (e.g., 'context_no_history')
        lang: The language code (default: 'zh')
    
    Returns:
        The localized label, or the key if not found
    """
    labels = get_intent_understanding_labels()
    intent_labels = labels.get(key, {})
    return intent_labels.get(lang, intent_labels.get('en', key))


def get_analysis_phases_list(lang: SupportedLanguage = DEFAULT_LANGUAGE) -> List[str]:
    """Get analysis phases as an ordered list for a specific language.
    
    Args:
        lang: The language code (default: 'zh')
    
    Returns:
        A list of phase labels in order
    """
    phases = get_analysis_phases()
    result = []
    
    # Sort by phase number and extract labels
    sorted_keys = sorted(
        [k for k in phases.keys() if k.startswith('phase_')],
        key=lambda k: int(k.split('_')[1])
    )
    
    for key in sorted_keys:
        label = phases[key].get(lang, phases[key].get('en', ''))
        if label:
            result.append(label)
    
    return result


def get_tool_labels_dict(lang: SupportedLanguage = DEFAULT_LANGUAGE) -> Dict[str, str]:
    """Get all tool labels as a simple dict for a specific language.
    
    Args:
        lang: The language code (default: 'zh')
    
    Returns:
        A dict mapping tool names to their localized labels
    """
    labels = get_tool_step_labels()
    return {
        tool: tool_labels.get(lang, tool_labels.get('en', tool))
        for tool, tool_labels in labels.items()
    }


def reload_labels():
    """Clear the label cache and reload from file."""
    _load_labels_file.cache_clear()
    get_tool_step_labels.cache_clear()
    get_analysis_phases.cache_clear()
    get_ui_text.cache_clear()
    get_intent_understanding_labels.cache_clear()
    get_stream_adapter_labels.cache_clear()
    get_vendor_auth_type_labels.cache_clear()
    get_file_parsing_labels.cache_clear()


# Convenience exports for backward compatibility
TOOL_STEP_LABELS = None  # Will be initialized on first access
ANALYSIS_PHASES = None


def _init_compat_vars():
    """Initialize backward-compatible module-level variables."""
    global TOOL_STEP_LABELS, ANALYSIS_PHASES
    if TOOL_STEP_LABELS is None:
        TOOL_STEP_LABELS = get_tool_labels_dict('zh')
    if ANALYSIS_PHASES is None:
        ANALYSIS_PHASES = get_analysis_phases_list('zh')


# Initialize on import
try:
    _init_compat_vars()
except FileNotFoundError:
    # Labels file may not exist in all environments
    TOOL_STEP_LABELS = {}
    ANALYSIS_PHASES = []
