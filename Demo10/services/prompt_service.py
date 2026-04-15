from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PromptRequest:
    model_name: str
    project_folder: str
    spec_text: str


class PromptBuilder:
    def build(self, request: PromptRequest) -> str:
        spec = request.spec_text.strip()
        folder = request.project_folder.strip() or "not selected"
        model = request.model_name.strip() or "not selected"
        return (
            "[ROLE / INSTRUCTION]\n"
            "You are assisting in a local coding workbench.\n"
            "Respond to the current spec only.\n"
            "Be concise, operational, and explicit.\n\n"
            "[PROJECT CONTEXT]\n"
            f"Project folder: {folder}\n\n"
            "[MODEL CONTEXT]\n"
            f"Selected model: {model}\n\n"
            "[USER SPEC]\n"
            f"{spec}\n\n"
            "[RESPONSE EXPECTATION]\n"
            "Return practical implementation guidance for the current spec.\n"
        )


from services.bundle_service import WorkingSetBundle

class BundleEditPromptBuilder:
    def build(self, request: PromptRequest, bundle: WorkingSetBundle) -> str:
        spec = request.spec_text.strip()
        folder = request.project_folder.strip() or "not selected"

        bundle_json = bundle.to_preview_text()

        return (
            "[ROLE / INSTRUCTION]\n"
            "You are a local coding assistant. You are performing a bounded bundle edit.\n"
            "You MUST return an updated version of the provided bundle in the EXACT JSON format specified below.\n"
            "Do NOT include conversational filler, explanations, or commentary outside the JSON.\n\n"
            "[PROJECT CONTEXT]\n"
            f"Project folder: {folder}\n\n"
            "[USER SPEC]\n"
            f"{spec}\n\n"
            "[SOURCE BUNDLE]\n"
            f"{bundle_json}\n\n"
            "[OUTPUT FORMAT REQUIREMENTS]\n"
            "Return ONLY a JSON object with this structure:\n"
            "{\n"
            '  "files": [\n'
            "    {\n"
            '      "relative_path": "path/to/file.py",\n'
            '      "selection_kind": "primary_editable",\n'
            '      "content_status": "ready",\n'
            '      "file_content": "updated content here"\n'
            "    }\n"
            "  ]\n"
            "}\n\n"
            "[CRITICAL CONSTRAINTS]\n"
            "1. Only edit files provided in the SOURCE BUNDLE.\n"
            "2. Do not invent files outside the allowed scope.\n"
            "3. Ensure the JSON is valid and escaped correctly.\n"
            "4. Preserve untouched files by including them as-is if they are part of the working set.\n"
            "5. The 'file_content' field must contain the FULL updated content of the file.\n"
        )
