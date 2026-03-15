from __future__ import annotations


def reliability_ratio(successes: int, failures: int) -> float:
    total = successes + failures
    if total <= 0:
        return 1.0
    return successes / total


def coverage_gate_met(coverage_percent: float, threshold_percent: float = 92.0) -> bool:
    return coverage_percent >= threshold_percent


def bug_reduction_percent(pre_period_bugs: int, post_period_bugs: int) -> float:
    if pre_period_bugs <= 0:
        return 0.0
    reduced = pre_period_bugs - post_period_bugs
    return (reduced / pre_period_bugs) * 100.0


def weekly_hours_saved(pre_hours_per_week: float, post_hours_per_week: float) -> float:
    saved = pre_hours_per_week - post_hours_per_week
    return saved if saved > 0 else 0.0
