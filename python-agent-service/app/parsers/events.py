"""
Event Visibility Configuration - Parses EVENTS.md configuration file.

This module provides functions to load and access event visibility settings
from the shared EVENTS.md file, similar to how labels.py handles LABELS.md.
"""

import re
from pathlib import Path
from typing import Dict, List, Optional, Set
from functools import lru_cache


# Path to the events config file
EVENTS_FILE = Path(__file__).parent.parent.parent / 'config' / 'EVENTS.md'


@lru_cache(maxsize=1)
def _load_events_file() -> str:
    """Load the EVENTS.md file content."""
    if not EVENTS_FILE.exists():
        return ""
    return EVENTS_FILE.read_text(encoding='utf-8')


def _parse_simple_list(content: str, section_name: str) -> Set[str]:
    """Parse a section that contains a simple list of ## items.
    
    Returns a set of item names.
    """
    result = set()
    
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
    
    # Parse each ## item
    item_pattern = r'^## (\S+)\s*$'
    for match in re.finditer(item_pattern, section_content, re.MULTILINE):
        result.add(match.group(1))
    
    return result


def _parse_labels_section(content: str, section_name: str) -> Set[str]:
    """Parse a section with ## items containing - label: value.
    
    Returns a set of label values.
    """
    result = set()
    
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
    
    # Parse label values
    label_pattern = r'^- label:\s*(.+)$'
    for match in re.finditer(label_pattern, section_content, re.MULTILINE):
        label = match.group(1).strip().strip('"\'')
        if label:
            result.add(label)
    
    return result


def _parse_patterns_section(content: str, section_name: str) -> List[str]:
    """Parse a section with ## items containing - pattern: value.
    
    Returns a list of regex patterns.
    """
    result = []
    
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
    
    # Parse pattern values
    pattern_pattern = r'^- pattern:\s*(.+)$'
    for match in re.finditer(pattern_pattern, section_content, re.MULTILINE):
        pattern = match.group(1).strip().strip('"\'')
        if pattern:
            result.append(pattern)
    
    return result


@lru_cache(maxsize=1)
def get_internal_event_types() -> Set[str]:
    """Get event types that are always internal (hidden)."""
    content = _load_events_file()
    return _parse_simple_list(content, 'Internal Event Types')


@lru_cache(maxsize=1)
def get_visible_event_types() -> Set[str]:
    """Get event types that are always visible."""
    content = _load_events_file()
    return _parse_simple_list(content, 'Visible Event Types')


@lru_cache(maxsize=1)
def get_internal_labels() -> Set[str]:
    """Get exact labels that mark events as internal."""
    content = _load_events_file()
    return _parse_labels_section(content, 'Internal Labels')


@lru_cache(maxsize=1)
def get_internal_label_patterns() -> List[str]:
    """Get regex patterns for internal labels."""
    content = _load_events_file()
    return _parse_patterns_section(content, 'Internal Label Patterns')


@lru_cache(maxsize=1)
def get_internal_tool_names() -> Set[str]:
    """Get tool names whose events should be hidden."""
    content = _load_events_file()
    return _parse_simple_list(content, 'Internal Tool Names')


def reload_events_config():
    """Clear the events cache and reload from file."""
    _load_events_file.cache_clear()
    get_internal_event_types.cache_clear()
    get_visible_event_types.cache_clear()
    get_internal_labels.cache_clear()
    get_internal_label_patterns.cache_clear()
    get_internal_tool_names.cache_clear()


def is_event_internal(
    event_type: str,
    label: Optional[str] = None,
    tool_name: Optional[str] = None,
    explicit_internal: Optional[bool] = None,
) -> bool:
    """
    Determine if an event should be marked as internal (hidden from users).
    
    Args:
        event_type: The type of the event (e.g., 'step', 'tool_call')
        label: The event label (optional)
        tool_name: The tool name if this is a tool-related event (optional)
        explicit_internal: If explicitly set, this takes precedence (optional)
    
    Returns:
        True if the event should be marked as internal, False otherwise
    
    Priority:
        1. explicit_internal (if set)
        2. internal_event_types (if matches)
        3. visible_event_types (if matches, return False)
        4. internal_labels (exact match)
        5. internal_label_patterns (regex match)
        6. internal_tool_names (if matches)
        7. Default: False (visible)
    """
    # 1. Explicit internal flag takes precedence
    if explicit_internal is not None:
        return explicit_internal
    
    # 2. Check if event type is always internal
    if event_type in get_internal_event_types():
        return True
    
    # 3. Check if event type is always visible
    if event_type in get_visible_event_types():
        return False
    
    # 4. Check exact label match
    if label and label in get_internal_labels():
        return True
    
    # 5. Check label patterns (regex)
    if label:
        for pattern in get_internal_label_patterns():
            try:
                if re.match(pattern, label, re.IGNORECASE):
                    return True
            except re.error:
                pass  # Skip invalid patterns
    
    # 6. Check tool names
    if tool_name and tool_name in get_internal_tool_names():
        return True
    
    # 7. Default: visible
    return False


def mark_event_internal(event: Dict) -> Dict:
    """
    Process an event dict and add 'internal' field if needed.
    
    This is a convenience function that takes an event dict,
    checks if it should be internal, and adds the 'internal' field.
    
    Args:
        event: The event dictionary
    
    Returns:
        The event dictionary with 'internal' field added if needed
    """
    # Skip if already has explicit internal flag
    if 'internal' in event and event['internal'] is not None:
        return event
    
    event_type = event.get('type', '')
    label = event.get('label')
    tool_name = event.get('toolName')
    
    if is_event_internal(event_type, label, tool_name):
        event['internal'] = True
    
    return event


def get_visibility_summary() -> Dict:
    """Get a summary of the current visibility configuration."""
    return {
        'internal_event_types': list(get_internal_event_types()),
        'visible_event_types': list(get_visible_event_types()),
        'internal_label_patterns': get_internal_label_patterns(),
        'internal_labels': list(get_internal_labels()),
        'internal_tool_names': list(get_internal_tool_names()),
    }
