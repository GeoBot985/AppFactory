import hashlib
from typing import List
from services.input_compiler.models import CompiledSpecIR
from .models import GoalSignature

class SignatureEngine:
    @staticmethod
    def build_signature(ir: CompiledSpecIR) -> GoalSignature:
        # derive from IR only
        # normalize:
        # lowercase
        # strip paths to relative
        # remove timestamps/IDs
        # stable ordering

        operation_types = sorted([op.op_type.value for op in ir.operations])

        targets = []
        for op in ir.operations:
            if op.target:
                # normalize target: strip leading slash, lowercase
                target = op.target.strip("/").lower()
                if target not in targets:
                    targets.append(target)
        targets.sort()

        constraints = sorted([c.constraint_type.lower() for c in ir.constraints])

        # Canonical tokens from title and objective (simplistic v1)
        intent_tokens = set()
        for text in [ir.title, ir.objective]:
            # very basic normalization
            tokens = text.lower().replace("_", " ").split()
            for t in tokens:
                clean_t = "".join(filter(str.isalnum, t))
                if clean_t:
                    intent_tokens.add(clean_t)

        sorted_tokens = sorted(list(intent_tokens))

        # Generate stable signature ID
        raw_sig = f"{'|'.join(operation_types)}:{'|'.join(targets)}:{'|'.join(constraints)}:{'|'.join(sorted_tokens)}"
        signature_id = hashlib.sha256(raw_sig.encode()).hexdigest()[:16]

        return GoalSignature(
            signature_id=signature_id,
            operation_types=operation_types,
            targets=targets,
            constraints=constraints,
            intent_tokens=sorted_tokens
        )
