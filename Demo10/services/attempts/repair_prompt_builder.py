from __future__ import annotations

from services.attempts.models import AttemptRecord


def build_repair_input(
    task_target: str,
    original_prompt: str,
    failure_class: str,
    failure_detail: str,
    history: list[AttemptRecord],
    strategy: str,
) -> str:
    prior = history[-1] if history else None
    prior_summary = prior.operation_plan_summary if prior else "none"
    return (
        f"You are repairing a failed code generation attempt for '{task_target}'.\n"
        f"Original intent:\n{original_prompt}\n\n"
        f"Failure class: {failure_class}\n"
        f"Failure detail: {failure_detail}\n"
        f"Previous plan summary: {prior_summary}\n"
        f"Strategy: {strategy}\n"
        "Constraints:\n"
        "- Preserve workspace path safety.\n"
        "- Do not use fuzzy patching.\n"
        "- Make the minimal change needed to satisfy the failure.\n"
        "- Return only the requested code content, no markdown.\n"
    )
