from __future__ import annotations
from typing import List, Dict, Any
from services.planner.models import Step, StepContract

OPERATION_TEMPLATES = {
    "create_file": [
        {
            "step_type": "validate_path",
            "contract": {
                "preconditions": ["path is valid string"],
                "postconditions": ["parent directory exists or can be created"],
                "failure_modes": ["invalid path", "permission denied"]
            }
        },
        {
            "step_type": "create_file",
            "contract": {
                "preconditions": ["path validated"],
                "postconditions": ["file created with initial content"],
                "failure_modes": ["disk full", "permission denied"]
            }
        },
        {
            "step_type": "verify_file_exists",
            "contract": {
                "preconditions": ["create_file completed"],
                "postconditions": ["file existence confirmed on disk"],
                "failure_modes": ["file not found after creation"]
            }
        }
    ],
    "modify_file": [
        {
            "step_type": "read_file",
            "contract": {
                "preconditions": ["file exists"],
                "postconditions": ["content loaded into memory"],
                "failure_modes": ["file not found", "read error"]
            }
        },
        {
            "step_type": "analyze_code",
            "contract": {
                "preconditions": ["content loaded"],
                "postconditions": ["edit points identified"],
                "failure_modes": ["syntax error", "logic mismatch"]
            }
        },
        {
            "step_type": "apply_modification",
            "contract": {
                "preconditions": ["analysis completed"],
                "postconditions": ["content updated in memory"],
                "failure_modes": ["patch conflict", "regex mismatch"]
            }
        },
        {
            "step_type": "write_file",
            "contract": {
                "preconditions": ["modification applied"],
                "postconditions": ["updated content written to disk"],
                "failure_modes": ["write error", "permission denied"]
            }
        },
        {
            "step_type": "verify_changes",
            "contract": {
                "preconditions": ["write_file completed"],
                "postconditions": ["changes verified via read-back"],
                "failure_modes": ["content mismatch"]
            }
        }
    ],
    "write_spec": [
        {
            "step_type": "resolve_spec_number",
            "contract": {
                "preconditions": ["context available"],
                "postconditions": ["next spec number determined"],
                "failure_modes": ["unable to resolve next number"]
            }
        },
        {
            "step_type": "generate_spec_content",
            "contract": {
                "preconditions": ["number resolved"],
                "postconditions": ["spec YAML content generated"],
                "failure_modes": ["generation failed"]
            }
        },
        {
            "step_type": "create_file",
            "contract": {
                "preconditions": ["content generated"],
                "postconditions": ["spec file created"],
                "failure_modes": ["write error"]
            }
        },
        {
            "step_type": "verify_file_exists",
            "contract": {
                "preconditions": ["create_file completed"],
                "postconditions": ["spec file exists"],
                "failure_modes": ["file not found"]
            }
        }
    ],
    "run_command": [
        {
            "step_type": "run_command",
            "contract": {
                "preconditions": ["command valid"],
                "postconditions": ["command executed", "exit code captured"],
                "failure_modes": ["command not found", "timeout", "non-zero exit"]
            }
        }
    ],
    "analyze_codebase": [
        {
            "step_type": "analyze_code",
            "contract": {
                "preconditions": ["codebase available"],
                "postconditions": ["insights generated"],
                "failure_modes": ["analysis failed"]
            }
        }
    ],
    "review_output": [
        {
            "step_type": "validate_output",
            "contract": {
                "preconditions": ["output available"],
                "postconditions": ["validation report generated"],
                "failure_modes": ["validation failed"]
            }
        }
    ]
}

def get_template(op_type: str) -> List[Dict[str, Any]]:
    return OPERATION_TEMPLATES.get(op_type, [])
