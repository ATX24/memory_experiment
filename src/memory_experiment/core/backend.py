from __future__ import annotations

import abc
from typing import Any

from .db import CaseDB
from .types import EvalCase, Scenario, ToolSpec


class MemoryBackend(abc.ABC):
    """A memory layout.

    A backend receives the scenario + the case's data (rows + facts) and
    exposes it to the agent through tools. To add a new layout:

        1. subclass MemoryBackend in backends/<name>.py
        2. implement name/description/setup/tools/layout_prompt
        3. register it in backends/__init__.py REGISTRY

    `setup` runs once per run with fresh, isolated storage (the operational
    tables are already created and filled); `tools` returns what the agent may
    call; `layout_prompt` is the ONLY backend-specific text the model sees.
    """

    name: str = "base"
    description: str = ""

    def __init__(self, **options: Any):
        self.options = options

    @abc.abstractmethod
    def setup(self, scenario: Scenario, case: EvalCase, db: CaseDB, workdir: str) -> None: ...

    @abc.abstractmethod
    def tools(self) -> list[ToolSpec]: ...

    @abc.abstractmethod
    def layout_prompt(self) -> str: ...

    def teardown(self) -> None:  # noqa: B027
        return None

    def spec(self) -> dict[str, Any]:
        return {"name": self.name, "description": self.description, "options": self.options}
