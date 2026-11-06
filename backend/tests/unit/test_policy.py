from datetime import date

import pytest

from app.domain.errors import DocumentsRequired, ValidationFailed
from app.domain.policy import (
    DocumentMeta,
    LeavePolicy,
    calendar_days,
    ranges_overlap,
    requires_escalation,
    validate_leave_request,
    working_days,
)

TODAY = date(2026, 11, 6)  # a Friday
PDF = DocumentMeta("cert.pdf", "application/pdf", 1024)


class TestDayCounting:
    def test_brief_example_is_five_days(self) -> None:
        assert calendar_days(date(2026, 11, 1), date(2026, 11, 5)) == 5

    def test_single_day(self) -> None:
        assert calendar_days(TODAY, TODAY) == 1

    def test_working_days_skip_weekend(self) -> None:
        # Fri 6 -> Mon 9: 4 calendar days, 2 working days
        assert calendar_days(date(2026, 11, 6), date(2026, 11, 9)) == 4
        assert working_days(date(2026, 11, 6), date(2026, 11, 9)) == 2

    @pytest.mark.parametrize(("days", "expected"), [(1, False), (3, False), (4, True), (30, True)])
    def test_escalation_threshold_is_strictly_more_than_three(
        self, days: int, expected: bool
    ) -> None:
        assert requires_escalation(days) is expected

    def test_threshold_is_configurable(self) -> None:
        assert requires_escalation(3, LeavePolicy(escalation_threshold_days=2)) is True


class TestValidation:
    def ok(self, **overrides: object) -> int:
        kwargs: dict[str, object] = {
            "from_date": date(2026, 11, 10),
            "to_date": date(2026, 11, 12),
            "reason": "Family function",
            "today": TODAY,
        }
        kwargs.update(overrides)
        return validate_leave_request(**kwargs)  # type: ignore[arg-type]

    def test_valid_short_leave_returns_days(self) -> None:
        assert self.ok() == 3

    def test_today_is_allowed(self) -> None:
        assert self.ok(from_date=TODAY, to_date=TODAY) == 1

    def test_end_before_start(self) -> None:
        with pytest.raises(ValidationFailed) as e:
            self.ok(from_date=date(2026, 11, 12), to_date=date(2026, 11, 10))
        assert "toDate" in e.value.details["fields"]

    def test_past_start(self) -> None:
        with pytest.raises(ValidationFailed) as e:
            self.ok(from_date=date(2026, 11, 1), to_date=date(2026, 11, 2))
        assert "fromDate" in e.value.details["fields"]

    def test_collects_all_field_errors_at_once(self) -> None:
        with pytest.raises(ValidationFailed) as e:
            self.ok(from_date=date(2026, 11, 1), to_date=date(2026, 10, 30), reason="x")
        assert set(e.value.details["fields"]) == {"fromDate", "toDate", "reason"}

    def test_span_limit(self) -> None:
        with pytest.raises(ValidationFailed) as e:
            self.ok(to_date=date(2026, 12, 31), documents=[PDF])
        assert "split" in e.value.details["fields"]["toDate"]

    def test_blank_reason_is_rejected(self) -> None:
        with pytest.raises(ValidationFailed):
            self.ok(reason="     ")

    def test_more_than_three_days_requires_documents(self) -> None:
        with pytest.raises(DocumentsRequired) as e:
            self.ok(to_date=date(2026, 11, 13))  # 4 days
        assert e.value.details["totalDays"] == 4

    def test_more_than_three_days_with_document_passes(self) -> None:
        assert self.ok(to_date=date(2026, 11, 13), documents=[PDF]) == 4

    @pytest.mark.parametrize(
        ("doc", "msg"),
        [
            (DocumentMeta("x.exe", "application/x-msdownload", 10), "isn't supported"),
            (DocumentMeta("big.pdf", "application/pdf", 6 * 1024 * 1024), "larger than"),
            (DocumentMeta("empty.pdf", "application/pdf", 0), "empty"),
        ],
    )
    def test_bad_documents(self, doc: DocumentMeta, msg: str) -> None:
        with pytest.raises(ValidationFailed, match="highlighted") as e:
            self.ok(documents=[doc])
        assert msg in e.value.details["fields"]["documents"]


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        ((1, 5), (5, 8), True),  # shared boundary day overlaps (inclusive)
        ((1, 5), (6, 8), False),  # back-to-back is fine
        ((3, 4), (1, 10), True),  # contained
    ],
)
def test_ranges_overlap(a: tuple[int, int], b: tuple[int, int], expected: bool) -> None:
    d = lambda n: date(2026, 11, n)  # noqa: E731
    assert ranges_overlap(d(a[0]), d(a[1]), d(b[0]), d(b[1])) is expected
