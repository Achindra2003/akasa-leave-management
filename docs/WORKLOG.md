# Work Log

A timestamped log of the build (IST, 2026-11-06), kept to show the process and how the time was split.

| Time | What |
|---|---|
| 12:43 | Received the problem statement (`Christ-FS-Coding-LeaveTracker.docx`) |
| ~13:00 | Research: production leave-system design, workflow and concurrency, Indian leave norms, HR agent patterns and guardrails → `RESEARCH.md` |
| ~13:20 | Stakeholder analysis (D-001), clarified assumptions (calendar-day counting, stack, AI scope, deploy target) → `DECISIONS.md` D-001…D-007 |
| ~13:35 | Model-agnostic LLM layer (Groq default), workflow-vs-agent split, plan for standing out → D-008…D-010; build plan → `PLAN.md` |
| 13:34 | First commit; repo + private GitHub remote |
| 13:37 | Adopted LangGraph and codified engineering standards (D-012, D-013) |
| 13:40 | Domain layer (policy, state machine, routing) + 55 unit tests |
| 13:50 | Async SQLAlchemy models, Alembic migration (btree_gist exclusion constraint, append-only audit trigger), RFC 9457 errors, JWT, services, API, AI layer (provider factory, scripted model, assistant + co-pilot graphs) |
| 13:56 | 40 integration tests on real Postgres (incl. concurrency + AI) → fixed timezone and tool date-parsing bugs |
| 14:08 | Frontend (interface-design skill) + Playwright E2E in headless Edge → fixed 2 client bugs (auth cache, effect cleanup) |
| 14:13 | Docker (multi-stage, non-root) verified from a fresh volume, CI, Render blueprint, eval harness (11/12 → fix → 12/12) |
| 14:14 | README (diagrams), EVALS, AI_USAGE, decisions D-014–D-016 |

_Times after 13:34 are git commit timestamps (`git log --date=format:%H:%M`)._
