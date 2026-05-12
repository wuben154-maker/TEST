# Vendored DeepAgents - 100% Official Code

Source: https://github.com/langchain-ai/deepagents (main branch)

Downloaded: All backends, middleware, graph for full functional parity with official.

## Contents

### Backends
- `protocol.py` - BackendProtocol, FileInfo, GrepMatch, WriteResult, EditResult, etc.
- `utils.py` - format_read_response, perform_string_replacement, grep_matches_from_files, etc.
- `state.py` - StateBackend (ephemeral LangGraph state)
- `filesystem.py` - FilesystemBackend
- `composite.py` - CompositeBackend
- `store.py` - StoreBackend (LangGraph BaseStore)
- `local_shell.py` - LocalShellBackend
- `sandbox.py` - BaseSandbox

### Middleware
- `filesystem.py` - FilesystemMiddleware
- `memory.py` - MemoryMiddleware
- `subagents.py` - SubAgentMiddleware, SubAgent, CompiledSubAgent
- `summarization.py` - SummarizationMiddleware
- `skills.py` - SkillsMiddleware
- `patch_tool_calls.py` - PatchToolCallsMiddleware
- `_utils.py` - Internal utilities

### Graph
- `graph.py` - create_deep_agent

## Import Path

All imports use `app._vendor.deepagents` instead of `deepagents`.
