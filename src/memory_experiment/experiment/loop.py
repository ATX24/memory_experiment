"""The experiment loop: every memory model x every case x N trials, graded, written as JSONL."""
from __future__ import annotations

import asyncio
import dataclasses
import json
from datetime import datetime, timezone
from pathlib import Path

from ..driver.run import run_case
from ..eval.types import Case, RunRecord, Workload
from ..memory_model import make_memory_model


async def run_experiment(workload: Workload, memory_models: list[str], trials: int, model: str, out_dir: Path, concurrency: int = 6, max_steps: int = 12, case_ids: list[str] | None = None, trial_start: int = 1) -> list[RunRecord]:
    out_dir.mkdir(parents=True, exist_ok=True)
    cases = [c for c in workload.cases if not case_ids or c.id in case_ids]
    sem = asyncio.Semaphore(concurrency)
    lock = asyncio.Lock()
    runs_path = out_dir / "runs.jsonl"
    records: list[RunRecord] = []
    total = len(cases) * len(memory_models) * trials
    done = 0

    async def job(mm: str, c: Case, t: int):
        nonlocal done
        async with sem:
            rec = await run_case(workload, mm, c, t, model, max_steps)
            try:
                g = await workload.grader.grade(workload, c, rec.answer, rec.final_text)
                rec.score, rec.passed, rec.grade_reason = g.score, g.passed, g.reason
            except Exception as e:  # noqa: BLE001 - a grader failure must not kill the experiment
                rec.score, rec.passed, rec.grade_reason = 0.0, False, f"grader error: {type(e).__name__}: {str(e)[:200]}"
                rec.error = rec.error or f"grader: {type(e).__name__}"
        async with lock:
            records.append(rec)
            with runs_path.open("a") as f:
                f.write(json.dumps(dataclasses.asdict(rec), default=str) + "\n")
            done += 1
            flag = "ok " if rec.passed else "ERR" if rec.error else "bad"
            print(f"[{done:3d}/{total}] {flag} t{t} {mm:18s} {c.id:12s} {rec.wall_ms/1000:5.1f}s calls={rec.tool_call_count} chars={rec.tool_result_chars}", flush=True)

    meta = {
        "workload": workload.name, "description": workload.description, "model": model, "trials": trials, "trial_start": trial_start,
        "memory_models": {m: make_memory_model(m).spec() for m in memory_models}, "grader": workload.grader.describe(),
        "n_cases": len(cases), "n_facts": len(workload.facts), "tables": [t.name for t in workload.tables], "started": datetime.now(timezone.utc).isoformat(),
    }
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2))
    await asyncio.gather(*(job(m, c, t) for t in range(trial_start, trial_start + trials) for m in memory_models for c in cases))
    return records
