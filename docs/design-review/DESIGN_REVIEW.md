# Design Review: Akasa Leave portal

Reviewed against: the assignment brief (RESEARCH.md §1) and the committed direction (DECISIONS.md D-015, D-023)
Philosophy: "Ops desk at dawn". Night-sky ink, cloud surfaces, one sunrise accent, departure-board dates, approval legs as a route.
Date: 2026-11-06

## Screenshots Captured

| Screenshot | Breakpoint | Description |
|---|---|---|
| `screenshots/review-login-{mobile-375,tablet-768,desktop-1280}.png` | all | Sign-in with demo accounts; product ticket as the visual |
| `screenshots/review-my-leave-*.png` | all | Apply form + history (employee) |
| `screenshots/review-request-sheet-*.png` | all | Deep-linked `?request=3` sheet (legs, documents, comments) |
| `screenshots/review-approvals-*.png` | all | Approver queue |
| `screenshots/review-team-*.png` | all | Team calendar roster grid |

Captured with Playwright driving headless Edge (no Playwright MCP was available in this environment).

## Summary
The interface carries its own visual language and every brief requirement is reachable in seconds. The review found one real accessibility/visual bug: the global focus style reshaped round buttons. It also found two mobile composition issues. All three are fixed and re-verified at 375px.

## Must Fix (fixed)
1. **Focus ring reshaped controls.** The global `:focus-visible` set `border-radius: 6px`, so round icon buttons turned square when focused. This was visible on the sheet's close button, which Radix auto-focuses (`review-request-sheet-mobile-375.png`, before). _Fix: the outline now follows each element's own radius, and the sheet focuses its container on open._

## Should Fix (fixed)
1. **Approval legs wrapped mid-route on mobile**, leaving a dangling connector line. _Fix: they're a vertical stepper below `sm` and a horizontal route above it._
2. **A lone "Withdraw" button floated in an empty card** when it was the only action. _Fix: one compact row ("Plans changed? You can withdraw until it's decided.") with an inline two-step confirm._

## Could Improve (not done, recorded)
1. **Dark mode:** none. It's an internal tool used in offices and hangars by day. If crew use it on night layovers, a dark theme would be the next design investment.
2. **Delegate picker** is a native `<select>` (accessible, but can't be styled to the token system). A Radix Select would match the rest.
3. **Team calendar on phones** shows about 3 days at a time (sticky names plus horizontal scroll). A per-person agenda list would read better below 480px.

## What Works Well
- **The signature is consistent:** departure-board dates, approval legs, coverage cells and the roster grid all read as one airline-ops system.
- **Status is never colour-only.** Every status carries an icon and a label, and the palette meets WCAG AA after the impeccable pass.
- **Server-driven affordances** (`allowedActions`) mean no screen ever shows a button that would fail.
- **Restraint in motion:** popovers grow out of their trigger, state changes settle in, and nothing animates on high-frequency actions.
