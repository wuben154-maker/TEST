"""DeepAgents middleware - Official + Extension layer.

Official middleware (from deepagents / langchain.agents):
- TodoListMiddleware, FilesystemMiddleware, SubAgentMiddleware, SummarizationMiddleware
  are built into create_deep_agent and used internally.

Extension layer (our business logic):
- TaskPlanner, context_task_runner: Task planning and CONTEXT execution
- SkillEvent: Event format for subagent stream adapter
"""

from app._vendor.deepagents import FilesystemMiddleware, SubAgentMiddleware
from app._vendor.deepagents.middleware.subagents import (CompiledSubAgent,
                                                         SubAgent)
from app._vendor.deepagents.middleware.summarization import \
    SummarizationMiddleware
from app.middleware.context_retriever import ContextRetriever
from app.middleware.file_parser import FileParser
from app.middleware.intent_models import (InputType, IntentDecision,
                                          IntentResult, ParameterRequest,
                                          SecuritySubType, TaskCategory)
from app.middleware.skill_events import SkillEvent

__all__ = [
    # Official (re-exported)
    "FilesystemMiddleware",
    "SubAgentMiddleware",
    "SummarizationMiddleware",
    "SubAgent",
    "CompiledSubAgent",
    "SkillEvent",
    # Extension layer
    "FileParser",
    "ContextRetriever",
    "IntentResult",
    "ParameterRequest",
    "TaskCategory",
    "IntentDecision",
    "InputType",
    "SecuritySubType",
]
