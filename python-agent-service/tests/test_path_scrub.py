"""Unit tests for the UI path scrubber."""

from __future__ import annotations

import pytest

from app.parsers.path_scrub import scrub_event, scrub_paths_for_ui


class TestScrubPathsForUi:
    def test_workspace_rewritten(self):
        assert (
            scrub_paths_for_ui("Saved to /workspace/report.md successfully")
            == "Saved to workspace/report.md successfully"
        )

    def test_workspace_with_nested_owner(self):
        # Owner segments MUST be stripped so the UI never surfaces
        # u_<user>/p_<project> to end users.
        assert (
            scrub_paths_for_ui("/workspace/u_alice/p_proj1/notes.md")
            == "workspace/notes.md"
        )

    def test_workspace_with_anonymous_owner(self):
        # Policy: collapse to basename; users never need to see nested owner
        # subdirs in the chat UI. See docs/Process/workspace-sandbox-unification.
        assert (
            scrub_paths_for_ui("/workspace/s_sess42/tmp/out.txt")
            == "workspace/out.txt"
        )

    def test_workspace_with_default_project(self):
        assert (
            scrub_paths_for_ui("/workspace/u_bob/default/note.md")
            == "workspace/note.md"
        )

    def test_bare_workspace_token(self):
        assert scrub_paths_for_ui("ls /workspace returned nothing") == "ls workspace returned nothing"

    def test_skills_rewritten_to_label(self):
        assert (
            scrub_paths_for_ui("Loaded /skills/web-security/SKILL.md")
            == "Loaded System Skill: web-security"
        )

    def test_skills_main_variant(self):
        assert (
            scrub_paths_for_ui("consult /skills-main/binary-analysis/SKILL.md for more")
            == "consult System Skill: binary-analysis for more"
        )

    def test_memories_basename_only(self):
        assert (
            scrub_paths_for_ui("wrote /memories/user/pref/foo.json now")
            == "wrote Memory: foo.json now"
        )

    def test_parameters_collapsed(self):
        assert (
            scrub_paths_for_ui("read from /parameters/credentials/key here")
            == "read from Parameters here"
        )
        assert scrub_paths_for_ui("see /parameters for more") == "see Parameters for more"

    def test_legacy_uploads_surface_as_workspace(self):
        # When there is no owner sub-structure the bare token surfaces.
        assert (
            scrub_paths_for_ui("uploaded /uploads/u_abc/report.pdf")
            == "uploaded workspace/report.pdf"
        )

    def test_uploads_with_user_default_owner_stripped(self):
        assert (
            scrub_paths_for_ui(
                "uploaded /uploads/u_fae/default/sub/report.pdf"
            )
            == "uploaded workspace/report.pdf"
        )

    def test_uploads_with_session_owner_stripped(self):
        assert (
            scrub_paths_for_ui("uploaded /uploads/s_sess123/file.txt")
            == "uploaded workspace/file.txt"
        )

    def test_already_scrubbed_pascal_owner_stripped(self):
        # Second pass must also strip when the path is already ``workspace/...``.
        assert (
            scrub_paths_for_ui(
                "workspace/u_fae4a472-7766-44ed/default/9aa_ghost.php"
            )
            == "workspace/9aa_ghost.php"
        )

    def test_host_paths_left_alone(self):
        # Sandbox / tool-argument absolute paths (/tmp, /etc, /Users, Windows
        # drives, ./rel) are intentionally NOT scrubbed so tool_input fields
        # and legitimate filesystem references still round-trip faithfully.
        for msg in [
            r"read C:\Users\chenf\secrets\key.pem now",
            "configured /etc/nginx/nginx.conf today",
            "saved to /Users/alice/project/out.log",
            "see ./docs/readme.md",
            "use ../notes/log.txt",
        ]:
            assert scrub_paths_for_ui(msg) == msg

    def test_untouched_on_clean_text(self):
        msg = "This is a regular sentence with no paths."
        assert scrub_paths_for_ui(msg) is msg or scrub_paths_for_ui(msg) == msg

    def test_idempotent(self):
        raw = "see /workspace/foo/bar.txt and /memories/a/b/c.json plus /parameters/x"
        once = scrub_paths_for_ui(raw)
        assert scrub_paths_for_ui(once) == once

    def test_none_and_empty(self):
        assert scrub_paths_for_ui(None) == ""
        assert scrub_paths_for_ui("") == ""

    def test_does_not_touch_scheme_urls(self):
        # https://host/path must not be rewritten as a POSIX path.
        msg = "visit https://example.com/home/report for details"
        assert scrub_paths_for_ui(msg) == msg

    def test_code_fence_internal_paths_rewritten(self):
        # Path inside prose of a code fence should still be scrubbed (text is text).
        raw = "```\nopen /workspace/a.py\n```"
        assert "workspace/a.py" in scrub_paths_for_ui(raw)
        assert "/workspace/" not in scrub_paths_for_ui(raw)


class TestScrubEvent:
    def test_scrubs_top_level_text_fields(self):
        ev = {
            "type": "tool_result",
            "id": "t1",
            "text": "wrote /workspace/a.md",
            "detail": "see /memories/user/pref.json",
            "label": "Updated /workspace/a.md",
        }
        out = scrub_event(ev)
        assert out["text"] == "wrote workspace/a.md"
        assert out["detail"] == "see Memory: pref.json"
        assert out["label"] == "Updated workspace/a.md"
        # original untouched
        assert ev["text"] == "wrote /workspace/a.md"

    def test_scrubs_nested_payload(self):
        ev = {
            "type": "tool_result",
            "payload": {
                "path": "/workspace/u_alice/p_proj1/out.md",
                "nested": {"memory": "/memories/x/y/z.json"},
            },
        }
        out = scrub_event(ev)
        assert out["payload"]["path"] == "workspace/out.md"
        assert out["payload"]["nested"]["memory"] == "Memory: z.json"

    def test_scrubs_blocks_list(self):
        ev = {
            "type": "assistant",
            "blocks": [
                {"type": "text", "text": "opened /workspace/x.txt"},
                {"type": "code", "code": "print('ok')"},
            ],
        }
        out = scrub_event(ev)
        assert out["blocks"][0]["text"] == "opened workspace/x.txt"
        assert out["blocks"][1]["code"] == "print('ok')"

    def test_non_dict_passthrough(self):
        assert scrub_event("plain") == "plain"
        assert scrub_event(None) is None
        assert scrub_event(42) == 42

    def test_is_immutable_on_original(self):
        ev = {"text": "/workspace/a.md", "payload": {"p": "/workspace/b.md"}}
        _ = scrub_event(ev)
        assert ev["text"] == "/workspace/a.md"
        assert ev["payload"]["p"] == "/workspace/b.md"

    def test_idempotent_event(self):
        ev = {
            "text": "/workspace/a/b.md and C:\\Users\\x\\y.log",
            "payload": {"p": "/memories/foo/bar.json"},
        }
        once = scrub_event(ev)
        twice = scrub_event(once)
        assert once == twice
