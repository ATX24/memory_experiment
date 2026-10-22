"""The agent is a LangGraph state machine shared by every backend:

    START -> model -> (tool calls?) -> tools -> model -> ... -> END

* `model` calls the chat model with the backend's tools plus a synthetic
  `submit_answer` tool whose schema is the scenario's answer schema.
* `tools` executes the requested backend tools (timed) and records results.
* The graph ends when `submit_answer` is called, the model stops calling tools,
  or the step budget is exhausted.
"""
from __future__ import annotations

import asyncio
import json
import operator
import time
from typing import Annotated, Any, TypedDict

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from ..core.types import AgentResult, ToolCallRecord, ToolSpec
from .model import make_model

SUBMIT = "submit_answer"


class AgentState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]
    answer: dict[str, Any] | None
    tool_records: Annotated[list[ToolCallRecord], operator.add]
    model_calls: Annotated[int, operator.add]
    model_ms: Annotated[float, operator.add]
    input_tokens: Annotated[int, operator.add]
    output_tokens: Annotated[int, operator.add]
    cache_read_tokens: Annotated[int, operator.add]
    error: str | None


def _openai_tool(spec: ToolSpec) -> dict[str, Any]:
    return {"type": "function", "function": {"name": spec.name, "description": spec.description, "parameters": spec.input_schema}}


def build_graph(*, system_prompt: str, tools: list[ToolSpec], answer_schema: dict[str, Any], model: str, max_steps: int):
    by_name = {t.name: t for t in tools}
    submit = ToolSpec(SUBMIT, "Submit your final answer. Call exactly once when done.", answer_schema, lambda a: "recorded")
    llm = make_model(model).bind_tools([_openai_tool(t) for t in [*tools, submit]])
    system = SystemMessage(content=system_prompt)

    async def model_node(state: AgentState) -> dict[str, Any]:
        t0 = time.perf_counter()
        try:
            msg: AIMessage = await llm.ainvoke([system, *state["messages"]])
        except Exception as e:  # noqa: BLE001
            return {"messages": [AIMessage(content=f"(model error) {e}")], "error": f"{type(e).__name__}: {e}", "model_calls": 1, "model_ms": (time.perf_counter() - t0) * 1000}
        u = msg.usage_metadata or {}
        return {
            "messages": [msg],
            "model_calls": 1,
            "model_ms": (time.perf_counter() - t0) * 1000,
            "input_tokens": u.get("input_tokens", 0),
            "output_tokens": u.get("output_tokens", 0),
            "cache_read_tokens": (u.get("input_token_details") or {}).get("cache_read", 0),
        }

    async def tools_node(state: AgentState) -> dict[str, Any]:
        last = state["messages"][-1]
        assert isinstance(last, AIMessage)
        out: list[ToolMessage] = []
        records: list[ToolCallRecord] = []
        answer = state.get("answer")
        for call in last.tool_calls:
            name, args = call["name"], call["args"] or {}
            if name == SUBMIT:
                answer = args
                out.append(ToolMessage(content="recorded", tool_call_id=call["id"]))
                continue
            t0 = time.perf_counter()
            err = False
            try:
                spec = by_name[name]
                text = await asyncio.to_thread(spec.handler, args)
            except Exception as e:  # noqa: BLE001 - surface to the model
                err, text = True, f"ERROR: {type(e).__name__}: {e}"
            records.append(ToolCallRecord(name, args, (time.perf_counter() - t0) * 1000, len(text), err))
            out.append(ToolMessage(content=text, tool_call_id=call["id"]))
        return {"messages": out, "tool_records": records, "answer": answer}

    def after_model(state: AgentState) -> str:
        if state.get("error"):
            return END
        last = state["messages"][-1]
        if isinstance(last, AIMessage) and last.tool_calls:
            return "tools"
        return END

    def after_tools(state: AgentState) -> str:
        if state.get("answer") is not None or state.get("model_calls", 0) >= max_steps:
            return END
        return "model"

    g = StateGraph(AgentState)
    g.add_node("model", model_node)
    g.add_node("tools", tools_node)
    g.add_edge(START, "model")
    g.add_conditional_edges("model", after_model, {"tools": "tools", END: END})
    g.add_conditional_edges("tools", after_tools, {"model": "model", END: END})
    return g.compile()


async def run_agent(*, system_prompt: str, user_prompt: str, tools: list[ToolSpec], answer_schema: dict[str, Any], model: str, max_steps: int = 12) -> AgentResult:
    graph = build_graph(system_prompt=system_prompt, tools=tools, answer_schema=answer_schema, model=model, max_steps=max_steps)
    t0 = time.perf_counter()
    try:
        final: AgentState = await graph.ainvoke(
            {"messages": [HumanMessage(content=user_prompt)], "answer": None, "tool_records": [], "model_calls": 0, "model_ms": 0.0, "input_tokens": 0, "output_tokens": 0, "cache_read_tokens": 0},
            config={"recursion_limit": max_steps * 2 + 4},
        )
        error = final.get("error")
    except Exception as e:  # noqa: BLE001
        final, error = {}, f"{type(e).__name__}: {e}"
    wall = (time.perf_counter() - t0) * 1000
    texts = [m.content for m in final.get("messages", []) if isinstance(m, AIMessage) and isinstance(m.content, str) and m.content]
    answer = final.get("answer")
    if answer is not None and not isinstance(answer, dict):
        try:
            answer = json.loads(answer)
        except Exception:  # noqa: BLE001
            answer = None
    return AgentResult(
        answer=answer,
        final_text="\n".join(texts)[-4000:],
        model_calls=final.get("model_calls", 0),
        wall_ms=wall,
        model_ms=final.get("model_ms", 0.0),
        input_tokens=final.get("input_tokens", 0),
        output_tokens=final.get("output_tokens", 0),
        cache_read_tokens=final.get("cache_read_tokens", 0),
        tool_calls=final.get("tool_records", []),
        error=error,
    )
