from __future__ import annotations

import asyncio
import dataclasses
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..agent.graph import run_agent
from ..backends import make_backend
from .db import CaseDB
from .grading import default_grader
from .prompts import build_system_prompt
from .types import EvalCase, RunRecord, Scenario


async def run_one(scenario: Scenario, backend_name: str, case: EvalCase, trial: int, model: str, max_steps: int) -> RunRecord:
    backend = make_backend(backend_name)
    db = CaseDB()
    db.open()
    try:
        db.create_tables(scenario.tables)
        for table, rows in case.rows.items():
            db.insert_rows(table, rows)
        with tempfile.TemporaryDirectory(prefix="memx_") as workdir:
            backend.setup(scenario, case, db, workdir)
            system = build_system_prompt(scenario, backend, case.user_id)
            res = await run_agent(system_prompt=system, user_prompt=case.prompt, tools=backend.tools(), answer_schema=scenario.answer_schema, model=model, max_steps=max_steps)
            backend.teardown()
    finally:
        db.close()
    grader = scenario.grader or default_grader
    score, notes = grader(case.expected, res.answer)
    return RunRecord(
        scenario=scenario.name,
        backend=backend_name,
        case_id=case.id,
        trial=trial,
        score=score,
        grade_notes=notes,
        expected=case.expected,
        answer=res.answer,
        model_calls=res.model_calls,
        wall_ms=res.wall_ms,
        model_ms=res.model_ms,
        tool_ms=sum(t.duration_ms for t in res.tool_calls),
        tool_call_count=len(res.tool_calls),
        tool_result_chars=sum(t.result_chars for t in res.tool_calls),
        input_tokens=res.input_tokens,
        output_tokens=res.output_tokens,
        cache_read_tokens=res.cache_read_tokens,
        tool_calls=[dataclasses.asdict(t) for t in res.tool_calls],
        final_text=res.final_text,
        error=res.error,
        model=model,
        tags=case.tags,
    )


async def run_suite(scenario: Scenario, backends: list[str], trials: int, model: str, out_dir: Path, concurrency: int = 6, max_steps: int = 12, case_ids: list[str] | None = None) -> list[RunRecord]:
    out_dir.mkdir(parents=True, exist_ok=True)
    cases = [c for c in scenario.cases if not case_ids or c.id in case_ids]
    sem = asyncio.Semaphore(concurrency)
    runs_path = out_dir / "runs.jsonl"
    lock = asyncio.Lock()
    records: list[RunRecord] = []
    total = len(cases) * len(backends) * trials
    done = 0

    async def job(b: str, c: EvalCase, t: int):
        nonlocal done
        async with sem:
            rec = await run_one(scenario, b, c, t, model, max_steps)
        async with lock:
            records.append(rec)
            with runs_path.open("a") as f:
                f.write(json.dumps(dataclasses.asdict(rec), default=str) + "\n")
            done += 1
            flag = "ok " if rec.score == 1 else "ERR" if rec.error else "bad"
            print(f"[{done:3d}/{total}] {flag} t{t} {b:18s} {c.id:28s} {rec.wall_ms/1000:5.1f}s calls={rec.tool_call_count} tok={rec.input_tokens}", flush=True)

    meta = {
        "scenario": scenario.name,
        "model": model,
        "trials": trials,
        "backends": {b: make_backend(b).spec() for b in backends},
        "n_cases": len(cases),
        "started": datetime.now(timezone.utc).isoformat(),
    }
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2))
    await asyncio.gather(*(job(b, c, t) for t in range(1, trials + 1) for b in backends for c in cases))
    return records
