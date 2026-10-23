"""Memory model registry. Add a new model by importing it and adding it here."""
from __future__ import annotations

from .base import MemoryModel, MemoryState
from .experience_fs import ExperienceFs
from .fs_prefs_plus_sql import FsPrefsPlusSql
from .plain_fs import PlainFs
from .shell_fs import ShellFs
from .sql_only import SqlOnly
from .virtual_fs import VirtualFs

REGISTRY: dict[str, type[MemoryModel]] = {m.name: m for m in [FsPrefsPlusSql, SqlOnly, VirtualFs, ExperienceFs, PlainFs, ShellFs]}


def make_memory_model(name: str, **options) -> MemoryModel:
    try:
        return REGISTRY[name](**options)
    except KeyError:
        raise KeyError(f"unknown memory model {name!r}; known: {sorted(REGISTRY)}") from None


__all__ = ["MemoryModel", "MemoryState", "REGISTRY", "make_memory_model"]
