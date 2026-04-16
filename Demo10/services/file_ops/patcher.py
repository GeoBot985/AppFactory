from __future__ import annotations

import re

from services.file_ops.models import PatchBlock, PatchOutcome


def apply_patch_blocks(content: str, patch_blocks: list[PatchBlock]) -> PatchOutcome:
    working = content
    matches_found = 0
    matches_replaced = 0

    for block in patch_blocks:
        if block.match_type == "exact":
            found = working.count(block.target)
            matches_found += found
            if found == 0:
                if block.required:
                    raise ValueError("patch_target_not_found")
                continue
            if not block.replace_all and found != block.expected_matches:
                raise ValueError("patch_match_count_mismatch")
            if block.replace_all:
                working = working.replace(block.target, block.replacement)
                matches_replaced += found
            else:
                working = working.replace(block.target, block.replacement, block.expected_matches)
                matches_replaced += block.expected_matches
            continue

        if block.match_type == "regex":
            matches = list(re.finditer(block.target, working, flags=re.MULTILINE))
            found = len(matches)
            matches_found += found
            if found == 0:
                if block.required:
                    raise ValueError("patch_target_not_found")
                continue
            if not block.replace_all and found != block.expected_matches:
                raise ValueError("patch_match_count_mismatch")
            count = 0 if block.replace_all else block.expected_matches
            working, replaced = re.subn(block.target, block.replacement, working, count=count, flags=re.MULTILINE)
            matches_replaced += replaced
            continue

        raise ValueError("invalid_operation_schema")

    return PatchOutcome(
        content=working,
        matches_found=matches_found,
        matches_replaced=matches_replaced,
        content_changed=working != content,
    )
