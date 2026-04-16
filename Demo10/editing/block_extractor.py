from __future__ import annotations

import re


def get_python_block_boundaries(lines: list[str], start_line: int) -> tuple[int, int]:
    """
    Given a list of lines and a starting line index (0-indexed),
    find the end of the Python block based on indentation.

    Returns (start_line, end_line) where end_line is inclusive.
    """
    if start_line >= len(lines):
        return start_line, start_line

    # 1. Handle decorators above the start line
    actual_start = start_line
    while actual_start > 0:
        prev_line = lines[actual_start - 1].strip()
        if prev_line.startswith("@"):
            actual_start -= 1
        elif not prev_line: # Allow blank lines between decorators? PEP8 says no usually but some might.
            # Usually we don't skip blank lines to find decorators unless we are sure.
            # Let's be conservative and only skip if it looks like a decorator.
            break
        else:
            break

    # 2. Find indentation of the definition line (not decorators)
    def_line = lines[start_line]
    match = re.match(r"^(\s*)", def_line)
    base_indent_str = match.group(1) if match else ""
    base_indent = len(base_indent_str.expandtabs(4))

    # 3. Find the end of the block
    last_content_line = start_line

    for i in range(start_line + 1, len(lines)):
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            continue

        indent_str = re.match(r"^(\s*)", line).group(1)
        indent = len(indent_str.expandtabs(4))

        if indent <= base_indent:
            # We hit a line with same or less indentation.
            # But wait, it might be a multi-line statement or a closing bracket?
            # For def/class blocks, anything with same indentation (except closing parens maybe)
            # marks the end if it's not a continuation.
            # Actually, standard Python blocks end when a line has same or less indentation
            # and is NOT a continuation line.
            break

        last_content_line = i

    # Clean up trailing blank lines from the block
    # Actually, the spec says "continue until next peer/higher-level definition or EOF"
    # If we have:
    # def foo():
    #     pass
    #
    # def bar():

    # We should probably not include the blank lines before bar in foo's block.
    # Let's trim trailing blank lines from our identified block.
    while last_content_line > start_line:
        if not lines[last_content_line].strip():
            last_content_line -= 1
        else:
            break

    return actual_start, last_content_line
