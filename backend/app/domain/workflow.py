"""Approval workflow: the state machine and approver routing, as pure functions.

The whole lifecycle is one explicit transition table. Anything not in the table is
illegal and raises ``InvalidTransition`` - there is no other code path that changes a
request's status (DECISIONS.md D-001, RESEARCH.md §2.2).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.enums import Action, LeaveStatus, Role
from app.domain.errors import InvalidTransition, NoApproverAvailable

S, A = LeaveStatus, Action

# (current status, action) -> next status.  Two entries need context and are resolved
# in ``next_status``: APPROVE at level 1 (depends on whether a level 2 exists) and
# RESPOND (returns to whichever level asked for information).
_TRANSITIONS: dict[tuple[LeaveStatus, Action], LeaveStatus | None] = {
    (S.PENDING_MANAGER, A.APPROVE): None,  # -> APPROVED or PENDING_HOD
    (S.PENDING_MANAGER, A.REJECT): S.REJECTED,
    (S.PENDING_MANAGER, A.REQUEST_INFO): S.INFO_REQUESTED,
    (S.PENDING_MANAGER, A.CANCEL): S.CANCELLED,
    (S.PENDING_HOD, A.APPROVE): S.APPROVED,
    (S.PENDING_HOD, A.REJECT): S.REJECTED,
    (S.PENDING_HOD, A.REQUEST_INFO): S.INFO_REQUESTED,
    (S.PENDING_HOD, A.CANCEL): S.CANCELLED,
    (S.INFO_REQUESTED, A.RESPOND): None,  # -> back to the level that asked
    (S.INFO_REQUESTED, A.CANCEL): S.CANCELLED,
}

APPROVER_ACTIONS = frozenset({A.APPROVE, A.REJECT, A.REQUEST_INFO})
EMPLOYEE_ACTIONS = frozenset({A.RESPOND, A.CANCEL})
COMMENT_REQUIRED = frozenset({A.REJECT, A.REQUEST_INFO, A.RESPOND})


def level_status(level: int) -> LeaveStatus:
    return S.PENDING_MANAGER if level == 1 else S.PENDING_HOD


def allowed_actions(status: LeaveStatus) -> set[Action]:
    return {action for (st, action) in _TRANSITIONS if st == status}


def next_status(
    status: LeaveStatus,
    action: Action,
    *,
    has_next_level: bool = False,
    info_requested_level: int | None = None,
) -> LeaveStatus:
    if (status, action) not in _TRANSITIONS:
        raise InvalidTransition(
            _friendly_invalid(status, action),
            details={"status": status.value, "action": action.value},
        )
    target = _TRANSITIONS[(status, action)]
    if target is not None:
        return target
    if action is A.APPROVE:  # level-1 approval
        return S.PENDING_HOD if has_next_level else S.APPROVED
    # RESPOND: go back to the approver who asked
    return level_status(info_requested_level or 1)


def _friendly_invalid(status: LeaveStatus, action: Action) -> str:
    if status.is_final:
        return f"This request is already {status.value.lower()}, so it can't be changed."
    if action is A.RESPOND:
        return "There's no open information request on this leave to respond to."
    verb = action.value.lower().replace("_", " ")
    state = status.value.lower().replace("_", " ")
    return f"You can't {verb} a request that is {state}."


# ---------------------------------------------------------------------------
# Approver routing
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class OrgPerson:
    id: int
    role: Role
    manager_id: int | None
    hod_id: int | None  # HOD of this person's department


@dataclass(frozen=True, slots=True)
class PlannedStep:
    level: int
    approver_id: int
    approver_role: Role  # the capacity they approve in (HR may stand in for a HOD)


def plan_approval_chain(
    employee: OrgPerson, *, escalate: bool, hr_admin_ids: list[int]
) -> list[PlannedStep]:
    """Decide who approves, encoding the real-org edge cases from D-001.

    * Level 1 = reporting manager; falls back to HR if none.
    * Level 2 (only if ``escalate``) = department HOD; falls back to HR when the HOD is
      missing, is the applicant, or already approved at level 1 - so long leave always
      gets two *different* sign-offs.
    * Nobody ever approves their own request.
    """

    def pick_hr(exclude: set[int]) -> int | None:
        return next((h for h in hr_admin_ids if h not in exclude), None)

    steps: list[PlannedStep] = []
    excluded = {employee.id}

    l1_id = employee.manager_id if employee.manager_id not in (None, employee.id) else None
    l1_role = Role.MANAGER
    if l1_id is None:
        l1_id, l1_role = pick_hr(excluded), Role.HR_ADMIN
    if l1_id is None:
        raise NoApproverAvailable(
            "We couldn't find anyone to approve your leave. Please contact HR to set up "
            "your reporting manager."
        )
    steps.append(PlannedStep(1, l1_id, l1_role))
    excluded.add(l1_id)

    if escalate:
        l2_id = employee.hod_id if employee.hod_id not in excluded and employee.hod_id else None
        l2_role = Role.HOD
        if l2_id is None:
            l2_id, l2_role = pick_hr(excluded), Role.HR_ADMIN
        if l2_id is None:
            raise NoApproverAvailable(
                "This leave needs a second approver (HOD or HR) but none is available. "
                "Please contact HR."
            )
        steps.append(PlannedStep(2, l2_id, l2_role))
    return steps
