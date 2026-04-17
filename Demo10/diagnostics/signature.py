import hashlib
import json
from typing import Optional
from .models import FailureSignature

def generate_signature(
    error_code: str,
    step_type: str,
    target: Optional[str] = None,
    operation_type: Optional[str] = None
) -> FailureSignature:
    # Normalization rules:
    # 1. strip paths to relative (already mostly handled if target is just a filename/relative path)
    # 2. lowercase
    # 3. remove timestamps (not present here)
    # 4. remove run-specific IDs (not present here)

    norm_error_code = error_code.upper()
    norm_step_type = step_type.lower()
    norm_target = target.lower() if target else ""
    norm_op_type = operation_type.lower() if operation_type else ""

    # Simple normalization for target if it looks like a path
    if "/" in norm_target:
        norm_target = norm_target.split("/")[-1]
    elif "\\" in norm_target:
        norm_target = norm_target.split("\\")[-1]

    raw_string = f"{norm_error_code}|{norm_step_type}|{norm_target}|{norm_op_type}"
    context_hash = hashlib.sha256(raw_string.encode()).hexdigest()

    signature_id = f"sig_{context_hash[:8]}"

    sig = FailureSignature(
        signature_id=signature_id,
        error_code=norm_error_code,
        step_type=norm_step_type,
        operation_type=norm_op_type or None,
        target=norm_target or None,
        context_hash=context_hash
    )

    # Note: standalone signatures.json storage is handled by PatternManager to maintain consistency.
    return sig
