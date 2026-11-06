import pytest

from app.domain.enums import Action as A
from app.domain.enums import LeaveStatus as S
from app.domain.enums import Role
from app.domain.errors import InvalidTransition, NoApproverAvailable
from app.domain.workflow import OrgPerson, allowed_actions, next_status, plan_approval_chain


class TestStateMachine:
    def test_short_leave_single_approval(self) -> None:
        assert next_status(S.PENDING_MANAGER, A.APPROVE, has_next_level=False) is S.APPROVED

    def test_long_leave_goes_to_hod(self) -> None:
        s = next_status(S.PENDING_MANAGER, A.APPROVE, has_next_level=True)
        assert s is S.PENDING_HOD
        assert next_status(s, A.APPROVE) is S.APPROVED

    @pytest.mark.parametrize("status", [S.PENDING_MANAGER, S.PENDING_HOD])
    def test_either_level_can_reject_or_request_info(self, status: S) -> None:
        assert next_status(status, A.REJECT) is S.REJECTED
        assert next_status(status, A.REQUEST_INFO) is S.INFO_REQUESTED

    @pytest.mark.parametrize(("level", "back_to"), [(1, S.PENDING_MANAGER), (2, S.PENDING_HOD)])
    def test_response_returns_to_the_level_that_asked(self, level: int, back_to: S) -> None:
        assert next_status(S.INFO_REQUESTED, A.RESPOND, info_requested_level=level) is back_to

    @pytest.mark.parametrize("final", [S.APPROVED, S.REJECTED, S.CANCELLED])
    @pytest.mark.parametrize("action", list(A))
    def test_final_states_are_terminal(self, final: S, action: A) -> None:
        with pytest.raises(InvalidTransition, match="already"):
            next_status(final, action)

    def test_cannot_respond_without_info_request(self) -> None:
        with pytest.raises(InvalidTransition):
            next_status(S.PENDING_MANAGER, A.RESPOND)

    def test_cannot_approve_while_waiting_for_info(self) -> None:
        with pytest.raises(InvalidTransition):
            next_status(S.INFO_REQUESTED, A.APPROVE)

    def test_allowed_actions(self) -> None:
        assert allowed_actions(S.INFO_REQUESTED) == {A.RESPOND, A.CANCEL}
        assert allowed_actions(S.APPROVED) == set()


HR = [900, 901]


def person(id: int = 1, manager: int | None = 10, hod: int | None = 20, role: Role = Role.EMPLOYEE):
    return OrgPerson(id=id, role=role, manager_id=manager, hod_id=hod)


class TestRouting:
    def test_short_leave_manager_only(self) -> None:
        steps = plan_approval_chain(person(), escalate=False, hr_admin_ids=HR)
        assert [(s.level, s.approver_id, s.approver_role) for s in steps] == [(1, 10, Role.MANAGER)]

    def test_long_leave_manager_then_hod(self) -> None:
        steps = plan_approval_chain(person(), escalate=True, hr_admin_ids=HR)
        assert [(s.approver_id, s.approver_role) for s in steps] == [
            (10, Role.MANAGER),
            (20, Role.HOD),
        ]

    def test_manager_is_also_hod_routes_level2_to_hr(self) -> None:
        steps = plan_approval_chain(person(manager=20, hod=20), escalate=True, hr_admin_ids=HR)
        assert [(s.approver_id, s.approver_role) for s in steps] == [
            (20, Role.MANAGER),
            (900, Role.HR_ADMIN),
        ]

    def test_hod_applying_never_self_approves(self) -> None:
        steps = plan_approval_chain(
            person(id=20, manager=50, hod=20, role=Role.HOD), escalate=True, hr_admin_ids=HR
        )
        assert all(s.approver_id != 20 for s in steps)
        assert steps[1].approver_role is Role.HR_ADMIN

    def test_no_manager_falls_back_to_hr(self) -> None:
        steps = plan_approval_chain(person(manager=None), escalate=False, hr_admin_ids=HR)
        assert steps[0].approver_role is Role.HR_ADMIN

    def test_hr_applying_is_approved_by_other_hr(self) -> None:
        steps = plan_approval_chain(
            person(id=900, manager=None, hod=None, role=Role.HR_ADMIN),
            escalate=True,
            hr_admin_ids=[*HR, 902],
        )
        assert [s.approver_id for s in steps] == [901, 902]

    def test_no_approver_at_all_is_a_clear_error(self) -> None:
        with pytest.raises(NoApproverAvailable):
            plan_approval_chain(person(manager=None), escalate=False, hr_admin_ids=[])

    def test_two_distinct_signoffs_always(self) -> None:
        with pytest.raises(NoApproverAvailable):
            plan_approval_chain(person(manager=900, hod=None), escalate=True, hr_admin_ids=[900])
