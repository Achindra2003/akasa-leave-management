# Architecture & Decision Log

This is a running log of the key decisions, the options considered and why each was chosen. Entries are added as the build goes, not written afterwards. Research behind these decisions is in [`RESEARCH.md`](./RESEARCH.md).

Format: **Context → Options → Decision → Why → Trade-off accepted**

---

## D-001 — Who actually uses this system? (Stakeholder analysis)

**Context.** The brief names only *Employee* and *Manager* (plus *HOD* in the validation rule). A real organisation has more people involved in leave, and leaving them out produces a demo that breaks on its first real edge case. Akasa Air is an **airline**, which adds operational stakeholders that a typical office company doesn't have.

| Actor | What they need | In a real org | **This build** |
|---|---|---|---|
| **Employee** (everyone, including managers and HODs) | Apply, attach documents, track status, respond to info requests, withdraw | Core | ✅ Built |
| **Reporting Manager** (L1 approver) | Queue of their *direct reports'* requests, approve/reject/ask for info with comments, view documents, see who else on the team is off | Core | ✅ Built |
| **HOD** (L2 approver, >3 days) | Queue of department requests already approved by the manager, same actions | Core | ✅ Built |
| **HR Admin** | Owns policy (leave types, thresholds, holidays), sees all requests, verifies medical docs, resolves stuck or conflicting cases, reads the audit trail, runs reports | Always exists; final escalation point | ✅ Read-all dashboard + audit log viewer. Policy editing ⏭ deferred |
| **Delegate / acting approver** | Approves while the manager is on leave, so requests don't stall | Very common (SAP, Workday, Darwinbox all have it) | ⏭ Designed (approver resolved at runtime), not built |
| **Peers / team** | "Who's out this week?", **without** seeing reasons or documents | Common | ◐ Team-overlap warning shown to approvers only |
| **Payroll / Finance** | Approved leave → loss-of-pay, encashment. Read-only consumer | Integration | ⏭ Approved data exposed via API; CSV export is a stretch goal |
| **Crew scheduling / Ops control** *(airline-specific)* | Pilot and cabin-crew leave affects the roster, DGCA flight-duty-time limits and minimum staffing. Leave isn't just HR, it's operational capacity | Critical at an airline | ◐ The co-pilot's "team overlap / coverage" flag shows the idea; full roster integration ⏭ |
| **Auditor / Compliance** | Tamper-evident history of who did what and when | Required | ✅ Append-only audit log |
| **System (scheduler)** | SLA reminders, auto-escalation when an approver doesn't act, marking leave as taken | Common | ⏭ Designed, not built |
| **AI assistant** (non-human actor) | Acts *on behalf of* a user | New | ✅ Built, with the user's own permissions, and every action audited as `via=assistant` |

**Real-world edge cases that follow from this, and our rules for them:**
1. **Roles are not exclusive.** A manager is also an employee who applies for leave. → Every user can apply. Approval authority comes from the **org structure** (`manager_id`, `department.hod_id`), not only from a role flag.
2. **No self-approval (separation of duties).** Nobody can act on their own request, even if they are their own HOD in the org chart.
3. **Manager and HOD are the same person** for someone (for example a direct report of the HOD) → the single approval counts for both levels? **No.** We route L2 to HR Admin so that >3-day leave always gets two *different* sign-offs, which is the intent of the rule.
4. **An HOD applies for leave** → L1 is their own manager. The L2 "HOD" step is skipped in favour of HR Admin, since they can't approve themselves.
5. **No manager or HOD assigned** → falls back to HR Admin. A request never gets stuck with nobody to approve it.
6. **Privacy.** Leave reasons and medical documents are visible only to the requester, the approvers in their chain, and HR. Never to peers.

**Decision.** Build roles `EMPLOYEE`, `MANAGER`, `HOD`, `HR_ADMIN`, with routing resolved from the org structure plus the fallbacks above. Delegation, SLA escalation, payroll export and roster integration are documented as the next steps.

**Why.** It covers what the brief asks for, plus the edge cases an evaluator is likely to probe ("what if the manager applies?", "what if there's no HOD?"), without spending the 3-hour budget on features nobody will demo.

**Trade-off.** Approver resolution is a small routing function and not a configurable workflow engine (Camunda/Temporal). That's enough for 2 levels. The `approval_steps` table keeps the option open for N levels.

---

## D-002 — Counting "consecutive leave > 3 days"

**Options.** Calendar days (inclusive) vs. working days (excluding weekends and holidays).
**Decision.** **Calendar days, inclusive** (`toDate − fromDate + 1`). Nov 1 → Nov 5 = 5 days → documents required, plus Manager → HOD approval.
**Why.** It matches the brief's literal word "consecutive" and their sample payload, and an assessor can check it in their head. The UI shows the working-day count alongside as information.
**Trade-off.** It's stricter than a working-day policy (Fri→Mon = 4 calendar days → triggers the HOD step). The rule sits in one function (`policy.requires_escalation`), so changing it is a one-line change.

## D-003 — Stack

**Decision.** Backend: **FastAPI + SQLAlchemy 2 + Alembic + PostgreSQL**. Frontend: **React + Vite + TypeScript + Tailwind**. Tests: **pytest** and **Vitest**.
**Why.** It's quick to build in 3 hours, the OpenAPI/Swagger docs come for free (useful for the "code and system knowledge" evaluation), Pydantic gives strong request validation, and it's typed end to end.
**Trade-off.** Python isn't the fastest runtime. That's irrelevant at this scale.

## D-004 — Database: PostgreSQL (Neon) over MongoDB

**Context.** We're deploying to Render with a managed database. Supabase, Neon and Mongo Atlas were all considered.
**Decision.** **PostgreSQL**, hosted on **Neon** (free tier, serverless, standard connection string).
**Why.**
- The domain is **relational**: users → manager, users → department → HOD, requests → approval steps → audit. Mongo would push referential integrity into application code.
- **Integrity guarantees the brief implicitly depends on:** foreign keys, transactions (a state change and its audit row commit together), and a **DB-level exclusion constraint** that blocks overlapping active leave for the same employee even under concurrent submissions (see RESEARCH §2.3). Mongo has none of these out of the box.
- Neon over Supabase: we only need a database, not Supabase's auth/storage stack. Neon is just Postgres, so local Docker and production behave the same.
**Trade-off.** We need schema migrations (Alembic). That's a feature, not a cost.

## D-005 — Agentic AI scope

**Decision.** (1) An **employee assistant**: natural language → a structured leave **draft** via tool calls, and the user **confirms** before anything is submitted. (2) An **approver co-pilot**: summarises a request and flags overlaps, missing documents and history. **Advisory only.**
**Why.** It addresses "Usage of AI tools" directly, and it follows production agent guardrails (RESEARCH §3): tools run under the user's own RBAC, there's a human confirmation before any write, the AI never approves or rejects, free text is treated as untrusted, and every action is audited. If there's no API key or the model fails, the portal still works fully.
**Trade-off.** It needs an `ANTHROPIC_API_KEY` for the AI panel. Assessors without one still get the complete portal.

## D-006 — Deliverable & deployment

**Decision.** `docker compose up` (app + Postgres + seed data) as the primary way to run it. Deploy to **Render** (Docker web service) with **Neon** Postgres for a live URL.
**Why.** The brief requires something they can run themselves. Docker makes that one command, and the live URL removes setup friction entirely.
**Trade-off.** Render's free tier cold-starts (around 30–50 s on first hit). This is documented in the README.

## D-007 — Where uploaded documents live

**Context.** Render's container filesystem is **ephemeral**: files written to disk disappear on every redeploy or restart.
**Options.** Local disk (breaks on Render) · S3/Supabase Storage (an extra service and credentials) · **Postgres `bytea` behind a storage interface**.
**Decision.** Store attachments in Postgres (`attachments.content`), with a 5 MB cap and only PDF/PNG/JPG allowed. Access goes through a `StorageBackend` interface, so moving to S3 later means a new class, not a rewrite.
**Why.** There's no extra infrastructure, it works the same locally and on Render, and the attachment commits in the same transaction as the request, so you can't end up with a request missing its document or a document with no request.
**Trade-off.** Putting blobs in the database doesn't scale to large volumes. That's fine for medical certificates at demo scale, and the interface makes the migration path explicit.

## D-008 — Model-agnostic LLM layer (Groq by default) — ⚠️ *Superseded by D-012*

**Context.** We're using a Groq key, but we don't want to be locked into one vendor.
**Options.** (a) Groq SDK directly (locked in) · (b) LiteLLM (a heavy dependency that hides the loop) · (c) **our own `LLMProvider` interface plus an OpenAI-compatible adapter**.
**Decision.** (c). A small `LLMProvider` protocol (`chat(messages, tools) -> ChatResult`) with two implementations:
- `OpenAICompatProvider`: configured by `LLM_BASE_URL`, `LLM_API_KEY` and `LLM_MODEL`. That one adapter covers **Groq, OpenAI, OpenRouter, Together, Ollama/vLLM (local), and Anthropic's/Gemini's OpenAI-compatible endpoints**. Switching provider means changing environment variables, not code.
- `FakeProvider`: deterministic and offline. It's used by the tests and evals, and as a **demo mode** when no key is set, so assessors still see the AI flow.
**Why.** Most providers now speak the OpenAI chat-completions and tools format. Writing the agent loop ourselves (rather than using a framework) keeps it about 100 lines, fully testable, and lets us explain every step in the interview.
**Trade-off.** Provider-specific extras such as prompt caching or reasoning settings aren't exposed. A native adapter can be added behind the same interface if one is ever needed.

## D-009 — Workflow vs agent: use the simplest pattern per feature — ⚠️ *Implementation superseded by D-012 (principles kept)*

Following "start with the simplest thing that works" (AGENTIC_PATTERNS_GUIDE §1):
- **Approver co-pilot → workflow, not agent.** The facts it needs are always the same (request, overlaps with the team's leave, documents, history), so **our code gathers them deterministically** and makes one LLM call to summarise and flag. This is predictable, cheap and testable, and the model can't invent the data.
- **Employee assistant → a bounded tool-calling agent (ReAct).** Here the steps really aren't known in advance: the user may ask about status, draft a leave, or ask a follow-up question. Guardrails:
  - **step limit** (6) and repeated-call detection; tool errors go back to the model as messages, not exceptions
  - **least privilege**: the agent's tools are `get_today`, `list_my_requests`, `get_request_status`, `check_overlap`, `draft_leave_request`. **It has no submit, approve or reject tool at all**, so the security comes from the tool set, not from the system prompt
  - **human in the loop**: `draft_leave_request` returns a validated draft card, and only the user's click on **Confirm** calls the normal REST endpoint, with all the usual validation
  - **untrusted text**: user-supplied reasons and comments are passed as delimited data
  - **structured output** is validated with Pydantic, with one retry that feeds the validation error back
  - **tracing**: every run is stored in `agent_runs` (steps, tool calls, latency, tokens) and appears in the audit log as `via=assistant`

## D-010 — How this submission stands out

Most candidates will vibe-code a CRUD app with a form and a table. We set ourselves apart with **evidence**, not more features:
1. **The workflow is correct by construction**: an explicit transition table, plus a DB exclusion constraint, plus optimistic locking, **and a concurrency test that proves it** (two parallel submits → exactly one succeeds).
2. **Agent evals**: a golden set of natural-language requests → expected draft and tool trajectory, run with `make eval`, and the results reported honestly in `docs/EVALS.md`, including failures.
3. **Zero-friction demo**: one command, seeded org, one-click "log in as Employee / Manager / HOD / HR" buttons, and AI demo mode without a key.
4. **Docs that show the thinking**: RESEARCH, DECISIONS, WORKLOG (timestamped), Mermaid diagrams (architecture, state machine, ER), and Limitations stated plainly.
5. **"Usage of AI tools" is an evaluated skill**, so `docs/AI_USAGE.md` records *how* AI was used to build this: what was delegated, what was verified, and what the AI got wrong and how we caught it.
6. **CI**: GitHub Actions runs lint, type-check, tests and the Docker build, with a status badge in the README.
7. **Domain framing**: the README opens with the airline context (crew availability is operational capacity), not just "a leave app".

## D-011 — UI design process: use specialised design skills, each for a defined purpose

**Context.** The UI is graded (colour coding, responsiveness, friendly errors), and AI-generated UIs tend to look generic. We have a set of design skills installed: `interface-design`, `emil-design-eng`, `mobile-native`, `break-ui`, `web-design-guidelines`, `impeccable`, `animate`, `design-taste-frontend`, and others.
**Decision.** Use each skill for one specific job, so they don't overlap:
| Stage | Skill | Why this one |
|---|---|---|
| Visual direction, tokens, layout of a **product/dashboard** UI | `interface-design` | Built for dashboards and admin tools. `design-taste-frontend` targets landing pages, which is the wrong fit |
| Component polish and micro-interactions | `emil-design-eng` (+ `animate` only where motion carries meaning, such as status changes) | Small, purposeful motion; not decoration |
| Mobile/responsive behaviour | `mobile-native` | The brief lists "Responsive web/mobile app" as a plus point |
| Stress test with worst-case data | `break-ui` | Long names, 30-day spans, empty queues: show it doesn't break |
| Final accessibility/UX audit | `web-design-guidelines` | A checklist-based review before submission |
**Status colour semantics** (used consistently everywhere): Pending Manager = amber, Pending HOD = indigo, Info Requested = sky, Approved = green, Rejected = red, Cancelled = slate. The colour always comes **with a text label and icon** (never colour alone, for accessibility).

## D-012 — Agents on LangGraph (revises D-008/D-009)

**Context.** On review, a hand-rolled loop reinvents what LangGraph gives us for free and is the industry default for stateful agents: **durable checkpoints, `interrupt()` for human-in-the-loop, recursion limits, streaming, and LangSmith tracing**. The deciding factor is human confirmation before submit. Done properly, the agent **pauses mid-graph**, the user may answer minutes later, and the run **resumes**. That needs persisted state, which is exactly what LangGraph checkpointers provide.
**Decision.**
- **Model-agnostic:** a `get_chat_model()` factory driven by `LLM_PROVIDER` / `LLM_MODEL` / `LLM_BASE_URL` / `LLM_API_KEY`. Providers: `groq` (default), `openai_compat` (OpenAI, OpenRouter, vLLM, Ollama, Gemini's/Anthropic's OpenAI-compatible endpoints), and `fake` (a scripted, deterministic tool-calling model for tests, evals and keyless demo). All return a LangChain `BaseChatModel`, so the graphs don't know which provider they're running on.
- **Employee assistant = agent graph:** `agent ⇄ tools (read-only) → [draft ready] → confirm (interrupt) → submit → END`. The submit node calls the **same `LeaveService.submit()`** as the REST API, under the user's identity, and writes audit `via=assistant`. The model never holds a submit tool. Submission happens only in a graph node that runs **after a human resume**.
- **Approver co-pilot = workflow graph:** `gather_facts (code) → summarise (LLM, structured output) → validate → END`. It's deterministic where it can be and the LLM is used only where needed (D-009's principle, kept).
- **Checkpointer:** `PostgresSaver` (`langgraph-checkpoint-postgres`) in prod, so pending confirmations survive restarts. `InMemorySaver` in tests.
- **Guardrails stay as in D-009:** least-privilege tools, recursion limit, untrusted-text delimiting, Pydantic validation, and every run traced (`agent_runs` table, plus optional LangSmith via env).
**Trade-off.** A heavier dependency than a 100-line loop, and the LangGraph API changes quickly, so versions are pinned. Worth it for durable interrupts and standard tooling a reviewer will recognise.

## D-013 — Engineering standards (the "modern, industry-standard" bar)

Influenced by the author's earlier projects (Helix: provider abstraction with a stub default, FastAPI serving the SPA, CI on Postgres, prompt-injection regression tests, a "Known gaps" README; Nirmit: Pydantic as the single contract source, a "headless brain" where all business logic lives in the backend).

**Backend**
- `uv` + `pyproject.toml` with a lockfile · `ruff` (lint + format) · `mypy` · `pre-commit`
- FastAPI with an **async** stack: SQLAlchemy 2.0 typed `Mapped[]` models + `psycopg` 3 (async) · `pydantic-settings` for config · `Annotated[..., Depends()]` dependency injection · lifespan handler
- Layers: `api` (routers, thin) → `services` (business rules, state machine, transactions) → `models`/`repositories`. Routers never touch the ORM directly.
- Errors as **RFC 9457 Problem Details** (`application/problem+json`), each with a stable `code` and a human-friendly `detail`, so the UI shows the message as-is
- Auth: JWT (PyJWT) + `pwdlib` (argon2). RBAC enforced in dependencies **and** re-checked in services (defence in depth).
- Structured JSON logging (`structlog`) with a request-ID middleware, and the same ID in audit rows · `/health` (liveness) + `/ready` (DB)
- Alembic migrations run on container start · versioned API `/api/v1`

**Frontend**
- Vite + React + TypeScript (strict) · TanStack Query (server state) · React Router · React Hook Form + **Zod** (the same rules as the backend; the server stays authoritative)
- Tailwind + shadcn/ui (Radix, accessible primitives) · `sonner` toasts for friendly errors
- **API types generated from OpenAPI** (`openapi-typescript`): Pydantic is the single source of truth, so frontend and backend can't drift
- ESLint + Prettier · Vitest + Testing Library

**Quality & delivery**
- Tests run against **real Postgres**, not SQLite, because the exclusion constraint and `FOR UPDATE` behaviour are Postgres-specific. Unit tests (pure domain logic) → integration tests (httpx `AsyncClient`, full flows, RBAC, concurrency) → agent tests (fake model, interrupt/resume) → evals (golden set)
- GitHub Actions: lint, type-check, tests with a Postgres service, frontend build, Docker build
- Multi-stage Dockerfile, non-root, `HEALTHCHECK`; FastAPI serves the built SPA (one image, one port) · `docker-compose.yml` with healthy `depends_on` · **`render.yaml` Blueprint** (deployment as code)
**Dropped:** the SQLite fallback. It can't enforce the overlap constraint, and we won't ship a mode that's less correct. Docker is the run path.
