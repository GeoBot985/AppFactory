import argparse
from pathlib import Path
from Demo10.knowledge.query import KnowledgeQuery
from Demo10.knowledge.store import KnowledgeStore

def main():
    parser = argparse.ArgumentParser(description="Demo10 Knowledge Base CLI")
    parser.add_argument("command", choices=["kb-summary", "kb-pattern", "kb-top-fixes"], help="Command to run")
    parser.add_argument("signature_id", nargs="?", help="Signature ID for kb-pattern")
    parser.add_argument("--workspace", default=".", help="Workspace root directory")

    args = parser.parse_args()
    workspace_root = Path(args.workspace).absolute()

    query = KnowledgeQuery(workspace_root)
    store = KnowledgeStore(workspace_root)

    if args.command == "kb-summary":
        show_summary(store)
    elif args.command == "kb-pattern":
        if not args.signature_id:
            print("Error: signature_id is required for kb-pattern")
            return
        show_pattern(args.signature_id, query)
    elif args.command == "kb-top-fixes":
        show_top_fixes(query)

def show_summary(store: KnowledgeStore):
    kb = store.load_kb()
    metrics = store._calculate_metrics(kb)

    print("\nKNOWLEDGE BASE SUMMARY\n")
    print(f"Total Entries:    {metrics['total_entries']}")
    print(f"Total Usage:      {metrics['total_usage']}")
    print(f"Total Successes:  {metrics['total_success']}")
    print(f"Overall Success Rate: {metrics['overall_success_rate']:.2%}")
    print(f"Active Patterns:  {len(kb.mappings)}")

def show_pattern(signature_id: str, query: KnowledgeQuery):
    solutions = query.get_solutions(signature_id)

    if not solutions:
        print(f"No knowledge found for pattern: {signature_id}")
        return

    print(f"\nKNOWLEDGE FOR PATTERN: {signature_id}\n")
    print(f"{'Rank':<4} | {'Suggestion ID':<20} | {'Success Rate':<12} | {'Usage':<5}")
    print("-" * 50)

    for sol in solutions:
        print(f"{sol.deterministic_rank:<4} | {sol.suggestion_id:<20} | {sol.success_rate:>11.1%} | {sol.usage_count:<5}")

def show_top_fixes(query: KnowledgeQuery):
    patterns = query.get_top_patterns(limit=5)

    if not patterns:
        print("No patterns found in Knowledge Base.")
        return

    print("\nTOP FIXES BY PATTERN\n")

    for p in patterns:
        print(f"Pattern: {p.signature_id} (RC: {p.root_cause_id})")
        for sol in p.ranked_solutions[:3]:
            print(f"  {sol.deterministic_rank}. {sol.suggestion_id} (success_rate={sol.success_rate:.1%})")
        print()

if __name__ == "__main__":
    main()
