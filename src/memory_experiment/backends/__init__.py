"""Backend registry. Add a new layout by importing it and adding it here."""
from __future__ import annotations

from ..core.backend import MemoryBackend
from .experience_fs import ExperienceFsBackend
from .fs_prefs_plus_sql import FsPrefsPlusSqlBackend
from .sql_only import SqlOnlyBackend
from .virtual_fs import VirtualFsBackend

REGISTRY: dict[str, type[MemoryBackend]] = {
    FsPrefsPlusSqlBackend.name: FsPrefsPlusSqlBackend,
    SqlOnlyBackend.name: SqlOnlyBackend,
    VirtualFsBackend.name: VirtualFsBackend,
    ExperienceFsBackend.name: ExperienceFsBackend,
}


def make_backend(name: str, **options) -> MemoryBackend:
    try:
        return REGISTRY[name](**options)
    except KeyError:
        raise KeyError(f"unknown backend {name!r}; known: {sorted(REGISTRY)}") from None
