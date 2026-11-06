# Work Log

A timestamped log of the build (IST, 2026-11-06), kept to show the process and how the time was split.

| Time | What |
|---|---|
| 12:43 | Received the problem statement (`Christ-FS-Coding-LeaveTracker.docx`) |
| ~13:00 | Research: production leave-system design, workflow and concurrency, Indian leave norms, HR agent patterns and guardrails → `RESEARCH.md` |
| ~13:20 | Stakeholder analysis (D-001), clarified assumptions (calendar-day counting, stack, AI scope, deploy target) → `DECISIONS.md` D-001…D-007 |
| ~13:35 | Model-agnostic LLM layer (Groq default), workflow-vs-agent split, plan for standing out → D-008…D-010; build plan → `PLAN.md` |
| 13:40 | Repo + GitHub (private). Adopted LangGraph and codified engineering standards (D-012, D-013) |
| 13:45 | Domain layer (policy, state machine, routing) + 55 unit tests |
| 13:50 | Async SQLAlchemy models, Alembic migration (btree_gist exclusion constraint, append-only audit trigger), RFC 9457 errors, JWT, services, API |
| 13:52 | AI layer: provider factory, scripted offline model, tools, assistant graph (interrupt), co-pilot workflow graph |
| 13:56 | 40 integration tests on real Postgres (incl. concurrency + AI) → fixed timezone and tool date-parsing bugs |
| 14:00 | Frontend (React 19, TanStack Query, RHF+Zod, Tailwind 4) using the interface-design skill |
| 14:05 | Playwright E2E in headless Edge → found and fixed 2 client bugs (auth cache, effect cleanup) |
| 14:10 | Docker (multi-stage, non-root), fresh-volume verification, CI, Render blueprint |
| 14:12 | Agent eval harness: first run 11/12 → fixed weekday-range parsing → 12/12, 0 safety violations |
| 14:15 | README (diagrams), EVALS, AI_USAGE, decisions D-014–D-016 |
