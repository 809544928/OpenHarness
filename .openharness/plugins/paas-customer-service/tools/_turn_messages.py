from __future__ import annotations

from collections import defaultdict
from copy import deepcopy

_MESSAGES_BY_CONVERSATION: dict[str, list[dict[str, str]]] = defaultdict(list)


def record_assistant_message(conversation_id: str, content: str) -> None:
    if not conversation_id.strip() or not content.strip():
        return
    _MESSAGES_BY_CONVERSATION[conversation_id].append(
        {
            "role": "assistant",
            "content": content,
        }
    )


def consume_assistant_messages(conversation_id: str) -> list[dict[str, str]]:
    messages = deepcopy(_MESSAGES_BY_CONVERSATION.get(conversation_id, []))
    _MESSAGES_BY_CONVERSATION.pop(conversation_id, None)
    return messages
