"""Research Configuration + request-scoped gateway model (isolated imports)."""

from unittest.mock import MagicMock, patch

from app.agents.research.open_deep_research_original.configuration import Configuration
from app.config import clear_settings_cache


def test_configuration_prefers_request_scoped_gateway_model(monkeypatch):
    """When analyze stream set request context, deep-research stages use that gateway id."""
    monkeypatch.setenv("DEFAULT_MODEL", "openai/gpt-4o")
    clear_settings_cache()

    def fake_registry() -> MagicMock:
        r = MagicMock()

        def gmc(model_id: str):
            if model_id == "doubao/doubao-seed-2-pro":
                return {"provider_id": "doubao", "model": {}, "provider": {}}
            return None

        r.get_model_config = gmc
        return r

    with patch("app.llm_gateway.registry.get_registry", fake_registry):
        with patch(
            "app.llm_gateway.request_context.get_request_llm_model_id",
            return_value="doubao/doubao-seed-2-pro",
        ):
            cfg = Configuration.from_runnable_config({"configurable": {}})
    assert cfg.research_model == "doubao:doubao-seed-2-pro"
    assert cfg.summarization_model == "doubao:doubao-seed-2-pro"


def test_configuration_prefers_llm_gateway_model_id_from_graph_over_context(monkeypatch):
    """Main graph passes llm_gateway_model_id; must override ContextVar for deep-research."""
    monkeypatch.setenv("DEFAULT_MODEL", "openai/gpt-4o")
    clear_settings_cache()

    def fake_registry() -> MagicMock:
        r = MagicMock()

        def gmc(model_id: str):
            if model_id == "graph-a/gr-alpha":
                return {"provider_id": "a", "model": {}, "provider": {}}
            if model_id == "ctx-only/model":
                return {"provider_id": "b", "model": {}, "provider": {}}
            return None

        r.get_model_config = gmc
        return r

    with patch("app.llm_gateway.registry.get_registry", fake_registry):
        with patch(
            "app.llm_gateway.request_context.get_request_llm_model_id",
            return_value="ctx-only/model",
        ):
            cfg = Configuration.from_runnable_config(
                {"configurable": {"llm_gateway_model_id": "graph-a/gr-alpha"}}
            )
    assert cfg.research_model == "graph-a:gr-alpha"
    assert cfg.summarization_model == "graph-a:gr-alpha"
