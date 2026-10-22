"""System prompt assembly: shared text + the memory model's layout paragraph."""
from __future__ import annotations

from ..eval.types import Workload
from ..memory_model.base import MemoryModel

BASE = """You are an assistant acting for a principal. Your tools give you access to what is remembered about the principal (their profile, preferences and standing instructions) and to operational data. Look things up with the tools; never guess facts the tools can tell you. Be efficient: make the fewest tool calls that still let you answer correctly.

When you are done, call `submit_answer` exactly once with your final structured answer."""


def build_system_prompt(workload: Workload, memory_model: MemoryModel, user_id: str) -> str:
    return "\n\n".join(
        [
            BASE,
            f"The current principal's id is `{user_id}`. Only this principal's memory applies; never apply another principal's rules.",
            "## Task\n" + workload.task_prompt.strip(),
            "## How your memory and data are laid out\n" + memory_model.layout_prompt().strip(),
        ]
    )
