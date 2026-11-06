"""Domain enumerations shared by models, schemas, services and the AI layer."""

from enum import StrEnum


class Role(StrEnum):
    EMPLOYEE = "EMPLOYEE"
    MANAGER = "MANAGER"
    HOD = "HOD"
    HR_ADMIN = "HR_ADMIN"


class LeaveStatus(StrEnum):
    PENDING_MANAGER = "PENDING_MANAGER"
    PENDING_HOD = "PENDING_HOD"
    INFO_REQUESTED = "INFO_REQUESTED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"

    @property
    def is_final(self) -> bool:
        return self in {LeaveStatus.APPROVED, LeaveStatus.REJECTED, LeaveStatus.CANCELLED}

    @property
    def is_active(self) -> bool:
        """Active requests block overlapping dates (mirrors the DB exclusion constraint)."""
        return self not in {LeaveStatus.REJECTED, LeaveStatus.CANCELLED}


class Action(StrEnum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    REQUEST_INFO = "REQUEST_INFO"
    RESPOND = "RESPOND"
    CANCEL = "CANCEL"


class StepDecision(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    INFO_REQUESTED = "INFO_REQUESTED"
    SKIPPED = "SKIPPED"  # request cancelled/rejected before this step was reached


class Channel(StrEnum):
    """How an action entered the system - recorded on every audit row."""

    UI = "ui"
    API = "api"
    ASSISTANT = "assistant"
    SYSTEM = "system"
