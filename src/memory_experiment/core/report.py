"""Aggregate runs.jsonl into per-backend / per-trial tables (markdown + json)."""
from __future__ import annotations

import json
import statistics as st
from collections import defaultdict
from pathlib import Path
from typing import Any


def load_runs(out_dir: Path) -> list[dict[str, Any]]:
    return [json.loads(l) for l in (out_dir / "runs.jsonl").read_text().splitlines() if l.strip()]


def _agg(rs: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(rs)
    mean = lambda k: st.mean(r[k] for r in rs) if rs else 0.0  # noqa: E731
    return {
        "n": n,
        "accuracy": sum(r["score"] for r in rs) / n if n else 0.0,
        "errors": sum(1 for r in rs if r["error"]),
        "wall_s": mean("wall_ms") / 1000,
        "model_s": mean("model_ms") / 1000,
        "tool_ms": mean("tool_ms"),
        "tool_calls": mean("tool_call_count"),
        "tool_chars": mean("tool_result_chars"),
        "model_calls": mean("model_calls"),
        "in_tok": mean("input_tokens"),
        "out_tok": mean("output_tokens"),
        "p50_wall_s": st.median(r["wall_ms"] for r in rs) / 1000 if rs else 0.0,
    }


def summarize(out_dir: Path) -> dict[str, Any]:
    runs = load_runs(out_dir)
    by_backend: dict[str, list] = defaultdict(list)
    by_bt: dict[tuple[str, int], list] = defaultdict(list)
    by_case: dict[tuple[str, str], list] = defaultdict(list)
    for r in runs:
        by_backend[r["backend"]].append(r)
        by_bt[(r["backend"], r["trial"])].append(r)
        by_case[(r["backend"], r["case_id"])].append(r)
    summary = {
        "overall": {b: _agg(rs) for b, rs in by_backend.items()},
        "per_trial": {f"{b}|t{t}": _agg(rs) for (b, t), rs in sorted(by_bt.items())},
        "per_case": {f"{b}|{c}": {"accuracy": sum(r["score"] for r in rs) / len(rs), "n": len(rs), "notes": sorted({r["grade_notes"] for r in rs if r["score"] < 1})} for (b, c), rs in sorted(by_case.items())},
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    (out_dir / "summary.md").write_text(to_markdown(out_dir, summary))
    return summary


def to_markdown(out_dir: Path, s: dict[str, Any]) -> str:
    meta = json.loads((out_dir / "meta.json").read_text()) if (out_dir / "meta.json").exists() else {}
    lines = [f"# Results: {meta.get('scenario','?')}  (model {meta.get('model','?')}, {meta.get('trials','?')} trials, {meta.get('n_cases','?')} cases)", ""]
    hdr = "| backend | n | accuracy | errors | mean wall s | p50 wall s | model s | tool ms | tool calls | tool chars | model calls | in tok | out tok |"
    lines += ["## Overall (all trials pooled)", "", hdr, "|" + "---|" * 13]
    for b, a in s["overall"].items():
        lines.append(f"| {b} | {a['n']} | {a['accuracy']:.1%} | {a['errors']} | {a['wall_s']:.1f} | {a['p50_wall_s']:.1f} | {a['model_s']:.1f} | {a['tool_ms']:.0f} | {a['tool_calls']:.1f} | {a['tool_chars']:.0f} | {a['model_calls']:.1f} | {a['in_tok']:.0f} | {a['out_tok']:.0f} |")
    lines += ["", "## Per trial", "", hdr.replace("backend", "backend / trial"), "|" + "---|" * 13]
    for k, a in s["per_trial"].items():
        lines.append(f"| {k} | {a['n']} | {a['accuracy']:.1%} | {a['errors']} | {a['wall_s']:.1f} | {a['p50_wall_s']:.1f} | {a['model_s']:.1f} | {a['tool_ms']:.0f} | {a['tool_calls']:.1f} | {a['tool_chars']:.0f} | {a['model_calls']:.1f} | {a['in_tok']:.0f} | {a['out_tok']:.0f} |")
    lines += ["", "## Per case (accuracy across trials)", "", "| backend | case | accuracy | failure notes |", "|---|---|---|---|"]
    for k, a in s["per_case"].items():
        b, c = k.split("|", 1)
        lines.append(f"| {b} | {c} | {a['accuracy']:.0%} | {'; '.join(a['notes'])[:200]} |")
    return "\n".join(lines) + "\n"
