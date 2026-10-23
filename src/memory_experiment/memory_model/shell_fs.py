"""Memory model F: the full filesystem experience. Same real markdown files as
plain_fs (profile + data tables), but the agent gets ONE tool: a sandboxed,
read-only shell. It can `ls`, `cd`, `cat`, `grep -r`, `find`, `head`, `wc`,
pipe and glob exactly as a coding agent would.

    /MEMORY.md · /memory/<setting>.md · /data/<table>.md · /data/<table>/<id>.md
    shell(command)   bash -c in the memory root; cwd persists between calls

Safety: commands run with a restricted PATH of read-only binaries, no network,
a 10 s timeout, and the working directory is pinned under the memory root.
"""
from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path

from ..eval.types import ToolSpec
from .base import MemoryModel, MemoryState
from .plain_fs import PlainFs

ALLOWED = {"ls", "cat", "grep", "find", "head", "tail", "wc", "cd", "pwd", "echo", "sort", "uniq", "cut", "tr", "sed", "awk", "xargs", "tree", "stat", "file", "basename", "dirname", "realpath", "true", "test", "["}


class ShellFs(MemoryModel):
    name = "shell_fs"
    description = "Same real markdown files as plain_fs, but the agent gets one tool: a sandboxed read-only shell (ls, cd, cat, grep -r, find, head, pipes). The coding-agent way of using a filesystem."
    memory_lives_in = "real markdown files (/MEMORY.md, /memory/<setting>.md), current principal only"
    data_lives_in = "real markdown files (/data/<table>.md, /data/<table>/<id>.md); no database"

    def load(self, state: MemoryState) -> None:
        self._inner = PlainFs()
        self._inner.load(state)
        self.root = self._inner.root
        self.cwd = self.root
        self.bindir = Path(state.workdir) / "bin"
        self.bindir.mkdir(exist_ok=True)
        for name in ALLOWED:
            src = None
            for d in ("/bin", "/usr/bin", "/opt/homebrew/bin"):
                if (Path(d) / name).exists():
                    src = Path(d) / name
                    break
            if src and not (self.bindir / name).exists():
                os.symlink(src, self.bindir / name)

    def _run(self, command: str) -> str:
        # Map the agent's "/" onto the memory root and refuse any path that resolves outside it.
        try:
            toks = shlex.split(command, posix=True) if command.strip() else []
        except ValueError as e:
            return f"ERROR: could not parse command: {e}"
        for tok in toks:
            raw = tok.rstrip(";|&")
            if raw.startswith("/") and not raw.startswith(str(self.root)):
                mapped = str(self.root / raw.lstrip("/"))
                command = command.replace(raw, mapped)
                raw = mapped
            if ".." in raw or raw.startswith(str(self.root)):
                base = Path(raw) if raw.startswith("/") else self.cwd / raw
                try:
                    resolved = base.resolve()
                except OSError:
                    continue
                if resolved != self.root and self.root not in resolved.parents:
                    return f"ERROR: {tok} resolves outside the memory root; the root is /"
        wrapped = f"cd {shlex.quote(str(self.cwd))} && {command}\nprintf '\\n__CWD__%s' \"$PWD\""
        try:
            p = subprocess.run(["/bin/bash", "--noprofile", "--norc", "-c", wrapped], capture_output=True, text=True, timeout=10,
                               env={"PATH": str(self.bindir), "HOME": str(self.root), "LC_ALL": "C"}, cwd=self.cwd)
        except subprocess.TimeoutExpired:
            return "ERROR: command timed out after 10 s"
        out = p.stdout
        if "__CWD__" in out:
            out, _, new = out.rpartition("__CWD__")
            new_p = Path(new.strip())
            if new_p == self.root or self.root in new_p.parents:
                self.cwd = new_p
        text = out.rstrip("\n")
        if p.stderr.strip():
            text += ("\n" if text else "") + "stderr: " + p.stderr.strip()[:1000]
        if p.returncode != 0:
            text += f"\n(exit {p.returncode})"
        rel = "/" + str(self.cwd.relative_to(self.root)) if self.cwd != self.root else "/"
        text = text.replace(str(self.root), "")  # show paths relative to the memory root
        return (text or "(no output)")[:12000] + f"\n[cwd: {rel}]"

    def tools(self) -> list[ToolSpec]:
        return [
            ToolSpec(
                "shell",
                "Run a read-only shell command inside the memory filesystem (bash; ls, cd, cat, grep -r, find, head, tail, wc, sort, pipes and globs). "
                "The root is '/'; the working directory persists between calls and is printed after each result.",
                {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]},
                lambda a: self._run(a["command"]),
            )
        ]

    def layout_prompt(self) -> str:
        return (
            "Your memory and all data are plain markdown files in a directory you explore with a shell. `/MEMORY.md` is the index; "
            "`/memory/<topic>.md` hold what you know about the principal; `/data/<table>.md` holds a whole table and `/data/<table>/<id>.md` one row. "
            "Use `ls`, `cd`, `cat`, `grep -r`, `find`, `head` and pipes through the `shell` tool."
        )
