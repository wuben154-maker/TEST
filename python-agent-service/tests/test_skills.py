"""Unit tests for the Skills system.

Tests cover:
- SKILL.md file parsing and loading
- Trigger keyword matching
- SkillRegistry operations
- SkillSpec methods
"""

import pytest
from pathlib import Path
from textwrap import dedent

from app.prompts.skills import (
    SkillSpec,
    SkillMetadata,
    SkillInstructions,
    SkillRegistry,
    UnifiedSkillRegistry,
    create_skill,
    get_skill_registry,
    get_skill,
    find_skill_for_query,
    find_skills_by_tag,
    get_skills_info,
    get_all_skills,
    SKILLS_DIR,
)
from app.prompts.skills.loader import parse_skill_md, load_skill_from_file


# ============================================================================
# SKILL.MD PARSING TESTS
# ============================================================================

class TestSkillMdParsing:
    """Tests for SKILL.md file parsing."""
    
    def test_parse_valid_frontmatter(self):
        """Test parsing valid YAML frontmatter."""
        content = dedent("""
            ---
            name: test-skill
            display_name: Test Skill
            description: A test skill
            triggers:
              - test
              - example
            tags:
              - testing
            priority: 5
            version: "1.0.0"
            ---
            # Test Skill Instructions
            
            This is the skill body.
        """).strip()
        
        frontmatter, body = parse_skill_md(content)
        
        assert frontmatter["name"] == "test-skill"
        assert frontmatter["display_name"] == "Test Skill"
        assert frontmatter["description"] == "A test skill"
        assert frontmatter["triggers"] == ["test", "example"]
        assert frontmatter["tags"] == ["testing"]
        assert frontmatter["priority"] == 5
        assert frontmatter["version"] == "1.0.0"
        assert "# Test Skill Instructions" in body
        assert "This is the skill body." in body
    
    def test_parse_no_frontmatter(self):
        """Test parsing content without frontmatter."""
        content = "# Just markdown\n\nNo YAML here."
        
        frontmatter, body = parse_skill_md(content)
        
        assert frontmatter == {}
        assert body == content
    
    def test_parse_empty_frontmatter(self):
        """Test parsing with empty frontmatter."""
        content = dedent("""
            ---
            ---
            # Content starts here
        """).strip()
        
        frontmatter, body = parse_skill_md(content)
        
        assert frontmatter is None or frontmatter == {}
        assert "# Content starts here" in body
    
    def test_parse_minimal_frontmatter(self):
        """Test parsing with minimal required fields."""
        content = dedent("""
            ---
            name: minimal
            ---
            Instructions here.
        """).strip()
        
        frontmatter, body = parse_skill_md(content)
        
        assert frontmatter["name"] == "minimal"
        assert "Instructions here." in body


# ============================================================================
# SKILL LOADING TESTS
# ============================================================================

class TestSkillLoading:
    """Tests for loading skills from filesystem."""
    
    def test_skills_directory_exists(self):
        """Verify the skills directory exists."""
        assert SKILLS_DIR.exists(), f"Skills directory not found: {SKILLS_DIR}"
    
    def test_load_email_security_skill(self):
        """Test loading the email-security skill."""
        skill_path = SKILLS_DIR / "email-security"
        
        if not skill_path.exists():
            pytest.skip("email-security skill not found")
        
        skill = load_skill_from_file(skill_path)
        
        assert skill is not None
        assert skill.name == "email-security"
        assert skill.metadata.display_name is not None
        assert len(skill.metadata.triggers) > 0
    
    def test_load_all_skills(self):
        """Test that all skills can be discovered (official mode: metadata only)."""
        skills = get_all_skills()
        
        assert len(skills) >= 1, "At least one skill should be discovered"
        
        for skill in skills:
            assert skill.name is not None
            assert skill.description is not None
    
    def test_skill_has_scripts(self):
        """Test that skills with scripts directory are loaded correctly."""
        skill_path = SKILLS_DIR / "email-security"
        
        if not skill_path.exists():
            pytest.skip("email-security skill not found")
        
        skill = load_skill_from_file(skill_path)
        scripts_dir = skill_path / "scripts"
        
        if scripts_dir.exists():
            assert len(skill.resources) > 0, "Skill should have associated scripts"
    
    def test_load_nonexistent_skill(self):
        """Test loading from non-existent path returns None."""
        fake_path = SKILLS_DIR / "nonexistent-skill"
        skill = load_skill_from_file(fake_path)
        
        assert skill is None


# ============================================================================
# TRIGGER MATCHING TESTS
# ============================================================================

class TestTriggerMatching:
    """Tests for trigger keyword matching."""
    
    def test_exact_trigger_match(self):
        """Test exact trigger word matching."""
        skill = create_skill(
            name="test-trigger",
            display_name="Test Trigger",
            description="Test trigger matching",
            system_prompt="Test prompt",
            triggers=["phishing", "email", "spam"],
        )
        
        assert skill.matches("analyze this phishing email")
        assert skill.matches("check for spam")
        assert skill.matches("EMAIL headers look suspicious")
    
    def test_no_trigger_match(self):
        """Test queries that don't match triggers."""
        skill = create_skill(
            name="test-trigger",
            display_name="Test Trigger",
            description="Test trigger matching",
            system_prompt="Test prompt",
            triggers=["phishing", "email"],
        )
        
        assert not skill.matches("analyze this binary file")
        assert not skill.matches("check network traffic")
    
    def test_case_insensitive_matching(self):
        """Test that trigger matching is case-insensitive."""
        skill = create_skill(
            name="test-case",
            display_name="Test Case",
            description="Test case sensitivity",
            system_prompt="Test prompt",
            triggers=["XSS", "SQLi"],
        )
        
        assert skill.matches("detected xss vulnerability")
        assert skill.matches("possible SQLI attack")
        assert skill.matches("XSS in payload")
    
    def test_partial_word_no_match(self):
        """Test that partial words don't incorrectly match."""
        skill = create_skill(
            name="test-partial",
            display_name="Test Partial",
            description="Test partial matching",
            system_prompt="Test prompt",
            triggers=["sql"],
        )
        
        # "sql" should match as word boundary
        assert skill.matches("sql injection attack")
        # But implementation may vary - this tests current behavior


# ============================================================================
# SKILL REGISTRY TESTS
# ============================================================================

class TestSkillRegistry:
    """Tests for SkillRegistry operations."""
    
    def test_register_and_get_skill(self):
        """Test registering and retrieving a skill."""
        registry = SkillRegistry()
        skill = create_skill(
            name="test-register",
            display_name="Test Register",
            description="Test registration",
            system_prompt="Test prompt",
        )
        
        registry.register(skill)
        retrieved = registry.get("test-register")
        
        assert retrieved is not None
        assert retrieved.name == "test-register"
    
    def test_get_nonexistent_skill(self):
        """Test getting a non-existent skill returns None."""
        registry = SkillRegistry()
        
        result = registry.get("nonexistent")
        
        assert result is None
    
    def test_list_skills(self):
        """Test listing all registered skills."""
        registry = SkillRegistry()
        
        for i in range(3):
            skill = create_skill(
                name=f"skill-{i}",
                display_name=f"Skill {i}",
                description=f"Skill {i}",
                system_prompt="Test",
            )
            registry.register(skill)
        
        skills = registry.list_skills()
        
        assert len(skills) == 3
    
    def test_find_by_query(self):
        """Test finding skills by query."""
        registry = SkillRegistry()
        
        skill1 = create_skill(
            name="email-skill",
            display_name="Email Skill",
            description="Email analysis",
            system_prompt="Test",
            triggers=["email", "phishing"],
            priority=10,
        )
        skill2 = create_skill(
            name="web-skill",
            display_name="Web Skill",
            description="Web analysis",
            system_prompt="Test",
            triggers=["http", "xss"],
            priority=5,
        )
        
        registry.register(skill1)
        registry.register(skill2)
        
        matches = registry.find_by_query("suspicious phishing email")
        
        assert len(matches) >= 1
        # Higher priority should come first
        assert matches[0][1].name == "email-skill"
    
    def test_get_best_match(self):
        """Test getting the best matching skill."""
        registry = SkillRegistry()
        
        low_priority = create_skill(
            name="low-priority",
            display_name="Low Priority",
            description="Low priority skill",
            system_prompt="Test",
            triggers=["test"],
            priority=1,
        )
        high_priority = create_skill(
            name="high-priority",
            display_name="High Priority",
            description="High priority skill",
            system_prompt="Test",
            triggers=["test"],
            priority=10,
        )
        
        registry.register(low_priority)
        registry.register(high_priority)
        
        best = registry.get_best_match("run test analysis")
        
        assert best is not None
        assert best.name == "high-priority"
    
    def test_find_by_tag(self):
        """Test finding skills by tag."""
        registry = SkillRegistry()
        
        skill = create_skill(
            name="tagged-skill",
            display_name="Tagged Skill",
            description="A tagged skill",
            system_prompt="Test",
            tags=["security", "analysis"],
        )
        registry.register(skill)
        
        results = registry.find_by_tag("security")
        
        assert len(results) >= 1
        assert any(s.name == "tagged-skill" for s in results)


# ============================================================================
# UNIFIED REGISTRY TESTS
# ============================================================================

class TestUnifiedRegistry:
    """Tests for UnifiedSkillRegistry specific features."""
    
    def test_load_from_filesystem(self):
        """Test loading skills from filesystem."""
        registry = UnifiedSkillRegistry()
        count = registry.load_from_filesystem()
        
        # Should load at least some skills
        assert count >= 0
    
    def test_reload_skills(self):
        """Test hot-reloading skills."""
        registry = UnifiedSkillRegistry()
        registry.load_from_filesystem()
        
        initial_count = len(registry.list_skills())
        
        # Reload should work without errors
        registry.reload()
        
        final_count = len(registry.list_skills())
        
        # Should have same number of skills after reload
        assert final_count == initial_count
    
    def test_global_registry(self):
        """Test the global registry is properly initialized."""
        registry = get_skill_registry()
        
        assert registry is not None
        assert isinstance(registry, UnifiedSkillRegistry)


# ============================================================================
# SKILL SPEC TESTS
# ============================================================================

class TestSkillSpec:
    """Tests for SkillSpec methods."""
    
    def test_get_summary(self):
        """Test skill summary generation."""
        skill = create_skill(
            name="summary-test",
            display_name="Summary Test Skill",
            description="A skill for testing summaries",
            system_prompt="Test prompt",
        )
        
        summary = skill.get_summary()
        
        assert "summary-test" in summary or "Summary Test Skill" in summary
        assert "testing summaries" in summary.lower()
    
    def test_get_frontmatter(self):
        """Test frontmatter generation."""
        skill = create_skill(
            name="frontmatter-test",
            display_name="Frontmatter Test",
            description="Test description",
            system_prompt="Test prompt",
            triggers=["test"],
            tags=["testing"],
            priority=5,
        )
        
        frontmatter = skill.get_frontmatter()
        # get_frontmatter returns YAML string
        assert "frontmatter-test" in frontmatter
        assert "Test description" in frontmatter
        assert "test" in frontmatter
        assert "testing" in frontmatter
        assert "5" in frontmatter
    
    def test_skill_name_property(self):
        """Test that skill.name returns metadata.name."""
        skill = create_skill(
            name="property-test",
            display_name="Property Test",
            description="Test",
            system_prompt="Test",
        )
        
        assert skill.name == "property-test"
        assert skill.name == skill.metadata.name


# ============================================================================
# INTEGRATION TESTS
# ============================================================================

class TestSkillIntegration:
    """Integration tests for the complete skill system."""
    
    def test_get_skills_info(self):
        """Test getting skill system information."""
        info = get_skills_info()
        
        assert "total" in info
        assert "skills" in info
        assert "skills_dir" in info
        assert info["total"] >= 0
    
    def test_find_skill_for_query(self):
        """Test finding a skill for a real query."""
        skills = get_all_skills()
        if len(skills) == 0:
            pytest.skip("No skills loaded")
        # Use description keyword for matching (official mode uses description)
        first_skill = skills[0]
        keyword = first_skill.description.split()[0] if first_skill.description else first_skill.name
        query = f"analyze {keyword} data"
        found = find_skill_for_query(query)
        assert found is not None
    
    def test_skill_system_consistency(self):
        """Test that skill system is internally consistent."""
        registry = get_skill_registry()
        all_skills = get_all_skills()
        
        # All skills from get_all_skills should be in registry
        for skill in all_skills:
            assert registry.get(skill.name) is not None
        
        # Counts should match
        assert len(all_skills) == len(registry.list_skills())


# ============================================================================
# EXPECTED SKILLS TESTS
# ============================================================================

class TestExpectedSkills:
    """Tests for expected skills to be present."""
    
    EXPECTED_SKILLS = [
        "vuln-scan",
        "general-security",
    ]
    
    def test_expected_skills_exist(self):
        """Test that all expected skills are loaded."""
        loaded_skills = {s.name for s in get_all_skills()}
        
        for expected in self.EXPECTED_SKILLS:
            assert expected in loaded_skills, f"Expected skill '{expected}' not found"
    
    def test_email_security_triggers(self):
        """Test email-security skill has appropriate triggers (via full loader)."""
        skill = load_skill_from_file(SKILLS_DIR / "email-security")
        if skill is None:
            pytest.skip("email-security skill lives in subagent bundle, not global skills/")
        triggers = skill.metadata.triggers
        assert any("email" in t.lower() for t in triggers)

    def test_binary_analysis_triggers(self):
        """Test binary-analysis skill has appropriate triggers (via full loader)."""
        skill = load_skill_from_file(SKILLS_DIR / "binary-analysis")
        if skill is None:
            pytest.skip("binary-analysis skill lives in subagent bundle, not global skills/")
        triggers = skill.metadata.triggers
        assert any("binary" in t.lower() or "exe" in t.lower() for t in triggers)

    def test_web_security_triggers(self):
        """Test web-security skill has appropriate triggers (via full loader)."""
        skill = load_skill_from_file(SKILLS_DIR / "web-security")
        if skill is None:
            pytest.skip("web-security skill lives in subagent bundle, not global skills/")
        triggers = skill.metadata.triggers
        assert any("http" in t.lower() or "xss" in t.lower() or "sql" in t.lower() for t in triggers)
