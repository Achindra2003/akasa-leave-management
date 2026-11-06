"""A deterministic, offline stand-in for an LLM.

Why it exists (D-008/D-012): tests and evals must be reproducible and free, and assessors
without an API key should still see the full agent flow (tool calls -> draft ->
human confirmation). It implements the same ``BaseChatModel`` + tool-calling interface as
the real providers, so the graphs run unchanged.

It understands a small, predictable grammar - ISO dates, "today/tomorrow", weekday names,
"next week", "N days", "for <reason>" - and is honest about being a demo model.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import date, timedelta
from typing import Any

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult

_WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
_MONTHS = {
    m: i + 1
    for i, m in enumerate(
        ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
    )
}


def _today_from(messages: list[BaseMessage]) -> date:
    for m in messages:
        if isinstance(m, SystemMessage):
            hit = re.search(r"Today is (\d{4}-\d{2}-\d{2})", str(m.content))
            if hit:
                return date.fromisoformat(hit.group(1))
    return date.today()


def parse_dates(text: str, today: date) -> tuple[date | None, date | None]:
    t = text.lower()
    iso = re.findall(r"\d{4}-\d{2}-\d{2}", t)
    if iso:
        a = date.fromisoformat(iso[0])
        return a, date.fromisoformat(iso[1]) if len(iso) > 1 else a

    # "12 nov" / "nov 12" style
    dm = re.findall(r"(\d{1,2})(?:st|nd|rd|th)?\s+(" + "|".join(_MONTHS) + r")[a-z]*", t)
    md = re.findall(r"(" + "|".join(_MONTHS) + r")[a-z]*\s+(\d{1,2})(?!\d)", t)
    pairs = [(int(d), _MONTHS[m]) for d, m in dm] or [(int(d), _MONTHS[m]) for m, d in md]
    if pairs:

        def mk(day: int, month: int) -> date:
            y = today.year + (1 if (month, day) < (today.month, today.day) else 0)
            return date(y, month, day)

        a = mk(*pairs[0])
        b = mk(*pairs[1]) if len(pairs) > 1 else a
        return a, b

    start: date | None = None
    if "day after tomorrow" in t:
        start = today + timedelta(days=2)
    elif "tomorrow" in t:
        start = today + timedelta(days=1)
    elif "today" in t:
        start = today
    elif "next week" in t:
        start = today + timedelta(days=7 - today.weekday())
    names = [w for w in _WEEKDAYS if w in t]
    if names and start is None:
        idx = _WEEKDAYS.index(names[0])
        delta = (idx - today.weekday()) % 7 or 7
        start = today + timedelta(days=delta)
    if start is None:
        return None, None

    n = re.search(r"(\d+)\s*(?:days?|d\b)", t)
    if n:
        return start, start + timedelta(days=int(n.group(1)) - 1)
    if len(names) > 1:
        idx2 = _WEEKDAYS.index(names[1])
        end = start + timedelta(days=(idx2 - start.weekday()) % 7)
        return start, end
    return start, start


def parse_reason(text: str) -> str | None:
    m = re.search(r"\b(?:for|because|reason[:\s]|due to)\s+(.+)$", text, re.IGNORECASE)
    if not m:
        return None
    reason = re.sub(r"\s+", " ", m.group(1)).strip(" .")
    # drop trailing date fragments like "from monday" that belong to the date clause
    reason = re.split(r"\b(?:from|on|starting|between)\b", reason, maxsplit=1)[0].strip(" ,.")
    return reason[:200] or None


class ScriptedLeaveModel(BaseChatModel):
    """Rule-based tool-calling model. See module docstring."""

    @property
    def _llm_type(self) -> str:
        return "scripted-leave-model"

    def bind_tools(self, tools: Any, **kwargs: Any) -> ScriptedLeaveModel:  # type: ignore[override]
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        return ChatResult(generations=[ChatGeneration(message=self._respond(messages))])

    # ------------------------------------------------------------------ logic
    def _respond(self, messages: list[BaseMessage]) -> AIMessage:
        system = next((str(m.content) for m in messages if isinstance(m, SystemMessage)), "")
        if "ROLE: APPROVER_COPILOT" in system:
            return AIMessage(content=self._copilot(messages))

        last = messages[-1]
        if isinstance(last, ToolMessage):
            return AIMessage(content=self._after_tool(last))

        text = str(last.content) if isinstance(last, HumanMessage) else ""
        low = text.lower()
        today = _today_from(messages)

        if re.search(r"\b(status|my (leaves|requests)|history|pending|approved\?)\b", low):
            return self._call("list_my_requests", {})
        if re.search(r"\b(policy|rule|how many days|document)\b", low) and "leave" not in low[:6]:
            return self._call("get_leave_policy", {})

        start, end = parse_dates(text, today)
        if start and end:
            reason = parse_reason(text)
            if not reason:
                return AIMessage(
                    content=f"Got it - {start:%a %d %b} to {end:%a %d %b}. "
                    'What\'s the reason for the leave? (e.g. "for a family function")'
                )
            return self._call(
                "draft_leave_request",
                {"from_date": start.isoformat(), "to_date": end.isoformat(), "reason": reason},
            )
        if any(w in low for w in ("leave", "off", "holiday", "vacation", "sick")):
            return AIMessage(
                content='Sure - which dates? You can say things like "tomorrow", '
                '"next Monday for 3 days" or "2026-12-01 to 2026-12-03".'
            )
        return AIMessage(
            content="I'm the leave assistant (offline demo model). I can draft a leave "
            "request for you, or show the status of your requests. Try: "
            '"I need leave next Monday for 2 days for my cousin\'s wedding".'
        )

    def _call(self, name: str, args: dict[str, Any]) -> AIMessage:
        return AIMessage(
            content="",
            tool_calls=[{"name": name, "args": args, "id": f"call_{uuid.uuid4().hex[:12]}"}],
        )

    def _after_tool(self, msg: ToolMessage) -> str:
        try:
            data = json.loads(str(msg.content))
        except json.JSONDecodeError:
            return "Something went wrong looking that up. Please try again."
        if msg.name == "list_my_requests":
            items = data.get("requests", [])
            if not items:
                return "You don't have any leave requests yet."
            lines = [
                f"- #{r['id']} {r['fromDate']} -> {r['toDate']} ({r['totalDays']}d): "
                f"**{r['status'].replace('_', ' ').title()}**"
                for r in items[:5]
            ]
            return "Here are your latest requests:\n" + "\n".join(lines)
        if msg.name == "get_leave_policy":
            return (
                f"Leave longer than {data['escalationThresholdDays']} consecutive days needs a "
                "supporting document and two approvals (Manager, then HOD). A single request "
                f"can cover up to {data['maxSpanDays']} days."
            )
        if msg.name == "draft_leave_request" and not data.get("ok"):
            return "I couldn't draft that: " + data.get("message", "please check the dates.")
        return "Done."

    def _copilot(self, messages: list[BaseMessage]) -> str:
        human = next(
            (str(m.content) for m in reversed(messages) if isinstance(m, HumanMessage)), ""
        )
        hit = re.search(r"<facts>(.*?)</facts>", human, re.DOTALL)
        facts = json.loads(hit.group(1)) if hit else {}
        flags: list[dict[str, str]] = []
        if facts.get("requiresDocuments") and not facts.get("attachments"):
            flags.append({"level": "high", "text": "Documents are required but none attached."})
        overlaps = facts.get("teamOverlaps", [])
        if overlaps:
            names = ", ".join(o["employeeName"] for o in overlaps[:3])
            flags.append(
                {
                    "level": "medium",
                    "text": f"{len(overlaps)} teammate(s) off on overlapping dates: {names}.",
                }
            )
        if facts.get("noticeDays", 99) < 2:
            flags.append({"level": "medium", "text": "Short notice (less than 2 days)."})
        if facts.get("recentRequestCount", 0) >= 3:
            flags.append(
                {
                    "level": "low",
                    "text": f"{facts['recentRequestCount']} requests in the last 90 days.",
                }
            )
        if not flags:
            flags.append({"level": "info", "text": "No conflicts or missing information found."})
        rec = "review" if any(f["level"] in ("high", "medium") for f in flags) else "looks_fine"
        questions = []
        if overlaps:
            questions.append("Who will cover the shifts during this period?")
        if facts.get("requiresDocuments") and not facts.get("attachments"):
            questions.append("Can you upload the supporting document?")
        return json.dumps(
            {
                "summary": (
                    f"{facts.get('employeeName', 'The employee')} requests "
                    f"{facts.get('totalDays')} "
                    f"day(s) ({facts.get('fromDate')} to {facts.get('toDate')}) for: "
                    f'"{facts.get("reason", "")}".'
                ),
                "flags": flags,
                "suggestedQuestions": questions,
                "recommendation": rec,
            }
        )
