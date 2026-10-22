from __future__ import annotations

import argparse
import asyncio
from datetime import datetime
from pathlib import Path

from .backends import REGISTRY
from .core.report import summarize
from .core.runner import run_suite
from .core.scenario import load_scenario


def main() -> None:
    p = argparse.ArgumentParser(prog="memx", description="Compare agent memory layouts on a scenario.")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="run the eval suite")
    r.add_argument("--scenario", required=True, help="directory containing scenario.py")
    r.add_argument("--backends", default="all", help="comma list or 'all'")
    r.add_argument("--trials", type=int, default=1)
    r.add_argument("--model", default="anthropic/claude-sonnet-5.5", help="AI Gateway model id")
    r.add_argument("--concurrency", type=int, default=6)
    r.add_argument("--max-steps", type=int, default=12, help="max model calls per run")
    r.add_argument("--cases", default="", help="comma list of case ids (default all)")
    r.add_argument("--out", default="", help="results dir (default results/<timestamp>)")

    s = sub.add_parser("report", help="re-aggregate a results dir")
    s.add_argument("out")

    sub.add_parser("backends", help="list registered backends")
    a = p.parse_args()

    if a.cmd == "backends":
        for name, cls in REGISTRY.items():
            print(f"{name:20s} {cls.description}")
        return
    if a.cmd == "report":
        summarize(Path(a.out))
        print((Path(a.out) / "summary.md").read_text())
        return

    scenario = load_scenario(a.scenario)
    backends = list(REGISTRY) if a.backends == "all" else a.backends.split(",")
    out = Path(a.out) if a.out else Path("results") / datetime.now().strftime("%Y%m%d-%H%M%S")
    cases = [c for c in a.cases.split(",") if c] or None
    asyncio.run(run_suite(scenario, backends, a.trials, a.model, out, a.concurrency, a.max_steps, cases))
    summarize(out)
    print((out / "summary.md").read_text())


if __name__ == "__main__":
    main()
