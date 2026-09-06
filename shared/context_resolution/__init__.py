"""ScholarFlow Context Resolution Layer.

Deterministic, multi-layer context resolution engine for Stage 0 research gates.
Extracts known parameters from conversation history, attachments, upstream outputs,
and on-demand project search to eliminate redundant questioning.
"""

from .context_resolver import (
    SOURCE_LAYER_PRIORITY,
    AttachmentContextProvider,
    ContextFact,
    ContextProvider,
    ContextResolver,
    ContextScope,
    ConversationContextProvider,
    FactType,
    FactVolatility,
    ProjectSearchContextProvider,
    ResolvedVariable,
    UpstreamArtifactContextProvider,
    VariableStatus,
)

__all__ = [
    "ContextResolver",
    "ContextProvider",
    "ContextFact",
    "ResolvedVariable",
    "ContextScope",
    "VariableStatus",
    "FactVolatility",
    "FactType",
    "SOURCE_LAYER_PRIORITY",
    "ConversationContextProvider",
    "AttachmentContextProvider",
    "UpstreamArtifactContextProvider",
    "ProjectSearchContextProvider",
]
