"""Run ONE case against ONE memory model: preset state, build the agent, execute, record."""
from __future__ import annotations

import dataclasses
import tempfile

from ..eval.types import Case, RunRecord, Workload
from ..memory_model import make_memory_model
from ..memory_model.base import MemoryState
from ..memory_model.db import CaseDB
from .graph import run_agent
from .prompts import build_system_prompt


async def run_case(workload: Workload, memory_model_name: str, case: Case, trial: int, model: str, max_steps: int) -> RunRecord:
    mm = make_memory_model(memory_model_name)
    db = CaseDB()
    db.open()
    try:
        # --- preset data state ---
        db.create_tables(workload.tables)
        for table, rows in workload.rows_for(case).items():
            db.insert_rows(table, rows)
        with tempfile.TemporaryDirectory(prefix="memx_") as workdir:
            # --- preset memory state (the memory model decides how to hold it) ---
            mm.load(MemoryState(user_id=case.user_id, facts=workload.facts_for(case), tables=workload.tables, db=db, workdir=workdir, fact_table_name=workload.fact_table_name, experiences=workload.experiences))
            system = build_system_prompt(workload, mm, case.user_id)
            res = await run_agent(system_prompt=system, user_prompt=case.prompt, tools=mm.tools(), answer_schema=workload.answer_schema, model=model, max_steps=max_steps)
            mm.unload()
    finally:
        db.close()
    return RunRecord(
        workload=workload.name, memory_model=memory_model_name, case_id=case.id, user_id=case.user_id, trial=trial,
        score=0.0, passed=False, grade_reason="(ungraded)", expected=case.expected, must_not=case.must_not, answer=res.answer, meta=case.meta,
        model_calls=res.model_calls, wall_ms=res.wall_ms, model_ms=res.model_ms, tool_ms=sum(t.duration_ms for t in res.tool_calls),
        tool_call_count=len(res.tool_calls), tool_result_chars=sum(t.result_chars for t in res.tool_calls),
        input_tokens=res.input_tokens, output_tokens=res.output_tokens, cache_read_tokens=res.cache_read_tokens,
        tool_calls=[dataclasses.asdict(t) for t in res.tool_calls], final_text=res.final_text, error=res.error, model=model, system_prompt=system,
    )
