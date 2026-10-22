from __future__ import annotations

import argparse
import asyncio
import json
import shutil
from datetime import datetime
from pathlib import Path

from .eval.loader import load_workload
from .experiment.loop import run_experiment
from .experiment.report import summarize
from .memory_model import REGISTRY


def main() -> None:
    p = argparse.ArgumentParser(prog="memx", description="Plug in a memory model, run it on a workload, grade it.")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="run every memory model on a workload")
    r.add_argument("--workload", required=True, help="directory containing workload.py")
    r.add_argument("--memory-models", default="all", help="comma list or 'all'")
    r.add_argument("--trials", type=int, default=1)
    r.add_argument("--trial-start", type=int, default=1, help="number trials from here (lets trials run as separate processes)")
    r.add_argument("--model", default="claude-opus-5-5", help="model id understood by the configured gateway")
    r.add_argument("--concurrency", type=int, default=6)
    r.add_argument("--max-steps", type=int, default=12, help="max model calls per run")
    r.add_argument("--cases", default="", help="comma list of case ids (default all)")
    r.add_argument("--out", default="", help="results dir (default results/<timestamp>)")

    s = sub.add_parser("report", help="re-aggregate a results dir"); s.add_argument("out")
    m = sub.add_parser("merge", help="merge results dirs (e.g. one per trial)"); m.add_argument("out"); m.add_argument("inputs", nargs="+")
    sub.add_parser("memory-models", help="list registered memory models")
    a = p.parse_args()

    if a.cmd == "memory-models":
        for name, cls in REGISTRY.items():
            print(f"{name:20s} memory: {cls.memory_lives_in}\n{'':20s} data:   {cls.data_lives_in}")
        return
    if a.cmd == "merge":
        out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
        with (out / "runs.jsonl").open("w") as f:
            for d in a.inputs:
                f.write((Path(d) / "runs.jsonl").read_text())
        metas = [json.loads((Path(d) / "meta.json").read_text()) for d in a.inputs]
        meta = dict(metas[0]); meta["trials"] = sum(m["trials"] for m in metas); meta["merged_from"] = a.inputs
        (out / "meta.json").write_text(json.dumps(meta, indent=2))
        summarize(out); print((out / "summary.md").read_text()); return
    if a.cmd == "report":
        summarize(Path(a.out)); print((Path(a.out) / "summary.md").read_text()); return

    wl = load_workload(a.workload)
    mms = list(REGISTRY) if a.memory_models == "all" else a.memory_models.split(",")
    out = Path(a.out) if a.out else Path("results") / datetime.now().strftime("%Y%m%d-%H%M%S")
    cases = [c for c in a.cases.split(",") if c] or None
    asyncio.run(run_experiment(wl, mms, a.trials, a.model, out, a.concurrency, a.max_steps, cases, a.trial_start))
    summarize(out); print((out / "summary.md").read_text())


if __name__ == "__main__":
    main()
