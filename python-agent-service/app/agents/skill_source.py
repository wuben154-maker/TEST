"""SkillSource protocol: official discovery today; tenant hook for Phase 2."""

from __future__ import annotations

from typing import Protocol

from app.prompts.skills.discovery import SkillMetadataRef, discover_skill_metadata


class SkillSource(Protocol):
    """Pluggable skill listing for orchestration and future tenancy."""

    def list_official(self) -> list[SkillMetadataRef]:
        """Return metadata for platform official skill packages."""
        ...

    def list_for_tenant(self, tenant_id: str | None) -> list[SkillMetadataRef]:
        """Return tenant-scoped packages; Phase 1 returns []."""
        ...


class OfficialSkillSource:
    """Phase 1: filesystem official skills only."""

    def list_official(self) -> list[SkillMetadataRef]:
        return discover_skill_metadata()

    def list_for_tenant(self, tenant_id: str | None) -> list[SkillMetadataRef]:  # noqa: ARG002
        return []
