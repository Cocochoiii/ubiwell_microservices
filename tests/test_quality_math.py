import pytest

from conftest import load_module

quality_math = load_module("quality_math", "shared/utils/reliability_math.py")


@pytest.mark.parametrize("successes", list(range(1, 111)))
def test_reliability_ratio_stays_bounded(successes: int) -> None:
    ratio = quality_math.reliability_ratio(successes, 200 - successes)
    assert 0.0 <= ratio <= 1.0


@pytest.mark.parametrize(
    ("pre_bugs", "post_bugs", "expected"),
    [
        (100, 20, 80.0),
        (50, 10, 80.0),
        (30, 6, 80.0),
        (10, 2, 80.0),
    ],
)
def test_bug_reduction_percent(pre_bugs: int, post_bugs: int, expected: float) -> None:
    assert quality_math.bug_reduction_percent(pre_bugs, post_bugs) == pytest.approx(expected)


@pytest.mark.parametrize("coverage", [92.0, 92.1, 99.0, 100.0])
def test_coverage_gate_met(coverage: float) -> None:
    assert quality_math.coverage_gate_met(coverage)


def test_coverage_gate_not_met() -> None:
    assert quality_math.coverage_gate_met(91.99) is False


@pytest.mark.parametrize(
    ("pre_hours", "post_hours", "expected_saved"),
    [
        (40.0, 20.0, 20.0),
        (32.5, 12.5, 20.0),
        (25.0, 5.0, 20.0),
    ],
)
def test_weekly_hours_saved(pre_hours: float, post_hours: float, expected_saved: float) -> None:
    assert quality_math.weekly_hours_saved(pre_hours, post_hours) == pytest.approx(expected_saved)


def test_reliability_ratio_with_zero_total() -> None:
    assert quality_math.reliability_ratio(0, 0) == pytest.approx(1.0)


def test_bug_reduction_with_zero_pre_period() -> None:
    assert quality_math.bug_reduction_percent(0, 0) == pytest.approx(0.0)


def test_weekly_hours_saved_when_negative_delta() -> None:
    assert quality_math.weekly_hours_saved(10.0, 12.0) == pytest.approx(0.0)
