import re


class MoveSelectionParseError(ValueError):
    def __init__(self, message: str, raw_response: str | None = None):
        super().__init__(message)
        self.raw_response = raw_response


def parse_move_selection(raw_response: str | None) -> dict:
    normalized = "" if raw_response is None else raw_response.strip()
    if not normalized:
        raise MoveSelectionParseError("No move selection found in model response", raw_response=raw_response)

    bare_integer = re.fullmatch(r"(\d+)", normalized)
    if bare_integer:
        return {
            "raw": raw_response,
            "parsed_index": int(bare_integer.group(1)),
            "parsed_move": None,
        }

    prefixed_integer = re.fullmatch(r"MOVE_INDEX:\s*(\d+)", normalized, flags=re.IGNORECASE)
    if prefixed_integer:
        return {
            "raw": raw_response,
            "parsed_index": int(prefixed_integer.group(1)),
            "parsed_move": None,
        }

    raise MoveSelectionParseError("Invalid move selection format", raw_response=raw_response)
