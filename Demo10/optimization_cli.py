import argparse
from pathlib import Path
from Demo10.optimization.analyzer import OptimizationAnalyzer
from Demo10.optimization.materializer import OptimizationMaterializer
from Demo10.optimization.adoption import OptimizationAdopter
from Demo10.optimization.reporting import OptimizationReporter

def main():
    parser = argparse.ArgumentParser(description="Demo10 Optimization CLI")
    subparsers = parser.add_subparsers(dest="command", help="Optimization commands")

    # optimize-analyze
    subparsers.add_parser("optimize-analyze", help="Analyze plans for optimization opportunities")

    # optimize-list-candidates
    list_parser = subparsers.add_parser("optimize-list-candidates", help="List optimization candidates")
    list_parser.add_argument("--status", choices=["proposed", "verified", "rejected", "adopted"], help="Filter by status")

    # optimize-materialize <candidate_id>
    mat_parser = subparsers.add_parser("optimize-materialize", help="Materialize an optimized plan variant")
    mat_parser.add_argument("candidate_id", help="Candidate ID")
    mat_parser.add_argument("--plan-id", required=True, help="Source plan ID")

    # optimize-verify <variant_id>
    verify_parser = subparsers.add_parser("optimize-verify", help="Verify an optimized plan variant")
    verify_parser.add_argument("variant_id", help="Variant ID")

    # optimize-adopt <variant_id>
    adopt_parser = subparsers.add_parser("optimize-adopt", help="Adopt an optimized plan variant")
    adopt_parser.add_argument("variant_id", help="Variant ID")

    # optimize-report
    subparsers.add_parser("optimize-report", help="Generate optimization report")

    args = parser.parse_args()
    workspace_root = Path(".").resolve()

    analyzer = OptimizationAnalyzer(workspace_root)
    materializer = OptimizationMaterializer(workspace_root)
    adopter = OptimizationAdopter(workspace_root)
    reporter = OptimizationReporter(workspace_root)

    if args.command == "optimize-analyze":
        candidates = analyzer.analyze_for_optimization()
        print(f"Analysis complete. Found {len(candidates)} candidates.")
        for c in candidates:
            print(f"- {c.candidate_id}: {c.optimization_type} ({c.status})")

    elif args.command == "optimize-list-candidates":
        candidates = analyzer.list_candidates(status=args.status)
        print(f"Candidates ({args.status or 'all'}):")
        for c in candidates:
            print(f"- {c.candidate_id}: {c.optimization_type} ({c.status})")

    elif args.command == "optimize-materialize":
        variant = materializer.materialize_optimized_variant([args.candidate_id], args.plan_id)
        print(f"Materialized variant {variant.variant_id} from plan {args.plan_id}")

    elif args.command == "optimize-verify":
        success = adopter.verify_variant(args.variant_id)
        if success:
            print(f"Variant {args.variant_id} verified successfully.")
        else:
            print(f"Variant {args.variant_id} verification failed.")

    elif args.command == "optimize-adopt":
        success = adopter.adopt_variant(args.variant_id)
        if success:
            print(f"Variant {args.variant_id} adopted.")
        else:
            print(f"Variant {args.variant_id} adoption failed (make sure it's verified first).")

    elif args.command == "optimize-report":
        report = reporter.generate_report()
        print(f"Report generated at {reporter.report_path}")

    else:
        parser.print_help()

if __name__ == "__main__":
    main()
