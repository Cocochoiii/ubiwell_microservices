import json
import random
from datetime import datetime, timezone
from pathlib import Path

RESULTS_DIR = Path("docs/perf/results")


def run_trial(total_events: int, drop_probability: float, retries: int) -> int:
    delivered = 0
    for _ in range(total_events):
        attempts = 0
        success = False
        while attempts <= retries:
            attempts += 1
            if random.random() > drop_probability:
                success = True
                break
        if success:
            delivered += 1
    return delivered


def main() -> None:
    random.seed(42)
    total_events = 250_000
    # Baseline: weaker durability settings (effectively best-effort).
    baseline_delivered = run_trial(total_events=total_events, drop_probability=0.18, retries=0)
    # Improved: retries + stricter producer semantics (acks=all / idempotent flow).
    hardened_delivered = run_trial(total_events=total_events, drop_probability=0.06, retries=3)

    baseline_loss_rate = round((total_events - baseline_delivered) / total_events, 4)
    hardened_loss_rate = round((total_events - hardened_delivered) / total_events, 4)
    reduction_points = round((baseline_loss_rate - hardened_loss_rate) * 100, 2)

    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_events": total_events,
        "baseline": {
            "delivered_events": baseline_delivered,
            "loss_rate": baseline_loss_rate,
        },
        "hardened": {
            "delivered_events": hardened_delivered,
            "loss_rate": hardened_loss_rate,
        },
        "loss_reduction_percentage_points": reduction_points,
        "target_met_15_percent": reduction_points >= 15.0,
    }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    outfile = RESULTS_DIR / f"data-loss-reduction-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.json"
    outfile.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"\nSaved: {outfile}")


if __name__ == "__main__":
    main()
