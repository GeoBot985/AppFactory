class MoveWatcher:
    def __init__(self, strict_extra_text: bool = False):
        self.strict_extra_text = strict_extra_text

    def _has_attempts_remaining(self, attempt: int, max_attempts: int) -> bool:
        return attempt < max_attempts

    def _normalized_raw(self, raw_response):
        if raw_response is None:
            return ""
        return raw_response.strip().lower()

    def _has_extra_text(self, raw_response, expected_value) -> bool:
        if not raw_response or expected_value is None:
            return False
        return self._normalized_raw(raw_response) != str(expected_value).strip().lower()

    def _is_repeated_invalid_pattern(self, context: dict, base_reason: str) -> bool:
        if context.get("attempt", 1) <= 1:
            return False

        current_signature = (
            base_reason,
            self._normalized_raw(context.get("raw_response")),
            str(context.get("parsed_index") or ""),
            (context.get("parsed_move") or "").lower(),
        )

        for prior in context.get("prior_attempts", []):
            prior_signature = (
                prior.get("reason_code"),
                self._normalized_raw(prior.get("raw_response")),
                str(prior.get("parsed_index") or ""),
                (prior.get("parsed_move") or "").lower(),
            )
            if prior_signature == current_signature:
                return True
        return False

    def _blocking_decision(self, attempt: int, max_attempts: int, base_reason: str, message: str) -> dict:
        if self._has_attempts_remaining(attempt, max_attempts):
            return {
                "decision": "retry",
                "reason_code": base_reason,
                "message": message,
                "force_retry": True,
                "forfeit": False,
            }
        return {
            "decision": "forfeit",
            "reason_code": "retry_limit_reached",
            "message": f"Retry limit reached after {base_reason}",
            "force_retry": False,
            "forfeit": True,
        }

    def inspect(self, context: dict) -> dict:
        attempt = context["attempt"]
        max_attempts = context["max_attempts"]
        raw_response = context.get("raw_response")
        parsed_index = context.get("parsed_index")
        parsed_move = context.get("parsed_move")
        parse_error = context.get("parse_error")
        is_legal = context.get("is_legal")
        move_output_mode = context.get("move_output_mode", "uci")

        if parse_error == "timeout":
            base_reason = "timeout"
            if self._is_repeated_invalid_pattern(context, base_reason):
                base_reason = "repeated_invalid_response"
            return self._blocking_decision(attempt, max_attempts, base_reason, "Model request timed out")

        if parse_error == "connection_error":
            base_reason = "connection_error"
            if self._is_repeated_invalid_pattern(context, base_reason):
                base_reason = "repeated_invalid_response"
            return self._blocking_decision(attempt, max_attempts, base_reason, "Model backend connection failed")

        if raw_response is None or raw_response.strip() == "":
            base_reason = "empty_response"
            if self._is_repeated_invalid_pattern(context, base_reason):
                base_reason = "repeated_invalid_response"
            return self._blocking_decision(attempt, max_attempts, base_reason, "Model returned an empty response")

        if parse_error == "selection_out_of_range":
            base_reason = "selection_out_of_range"
            if self._is_repeated_invalid_pattern(context, base_reason):
                base_reason = "repeated_invalid_response"
            return self._blocking_decision(attempt, max_attempts, base_reason, "Selection number is outside the legal move list")

        if parse_error == "resolved_move_illegal":
            base_reason = "resolved_move_illegal"
            if self._is_repeated_invalid_pattern(context, base_reason):
                base_reason = "repeated_invalid_response"
            return self._blocking_decision(attempt, max_attempts, base_reason, "Resolved move is illegal in current position")

        if parsed_move and not is_legal:
            base_reason = "illegal_move"
            if self._is_repeated_invalid_pattern(context, base_reason):
                base_reason = "repeated_invalid_response"
            return self._blocking_decision(attempt, max_attempts, base_reason, "Parsed move is illegal in current position")

        if parse_error or (move_output_mode == "index" and parsed_index is None) or (move_output_mode != "index" and not parsed_move):
            base_reason = parse_error or "parse_failed"
            if self._is_repeated_invalid_pattern(context, base_reason):
                base_reason = "repeated_invalid_response"
            if base_reason == "invalid_selection_format":
                return self._blocking_decision(attempt, max_attempts, base_reason, "No valid option number could be parsed")
            return self._blocking_decision(attempt, max_attempts, base_reason, "No valid move could be parsed")

        expected_value = parsed_index if move_output_mode == "index" else parsed_move
        if self._has_extra_text(raw_response, expected_value):
            if self.strict_extra_text:
                return self._blocking_decision(
                    attempt,
                    max_attempts,
                    "extra_text_detected",
                    "Legal selection included extra text",
                )
            return {
                "decision": "allow",
                "reason_code": "extra_text_detected",
                "message": "Legal selection allowed but extra text was detected",
                "force_retry": False,
                "forfeit": False,
            }

        return {
            "decision": "allow",
            "reason_code": "ok",
            "message": "Move allowed",
            "force_retry": False,
            "forfeit": False,
        }
