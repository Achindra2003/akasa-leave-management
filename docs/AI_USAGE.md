# How AI Tools Were Used to Build This

"Usage of AI tools" is one of the evaluated skills, so this is an honest account. The build was done pair-programming with **Claude Code** (an agentic coding CLI). I directed it, reviewed the work, and made the calls. The AI wrote most of the code under that direction.

## Division of labour

| I (the engineer) did | The AI assistant did |
|---|---|
| Set scope and constraints: 3-hour box, production-grade, decision log, tests, deployable | Researched production leave-system designs and HR-agent guardrails (with sources) → `RESEARCH.md` |
| Answered the brief's open questions: calendar-day counting, stack, AI scope, Postgres (Neon) + Render | Proposed options with trade-offs for each, and recorded the chosen ones in `DECISIONS.md` |
| Pushed for real-org thinking ("who else uses this system?") | Wrote the stakeholder analysis and routing edge cases (manager = HOD, HOD self-apply, no approver) |
| Required **LangGraph** and a **model-agnostic** layer (Groq by default) | Verified the current LangGraph 1.2 API with a probe script *before* writing agent code |
| Chose the design skills to apply and the "airline" framing | Wrote the domain layer, API, migrations, frontend, tests, Docker, CI and evals |
| Reviewed the output and asked for corrections | Ran tests, E2E and evals after each step and fixed what failed |

## Where the AI was wrong, and how each was caught
Every one of these was caught by a test, a type-check or a visual check, not noticed by luck:

1. **A lint "fix" broke runtime code.** A bulk text replacement meant for a Pydantic field (`steps = []` → `Field(default_factory=list)`) hit a local variable instead. **Caught by:** 9 failing AI integration tests (`'FieldInfo' object has no attribute 'append'`).
2. **Timezone bug.** "Today" was computed in UTC, so an IST user applying at 00:30 would be told their leave "starts in the past". Also, a tool parsed a full datetime with `date.fromisoformat`, which fails on Python 3.11. **Caught by:** assistant tests producing no draft. **Fixed with** a single org-timezone clock (`app/core/clock.py`).
3. **Login never completed in the browser.** `queryClient.clear()` detached the React Query observer for the current user, so the app bounced back to `/login`. **Caught by:** the Playwright E2E. The API tests passed because the bug was purely client-side.
4. **Blank screen after the assistant replied.** `useEffect(() => el.scrollIntoView())` implicitly returned `scrollIntoView`'s result. Current Chromium returns a **Promise**, and React called it as a cleanup function ("l is not a function"). **Caught by:** E2E, then diagnosed from the `pageerror` event.
5. **The demo model parsed "Friday to Monday" backwards.** **Caught by:** the agent eval golden set (11/12 on the first run). See `EVALS.md`.
6. **The docs overstated the code.** The README claimed documents sat "behind a storage interface" that was planned but never built. **Caught by:** reviewing the docs against the code before submitting. The claim was corrected, and D-007 now says so plainly.
7. **A wrong unit-test expectation** (an HR-applies-for-leave case with too few HR admins). The test was wrong, not the code. The routing correctly refused rather than allowing self-approval, so the test was fixed with an extra HR admin.

## Practices that kept AI-written code trustworthy
- **Tests against real infrastructure** (Postgres, a real browser), not mocks. Bugs 3 and 4 would have been invisible otherwise.
- **The AI verified library APIs by running them** (a LangGraph probe script) rather than relying on memory.
- **Small, committed phases.** Every phase ended green and was committed, so the git history shows how the build progressed.
- **The decision log was written during the build**, not reconstructed afterwards.
- **Evals for the AI feature itself**, with failures reported and not hidden.
