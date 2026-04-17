#!/usr/bin/env python3
import sys
import argparse
import json
from pathlib import Path
from Demo10.macros.promotion import MacroPromotionEngine
from Demo10.macros.library import MacroLibraryManager
from Demo10.macros.expansion import MacroExpansionEngine
from Demo10.macros.governance import MacroGovernance

def main():
    parser = argparse.ArgumentParser(description="Demo10 Macro Management CLI")
    parser.add_argument("--workspace-root", default=".", help="Workspace root directory")

    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # macro-list
    subparsers.add_parser("macro-list", help="List all macros in the library")

    # macro-show
    show_parser = subparsers.add_parser("macro-show", help="Show details of a macro")
    show_parser.add_argument("macro_id", help="Macro ID (name:version)")

    # macro-promote
    promote_parser = subparsers.add_parser("macro-promote", help="Promote a fragment to a macro")
    promote_parser.add_argument("fragment_id", help="Source fragment ID")
    promote_parser.add_argument("--name", required=True, help="Proposed macro name")
    promote_parser.add_argument("--version", default="v1", help="Proposed macro version")

    # macro-verify
    verify_parser = subparsers.add_parser("macro-verify", help="Verify a macro")
    verify_parser.add_argument("macro_id", help="Macro ID (name:version)")

    # macro-activate
    activate_parser = subparsers.add_parser("macro-activate", help="Activate a macro version")
    activate_parser.add_argument("macro_id", help="Macro ID (name:version)")

    # macro-deprecate
    deprecate_parser = subparsers.add_parser("macro-deprecate", help="Deprecate a macro version")
    deprecate_parser.add_argument("macro_id", help="Macro ID (name:version)")

    # macro-expand
    expand_parser = subparsers.add_parser("macro-expand", help="Expand a macro for testing")
    expand_parser.add_argument("macro_id", help="Macro ID (name:version or name for active)")
    expand_parser.add_argument("--inputs", help="JSON string of bound inputs")

    # macro-candidates
    subparsers.add_parser("macro-candidates", help="List macro promotion candidates")

    # macro-adopt
    adopt_parser = subparsers.add_parser("macro-adopt", help="Adopt a promotion candidate")
    adopt_parser.add_argument("candidate_id", help="Candidate ID")

    args = parser.parse_args()
    workspace_root = Path(args.workspace_root).resolve()

    promotion_engine = MacroPromotionEngine(workspace_root)
    library_manager = MacroLibraryManager(workspace_root)
    expansion_engine = MacroExpansionEngine(library_manager)
    governance = MacroGovernance(workspace_root)

    if args.command == "macro-list":
        macros = library_manager.list_macros()
        library = library_manager.load_library()
        print(f"{'NAME':<30} {'VERSION':<10} {'STATUS':<15} {'ACTIVE':<10}")
        print("-" * 65)
        for m in macros:
            is_active = "yes" if library.active_versions.get(m.name) == m.version else "no"
            print(f"{m.name:<30} {m.version:<10} {m.verification_status:<15} {is_active:<10}")

    elif args.command == "macro-show":
        if ":" in args.macro_id:
            name, version = args.macro_id.split(":", 1)
            macro = library_manager.get_macro(name, version)
        else:
            macro = library_manager.get_active_macro(args.macro_id)

        if macro:
            print(json.dumps(vars(macro), indent=2, default=str))
        else:
            print(f"Macro not found: {args.macro_id}")

    elif args.command == "macro-promote":
        candidate = promotion_engine.promote_fragment_to_macro(args.fragment_id, args.name, args.version)
        print(f"Promotion candidate created: {candidate.candidate_id} (Status: {candidate.status})")

    elif args.command == "macro-verify":
        success = governance.verify_macro(args.macro_id)
        print(f"Verification {'successful' if success else 'failed'} for {args.macro_id}")

    elif args.command == "macro-activate":
        success = governance.activate_macro(args.macro_id)
        print(f"Activation {'successful' if success else 'failed'} for {args.macro_id}")

    elif args.command == "macro-deprecate":
        success = governance.deprecate_macro(args.macro_id)
        print(f"Deprecation {'successful' if success else 'failed'} for {args.macro_id}")

    elif args.command == "macro-expand":
        bound_inputs = json.loads(args.inputs) if args.inputs else {}
        result = expansion_engine.expand_macro(args.macro_id, bound_inputs)
        print(json.dumps(vars(result), indent=2, default=str))

    elif args.command == "macro-candidates":
        candidates = promotion_engine.list_candidates()
        print(f"{'ID':<15} {'NAME':<20} {'FRAGMENT':<15} {'STATUS':<10}")
        print("-" * 60)
        for c in candidates:
            print(f"{c.candidate_id:<15} {c.proposed_name:<20} {c.source_fragment_id:<15} {c.status:<10}")

    elif args.command == "macro-adopt":
        macro = governance.adopt_candidate(args.candidate_id)
        if macro:
            print(f"Candidate adopted as macro: {macro.macro_id}")
        else:
            print(f"Failed to adopt candidate: {args.candidate_id}")

    else:
        parser.print_help()

if __name__ == "__main__":
    main()
