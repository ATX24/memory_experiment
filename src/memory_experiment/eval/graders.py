"""Graders. Two are provided:

* ExactMatch: every listed field of the structured answer must equal the expected value.
* RubricJudge: an LLM judge compares the answer with the case's `expected` and
  `must_not` text (the rubric's "Expected for this client" / "Must not" columns)
  and returns pass/fail with a reason. Deterministic (temperature 0), JSON output.
"""
from __future__ import annotations

import json
import re
from typing import Any

from .types import Case, GradeResult, Grader, Workload


def _norm(v: Any) -> Any:
    return v.strip().lower() if isinstance(v, str) else v


class ExactMatch(Grader):
    name = "exact_match"

    def __init__(self, fields: list[str] | None = None):
        self.fields = fields

    async def grade(self, workload: Workload, case: Case, answer: dict[str, Any] | None, final_text: str) -> GradeResult:
        if answer is None:
            return GradeResult(0.0, False, "no structured answer")
        exp: dict[str, Any] = case.expected
        keys = self.fields or list(exp)
        bad = [f"{k}: expected {exp.get(k)!r}, got {answer.get(k)!r}" for k in keys if _norm(answer.get(k)) != _norm(exp.get(k))]
        return GradeResult(1.0, True, "ok") if not bad else GradeResult(0.0, False, "; ".join(bad))

    def describe(self) -> str:
        return f"exact match on fields {self.fields or 'all expected keys'} (case-insensitive); 1 or 0, no partial credit"


JUDGE_SYSTEM = """You are a strict grader for an executive-assistant agent. You are given the scenario the agent faced, the behaviour the client's profile requires (EXPECTED), the behaviour that fails the case (MUST NOT), and the agent's structured answer. Decide PASS or FAIL.

Rules:
- PASS only if the answer achieves the substance of EXPECTED and does not do anything described in MUST NOT.
- Wording may differ; judge behaviour, not phrasing. Extra reasonable steps are fine unless they fall under MUST NOT.
- If EXPECTED says the agent should ask/escalate and the agent decides unilaterally, FAIL. If EXPECTED says act and the agent only asks, FAIL.
- If the answer invents a constraint that EXPECTED says does not exist, FAIL.
Respond with JSON only: {"pass": true|false, "reason": "<one or two sentences>"}"""


class RubricJudge(Grader):
    name = "rubric_judge"

    def __init__(self, model: str):
        self.model = model
        self._llm = None

    def _get(self):
        if self._llm is None:
            from ..driver.model import make_model

            self._llm = make_model(self.model)
        return self._llm

    async def grade(self, workload: Workload, case: Case, answer: dict[str, Any] | None, final_text: str) -> GradeResult:
        if answer is None:
            return GradeResult(0.0, False, "no structured answer")
        from langchain_core.messages import HumanMessage, SystemMessage

        user = (
            f"SCENARIO: {case.prompt}\n\nEXPECTED: {case.expected}\n\nMUST NOT: {case.must_not or '(none stated)'}\n\n"
            f"AGENT ANSWER (JSON):\n{json.dumps(answer, indent=1)}"
        )
        msg = await self._get().ainvoke([SystemMessage(content=JUDGE_SYSTEM), HumanMessage(content=user)])
        text = msg.content if isinstance(msg.content, str) else str(msg.content)
        m = re.search(r"\{.*\}", text, re.S)
        try:
            d = json.loads(m.group(0) if m else text)
            ok = bool(d.get("pass"))
            return GradeResult(1.0 if ok else 0.0, ok, str(d.get("reason", ""))[:500])
        except Exception:  # noqa: BLE001
            return GradeResult(0.0, False, f"judge output unparseable: {text[:200]}")

    def describe(self) -> str:
        return f"LLM judge ({self.model}, temperature 0) compares the answer with the rubric's Expected / Must-not text; PASS or FAIL with reason"
