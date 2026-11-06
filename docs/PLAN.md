# Build Plan

Rule: **every phase ends in a working, committed state.** If time runs out, we ship the last green phase. Items marked ✂️ are the first to be cut.

## Data model

```
departments(id, name, hod_id → users)
users(id, name, email UNIQUE, password_hash, role[EMPLOYEE|MANAGER|HOD|HR_ADMIN], manager_id → users, department_id)
leave_requests(id, employee_id, from_date, to_date, total_days, reason, status, current_step,
               requires_documents bool, info_requested_by_step, version, created_at, updated_at)
    EXCLUDE USING gist (employee_id WITH =, daterange(from_date, to_date, '[]') WITH &&)
            WHERE status NOT IN ('REJECTED','CANCELLED')
    CHECK (to_date >= from_date)
approval_steps(id, request_id, level[1|2], approver_role[MANAGER|HOD|HR_ADMIN], approver_id,
               decision[PENDING|APPROVED|REJECTED|INFO_REQUESTED], comment, decided_at)
attachments(id, request_id, filename, content_type, size, content bytea, uploaded_by, created_at)
comments(id, request_id, author_id, body, kind[COMMENT|INFO_REQUEST|INFO_RESPONSE], created_at)
audit_logs(id, actor_id, via[ui|api|assistant|system], action, entity, entity_id,
           before jsonb, after jsonb, metadata jsonb, request_id(correlation), created_at)   -- append-only
agent_runs(id, user_id, kind[assistant|copilot], input, steps jsonb, output, model, latency_ms, tokens, created_at)
```

## Workflow (single transition table)

| From | Action | Who | To |
|---|---|---|---|
| — | submit | employee | PENDING_MANAGER |
| PENDING_MANAGER | approve | L1 approver | APPROVED (≤3 days) / PENDING_HOD (>3 days) |
| PENDING_HOD | approve | L2 approver | APPROVED |
| PENDING_MANAGER / PENDING_HOD | reject (comment required) | approver at that step | REJECTED |
| PENDING_MANAGER / PENDING_HOD | request_info (comment required) | approver at that step | INFO_REQUESTED |
| INFO_REQUESTED | respond (+ optional documents) | employee | back to the step that asked |
| PENDING_* / INFO_REQUESTED | cancel | employee | CANCELLED |

Validation (server-side always, mirrored client-side): required fields; `toDate ≥ fromDate`; no dates in the past; maximum span of 30 days; reason 5–500 characters; **>3 days → at least one document (PDF/PNG/JPG, ≤5 MB) before submit**; no overlap with your own active leave.

## API (v1)

```
POST /api/auth/login                    GET  /api/auth/me
POST /api/leaves (multipart)            GET  /api/leaves/mine
GET  /api/leaves/{id}  (+timeline)      POST /api/leaves/{id}/cancel
POST /api/leaves/{id}/respond (multipart: comment + files)
GET  /api/approvals/pending             POST /api/approvals/{id}/{approve|reject|request-info}
GET  /api/attachments/{id}  (authorised download)
GET  /api/admin/requests  GET /api/admin/audit   (HR)
POST /api/ai/assistant  (chat → reply + optional draft)
GET  /api/ai/copilot/{request_id}  (summary + flags)
GET  /health  GET /ready
```

## Phases (about 3 h)

| # | Time | Phase | Done when |
|---|---|---|---|
| 0 | 10m | Scaffold: git, backend/frontend skeletons, compose Postgres, Makefile, CI stub | `docker compose up db` + `/health` returns 200 |
| 1 | 35m | Models + Alembic + seed org; workflow state machine + routing + validation as **pure functions with unit tests** | `pytest tests/unit` green |
| 2 | 30m | REST API + JWT/RBAC + attachments + audit + error envelope; **integration tests** (full flows, RBAC denials, concurrency) | `pytest` green against Postgres |
| 3 | 45m | Frontend: login switcher, apply form (live validation, day counter, doc upload when >3), my requests, approvals queue, request detail with timeline, colour-coded statuses, responsive, HR audit view | Golden path works in a browser |
| 4 | 30m | AI: provider interface + Groq/OpenAI-compatible adapter + Fake; assistant agent with tools → draft card → confirm; co-pilot summary; agent_runs; evals | `make eval` reports results; works with and without a key |
| 5 | 20m | Dockerfile (multi-stage, non-root, healthcheck), full compose, Render + Neon deploy | Fresh-clone `docker compose up` works; live URL |
| 6 | 10m | README (diagrams, demo accounts, screenshots), EVALS, AI_USAGE, LIMITATIONS | Submit |

✂️ Cut order if behind: Playwright E2E → HR audit UI (keep the API) → co-pilot → CI → live deploy (Docker stays).
