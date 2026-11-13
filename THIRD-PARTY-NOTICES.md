# Third-party notices

This repository does not vendor any third-party code, fonts or assets. Runtime and test dependencies
(LangGraph, langgraph-checkpoint-sqlite, FastAPI, uvicorn, pytest and their dependencies) are installed with pip from
`requirements.lock` and keep their own licenses.

The agents are external command line tools (`claude`, `codex`) that you install and license yourself; nothing from
them is included here.
