# Research Notes — Employee Leave Management System

This is the pre-build research, done on 2026-11-06 before writing any code. It covers how production leave and HRMS systems are usually designed and how an AI agent can be added safely. Each finding is mapped to what it means for this assignment. Final decisions and their reasons are in [`DECISIONS.md`](./DECISIONS.md).

---

## 1. The assignment (from `Christ-FS-Coding-LeaveTracker.docx`)

| Area | Requirement |
|---|---|
| Employee | Apply for leave, view leave history and status, attach documents |
| Manager | View pending requests, approve or reject with comments, view documents, **ask for more information** |
| Validation | **If consecutive leave is more than 3 days, documents are mandatory and two approvals are needed: Manager, then HOD** |
| Payload | `employeeName`, `fromDate`, `toDate`, `reason` |
| Deliverable | **Something the assessors can run themselves**, plus a README with run instructions |
| Evaluated on | Workflow implementation, form validation, CRUD, **use of AI tools**, code and system knowledge |
| Plus points | Audit logs, friendly error messages, colour coding in the UI, responsive web/mobile layout |

The heaviest-weighted items are the **workflow**, the **portal UI**, and the **"use of AI tools"** (an agentic feature fits here directly).

---

## 2. How production leave systems are built

### 2.1 Core entities
Production LLDs and HRMS products such as Odoo, Oracle HCM and Keka share a common set of entities:
- **User / Employee**, with a role and a reporting line (`manager_id`; the HOD is found through the department)
- **Department**, which has an HOD
- **LeaveType**: policy stored as data (paid?, documentation required?, accrual rate, carry-forward cap) instead of hard-coded
- **LeaveRequest**, whose status follows a state machine
- **Approval / ApprovalStep**, one row per approver decision. Multi-level chains are rows, not columns.
- **Attachment**
- **AuditLog** (append-only)
- *(Optional)* **LeaveBalance and a LeaveTransaction ledger**: append-only grant/consume/reversal rows with the balance derived from them, and idempotent accrual jobs keyed by period

**Implication:** model approvals as a separate `approval_steps` table so "Manager → HOD" is just data, and adding a third level later needs no schema change. Balances and accrual are **not in the spec**, so they are noted as a future extension.

### 2.2 Request state machine
The usual production lifecycle is `PENDING → APPROVED → TAKEN`, `PENDING → REJECTED`, `APPROVED → CANCELLED`. Multi-level systems route long absences to a second approver (HR or HOD) after the manager.

Mapped to our spec:
```
                    ┌─────────── request info ───────────┐
                    ▼                                    │
 SUBMIT ─► PENDING_MANAGER ──approve──► (≤3 days) APPROVED
              │    ▲                 └► (>3 days) PENDING_HOD ──approve──► APPROVED
              │    │ employee responds              │   ▲
              │    └──── INFO_REQUESTED ◄───────────┘   │ (HOD can also request info)
              ├──reject──► REJECTED   (HOD can reject too)
              └──withdraw (employee)──► CANCELLED   (allowed while not final)
```
- Transitions are kept in **one explicit table** (`(state, action, role) → next_state`). Any other move is rejected with a clear 409 error. This keeps the workflow testable and stops illegal jumps (for example, an HOD approving before the manager).
- `INFO_REQUESTED` remembers which stage asked, so the employee's response goes back to that same approver.

### 2.3 Concurrency and integrity
- A plain "check for overlap, then insert" is a **race**: two simultaneous submissions can both pass the check.
- The production fix in Postgres is an **exclusion constraint**: `EXCLUDE USING gist (employee_id WITH =, daterange(from,to,'[]') WITH &&) WHERE (status NOT IN ('REJECTED','CANCELLED'))` with `btree_gist`. The database itself guarantees no overlapping active leaves.
- For approver actions, use **optimistic locking** (a `version` column) so two managers clicking at the same moment can't both act on the same request.
- Every state change and its audit row are written **in the same DB transaction**.

### 2.4 "Consecutive days" counting
HRMS products count leave as **business days** (excluding weekends and public holidays). Policies such as India's "sandwich rule" count intervening weekends when leave surrounds them. The assignment only says "consecutive leaves more than 3", so this is an **assumption we have to state**. → see DECISIONS.md.

### 2.5 Documents
Industry practice: medical or supporting certificates become mandatory beyond about 2–3 consecutive days, which matches the assignment's threshold of 3. Good practice is to whitelist MIME types (pdf/png/jpg), cap file size, store under random names (never the user-supplied path), and serve files only through an authorised endpoint, never as a public static folder.

### 2.6 Audit logs
Use an append-only table: `actor, action, entity, entity_id, before/after (JSON), comment, timestamp, request_id/correlation id`. Never update or delete rows. Expose it as a per-request timeline in the UI, because it doubles as the "history" the user sees.

---

## 3. Making it agentic: how production HR agents work

The field is moving from FAQ bots to agents that **complete the request**. Recurring production patterns:

| Pattern | What it means for us |
|---|---|
| **Tool calling, not free text.** The model proposes tool calls (`check_overlap`, `get_my_requests`, `draft_leave_request`) and the application executes them | The agent calls our **existing service layer**, so every business rule still applies |
| **Agent acts with the user's own permissions**, never as a service account with full access | Each tool runs under the logged-in user's identity and RBAC |
| **Human confirmation before write actions** | The agent **drafts**; the user clicks **Confirm** to submit. The agent never submits, approves or rejects on its own |
| **Agent never denies, only humans decide** | For managers the agent only **summarises and flags**; the approve/reject buttons stay human |
| **Ask a clarifying question when dates or type are ambiguous** | Natural-language dates ("next Mon to Wed") are resolved against today's date and echoed back for confirmation |
| **Prompt-injection defence.** Free-text fields (reason, comments) are untrusted | Leave reasons are passed to the model as data and never let it bypass a tool's checks; tools re-validate everything |
| **Audit what the agent did and why** | Agent-initiated drafts and submissions are tagged `via=assistant` in the audit log |
| **Fail closed and degrade gracefully** | No API key, or the model is down → the portal still works fully and the assistant panel shows "unavailable" |

Agent features worth building, ranked by value against the time they take:
1. **Employee assistant:** "I need leave from next Monday to Thursday for my sister's wedding" → structured draft (dates resolved, day count, a warning that >3 days needs documents and HOD approval) → user confirms. *Directly addresses "Usage of AI tools" and "Form validation".*
2. **Approver co-pilot:** a one-click summary for managers/HODs: request facts, overlapping team leaves, document present?, previous requests, suggested questions to ask. Advisory only.
3. *(Stretch)* "What's the status of my leave?" Q&A over the user's own data.

---

## 4. Production-grade engineering checklist

- **Layered backend:** routers (HTTP) → services (business rules and the state machine) → repositories/ORM. Pydantic schemas at the boundary.
- **Config via environment variables** (12-factor), with `.env.example` committed.
- **Migrations** (Alembic), not `create_all` in production.
- **Consistent error envelope:** `{ "error": { "code", "message", "details" } }` with human-friendly messages, so the UI can show them directly (a plus point).
- **AuthN/AuthZ:** JWT login, role-based guards (EMPLOYEE / MANAGER / HOD). A manager only sees their own reports, and an HOD only their department.
- **Structured logging** with a request ID; `/health` (liveness) and `/ready` (DB check) endpoints.
- **OpenAPI/Swagger** docs, generated automatically.
- **Testing pyramid:** unit tests (state machine, day counting, validators) → API integration tests (full approve/reject/info flows, RBAC denials, upload validation) → a few E2E smoke tests. CI-style `make test`.
- **Docker:** multi-stage build, non-root user, healthcheck, `docker compose up` brings up app + DB with seed data. A single command for assessors.
- **Seed data and demo accounts** so assessors can log in as Employee, Manager and HOD immediately.

---

## 5. Out of scope (researched, deliberately deferred)
- Leave balances, accrual and the carry-forward ledger: not required. Would be added as an append-only `leave_transactions` ledger.
- Public-holiday calendar per region: would plug into the day-counting function.
- Email/Slack notifications: would hook onto the same domain events that write audit rows.
- SSO/OIDC: we use local JWT auth for the demo.

---

## Sources
- [Low-Level Design: Employee Leave Management System (techinterview.org)](https://www.techinterview.org/post/3233464881/lld-employee-leave-management/)
- [Odoo – eh_hr_leave_pro (append-only ledger, idempotent accrual)](https://apps.odoo.com/apps/modules/17.0/eh_hr_leave_pro)
- [Oracle HCM – Managing Leave Accrual](https://docs.oracle.com/cd/G40410_01/hcm92pbr53/eng/hcm/hpay/ManagingLeaveAccrual-3e39ce.html)
- [Udyamo HRMS – Applying & Approving Leaves](https://udyamo-hrms-book.pages.dev/en/part-5/ch24-applying-approving-leaves)
- [ClayHR – Why overlapping leave requests are allowed](https://www.clayhr.com/articles/why-does-clayhr-allow-overlapping-leave-requests)
- [Supabase – Range columns & exclusion constraints](https://supabase.com/blog/range-columns)
- [Preventing double bookings with PostgreSQL exclusion constraints (DEV)](https://dev.to/ripazocom/preventing-double-bookings-with-postgresql-exclusion-constraints-5efn)
- [Cybertec – PostgreSQL EXCLUDE beyond UNIQUE](https://www.cybertec-postgresql.com/en/postgresql-exclude-beyond-unique/)
- [Keka – Leave policy in India](https://www.keka.com/compliance/leave-policy)
- [Payoneer – Leave policy in India 2026](https://www.payoneer.com/resources/workforce-management/leave-policy/india/)
- [Rework – Time Off and Leave Agent build blueprint](https://resources.rework.com/vi/libraries/ai-agents/ai-time-off-leave-agent)
- [Workativ – HR AI agent for leave management](https://workativ.com/blog/hr-ai-agent-for-leave-management-automate-from-request-to-approval)
- [C# Corner – Employee leave request agent](https://www.c-sharpcorner.com/article/ai-agents-in-practice-employee-leave-request-agent)
- [OWASP – AI Agent Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/AI%5FAgent%5FSecurity%5FCheat%5FSheet.html)
- [Hardening AI features against prompt injection (DEV)](https://dev.to/kowshik_jallipalli_a7e0a5/hardening-ai-features-practical-defense-against-prompt-injection-and-risky-tools-3b)
- [FastAPI production template (GitHub)](https://github.com/aidynomirtay/fastapi_production_template)
- [cookiecutter-fastapi-docker (GitHub)](https://github.com/vitalk/cookiecutter-fastapi-docker)
