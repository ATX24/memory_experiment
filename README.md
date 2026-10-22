# memory_experiment

Plug in a **memory model**, run it on a **workload**, grade it against a **rubric**.
Same agent, same model, same preset state; only the way memory and data are
stored and exposed to the agent changes.

```
src/memory_experiment/
  memory_model/   how facts (memory state) and rows (data state) are held and exposed as tools
  driver/         runs one case: LangGraph agent (model -> tools -> model) over a memory model
  eval/           Workload / Case types, loader, graders (exact match, LLM rubric judge)
  experiment/     the loop (memory models x cases x trials), aggregation, markdown report
gateway/          local OpenAI-compatible server fronting the Claude Code CLI (BAML ClaudeCodeClient)
workloads/        public example workload
private/          real workloads + rubric data (git-ignored)
```

## Memory models

| name | memory lives in | data lives in | tools |
|---|---|---|---|
| `fs_prefs_plus_sql` | real markdown files (`/MEMORY.md`, `/memory/<topic>.md`) | Postgres | `list_dir`, `read_file`, `sql_query` |
| `sql_only` | Postgres table `memory` (all principals) | Postgres | `sql_query` |
| `virtual_fs` | Postgres, rendered on read as `/memory/topics/<topic>.md` | Postgres, rendered as `/data/<table>/...` | `list_dir`, `read_file`, `search` |
| `experience_fs` | Postgres `experience_items` (observations) grouped into experiences | Postgres rows linked into experiences, rendered inside `/<experience>.md` | `list_dir`, `read_file`, `search` |
| `plain_fs` | real markdown files | real markdown files, no database | `list_dir`, `read_file`, `grep` |

Add one: subclass `MemoryModel` (`load(state)`, `tools()`, `layout_prompt()`) in
`memory_model/<name>.py` and add it to `REGISTRY`.

## Workloads

A workload is one Python file exporting `WORKLOAD: Workload`: task instructions,
preset **memory state** (`facts`, per principal), preset **data state** (`tables` +
`rows`), the `cases` (prompt, principal, expected, must-not, metadata such as
rubric row / swap group / blocking), an answer JSON schema and a grader. Every run
presets both states fresh (new Postgres schema + temp dir), so each case sees the
memory the task depends on and nothing from other runs.

## Grading

* `ExactMatch(fields)` for structured expected answers.
* `RubricJudge(model)` for rubric-style cases: compares the structured answer with
  the case's Expected / Must-not text, returns PASS or FAIL with a reason.

Reports aggregate pass rate overall, on blocking rows, per principal (profile recall
and cross-principal isolation), per rubric row, swap-matrix groups (all principals'
sides must pass), plus wall/model/tool time, tool calls and chars returned per run.

## Run

```bash
createdb memory_experiment                 # or set MEMORY_EXPERIMENT_DSN
cd gateway && baml pack chat_turn -o chat_turn_bin && cd ..
python3 gateway/server.py --port 8791 &    # Claude Code behind an OpenAI-compatible endpoint
printf 'AI_GATEWAY_API_KEY=local\nAI_GATEWAY_BASE_URL=http://127.0.0.1:8791/v1\n' > .env
uv sync
uv run memx memory-models
uv run memx run --workload workloads/example --trials 1
uv run memx run --workload private/workloads/<name> --memory-models all --trials 3 --concurrency 6
uv run memx merge results/all results/t1 results/t2 results/t3   # when trials ran as separate processes
```
