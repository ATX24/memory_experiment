from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from .types import Workload


def load_workload(path: str | Path) -> Workload:
    """Load `workload.py` from a directory; it must define `WORKLOAD: Workload`.
    Workload directories live outside the repo (private/) or in workloads/ for examples."""
    p = Path(path)
    file = p / "workload.py" if p.is_dir() else p
    spec = importlib.util.spec_from_file_location(f"workload_{file.parent.name}", file)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    wl = mod.WORKLOAD
    if not isinstance(wl, Workload):
        raise TypeError("WORKLOAD must be a memory_experiment.eval.types.Workload")
    return wl
