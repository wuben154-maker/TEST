"""Tests for fuzzy matching functionality in ContextRetriever.

Tests verify that fuzzy matching works correctly without requiring
vector embeddings or pgvector.
"""

import pytest
from app.middleware.context_retriever import ContextRetriever
from app.backends.store import InMemoryStore, StoreBackend


class TestFuzzyMatching:
    """Test fuzzy matching functionality."""
    
    @pytest.fixture
    def retriever(self):
        """Create a ContextRetriever with in-memory store."""
        # Note: ContextRetriever expects BaseStore, not StoreBackend
        store = InMemoryStore()
        return ContextRetriever(store_backend=store)
    
    @pytest.mark.asyncio
    async def test_exact_key_match(self, retriever):
        """Test exact key matching (backward compatible)."""
        session_id = "test_session"
        
        # Save some memories
        await retriever.save_to_long_term(session_id, "api_key_vt", "secret123")
        await retriever.save_to_long_term(session_id, "analysis_cve_2024", "CVE-2024-3094 analysis")
        
        # Exact match
        results = await retriever.get_long_term_context(session_id, key="api_key_vt")
        
        assert len(results) > 0
        assert any(item["key"] == "api_key_vt" for item in results)
    
    @pytest.mark.asyncio
    async def test_fuzzy_match_by_key(self, retriever):
        """Test fuzzy matching by key."""
        session_id = "test_session"
        
        # Save memories with different keys
        await retriever.save_to_long_term(
            session_id, 
            "virus_total_api_key", 
            "vt_api_secret"
        )
        await retriever.save_to_long_term(
            session_id,
            "vt_api_token",
            "another_token"
        )
        await retriever.save_to_long_term(
            session_id,
            "unrelated_key",
            "some_value"
        )
        
        # Fuzzy search for "virus total" or "vt"
        results = await retriever.get_long_term_context(
            session_id, 
            query="virus total"
        )
        
        # Should find both virus_total_api_key and vt_api_token
        assert len(results) >= 2
        keys = [item["key"] for item in results]
        assert "virus_total_api_key" in keys or "vt_api_token" in keys
    
    @pytest.mark.asyncio
    async def test_fuzzy_match_by_value(self, retriever):
        """Test fuzzy matching by value content."""
        session_id = "test_session"
        
        # Save memories with descriptive values
        await retriever.save_to_long_term(
            session_id,
            "analysis_1",
            "CVE-2024-3094 is a backdoor vulnerability in xz utils"
        )
        await retriever.save_to_long_term(
            session_id,
            "analysis_2",
            "Log4j vulnerability affects Java applications"
        )
        
        # Search for "xz backdoor"
        results = await retriever.get_long_term_context(
            session_id,
            query="xz backdoor"
        )
        
        # Should find analysis_1
        assert len(results) > 0
        assert any("xz" in item.get("value", "").lower() for item in results)
    
    @pytest.mark.asyncio
    async def test_similarity_calculation(self, retriever):
        """Test similarity calculation logic."""
        # Test exact match
        similarity = retriever._calculate_similarity(
            "api key", {"api", "key"}, "api_key", "value"
        )
        assert similarity >= 0.9
        
        # Test partial match
        similarity = retriever._calculate_similarity(
            "virus total", {"virus", "total"}, "vt_api", "value"
        )
        assert similarity > 0.0  # Should have some similarity
        
        # Test no match
        similarity = retriever._calculate_similarity(
            "completely different", {"completely", "different"}, 
            "unrelated_key", "unrelated_value"
        )
        assert similarity < 0.5  # Low similarity
    
    @pytest.mark.asyncio
    async def test_combined_key_and_query(self, retriever):
        """Test combining exact key match and fuzzy query."""
        session_id = "test_session"
        
        await retriever.save_to_long_term(session_id, "exact_key", "value1")
        await retriever.save_to_long_term(session_id, "similar_key", "value2")
        
        # Both key and query provided
        results = await retriever.get_long_term_context(
            session_id,
            key="exact_key",
            query="similar"
        )
        
        # Should include exact match and fuzzy matches
        assert len(results) >= 1
        assert any(item["key"] == "exact_key" for item in results)
    
    @pytest.mark.asyncio
    async def test_limit_enforcement(self, retriever):
        """Test that limit is enforced."""
        session_id = "test_session"
        
        # Save many memories
        for i in range(20):
            await retriever.save_to_long_term(
                session_id,
                f"key_{i}",
                f"value_{i}"
            )
        
        # Request with limit
        results = await retriever.get_long_term_context(
            session_id,
            query="key",
            limit=5
        )
        
        assert len(results) <= 5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
