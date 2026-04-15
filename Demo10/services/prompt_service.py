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
