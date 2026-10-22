# memory_experiment

A harness for comparing **agent memory layouts**: the same task, the same
underlying data, the same model and agent loop; only the *interface* through
which the agent reaches its memory and data changes.

The agent is a [LangGraph](https://github.com/langchain-ai/langgraph) state
machine (`model -> tools -> model ...`) and the model is served through the
[Vercel AI Gateway](https://vercel.com/ai-gateway) (`anthropic/claude-sonnet-5.5`
by default). Postgres backs every layout so storage cost is held constant.

## Layouts (backends)

| name | memory (preferences) | operational data | tools |
|---|---|---|---|
| `fs_prefs_plus_sql` | real markdown files (`MEMORY.md` + `preferences/<topic>.md`) | Postgres | `list_dir`, `read_file`, `sql_query` |
| `sql_only` | `preferences` table | Postgres | `sql_query` |
| `virtual_fs` | Postgres, rendered as `/memory/...` | Postgres, rendered as `/data/<table>/...` | `list_dir`, `read_file`, `search` |

Adding a layout = one file in `src/memory_experiment/backends/` subclassing
`MemoryBackend` (`setup`, `tools`, `layout_prompt`) + one line in `REGISTRY`.

## Scenarios

A *scenario* defines the task: tables, per-case rows, preference facts, eval
cases with expected answers, and an answer JSON schema. It is a plain Python
file (`scenario.py` exporting `SCENARIO`) loaded from a directory you point at
with `--scenario`. `scenarios/example/` is a toy one; real scenarios live in
`private/` which is git-ignored.

## Run

```bash
createdb memory_experiment            # or set MEMORY_EXPERIMENT_DSN
echo 'AI_GATEWAY_API_KEY=...' > .env
uv sync
uv run memx backends
uv run memx run --scenario scenarios/example --trials 1
uv run memx run --scenario private/my_task --backends all --trials 3 --concurrency 6
uv run memx report results/<timestamp>
```

Each run writes `results/<timestamp>/runs.jsonl` (one record per agent run:
score, wall/model/tool time, tool calls, tokens, final answer) plus
`summary.md` / `summary.json` aggregated per backend, per trial and per case.

## Metrics

* **accuracy**: structured answer matches the case's expected fields (default grader; scenarios can supply their own)
* **wall / model / tool time**: end-to-end latency and where it went
* **tool calls / tool chars**: how many retrievals and how much text came back
* **input / output tokens**: context cost of the layout
