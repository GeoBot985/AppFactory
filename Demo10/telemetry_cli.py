import sys
import argparse
from pathlib import Path
from datetime import date
from telemetry.aggregator import TelemetryAggregator
from telemetry.query import TelemetryQuery
from telemetry.alerts import TelemetryAlerts
from telemetry.dashboard import TelemetryDashboard

def main():
    parser = argparse.ArgumentParser(description="Demo10 Telemetry CLI")
    subparsers = parser.add_subparsers(dest="command")

    # summary
    subparsers.add_parser("summary", help="Show system health summary")

    # metrics
    metrics_parser = subparsers.add_parser("metrics", help="Show specific metrics")
    metrics_parser.add_argument("--name", help="Metric name")
    metrics_parser.add_argument("--range", type=int, default=7, help="Range in days")

    # alerts
    subparsers.add_parser("alerts", help="Show recent alerts")

    # generate-dashboard
    subparsers.add_parser("generate-dashboard", help="Generate HTML dashboard")

    # aggregate (manual trigger)
    subparsers.add_parser("aggregate", help="Trigger deterministic aggregation for today")

    args = parser.parse_args()
    workspace_root = Path(".")

    if args.command == "aggregate":
        aggregator = TelemetryAggregator(workspace_root)
        agg = aggregator.aggregate_day(date.today())
        print(f"Aggregation complete for {date.today()}")
        print(agg.model_dump_json(indent=2))

    elif args.command == "summary":
        query = TelemetryQuery(workspace_root)
        stats = query.get_summary_stats(7)
        print("\nSYSTEM HEALTH SUMMARY (Last 7 Days)\n")
        print(f"Runs: {stats.get('runs_total', 0)}")
        print(f"Failures: {stats.get('runs_failed', 0)} ({stats.get('failure_rate', 0):.1%})")

        agg = query.get_daily_aggregate(date.today())
        if agg:
            print(f"\nVerification:")
            print(f"Pass: {agg.verification_pass}")
            print(f"Warn: {agg.verification_warn}")
            print(f"Fail: {agg.verification_fail}")

            print(f"\nPromotions:")
            print(f"Approved: {agg.promotions_approved}")
            print(f"Rejected: {agg.promotions_rejected}")

    elif args.command == "alerts":
        alerts_service = TelemetryAlerts(workspace_root)
        recent = alerts_service.get_recent_alerts(1)
        print("\nRECENT ALERTS\n")
        if not recent:
            print("No alerts found.")
        for a in recent:
            print(f"[{a.timestamp.strftime('%H:%M:%S')}] {a.severity.upper()}: {a.message}")

    elif args.command == "generate-dashboard":
        dashboard = TelemetryDashboard(workspace_root)
        dashboard.generate_html()

    elif args.command == "metrics":
        query = TelemetryQuery(workspace_root)
        if args.name:
            metrics = query.get_metric(args.name, args.range)
            for m in metrics:
                print(f"{m.timestamp.strftime('%Y-%m-%d')}: {m.value}")
        else:
            print("Please specify --name")

if __name__ == "__main__":
    main()
