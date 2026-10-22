from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from .types import Scenario


def load_scenario(path: str | Path) -> Scenario:
    """Load `scenario.py` from a directory; it must define `SCENARIO: Scenario`."""
    p = Path(path)
    file = p / "scenario.py" if p.is_dir() else p
    spec = importlib.util.spec_from_file_location(f"scenario_{file.parent.name}", file)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    sc = mod.SCENARIO
    if not isinstance(sc, Scenario):
        raise TypeError("SCENARIO must be a memory_experiment.core.types.Scenario")
    return sc
