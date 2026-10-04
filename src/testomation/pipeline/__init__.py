"""Pipeline runner: fixed stages, stage state in Postgres, compute budget.

Stages (docs/AGENT_RUNTIME.md): refresh basis + scope → run approved specs →
triage failures → generate missing tests → report. Plain code; no LangGraph.
"""
