from __future__ import annotations
import re
from typing import List, Dict, Any, Optional
from .models import TemplateSelectionResult, MatchStrength, DraftTemplate
from .registry import TemplateRegistry

class TemplateSelector:
    def __init__(self, registry: TemplateRegistry):
        self.registry = registry

    def select_template(self, request_text: str) -> TemplateSelectionResult:
        request_lower = request_text.lower()

        # Heuristics for initial set of templates

        # 1. build_small_app
        if any(kw in request_lower for kw in ["build app", "create app", "scaffold app", "new app", "notes app", "todo app"]):
            inferred = {}
            if "tkinter" in request_lower: inferred["ui_type"] = "tkinter"
            elif "cli" in request_lower: inferred["ui_type"] = "cli"

            # Try to extract app name
            type_match = re.search(r"(\w+)\s+app", request_lower)
            if type_match and type_match.group(1) not in ["build", "create", "scaffold", "new", "small", "a", "an", "the"]:
                inferred["app_name"] = type_match.group(1)
            else:
                name_match = re.search(r"(?:app named|app called|app) ([\w-]+)", request_lower)
                if name_match and name_match.group(1) not in ["with", "to", "for", "a", "an", "the"]:
                    inferred["app_name"] = name_match.group(1)

            return TemplateSelectionResult(
                template_id="build_small_app",
                strength=MatchStrength.STRONG,
                reason="Request indicates building a new application.",
                inferred_parameters=inferred
            )

        # 2. fix_bug
        if any(kw in request_lower for kw in ["fix bug", "resolve bug", "debug", "crash", "error in", "fix failing"]):
            inferred = {}
            # Try to extract file path
            path_match = re.search(r"in ([\w/.-]+\.py)", request_lower)
            if path_match: inferred["failing_file"] = path_match.group(1)

            return TemplateSelectionResult(
                template_id="fix_bug",
                strength=MatchStrength.STRONG,
                reason="Request indicates fixing a bug or error.",
                inferred_parameters=inferred
            )

        # 3. add_tests
        if any(kw in request_lower for kw in ["add tests", "increase coverage", "test for", "unit test"]):
            inferred = {}
            path_match = re.search(r"for ([\w/.-]+\.py)", request_lower)
            if path_match: inferred["target_module"] = path_match.group(1)

            return TemplateSelectionResult(
                template_id="add_tests",
                strength=MatchStrength.STRONG,
                reason="Request indicates adding tests.",
                inferred_parameters=inferred
            )

        # 4. add_ui_screen
        if any(kw in request_lower for kw in ["add screen", "new window", "ui screen", "add ui"]):
            return TemplateSelectionResult(
                template_id="add_ui_screen",
                strength=MatchStrength.STRONG,
                reason="Request indicates adding a UI component.",
                inferred_parameters={}
            )

        # 5. add_feature
        if any(kw in request_lower for kw in ["add feature", "implement feature", "new capability"]):
            return TemplateSelectionResult(
                template_id="add_feature",
                strength=MatchStrength.STRONG,
                reason="Request indicates adding a new feature.",
                inferred_parameters={}
            )

        # 6. patch_existing_module (Weak match for general editing)
        if any(kw in request_lower for kw in ["patch", "refactor", "update file", "change"]):
            return TemplateSelectionResult(
                template_id="patch_existing_module",
                strength=MatchStrength.WEAK,
                reason="Request indicates a general file modification.",
                inferred_parameters={}
            )

        return TemplateSelectionResult(
            template_id=None,
            strength=MatchStrength.NONE,
            reason="No strong template match found."
        )
