from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Literal, Tuple

@dataclass
class CompileIssue:
    severity: Literal["warning", "error"]
    code: str
    message: str
    field: Optional[str] = None
    source_span: Optional[Tuple[int, int]] = None

    repairable: bool = False
    repair_type: Optional[Literal[
        "select_option",
        "provide_value",
        "remove_conflict",
        "clarify_reference",
        "split_instruction"
    ]] = None

    def to_dict(self):
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "field": self.field,
            "source_span": self.source_span,
            "repairable": self.repairable,
            "repair_type": self.repair_type
        }

# Stable Issue Codes
MISSING_OBJECTIVE = "MISSING_OBJECTIVE"
MISSING_TITLE = "MISSING_TITLE"
NO_SUPPORTED_OPERATION = "NO_SUPPORTED_OPERATION"
AMBIGUOUS_TARGET_FILE = "AMBIGUOUS_TARGET_FILE"
CONFLICTING_ACTIONS = "CONFLICTING_ACTIONS"
MISSING_REQUIRED_TARGET = "MISSING_REQUIRED_TARGET"
COMPILER_INTERNAL_FAILURE = "COMPILER_INTERNAL_FAILURE"
UNSUPPORTED_VERB = "UNSUPPORTED_VERB"
UNKNOWN_REFERENCE = "UNKNOWN_REFERENCE"
INFERRED_TITLE = "INFERRED_TITLE"
VAGUE_WORDING = "VAGUE_WORDING"
ASSUMED_TARGET_DIRECTORY = "ASSUMED_TARGET_DIRECTORY"
