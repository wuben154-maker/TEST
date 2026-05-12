"""Pytest configuration and fixtures for skill tests."""

import sys
from pathlib import Path
import pytest

# Add the app directory to Python path for imports
APP_DIR = Path(__file__).parent.parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))


@pytest.fixture
def sample_skill_md():
    """Provide sample SKILL.md content for testing."""
    return """---
name: test-skill
display_name: Test Skill
description: A skill for testing purposes
triggers:
  - test
  - example
  - sample
tags:
  - testing
  - unit-test
priority: 5
version: "1.0.0"
max_iterations: 10
timeout_seconds: 60
---

<skill>
<name>Test Skill</name>
<version>1.0</version>

<role>
You are a test skill for unit testing the skill system.
</role>

<capabilities>
- Parse test data
- Validate test cases
- Generate test reports
</capabilities>

<workflow>
1. Receive test input
2. Process according to rules
3. Return structured output
</workflow>

<output-format>
**Test Result**: [PASS/FAIL]
**Details**: [Analysis details]
</output-format>
</skill>
"""


@pytest.fixture
def minimal_skill_md():
    """Provide minimal valid SKILL.md content."""
    return """---
name: minimal
description: Minimal skill
---
Basic instructions.
"""


@pytest.fixture
def temp_skills_dir(tmp_path):
    """Create a temporary skills directory with test skills."""
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    
    # Create a test skill
    test_skill_dir = skills_dir / "test-skill"
    test_skill_dir.mkdir()
    
    skill_md = test_skill_dir / "SKILL.md"
    skill_md.write_text("""---
name: test-skill
display_name: Test Skill
description: A temporary test skill
triggers:
  - temp
  - test
tags:
  - temporary
priority: 1
---
# Test Skill

This is a temporary test skill.
""")
    
    # Create scripts directory
    scripts_dir = test_skill_dir / "scripts"
    scripts_dir.mkdir()
    
    script = scripts_dir / "test_script.py"
    script.write_text("""#!/usr/bin/env python3
\"\"\"Test script.\"\"\"

def main():
    print("Test script executed")

if __name__ == "__main__":
    main()
""")
    
    return skills_dir
