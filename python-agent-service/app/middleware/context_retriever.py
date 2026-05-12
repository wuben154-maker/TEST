"""Context Retriever - Context retrieval and management module.

This module provides the ContextRetriever class, which manages both short-term
and long-term memory for intent understanding.

Purpose:
    - Short-term memory: In-memory session history (current conversation)
    - Long-term memory: Persistent storage across sessions (using StoreBackend)
    - Context summarization: Generate concise context summaries for LLM processing
    - Fuzzy matching: Find relevant memories using text similarity (no vector DB required)
    - Conversation history: Retrieve and search historical conversations (P2 Enhancement)
    - Result merging: Combine multiple analysis results into single documents (P2 Enhancement)

Key Features:
    - Automatic entity extraction (IOCs, IPs, domains, hashes, filenames)
    - User preference detection (language, task types)
    - Access statistics tracking
    - Encrypted storage support for sensitive parameters
    - LangGraph checkpointing integration for persistent state

Usage:
    Used by TaskPlanner for context retrieval during CONTEXT task execution.
    Also used for saving user parameters (submit_parameters) and long-term memory.

Example:
    ```python
    from app.backends.store import InMemoryStore
    from app.middleware.context_retriever import ContextRetriever
    
    store = InMemoryStore()
    retriever = ContextRetriever(store_backend=store)
    
    # Get context summary (async version with long-term memory)
    summary = await retriever.get_context_summary(
        session_id="user123", 
        language="en",
        query="malware analysis",  # Optional query for relevance filtering
        include_long_term=True  # Enable long-term memory
    )
    
    # Save to long-term memory
    await retriever.save_to_long_term(
        session_id="user123",
        key="api_key_vt",
        value="secret-key",
        encrypted=True
    )
    ```
"""

import re
from datetime import datetime, timezone
from typing import Any

import structlog

from app.datetime_support import format_api_datetime, now_app, parse_timestamp_flexible

logger = structlog.get_logger()


class ContextRetriever:
    """Context retriever - combines short-term and long-term memory."""
    
    def __init__(self, store_backend: Any = None, state_backend: Any = None):
        self.store = store_backend
        self.state = state_backend
        self._session_history: dict[str, list[dict]] = {}
    
    def add_to_short_term(self, session_id: str, entry: dict):
        """Add entry to short-term memory."""
        if session_id not in self._session_history:
            self._session_history[session_id] = []
        self._session_history[session_id].append({
            **entry,
            "timestamp": format_api_datetime(now_app()),
        })
        # Keep recent N entries (read from config, default 20)
        limit = getattr(self, '_short_term_limit', 20)
        self._session_history[session_id] = self._session_history[session_id][-limit:]
    
    def get_short_term_context(self, session_id: str) -> list[dict]:
        """Get short-term memory."""
        return self._session_history.get(session_id, [])
    
    async def get_long_term_context(
        self, 
        session_id: str, 
        key: str = "",
        query: str = "",
        limit: int = 10
    ) -> list[dict]:
        """Get long-term memory, supports keyword and fuzzy matching.
        
        Args:
            session_id: Session ID
            key: Exact keyword match (high priority)
            query: Fuzzy query text (used when key is empty)
            limit: Maximum number of results to return
        
        Returns:
            List of matched memories
        """
        if not self.store:
            return []
        
        namespace = f"memories/{session_id}"
        results = []
        
        try:
            # 1. Exact keyword match (highest priority)
            if key:
                items = await self.store.search(key, namespace=namespace)
                results.extend([item.to_dict() for item in items])
                logger.debug("Exact key match", key=key, count=len(results))
            
            # 2. Fuzzy matching (when no exact match or need more results)
            if query and len(results) < limit and self._should_use_fuzzy_matching():
                fuzzy_results = await self._fuzzy_search(namespace, query, limit - len(results))
                results.extend(fuzzy_results)
                logger.debug("Fuzzy match", query=query, count=len(fuzzy_results))
            
            # 3. If neither key nor query provided, return recent records
            if not key and not query:
                all_keys = await self.store.list_keys(namespace=namespace)
                for item_key in all_keys[-limit:]:  # Get recent N entries
                    item = await self.store.get(item_key, namespace=namespace)
                    if item:
                        results.append(item.to_dict())
            
            return results[:limit]
        except Exception as e:
            logger.warning("Failed to retrieve long-term context", error=str(e))
            return []
    
    async def _fuzzy_search(
        self, 
        namespace: str, 
        query: str, 
        limit: int
    ) -> list[dict]:
        """Fuzzy search: text similarity-based matching.
        
        Uses simple text similarity algorithm (Jaccard similarity + containment matching),
        no vector embeddings or large models required.
        """
        if not query:
            return []
        
        query_lower = query.lower()
        query_words = set(query_lower.split())
        
        # Get all keys
        all_keys = await self.store.list_keys(namespace=namespace)
        
        # Calculate similarity and sort
        scored_items = []
        for item_key in all_keys:
            item = await self.store.get(item_key, namespace=namespace)
            if not item:
                continue
            
            # Calculate similarity
            similarity = self._calculate_similarity(query_lower, query_words, item_key, item.value)
            
            # Use configured minimum similarity threshold
            min_similarity = self._get_min_similarity_threshold()
            if similarity >= min_similarity:
                scored_items.append((similarity, item.to_dict()))
        
        # Sort by similarity descending
        scored_items.sort(key=lambda x: x[0], reverse=True)
        
        # Return top limit results
        return [item for _, item in scored_items[:limit]]
    
    def _calculate_similarity(
        self, 
        query_lower: str, 
        query_words: set, 
        key: str, 
        value: Any
    ) -> float:
        """Calculate similarity between query text and memory item.
        
        Uses multiple strategies:
        1. Keyword containment matching (high weight)
        2. Jaccard similarity (word set overlap)
        3. Value content matching (if value is string)
        
        Returns:
            Similarity score (0.0 - 1.0)
        """
        key_lower = key.lower()
        key_words = set(key_lower.split())
        
        # Strategy 1: Exact containment matching (highest weight)
        if query_lower in key_lower or key_lower in query_lower:
            return 1.0
        
        # Strategy 2: Keyword containment matching
        if query_words.issubset(key_words) or key_words.issubset(query_words):
            return 0.9
        
        # Strategy 3: Jaccard similarity (word set overlap)
        intersection = query_words & key_words
        union = query_words | key_words
        jaccard_score = len(intersection) / len(union) if union else 0.0
        
        # Strategy 4: Value content matching (if value is string)
        value_score = 0.0
        if isinstance(value, str):
            value_lower = value.lower()
            value_words = set(value_lower.split())
            
            # Check if query words are in value
            if query_lower in value_lower:
                value_score = 0.8
            elif query_words & value_words:  # Has intersection
                value_intersection = query_words & value_words
                value_score = len(value_intersection) / len(query_words)
        
        # Combined score: take highest score, but consider multiple strategy overlap
        max_score = max(jaccard_score, value_score)
        
        # If there's partial match, give some score
        if intersection:
            partial_score = len(intersection) / len(query_words) * 0.6
            max_score = max(max_score, partial_score)
        
        return min(max_score, 1.0)
    
    def _should_use_fuzzy_matching(self) -> bool:
        """Check if fuzzy matching is enabled (read from config)."""
        try:
            from app.config.intent_config import get_config
            config = get_config()
            return config.context.fuzzy_matching.enabled
        except Exception:
            return True  # Default enabled
    
    def _get_min_similarity_threshold(self) -> float:
        """Get minimum similarity threshold (read from config)."""
        try:
            from app.config.intent_config import get_config
            config = get_config()
            return config.context.fuzzy_matching.min_similarity
        except Exception:
            return 0.3  # Default threshold
    
    async def _update_access_stats(self, item: Any, namespace: str, key: str):
        """Update access statistics (async, non-blocking main flow)."""
        try:
            if not self.store:
                return
            
            # Update access statistics in metadata
            metadata = item.metadata or {}
            access_count = metadata.get("access_count", 0) + 1
            metadata["access_count"] = access_count
            
            if not metadata.get("first_accessed_at"):
                from datetime import datetime, timezone
                metadata["first_accessed_at"] = format_api_datetime(now_app())
            
            metadata["last_accessed_at"] = format_api_datetime(now_app())
            
            # Update storage (keep original value)
            await self.store.set(key, item.value, namespace=namespace, metadata=metadata)
        except Exception as e:
            # Silent failure, don't affect main flow
            logger.debug("Failed to update access stats", error=str(e))
    
    async def save_to_long_term(
        self, 
        session_id: str, 
        key: str, 
        value: Any, 
        encrypted: bool = False,
        metadata: dict | None = None
    ):
        """Save to long-term memory.
        
        Args:
            session_id: Session ID
            key: Memory key
            value: Memory value
            encrypted: Whether to encrypt storage
            metadata: Optional metadata (e.g., access statistics, tags, etc.)
        """
        if not self.store:
            return
        
        namespace = f"parameters/{session_id}" if encrypted else f"memories/{session_id}"
        
        # Merge metadata
        final_metadata = metadata or {}
        if not encrypted:
            # For memories, add access statistics fields
            final_metadata.setdefault("access_count", 0)
            final_metadata.setdefault("first_accessed_at", None)
        
        try:
            await self.store.set(key, value, namespace=namespace, metadata=final_metadata)
        except Exception as e:
            logger.warning("Failed to save to long-term memory", error=str(e))
    
    async def get_context_summary(
        self, 
        session_id: str, 
        language: str = "en",
        query: str = "",
        include_long_term: bool = True
    ) -> str:
        """Get enhanced context summary for LLM processing (Stage 1 Enhanced).
        
        Extracts:
        - Key entities (IOCs, filenames, etc.) - up to 20 entities
        - Analyzed file list - up to 10 files
        - User preferences (language, output format, etc.)
        - Recent interaction history - up to 10 summaries, 200 chars each
        - Long-term memory (if enabled) - relevant historical context
        
        Args:
            session_id: Session ID
            language: Language code (en/zh/ja/ko), default is English
            query: Optional query text for relevance filtering of long-term memory
            include_long_term: Whether to include long-term memory (default: True)
        
        Returns:
            Enhanced context summary string
        """
        # Load configuration
        try:
            from app.config.intent_config import get_config
            config = get_config()
            summary_config = config.context.summary
        except Exception:
            # Fallback to defaults if config not available
            summary_config = type('Config', (), {
                'max_entities': 20,
                'max_files': 10,
                'max_summaries': 10,
                'summary_length': 200,
                'include_long_term': True,
                'long_term_limit': 10,
                'fallback_summary_length': 250,
            })()
        
        # Use unified language file system
        from app.parsers.labels import get_intent_label

        # Get multi-language labels
        templates = {
            "no_history": get_intent_label("context_no_history", language),
            "key_entities": get_intent_label("context_key_entities", language),
            "analyzed_files": get_intent_label("context_analyzed_files", language),
            "user_preferences": get_intent_label("context_user_preferences", language),
            "recent_interactions": get_intent_label("context_recent_interactions", language),
            "conversation_history": get_intent_label("context_conversation_history", language),
            "user": get_intent_label("context_user_label", language),
        }
        
        # Get short-term memory
        short_term_history = self.get_short_term_context(session_id)
        
        # Get long-term memory if enabled (Stage 1 Enhancement)
        long_term_history = []
        if include_long_term and summary_config.include_long_term and self.store:
            try:
                long_term_items = await self.get_long_term_context(
                    session_id=session_id,
                    query=query,  # Use query for relevance filtering
                    limit=summary_config.long_term_limit
                )
                # Convert long-term items to history format
                long_term_history = [
                    {
                        "type": "long_term_memory",
                        "summary": item.get("value", ""),
                        "key": item.get("key", ""),
                        "timestamp": item.get("created_at"),
                        "metadata": item.get("metadata", {}),
                    }
                    for item in long_term_items
                ]
            except Exception as e:
                logger.debug("Failed to retrieve long-term memory", error=str(e))
        
        # Merge short-term and long-term history
        combined_history = short_term_history + long_term_history
        
        if not combined_history:
            return templates["no_history"]
        
        # Extract key information with increased limits (Stage 1 Enhancement)
        entities = self._extract_entities(combined_history, max_entities=summary_config.max_entities)
        files = self._extract_files(combined_history, max_files=summary_config.max_files)
        preferences = self._extract_preferences(combined_history, language)
        recent_summaries = self._extract_recent_summaries(
            combined_history, 
            language, 
            limit=summary_config.max_summaries,
            summary_length=summary_config.summary_length
        )
        
        # Build enhanced summary
        parts = []
        
        if entities:
            parts.append(f"{templates['key_entities']}: {', '.join(entities[:summary_config.max_entities])}")
        
        if files:
            parts.append(f"{templates['analyzed_files']}: {', '.join(files[:summary_config.max_files])}")
        
        if preferences:
            parts.append(f"{templates['user_preferences']}: {preferences}")
        
        if recent_summaries:
            parts.append(f"{templates['recent_interactions']}:")
            parts.extend(recent_summaries)
        
        # Fallback: if no structured summary, use full history with increased length
        if not parts:
            fallback_summaries = [
                f"- {entry.get('type', 'unknown')}: {entry.get('summary', '')[:summary_config.fallback_summary_length]}"
                for entry in combined_history[-summary_config.max_summaries:]
            ]
            return f"{templates['conversation_history']}:\n" + "\n".join(fallback_summaries)
        
        return "\n".join(parts)
    
    def get_context_summary_sync(self, session_id: str, language: str = "en") -> str:
        """Synchronous wrapper for get_context_summary (for backward compatibility).
        
        Note: This method does not include long-term memory. Use async version for full features.
        """
        import asyncio
        try:
            loop = asyncio.get_running_loop()
            if loop.is_running():
                return self._get_context_summary_sync_only(session_id, language)
        except RuntimeError:
            pass
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                return self._get_context_summary_sync_only(session_id, language)
            return loop.run_until_complete(
                self.get_context_summary(session_id, language, include_long_term=False)
            )
        except (RuntimeError, Exception):
            return asyncio.run(
                self.get_context_summary(session_id, language, include_long_term=False)
            )
    
    def _get_context_summary_sync_only(self, session_id: str, language: str = "en") -> str:
        """Synchronous-only version without long-term memory (fallback)."""
        # Load configuration
        try:
            from app.config.intent_config import get_config
            config = get_config()
            summary_config = config.context.summary
        except Exception:
            summary_config = type('Config', (), {
                'max_entities': 20,
                'max_files': 10,
                'max_summaries': 10,
                'summary_length': 200,
                'fallback_summary_length': 250,
            })()
        
        from app.parsers.labels import get_intent_label
        
        templates = {
            "no_history": get_intent_label("context_no_history", language),
            "key_entities": get_intent_label("context_key_entities", language),
            "analyzed_files": get_intent_label("context_analyzed_files", language),
            "user_preferences": get_intent_label("context_user_preferences", language),
            "recent_interactions": get_intent_label("context_recent_interactions", language),
            "conversation_history": get_intent_label("context_conversation_history", language),
            "user": get_intent_label("context_user_label", language),
        }
        
        history = self.get_short_term_context(session_id)
        if not history:
            return templates["no_history"]
        
        entities = self._extract_entities(history, max_entities=summary_config.max_entities)
        files = self._extract_files(history, max_files=summary_config.max_files)
        preferences = self._extract_preferences(history, language)
        recent_summaries = self._extract_recent_summaries(
            history, 
            language, 
            limit=summary_config.max_summaries,
            summary_length=summary_config.summary_length
        )
        
        parts = []
        if entities:
            parts.append(f"{templates['key_entities']}: {', '.join(entities[:summary_config.max_entities])}")
        if files:
            parts.append(f"{templates['analyzed_files']}: {', '.join(files[:summary_config.max_files])}")
        if preferences:
            parts.append(f"{templates['user_preferences']}: {preferences}")
        if recent_summaries:
            parts.append(f"{templates['recent_interactions']}:")
            parts.extend(recent_summaries)
        
        if not parts:
            fallback_summaries = [
                f"- {entry.get('type', 'unknown')}: {entry.get('summary', '')[:summary_config.fallback_summary_length]}"
                for entry in history[-summary_config.max_summaries:]
            ]
            return f"{templates['conversation_history']}:\n" + "\n".join(fallback_summaries)
        
        return "\n".join(parts)
    
    async def get_conversation_history(
        self,
        session_id: str,
        limit: int = 50,
        since: datetime | None = None
    ) -> list[dict]:
        """Get full conversation history (P2 Enhancement).
        
        Args:
            session_id: Session ID
            limit: Maximum number of entries to return
            since: Only return entries after this timestamp
        
        Returns:
            List of conversation entries with metadata
        """
        # Try to get from checkpointer first (if available)
        if hasattr(self, '_checkpointer') and self._checkpointer:
            try:
                from langgraph.checkpoint.postgres import PostgresSaver
                if isinstance(self._checkpointer, PostgresSaver):
                    # Query checkpoints for this thread
                    config = {"configurable": {"thread_id": session_id}}
                    checkpoints = await self._checkpointer.list(config=config)
                    
                    # Convert checkpoints to conversation entries
                    history = []
                    for cp in checkpoints[-limit:]:  # Get most recent
                        cp_data = cp.get("checkpoint", {})
                        messages = cp_data.get("channel_values", {}).get("messages", [])
                        
                        for msg in messages:
                            entry = {
                                "type": "message",
                                "role": msg.get("type", "unknown"),
                                "content": msg.get("content", ""),
                                "timestamp": cp.get("metadata", {}).get("created_at"),
                                "checkpoint_id": cp.get("checkpoint_id"),
                            }
                            if since is None or (
                                entry["timestamp"]
                                and parse_timestamp_flexible(entry["timestamp"]) > since
                            ):
                                history.append(entry)
                    
                    if history:
                        return history[-limit:]
            except Exception as e:
                logger.debug("Could not get history from checkpointer", error=str(e))
        
        # Fallback to short-term memory
        history = self.get_short_term_context(session_id)
        
        if since:
            filtered = []
            for entry in history:
                entry_time = entry.get("timestamp")
                if entry_time:
                    try:
                        if isinstance(entry_time, str):
                            entry_dt = parse_timestamp_flexible(entry_time)
                        else:
                            entry_dt = entry_time
                        if entry_dt > since:
                            filtered.append(entry)
                    except Exception:
                        filtered.append(entry)  # Include if parsing fails
                else:
                    filtered.append(entry)
            history = filtered
        
        return history[-limit:]
    
    async def search_conversations(
        self,
        session_id: str,
        query: str,
        limit: int = 10
    ) -> list[dict]:
        """Search conversations by content (P2 Enhancement).
        
        Args:
            session_id: Session ID
            query: Search query text
            limit: Maximum number of results
        
        Returns:
            List of matching conversation entries
        """
        # Get conversation history
        history = await self.get_conversation_history(session_id, limit=100)
        
        if not query:
            return history[:limit]
        
        query_lower = query.lower()
        query_words = set(query_lower.split())
        
        # Score and filter entries
        scored_entries = []
        for entry in history:
            # Extract searchable text
            searchable_text = ""
            if entry.get("summary"):
                searchable_text += entry["summary"] + " "
            if entry.get("text"):
                searchable_text += entry["text"] + " "
            if entry.get("content"):
                searchable_text += entry["content"] + " "
            
            if not searchable_text:
                continue
            
            # Calculate similarity
            text_lower = searchable_text.lower()
            text_words = set(text_lower.split())
            
            # Simple scoring
            if query_lower in text_lower:
                score = 1.0
            elif query_words.issubset(text_words) or text_words.issubset(query_words):
                score = 0.9
            else:
                intersection = query_words & text_words
                if intersection:
                    score = len(intersection) / len(query_words)
                else:
                    continue  # No match
            
            scored_entries.append((score, entry))
        
        # Sort by score and return top results
        scored_entries.sort(key=lambda x: x[0], reverse=True)
        return [entry for _, entry in scored_entries[:limit]]
    
    async def get_analysis_results(
        self,
        session_id: str,
        analysis_ids: list[str] | None = None
    ) -> list[dict]:
        """Get specific analysis results (P2 Enhancement).
        
        Args:
            session_id: Session ID
            analysis_ids: Optional list of specific analysis IDs to retrieve
        
        Returns:
            List of analysis result entries
        """
        history = await self.get_conversation_history(session_id, limit=100)
        
        # Filter for analysis results
        results = []
        for entry in history:
            entry_type = entry.get("type", "")
            entry_id = entry.get("id", "")
            
            # Check if this is an analysis result
            if entry_type in ["intent_result", "analysis", "conclusion"]:
                if analysis_ids is None or entry_id in analysis_ids:
                    results.append({
                        "id": entry_id,
                        "type": entry_type,
                        "summary": entry.get("summary", ""),
                        "content": entry.get("content", ""),
                        "timestamp": entry.get("timestamp"),
                        "metadata": {
                            "category": entry.get("category"),
                            "input_type": entry.get("input_type"),
                            "confidence": entry.get("confidence"),
                        }
                    })
        
        return results
    
    async def merge_analysis_results(
        self,
        session_id: str,
        result_ids: list[str],
        language: str = "en"
    ) -> str:
        """Merge multiple analysis results into single document (P2 Enhancement).
        
        Args:
            session_id: Session ID
            result_ids: List of analysis result IDs to merge
            language: Output language
        
        Returns:
            Merged document as string
        """
        results = await self.get_analysis_results(session_id, analysis_ids=result_ids)
        
        if not results:
            from app.parsers.labels import get_intent_label
            return get_intent_label("context_no_results", language)
        
        # Use unified language file system
        from app.parsers.labels import get_intent_label
        
        templates = {
            "title": get_intent_label("merge_report_title", language),
            "summary": get_intent_label("merge_report_summary", language),
            "section": get_intent_label("merge_report_section", language),
        }
        
        # Build merged document
        parts = [f"# {templates['title']}\n"]
        parts.append(f"\n{templates['summary']}: {len(results)} analysis result(s)\n")
        
        for idx, result in enumerate(results, 1):
            parts.append(f"\n## {templates['section']} {idx}")
            parts.append(f"\n**ID**: {result['id']}")
            parts.append(f"\n**Type**: {result['type']}")
            parts.append(f"\n**Timestamp**: {result.get('timestamp', 'N/A')}")
            
            if result.get("summary"):
                parts.append(f"\n**Summary**: {result['summary']}")
            
            if result.get("content"):
                parts.append(f"\n**Content**:\n{result['content']}")
            
            if result.get("metadata"):
                metadata = result["metadata"]
                if metadata.get("category"):
                    parts.append(f"\n**Category**: {metadata['category']}")
                if metadata.get("confidence"):
                    parts.append(f"\n**Confidence**: {metadata['confidence']}")
            
            parts.append("\n---\n")
        
        return "\n".join(parts)

    async def get_history_facts(
        self,
        session_id: str,
        query: str,
        limit: int = 5,
    ) -> list[dict]:
        """Extract structured history facts for subagent payload injection."""
        candidates = await self.search_conversations(session_id=session_id, query=query, limit=max(limit * 3, 10))
        facts: list[dict] = []
        seen: set[str] = set()
        for entry in candidates:
            source_id = str(entry.get("id") or entry.get("checkpoint_id") or entry.get("timestamp") or "")
            if not source_id:
                source_id = f"hist-{len(facts) + 1}"
            if source_id in seen:
                continue
            seen.add(source_id)
            summary = str(entry.get("summary") or entry.get("content") or entry.get("text") or "").strip()
            if not summary:
                continue
            summary = summary[:300]
            facts.append(
                {
                    "sourceId": source_id,
                    "artifactType": self._infer_artifact_type(entry),
                    "summary": summary,
                    "entities": self._extract_entities([entry], max_entities=8),
                    "confidence": self._extract_confidence(entry),
                    "timeRange": entry.get("timestamp"),
                    "trust": "untrusted_text",
                }
            )
            if len(facts) >= limit:
                break
        return facts

    def _infer_artifact_type(self, entry: dict) -> str:
        """Infer artifact type from history entry metadata."""
        input_type = str(entry.get("input_type") or entry.get("metadata", {}).get("input_type") or "").lower()
        category = str(entry.get("category") or entry.get("metadata", {}).get("category") or "").lower()
        text = " ".join(
            [
                str(entry.get("summary") or ""),
                str(entry.get("content") or ""),
                str(entry.get("text") or ""),
            ]
        ).lower()
        if input_type in {"email", "binary", "code", "log", "document", "image"}:
            return input_type
        if "email" in text:
            return "email"
        if "binary" in text or "malware" in text:
            return "binary"
        if "web" in text or "url" in text:
            return "web"
        if category:
            return category
        return "generic"

    def _extract_confidence(self, entry: dict) -> float:
        """Extract numeric confidence from entry metadata."""
        raw = entry.get("confidence")
        if raw is None:
            raw = entry.get("metadata", {}).get("confidence")
        try:
            if raw is None:
                return 0.0
            value = float(raw)
            if value < 0:
                return 0.0
            if value > 1:
                return min(value / 100.0, 1.0)
            return value
        except Exception:
            return 0.0
    
    def _extract_entities(self, history: list[dict], max_entities: int = 20) -> list[str]:
        """Extract key entities (IOCs, IPs, domains, hashes, etc.).
        
        Args:
            history: History records
            max_entities: Maximum number of entities to return (Stage 1: increased from 10 to 20)
        """
        entities = set()
        
        for entry in history:
            # Extract entities from summary
            summary = entry.get("summary", "")
            text = entry.get("text", "")
            combined = f"{summary} {text}"
            
            # Extract IP addresses (increased limits)
            ip_pattern = r'\b(?:\d{1,3}\.){3}\d{1,3}\b'
            ips = re.findall(ip_pattern, combined)
            entities.update(ips[:10])  # Increased from 5 to 10 IPs
            
            # Extract domains (increased limits)
            domain_pattern = r'\b(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}\b'
            domains = re.findall(domain_pattern, combined)
            entities.update(domains[:10])  # Increased from 5 to 10 domains
            
            # Extract hash values (MD5/SHA256) (increased limits)
            hash_pattern = r'\b[a-fA-F0-9]{32,64}\b'
            hashes = re.findall(hash_pattern, combined)
            entities.update(hashes[:5])  # Increased from 3 to 5 hashes
            
            # Extract filenames (increased limits)
            file_pattern = r'\b[\w\-\.]+\.(exe|dll|pdf|docx?|xlsx?|zip|rar|7z|pcap|elf)\b'
            files = re.findall(file_pattern, combined, re.IGNORECASE)
            entities.update([f[0] for f in files[:10]])  # Increased from 5 to 10 filenames
        
        return list(entities)[:max_entities]
    
    def _extract_files(self, history: list[dict], max_files: int = 10) -> list[str]:
        """Extract list of analyzed files.
        
        Args:
            history: History records
            max_files: Maximum number of files to return (Stage 1: increased from 5 to 10)
        """
        files = set()
        
        for entry in history:
            # Extract from file list
            if "files" in entry:
                file_list = entry["files"]
                if isinstance(file_list, list):
                    for f in file_list:
                        if isinstance(f, dict):
                            files.add(f.get("filename", ""))
                        elif isinstance(f, str):
                            files.add(f)
            
            # Extract filenames from text
            text = entry.get("text", "") + entry.get("summary", "")
            file_pattern = r'\b[\w\-\.]+\.(exe|dll|pdf|docx?|xlsx?|zip|rar|7z|pcap|elf|txt|log|md)\b'
            found_files = re.findall(file_pattern, text, re.IGNORECASE)
            files.update([f[0] for f in found_files])
        
        return list(files)[:max_files]
    
    def _extract_preferences(self, history: list[dict], language: str = "en") -> str:
        """Extract user preferences (language, output format, etc.).
        
        Args:
            history: History records
            language: Language code
        """
        # Use unified language file system
        from app.parsers.labels import get_intent_label
        
        labels = {
            "language": get_intent_label("context_language_label", language),
            "common_task_type": get_intent_label("context_common_task_type", language),
        }
        preferences = []
        
        # Detect language preference (from history records)
        languages = {}
        for entry in history:
            lang = entry.get("language", "")
            if lang:
                languages[lang] = languages.get(lang, 0) + 1
        
        if languages:
            preferred_lang = max(languages.items(), key=lambda x: x[1])[0]
            preferences.append(f"{labels['language']}: {preferred_lang}")
        
        # Detect task type preference
        task_types = {}
        for entry in history:
            category = entry.get("category", "")
            if category:
                task_types[category] = task_types.get(category, 0) + 1
        
        if task_types:
            preferred_task = max(task_types.items(), key=lambda x: x[1])[0]
            preferences.append(f"{labels['common_task_type']}: {preferred_task}")
        
        return ", ".join(preferences) if preferences else ""
    
    def _extract_recent_summaries(
        self, 
        history: list[dict], 
        language: str = "en", 
        limit: int = 10,
        summary_length: int = 200
    ) -> list[str]:
        """Extract recent interaction summaries.
        
        Args:
            history: History records
            language: Language code
            limit: Maximum number of results to return (Stage 1: increased from 5 to 10)
            summary_length: Maximum length per summary (Stage 1: increased from 80 to 200)
        """
        # Use unified language file system
        from app.parsers.labels import get_intent_label
        
        labels = {
            "user": get_intent_label("context_user_label", language),
        }
        summaries = []
        
        for entry in history[-limit:]:
            entry_type = entry.get("type", "unknown")
            summary = entry.get("summary", "")
            category = entry.get("category", "")
            
            # Truncate summary to specified length
            truncated_summary = summary[:summary_length] if summary else ""
            
            if entry_type == "user_input":
                summaries.append(f"  - {labels['user']}: {truncated_summary}")
            elif entry_type == "intent_result":
                summaries.append(f"  - [{category}] {truncated_summary}")
            elif entry_type == "long_term_memory":
                # Format long-term memory entries
                key = entry.get("key", "")
                summaries.append(f"  - [历史] {key}: {truncated_summary}")
        
        return summaries
