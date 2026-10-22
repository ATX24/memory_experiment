"""System prompt assembly. Shared by all backends except the layout paragraph."""
from __future__ import annotations

from .backend import MemoryBackend
from .types import Scenario

BASE = """You are an assistant completing a task for a user. Your tools give you access to the user's stored memory (preferences and facts about them) and to live operational data. Look things up with the tools; never guess facts the tools can tell you. Be efficient: make the fewest tool calls that still let you answer correctly.

When you are done, call `submit_answer` exactly once with your final structured answer."""


def build_system_prompt(scenario: Scenario, backend: MemoryBackend, user_id: str) -> str:
    return "\n\n".join(
        [
            BASE,
            f"The current user's id is `{user_id}`. Only this user's memory is relevant.",
            "## Task\n" + scenario.task_prompt.strip(),
            "## How your memory and data are laid out\n" + backend.layout_prompt().strip(),
        ]
    )
