"""Layout E: a plain filesystem, nothing else. Preferences AND operational data are
materialised as real markdown files, the way an "instinct"/Claude Code memory
directory works, and the agent gets the usual coding-agent trio of tools:

    /MEMORY.md                 index of what is where
    /preferences/<topic>.md    one file per preference topic (current user only)
    /data/<table>.md           the whole table as a markdown table
    /data/<table>/README.md    column list + description
    /data/<table>/<pk>.md      one file per row
    list_dir, read_file, grep  (grep = regex search over all files -> path:line)
"""
from __future__ import annotations

import os
import re
from pathlib import Path

from psycopg import sql

from ..core.backend import MemoryBackend
from ..core.db import CaseDB
from ..core.render import facts_to_markdown, row_to_markdown, rows_to_markdown
from ..core.types import EvalCase, Scenario, ToolSpec
from ._common import PATH_SCHEMA


class PlainFsBackend(MemoryBackend):
    name = "plain_fs"
    description = (
        "Everything is real markdown files on disk (MEMORY.md index, preferences/<topic>.md, data/<table>.md and "
        "data/<table>/<id>.md); no database. Tools: list_dir, read_file, grep."
    )

    def setup(self, scenario: Scenario, case: EvalCase, db: CaseDB, workdir: str) -> None:
        self.root = (Path(workdir) / "fs").resolve()
        (self.root / "preferences").mkdir(parents=True)
        by_cat: dict[str, list] = {}
        for f in case.facts:
            if f.user_id == case.user_id:
                by_cat.setdefault(f.category, []).append(f)
        index = ["# Memory index", "", "## Preferences (one file per topic)", ""]
        for cat, facts in sorted(by_cat.items()):
            (self.root / "preferences" / f"{cat}.md").write_text(facts_to_markdown(cat, facts))
            index.append(f"- preferences/{cat}.md ({len(facts)} notes)")
        index += ["", "## Data", ""]
        for t in scenario.tables:
            rows = db.query(sql.SQL("SELECT * FROM {} ORDER BY {}").format(sql.Identifier(t.name), sql.Identifier(t.primary_key)))  # includes generated keys
            d = self.root / "data" / t.name
            d.mkdir(parents=True)
            (self.root / "data" / f"{t.name}.md").write_text(f"# {t.name}\n\n{t.description}\n\n" + rows_to_markdown(rows) + "\n")
            (d / "README.md").write_text(f"# {t.name}\n\n{t.description}\n\nColumns: {t.columns_sql}\n\nOne file per row, named by {t.primary_key}; ../{t.name}.md has every row.\n")
            for r in rows:
                (d / f"{r[t.primary_key]}.md").write_text(row_to_markdown(t.name, r))
            index.append(f"- data/{t.name}.md : {t.description} ({len(rows)} rows; one file per row under data/{t.name}/)")
        (self.root / "MEMORY.md").write_text("\n".join(index) + "\n")

    def _resolve(self, rel: str) -> Path:
        p = (self.root / rel.lstrip("/")).resolve()
        if p != self.root and self.root not in p.parents:
            raise PermissionError("path escapes the memory directory")
        return p

    def tools(self) -> list[ToolSpec]:
        def list_dir(a):
            p = self._resolve(a.get("path", "/"))
            if not p.is_dir():
                return f"ERROR: no such directory {a.get('path')}"
            return "\n".join((n + "/" if (p / n).is_dir() else n) for n in sorted(os.listdir(p))) or "(empty)"

        def read_file(a):
            p = self._resolve(a["path"])
            return p.read_text() if p.is_file() else f"ERROR: no such file {a['path']}"

        def grep(a):
            try:
                rx = re.compile(a["pattern"], re.IGNORECASE)
            except re.error as e:
                return f"ERROR: bad regex: {e}"
            base = self._resolve(a.get("path", "/"))
            hits = []
            for f in sorted(base.rglob("*.md") if base.is_dir() else [base]):
                for i, line in enumerate(f.read_text().splitlines(), 1):
                    if rx.search(line):
                        hits.append(f"/{f.relative_to(self.root)}:{i}: {line.strip()[:200]}")
                        if len(hits) >= 100:
                            return "\n".join(hits) + "\n(truncated at 100 matches)"
            return "\n".join(hits) if hits else "(no matches)"

        return [
            ToolSpec("list_dir", "List entries in a directory. Root is '/'.", PATH_SCHEMA, list_dir),
            ToolSpec("read_file", "Read a file.", PATH_SCHEMA, read_file),
            ToolSpec("grep", "Case-insensitive regex search over markdown files under a path (default '/'); returns path:line: text.",
                     {"type": "object", "properties": {"pattern": {"type": "string"}, "path": {"type": "string"}}, "required": ["pattern"]}, grep),
        ]

    def layout_prompt(self) -> str:
        return (
            "Your memory and all data are plain markdown files in a directory. `/MEMORY.md` is the index; "
            "`/preferences/<topic>.md` hold the user's preferences; `/data/<table>.md` holds a whole table and "
            "`/data/<table>/<id>.md` one row. Tools: list_dir, read_file, grep."
        )
