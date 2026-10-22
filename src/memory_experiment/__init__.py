"""memory_experiment: plug in a memory model, run it on a workload, grade it with a rubric.

    memory_model/  how facts + data are stored and exposed to the agent as tools
    driver/        runs one case: LangGraph agent (model -> tools -> model) over a memory model
    eval/          workload + case types, loaders, graders (exact match, rubric judge)
    experiment/    the loop (models x cases x trials), aggregation, report
"""
