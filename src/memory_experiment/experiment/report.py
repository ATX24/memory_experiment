"""Aggregate runs.jsonl -> summary.json + summary.md.

Per memory model: pass rate (overall, blocking rows only, per principal, per rubric row),
swap-matrix pass (a swap group passes only if every principal's side passes),
speed and retrieval metrics (wall/model/tool time, tool calls, chars returned)."""
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
    blocking = [r for r in rs if str(r["meta"].get("blocking", "")).lower() in ("yes", "true", "1")]
    return {
        "n": n, "pass_rate": sum(r["score"] for r in rs) / n if n else 0.0,
        "blocking_n": len(blocking), "blocking_pass_rate": (sum(r["score"] for r in blocking) / len(blocking)) if blocking else None,
        "errors": sum(1 for r in rs if r["error"]), "no_answer": sum(1 for r in rs if r["answer"] is None),
        "wall_s": mean("wall_ms") / 1000, "p50_wall_s": st.median(r["wall_ms"] for r in rs) / 1000 if rs else 0.0,
        "model_s": mean("model_ms") / 1000, "tool_ms": mean("tool_ms"), "tool_calls": mean("tool_call_count"), "tool_chars": mean("tool_result_chars"),
        "model_calls": mean("model_calls"), "out_tok": mean("output_tokens"),
    }


def swap_matrix(rs: list[dict[str, Any]]) -> dict[str, Any]:
    """swap group -> per trial: all principals' sides passed?"""
    groups: dict[str, dict[int, list[bool]]] = defaultdict(lambda: defaultdict(list))
    for r in rs:
        g = r["meta"].get("swap_group")
        if g:
            groups[g][r["trial"]].append(bool(r["passed"]))
    out = {}
    for g, by_trial in sorted(groups.items()):
        pair_pass = [all(v) for v in by_trial.values()]
        out[g] = {"pass_rate": sum(pair_pass) / len(pair_pass), "trials": len(pair_pass), "sides": max(len(v) for v in by_trial.values())}
    return out


def summarize(out_dir: Path) -> dict[str, Any]:
    runs = load_runs(out_dir)
    by_mm: dict[str, list] = defaultdict(list)
    for r in runs:
        by_mm[r["memory_model"]].append(r)
    summary: dict[str, Any] = {"overall": {}, "per_trial": {}, "per_principal": {}, "per_rubric_row": {}, "swap": {}, "per_case": {}}
    for mm, rs in by_mm.items():
        summary["overall"][mm] = _agg(rs)
        for t in sorted({r["trial"] for r in rs}):
            summary["per_trial"][f"{mm}|t{t}"] = _agg([r for r in rs if r["trial"] == t])
        for u in sorted({r["user_id"] for r in rs}):
            summary["per_principal"][f"{mm}|{u}"] = _agg([r for r in rs if r["user_id"] == u])
        rows: dict[str, list] = defaultdict(list)
        for r in rs:
            rows[r["meta"].get("rubric_row", "?")].append(r)
        summary["per_rubric_row"][mm] = {k: sum(x["score"] for x in v) / len(v) for k, v in sorted(rows.items())}
        summary["swap"][mm] = swap_matrix(rs)
        cases: dict[str, list] = defaultdict(list)
        for r in rs:
            cases[r["case_id"]].append(r)
        summary["per_case"][mm] = {c: {"pass_rate": sum(x["score"] for x in v) / len(v), "reasons": sorted({x["grade_reason"] for x in v if not x["passed"]})[:3]} for c, v in sorted(cases.items())}
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    (out_dir / "summary.md").write_text(to_markdown(out_dir, summary))
    return summary


def _pct(x):
    return "—" if x is None else f"{x:.0%}"


def to_markdown(out_dir: Path, s: dict[str, Any]) -> str:
    meta = json.loads((out_dir / "meta.json").read_text()) if (out_dir / "meta.json").exists() else {}
    L = [f"# Results: {meta.get('workload','?')}  (model {meta.get('model','?')}, {meta.get('trials','?')} trials, {meta.get('n_cases','?')} cases)", ""]
    L += ["## Overall (all trials pooled)", "", "| memory model | n | pass | pass (blocking rows) | no answer | errors | mean wall s | p50 wall s | model calls | tool calls | tool chars | tool ms | out tok |", "|" + "---|" * 13]
    for mm, a in s["overall"].items():
        L.append(f"| {mm} | {a['n']} | {_pct(a['pass_rate'])} | {_pct(a['blocking_pass_rate'])} | {a['no_answer']} | {a['errors']} | {a['wall_s']:.1f} | {a['p50_wall_s']:.1f} | {a['model_calls']:.1f} | {a['tool_calls']:.1f} | {a['tool_chars']:.0f} | {a['tool_ms']:.0f} | {a['out_tok']:.0f} |")
    L += ["", "## Per trial", "", "| memory model / trial | n | pass | mean wall s | tool calls | tool chars |", "|---|---|---|---|---|---|"]
    for k, a in s["per_trial"].items():
        L.append(f"| {k} | {a['n']} | {_pct(a['pass_rate'])} | {a['wall_s']:.1f} | {a['tool_calls']:.1f} | {a['tool_chars']:.0f} |")
    L += ["", "## Per principal (profile recall + isolation)", "", "| memory model / principal | n | pass | pass (blocking) |", "|---|---|---|---|"]
    for k, a in s["per_principal"].items():
        L.append(f"| {k} | {a['n']} | {_pct(a['pass_rate'])} | {_pct(a['blocking_pass_rate'])} |")
    if any(s["swap"].values()):
        mms = list(s["swap"])
        groups = sorted({g for v in s["swap"].values() for g in v})
        L += ["", "## Swap matrix (a group passes only when every principal's side passes in the same trial)", "", "| swap group | " + " | ".join(mms) + " |", "|" + "---|" * (len(mms) + 1)]
        for g in groups:
            L.append(f"| {g} | " + " | ".join(_pct(s["swap"][mm].get(g, {}).get("pass_rate")) for mm in mms) + " |")
        L.append("| **all groups** | " + " | ".join(_pct(st.mean(v["pass_rate"] for v in s["swap"][mm].values()) if s["swap"][mm] else None) for mm in mms) + " |")
    mms = list(s["per_rubric_row"])
    rows = sorted({r for v in s["per_rubric_row"].values() for r in v})
    L += ["", "## Per rubric row (pass rate)", "", "| rubric row | " + " | ".join(mms) + " |", "|" + "---|" * (len(mms) + 1)]
    for r in rows:
        L.append(f"| {r} | " + " | ".join(_pct(s["per_rubric_row"][mm].get(r)) for mm in mms) + " |")
    L += ["", "## Failed cases", "", "| memory model | case | pass | judge reasons |", "|---|---|---|---|"]
    for mm, cases in s["per_case"].items():
        for c, a in cases.items():
            if a["pass_rate"] < 1:
                L.append(f"| {mm} | {c} | {_pct(a['pass_rate'])} | {' / '.join(a['reasons'])[:300]} |")
    return "\n".join(L) + "\n"
