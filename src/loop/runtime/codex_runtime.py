"""Codex/ChatGPT Work adapter exported from the runtime layer."""

from ..agents.conversation import ConversationAgentRuntime


class CodexConversationRuntime(ConversationAgentRuntime):
    """Queue tasks for the active Codex/Work conversation without API assumptions."""

    name = "codex-conversation"


__all__ = ["CodexConversationRuntime"]
