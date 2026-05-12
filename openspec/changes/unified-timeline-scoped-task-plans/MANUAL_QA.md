# Manual QA — unified timeline & scoped task plans

Run after backend + frontend changes for this change. Record pass/fail and build.

## Multi-subagent turn

1. Start an analysis that delegates to at least two different `subagent_type` values (e.g. web + code).
2. Confirm subagent explore/tool rows appear under the correct delegation blocks in the left timeline.
3. If subagents emit task UI, confirm separate boards or labels do not overwrite each other.

## `write_todos` + server `task_plan`

1. Trigger a turn where the main agent uses `write_todos` (todo list) and later receives a full `task_plan` from the server.
2. Confirm main task board updates without duplicate rows for the same logical step where ids differ (`main:todo:…` vs server ids).
3. Complete a todo-driven run and confirm `task_error` / stream `error` only marks the intended scope (main vs subagent board).

## History replay after refresh

1. During an in-progress analysis with a visible task board, reload the page.
2. Confirm restore polling repopulates `taskPlanMain` (and any restored subagent plans if persisted).
3. Open a **completed** turn from conversation history that had a timeline + task board; confirm order matches live run (no duplicated understanding/summary blocks after recent CommandCenter layout changes).
