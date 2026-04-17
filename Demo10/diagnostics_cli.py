import argparse
import sys
from pathlib import Path
from diagnostics.query import DiagnosticsQuery

def main():
    parser = argparse.ArgumentParser(description="Demo10 Diagnostics CLI")
    subparsers = parser.add_subparsers(dest="command")

    # summary
    subparsers.add_parser("summary", help="Show diagnostics summary")

    # top-failures
    top_parser = subparsers.add_parser("top-failures", help="Show top failure patterns")
    top_parser.add_argument("--limit", type=int, default=5, help="Limit number of patterns")

    # run
    run_parser = subparsers.add_parser("run", help="Show diagnostics for a specific run")
    run_parser.add_argument("run_id", help="The ID of the run")

    args = parser.parse_args()

    workspace_root = Path(".")
    query = DiagnosticsQuery(workspace_root)

    if args.command == "summary":
        show_summary(query)
    elif args.command == "top-failures":
        show_top_failures(query, args.limit)
    elif args.command == "run":
        show_run_diagnostics(query, args.run_id)
    else:
        parser.print_help()

def show_summary(query: DiagnosticsQuery):
    root_causes = query.get_root_causes()
    print("\nDIAGNOSTICS SUMMARY - ROOT CAUSES")
    print("-" * 50)
    if not root_causes:
        print("No root causes recorded.")
    else:
        for rc in sorted(root_causes, key=lambda x: x.count, reverse=True):
            print(f"{rc.root_cause}: {rc.count} occurrences ({len(rc.affected_runs)} runs)")

def show_top_failures(query: DiagnosticsQuery, limit: int):
    patterns = query.get_top_failures(limit)
    print(f"\nTOP FAILURE PATTERNS (limit {limit})")
    print("-" * 50)
    if not patterns:
        print("No failure patterns recorded.")
    else:
        for i, p in enumerate(patterns, 1):
            print(f"{i}. {p.error_code} ({p.occurrences} occurrences)")
            print(f"   Root Cause: {p.root_cause_id}")
            print(f"   Impact Score: {p.impact_score:.1f}")
            print()

def show_run_diagnostics(query: DiagnosticsQuery, run_id: str):
    diag = query.get_run_diagnostics(run_id)
    print(f"\nDIAGNOSTICS FOR RUN: {run_id}")
    print("-" * 50)
    if not diag["failures"]:
        print("No failures recorded for this run.")
    else:
        print(f"Total failures: {diag['failure_count']}")
        for f in diag["failures"]:
            print(f"- {f['error_code']} at {f['timestamp']}")
            print(f"  Step ID: {f['step_id']}")
            print(f"  Root Cause: {f['root_cause_id']}")
            print(f"  Signature: {f['signature_id']}")

if __name__ == "__main__":
    main()
