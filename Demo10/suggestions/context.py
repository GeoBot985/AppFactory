import os
from pathlib import Path
from typing import List, Optional, Dict, Any
from .models import RepairSuggestion

def enrich_suggestion(suggestion: RepairSuggestion, workspace_root: Path, context_data: Optional[Dict[str, Any]] = None):
    """
    Enriches a suggestion with workspace-specific context.
    Example: for invalid_path, find similar files in the workspace.
    """
    if suggestion.root_cause_id == "execution_error.invalid_path":
        # Attempt to find similar files if a target path was provided in context
        invalid_path = context_data.get("invalid_path") if context_data else None
        if invalid_path:
            suggestions = find_closest_files(invalid_path, workspace_root)
            if suggestions:
                suggestion.description += f" Did you mean one of these: {', '.join(suggestions)}?"
                # Could also add an action to select one of these

    # Add more enrichment rules as needed

def find_closest_files(target: str, workspace_root: Path, limit: int = 3) -> List[str]:
    """Simple heuristic to find files with similar names in the workspace."""
    target_name = os.path.basename(target).lower()
    matches = []

    # Very simple fuzzy match for v1:
    # 1. common prefix
    # 2. substring
    # 3. simple character set overlap (if above fails)

    target_base = os.path.splitext(target_name)[0]

    for root, dirs, files in os.walk(workspace_root):
        if any(p in root for p in ["runtime_data", ".pytest_cache", "__pycache__", ".git"]):
            continue
        for f in files:
            f_lower = f.lower()
            f_base = os.path.splitext(f_lower)[0]

            # Substring match
            if target_base in f_base or f_base in target_base:
                rel_path = os.path.relpath(os.path.join(root, f), workspace_root)
                matches.append(rel_path)
            # Prefix match (first 3 chars)
            elif len(target_base) >= 3 and len(f_base) >= 3 and target_base[:3] == f_base[:3]:
                rel_path = os.path.relpath(os.path.join(root, f), workspace_root)
                if rel_path not in matches:
                    matches.append(rel_path)

            if len(matches) >= limit:
                return matches
    return matches
