import json
from datetime import datetime, timezone
from pathlib import Path

RESULTS_DIR = Path("docs/perf/results")
OUTPUT_REPORT = Path("docs/perf/IOS_EDGE_REPORT.md")
TEMPLATE_PATH = Path("docs/perf/IOS_EDGE_REPORT_TEMPLATE.md")


def latest_result(pattern: str) -> Path | None:
    candidates = sorted(RESULTS_DIR.glob(pattern))
    return candidates[-1] if candidates else None


def load_json(path: Path | None) -> dict:
    if not path:
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    reliability_path = latest_result("ios-edge-reliability-*.json")
    data = load_json(reliability_path)
    template = TEMPLATE_PATH.read_text(encoding="utf-8")

    report = template.format(
        generated_at=datetime.now(timezone.utc).isoformat(),
        readings=data.get("total_daily_sensor_readings", "N/A"),
        reliability=data.get("reliability", "N/A"),
        reliability_target=data.get("reliability_target", "N/A"),
        target_met=data.get("target_met", "N/A"),
        baseline_cost=data.get("baseline_cloud_cost_usd", "N/A"),
        cost_after=data.get("estimated_cloud_cost_after_usd", "N/A"),
        monthly_savings=data.get("estimated_monthly_savings_usd", "N/A"),
        source_file=reliability_path.as_posix() if reliability_path else "N/A",
    )
    OUTPUT_REPORT.write_text(report, encoding="utf-8")
    print(f"Generated: {OUTPUT_REPORT}")


if __name__ == "__main__":
    main()
