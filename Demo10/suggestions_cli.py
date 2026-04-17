import argparse
import sys
from pathlib import Path
from Demo10.diagnostics.query import DiagnosticsQuery
from Demo10.diagnostics.classifier import classify_failure
from Demo10.suggestions.engine import SuggestionEngine
from Demo10.telemetry.models import TelemetryEvent

def main():
    parser = argparse.ArgumentParser(description="Demo10 Repair Suggestions CLI")
    parser.add_argument("command", choices=["suggest-fixes"], help="Command to run")
    parser.add_argument("run_id", nargs="?", help="ID of the run to suggest fixes for")
    parser.add_argument("--top", action="store_true", help="Show top effectiveness metrics")
    parser.add_argument("--workspace", default=".", help="Workspace root directory")

    args = parser.parse_args()
    workspace_root = Path(args.workspace).absolute()

    engine = SuggestionEngine(workspace_root)
    query = DiagnosticsQuery(workspace_root)

    if args.command == "suggest-fixes":
        if args.top:
            show_top_effectiveness(engine)
        elif args.run_id:
            show_suggestions_for_run(args.run_id, query, engine)
        else:
            print("Error: run_id or --top is required for suggest-fixes")
            sys.exit(1)

def show_suggestions_for_run(run_id: str, query: DiagnosticsQuery, engine: SuggestionEngine):
    run_diag = query.get_run_diagnostics(run_id)
    failures = run_diag.get("failures", [])

    if not failures:
        print(f"No failures found for run {run_id}")
        return

    print(f"\nSUGGESTED FIXES for run {run_id}\n")

    for i, fail in enumerate(failures):
        # In a real scenario, we might reconstruct the TelemetryEvent or use the RootCause directly
        # For this CLI, we'll use the root_cause_id from the failure instance
        from Demo10.diagnostics.models import RootCause

        rc_id = fail.get("root_cause_id", "execution_error.unknown")
        category = rc_id.split('.')[0] if '.' in rc_id else "execution_error"
        subcategory = rc_id.split('.')[1] if '.' in rc_id else "unknown"

        root_cause = RootCause(
            root_cause_id=rc_id,
            category=category, # type: ignore
            subcategory=subcategory,
            description="Failure detected in run",
            deterministic=True
        )

        # Extract context if available (e.g. for invalid_path)
        context_data = {}
        if rc_id == "execution_error.invalid_path":
            # Heuristic: find a path in the failure signature or error message
            # For now, we'll try to get 'target' from the failure metadata if present
            context_data["invalid_path"] = fail.get("target") or fail.get("path")

        suggestions = engine.generate_suggestions(root_cause, context_data=context_data)

        if not suggestions:
            print(f"{i+1}. No suggestions available for root cause: {rc_id}")
            continue

        for j, sug in enumerate(suggestions):
            print(f"{j+1}. {sug.description} [{sug.confidence.upper()} CONFIDENCE]")
            for action in sug.actions:
                print(f"   - {action.instructions}")
                if action.value:
                    print(f"   - Suggested: {action.value}")
            print()

def show_top_effectiveness(engine: SuggestionEngine):
    eff_list = engine.tracker.get_effectiveness()
    if not eff_list:
        print("No suggestion metrics available yet.")
        return

    print("\nSUGGESTION EFFECTIVENESS METRICS\n")
    print(f"{'Suggestion ID':<40} | {'Usage':<5} | {'Applied':<7} | {'Resolved':<8}")
    print("-" * 70)

    # Sort by resolution rate
    sorted_eff = sorted(eff_list, key=lambda e: e.resolution_count / max(e.usage_count, 1), reverse=True)

    for eff in sorted_eff:
        print(f"{eff.suggestion_id:<40} | {eff.usage_count:<5} | {eff.application_count:<7} | {eff.resolution_count:<8}")

if __name__ == "__main__":
    main()
