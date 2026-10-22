"""memory_experiment: compare agent memory layouts on a task.

The harness is scenario-agnostic. A *scenario* (schema, seed rows, preference
facts, eval cases, grader) is loaded from a directory at runtime; a *backend*
(memory layout) decides how that data is exposed to the agent as tools. The
agent itself is a LangGraph state machine calling a model through the Vercel
AI Gateway.
"""
